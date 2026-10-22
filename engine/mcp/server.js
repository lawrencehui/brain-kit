#!/usr/bin/env node
/**
 * Second-brain MCP server (brain-kit).
 *
 * Exposes the second-brain vault (Obsidian markdown at BRAIN_VAULT) to any
 * MCP client — Claude Code, Codex, etc. — so a session in *any* project can
 * both retrieve from and append to the brain natively.
 *
 * Design follows the Karpathy "wiki LLM" model used by this vault: retrieval is
 * agentic grep + read (ripgrep over markdown), NOT a vector DB. The server only
 * exposes primitives; the calling agent reasons over them.
 *
 * Tools:
 *   - brain_search(query)            ripgrep across the vault, returns hits + excerpts
 *   - brain_read(path)               return a full page by vault-relative path
 *   - brain_capture(text, ...)       append a timestamped note into raw/journal/
 *
 * Launch (stdio): node server.js
 * Vault: BRAIN_VAULT env var, else the vault this file lives in (<vault>/meta/mcp/server.js).
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { writeFile, readFile, mkdir, readdir, stat } from "node:fs/promises";
import { resolve, join, relative, isAbsolute, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);

// ---------------------------------------------------------------------------
// Constants & helpers
// ---------------------------------------------------------------------------

const VAULT = resolve(process.env.BRAIN_VAULT || join(dirname(fileURLToPath(import.meta.url)), "..", ".."));
const BRAIN_NAME = process.env.BRAIN_NAME || "brain";
const JOURNAL = join(VAULT, "raw", "journal");
const CHARACTER_LIMIT = 25000; // cap any single response to protect agent context
const KINDS = ["note", "finding", "feedback", "worklog", "idea"];

/** Resolve a vault-relative path, refusing anything that escapes the vault. */
function safeVaultPath(rel) {
  if (isAbsolute(rel)) {
    const abs = resolve(rel);
    if (abs !== VAULT && !abs.startsWith(VAULT + "/")) {
      throw new Error(`Path is outside the vault: ${rel}`);
    }
    return abs;
  }
  const abs = resolve(VAULT, rel);
  if (abs !== VAULT && !abs.startsWith(VAULT + "/")) {
    throw new Error(`Path escapes the vault: ${rel}`);
  }
  return abs;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** Local-time stamp + random suffix → collision-safe filename, same scheme as brain.sh. */
function stamp() {
  const d = new Date();
  const date = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  const time = `${pad2(d.getHours())}${pad2(d.getMinutes())}${pad2(d.getSeconds())}`;
  const rand = String(Math.floor(Math.random() * 9000) + 1000);
  return { date, time, rand, name: `${date}-${time}-${rand}.md` };
}

function truncate(text, note) {
  if (text.length <= CHARACTER_LIMIT) return text;
  const head = text.slice(0, CHARACTER_LIMIT);
  return `${head}\n\n…[truncated at ${CHARACTER_LIMIT} chars${note ? `; ${note}` : ""}]`;
}

/** List markdown headings: [{ level, title, line }]. */
function extractHeadings(text) {
  const out = [];
  const lines = text.split("\n");
  let inFence = false;
  for (let i = 0; i < lines.length; i++) {
    if (/^```/.test(lines[i])) inFence = !inFence;
    if (inFence) continue;
    const m = lines[i].match(/^(#{1,6})\s+(.*)$/);
    if (m) out.push({ level: m[1].length, title: m[2].trim(), line: i });
  }
  return out;
}

/** Return one section (heading → next same-or-higher heading), or null. Case-insensitive substring match on the title. */
function extractSection(text, heading) {
  const hs = extractHeadings(text);
  const q = heading.toLowerCase();
  const hit = hs.find((h) => h.title.toLowerCase().includes(q));
  if (!hit) return null;
  const lines = text.split("\n");
  let end = lines.length;
  for (const h of hs) {
    if (h.line > hit.line && h.level <= hit.level) { end = h.line; break; }
  }
  return lines.slice(hit.line, end).join("\n").trim();
}

const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Lower = higher priority when ranking search results. */
function pathPriority(p) {
  if (p.startsWith("wiki/projects/")) return 0;
  if (p.startsWith("wiki/") && !p.startsWith("wiki/sources/")) return 1;
  if (p.startsWith("wiki/sources/")) return 2;
  if (p.startsWith("meta/")) return 3;
  return 4; // raw/
}

// ---------------------------------------------------------------------------
// Server
// ---------------------------------------------------------------------------

const server = new McpServer({ name: `${BRAIN_NAME}-mcp-server`, version: "1.2.0" });

// --- brain_search -----------------------------------------------------------

server.registerTool(
  "brain_search",
  {
    title: "Search the second brain",
    description: `Full-text search across the second-brain vault (Obsidian markdown).

Runs ripgrep over wiki/ (synthesised pages), raw/ (source captures) and meta/. Case-insensitive substring/regex match. Use this first to locate pages, then brain_read to load a full page.

Args:
  - query (string): text or regex to search for (e.g. "my-app", "market impact", "walk.forward")
  - limit (number): max matching lines to return, 1-200 (default 40)

Returns markdown grouped by file (path → matching lines with line numbers), plus structuredContent { total, count, hits: [{ path, line, text }] }. Returns "No matches" if nothing is found. Paths are vault-relative and can be passed straight to brain_read.`,
    inputSchema: {
      query: z
        .string()
        .min(2, "Query must be at least 2 characters")
        .max(200, "Query must not exceed 200 characters")
        .describe("Text or regex to search for across the vault"),
      limit: z
        .number()
        .int()
        .min(1)
        .max(200)
        .default(40)
        .describe("Maximum number of matching lines to return"),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ query, limit }) => {
    const args = [
      "--line-number",
      "--no-heading",
      "--color", "never",
      "--ignore-case",
      "--max-count", "20", // per-file cap
      "--glob", "*.md",
      "--glob", "!**/node_modules/**",
      "--", query,
      "wiki", "raw", "meta",
    ];
    let stdout = "";
    try {
      ({ stdout } = await execFileAsync("rg", args, {
        cwd: VAULT,
        maxBuffer: 8 * 1024 * 1024,
      }));
    } catch (err) {
      // ripgrep exits 1 when there are no matches — not an error: fall through so the
      // multi-term ranked fallback below still gets a chance to run.
      if (!(err && err.code === 1)) {
        return {
          content: [{ type: "text", text: `Error: search failed (${err?.message || String(err)}). Is ripgrep installed?` }],
          isError: true,
        };
      }
      stdout = "";
    }

    let lines = stdout.split("\n").filter(Boolean);
    let fallbackNote = "";

    // Ranked multi-term fallback: a multi-word query with (almost) no literal hits is
    // re-run as OR-of-terms, ranked by term coverage per file — so "garmin auth fix"
    // finds the pages that mention all/most terms even if the phrase never appears.
    if (lines.length < 3 && /\s/.test(query.trim())) {
      const terms = [...new Set(query.trim().split(/\s+/).filter((t) => t.length >= 3))];
      if (terms.length >= 2) {
        try {
          const orArgs = [
            "--line-number", "--no-heading", "--color", "never", "--ignore-case",
            "--max-count", "20", "--glob", "*.md", "--glob", "!**/node_modules/**",
            "--", terms.map(escapeRegex).join("|"), "wiki", "raw", "meta",
          ];
          const { stdout: orOut } = await execFileAsync("rg", orArgs, { cwd: VAULT, maxBuffer: 8 * 1024 * 1024 });
          const orLines = orOut.split("\n").filter(Boolean);
          // Rank files: distinct terms matched desc → path priority → hit count desc.
          const files = new Map();
          for (const l of orLines) {
            const m = l.match(/^(.*?):(\d+):(.*)$/);
            if (!m) continue;
            const f = files.get(m[1]) || { lines: [], termsHit: new Set() };
            if (f.lines.length < 4) f.lines.push(l);
            const low = m[3].toLowerCase();
            for (const t of terms) if (low.includes(t.toLowerCase())) f.termsHit.add(t.toLowerCase());
            f.count = (f.count || 0) + 1;
            files.set(m[1], f);
          }
          const ranked = [...files.entries()].sort((a, b) =>
            b[1].termsHit.size - a[1].termsHit.size ||
            pathPriority(a[0]) - pathPriority(b[0]) ||
            b[1].count - a[1].count
          ).slice(0, 8);
          if (ranked.length) {
            lines = ranked.flatMap(([, f]) => f.lines);
            fallbackNote = `No literal match for the full phrase — showing ranked multi-term results for [${terms.join(", ")}] (best term-coverage first).`;
          }
        } catch { /* fallback is best-effort; keep exact results */ }
      }
    }

    if (!lines.length) {
      return { content: [{ type: "text", text: `No matches for "${query}".` }],
               structuredContent: { total: 0, count: 0, hits: [] } };
    }

    const total = lines.length;
    const hits = lines.slice(0, limit).map((l) => {
      const m = l.match(/^(.*?):(\d+):(.*)$/);
      if (!m) return { path: l, line: 0, text: "" };
      return { path: m[1], line: Number(m[2]), text: m[3].trim().slice(0, 300) };
    });

    // Group for human-readable markdown.
    const byFile = new Map();
    for (const h of hits) {
      if (!byFile.has(h.path)) byFile.set(h.path, []);
      byFile.get(h.path).push(h);
    }
    const md = [`# Search: "${query}"`, "", `${total} matching line(s)${total > limit ? `, showing ${limit}` : ""} across ${byFile.size} file(s).`, ""];
    if (fallbackNote) md.splice(2, 0, `_${fallbackNote}_`, "");
    for (const [path, hs] of byFile) {
      md.push(`## ${path}`);
      for (const h of hs) md.push(`- L${h.line}: ${h.text}`);
      md.push("");
    }
    if (total > limit) md.push(`…${total - limit} more matching line(s). Narrow the query or raise \`limit\`.`);

    return {
      content: [{ type: "text", text: truncate(md.join("\n"), "raise limit or narrow the query") }],
      structuredContent: { total, count: hits.length, hits },
    };
  }
);

// --- brain_read -------------------------------------------------------------

server.registerTool(
  "brain_read",
  {
    title: "Read a brain page",
    description: `Return the full contents of one page in the second-brain vault by its vault-relative path.

Use after brain_search to load a page in full (e.g. "wiki/projects/my-app.md", "wiki/index.md"). Paths must be inside the vault; absolute paths outside it are rejected.

Args:
  - path (string): vault-relative path, e.g. "wiki/projects/my-app.md"
  - heading (string, optional): return ONLY the section whose heading contains this text (case-insensitive) — use for big pages instead of reading the whole file

Returns the raw markdown (frontmatter + body). Responses over ${CHARACTER_LIMIT} chars are truncated with a marker AND a list of the page's headings so you can re-request just the section you need via \`heading\`. Returns an actionable error if the file does not exist.`,
    inputSchema: {
      path: z
        .string()
        .min(1, "Path is required")
        .max(400)
        .describe('Vault-relative path, e.g. "wiki/projects/my-app.md"'),
      heading: z
        .string()
        .min(2)
        .max(200)
        .optional()
        .describe("Optional: return only the section whose heading contains this text"),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ path, heading }) => {
    let abs;
    try {
      abs = safeVaultPath(path);
    } catch (err) {
      return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
    }
    try {
      const text = await readFile(abs, "utf8");
      const rel = relative(VAULT, abs);

      // Section mode: return just the requested heading's section.
      if (heading) {
        const sec = extractSection(text, heading);
        if (sec === null) {
          const hs = extractHeadings(text).map((h) => `${"  ".repeat(h.level - 1)}- ${h.title}`).join("\n");
          return {
            content: [{ type: "text", text: `Error: no heading containing "${heading}" in ${rel}. Available headings:\n${hs}` }],
            isError: true,
          };
        }
        const body = truncate(sec, "narrow the heading");
        return {
          content: [{ type: "text", text: body }],
          structuredContent: { path: rel, heading, content: body, bytes: Buffer.byteLength(sec), truncated: sec.length > CHARACTER_LIMIT },
        };
      }

      let body = truncate(text, `read it directly at ${rel}`);
      if (text.length > CHARACTER_LIMIT) {
        // Make truncation navigable: list all headings so the agent can fetch sections.
        const hs = extractHeadings(text).map((h) => `${"  ".repeat(h.level - 1)}- ${h.title}`).join("\n");
        body += `\n\nFull page is ${text.length} chars. Re-request any section with brain_read(path, heading):\n${hs}`;
      }
      // Include the page body in structuredContent too: some clients render only
      // structuredContent and ignore the text block — without `content` here they
      // would see metadata only. Keep the text block for clients that use it.
      return {
        content: [{ type: "text", text: body }],
        structuredContent: {
          path: rel,
          content: body,
          bytes: Buffer.byteLength(text),
          truncated: text.length > CHARACTER_LIMIT,
        },
      };
    } catch (err) {
      if (err && err.code === "ENOENT") {
        return {
          content: [{ type: "text", text: `Error: no page at "${path}". Use brain_search to find the right path first.` }],
          isError: true,
        };
      }
      return { content: [{ type: "text", text: `Error: could not read "${path}": ${err.message}` }], isError: true };
    }
  }
);

// --- brain_capture ----------------------------------------------------------

server.registerTool(
  "brain_capture",
  {
    title: "Capture a note into the brain",
    description: `Append a timestamped note into the second brain (raw/journal/). The next scheduled sync (skipped when nothing changed) ingests it into the wiki and cross-links it; nothing is committed by this call.

This is the same data hub as the \`brain\` CLI — use it to dump a finding, decision, feedback, or end-of-session worklog from any project so other sessions can recall it tomorrow. Do NOT pass secrets/credentials; provenance (cwd, kind) is recorded.

Args:
  - text (string): the note body (one line to a few paragraphs)
  - project (string, optional): project tag this relates to, e.g. "my-app"
  - kind (enum, optional): one of ${KINDS.map((k) => `"${k}"`).join(", ")} (default "note")

Returns the vault-relative path of the file written, plus structuredContent { path, project, kind }.`,
    inputSchema: {
      text: z
        .string()
        .min(1, "Note text is required")
        .max(20000)
        .describe("The note body to capture"),
      project: z
        .string()
        .max(80)
        .optional()
        .describe('Optional project tag, e.g. "my-app"'),
      kind: z
        .enum(KINDS)
        .default("note")
        .describe("Type of capture"),
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false,
    },
  },
  async ({ text, project, kind }) => {
    try {
      await mkdir(JOURNAL, { recursive: true });
      const { date, name } = stamp();
      const abs = join(JOURNAL, name);
      const fm = [
        "---",
        `captured: ${date}`,
        "from: mcp",
        `cwd: ${process.cwd()}`,
        `project: ${project || ""}`,
        `kind: ${kind}`,
        "status: unprocessed",
        "---",
        "",
        text.trim(),
        "",
      ].join("\n");
      await writeFile(abs, fm, { flag: "wx" }); // wx → never clobber
      const rel = relative(VAULT, abs);
      return {
        content: [{ type: "text", text: `Captured → ${rel}\nThe next scheduled sync will ingest and cross-link it (or run /ingest in the vault to process now).` }],
        structuredContent: { path: rel, project: project || null, kind },
      };
    } catch (err) {
      return { content: [{ type: "text", text: `Error: could not capture note: ${err.message}` }], isError: true };
    }
  }
);

// --- brain_context -----------------------------------------------------------

server.registerTool(
  "brain_context",
  {
    title: "Load project context from the brain",
    description: `One-call session bootstrap: assemble everything the brain knows about a project — its wiki page, the most recent worklog/source digests, and its project-scoped lessons — in a single response.

Use this at the START of a session instead of chaining brain_search + multiple brain_read calls. For anything it truncates, follow up with brain_read(path, heading).

Args:
  - project (string): project slug or name, e.g. "my-app"

Returns assembled markdown: project page (headings-indexed if large) + latest source digests + scoped lessons, plus structuredContent { page, sources, lessonCount }.`,
    inputSchema: {
      project: z
        .string()
        .min(2)
        .max(80)
        .describe('Project slug or name, e.g. "my-app"'),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  async ({ project }) => {
    const slug = project.toLowerCase().trim().replace(/[\s_]+/g, "-");
    const PAGE_BUDGET = 12000;   // chars of the project page
    const SOURCE_BUDGET = 4000;  // chars per recent source digest
    const md = [];
    const sc = { page: null, sources: [], lessonCount: 0 };

    // 1. Project page — direct slug, else alias/name search across wiki/projects.
    let pageRel = `wiki/projects/${slug}.md`;
    let pageText = null;
    try {
      pageText = await readFile(join(VAULT, pageRel), "utf8");
    } catch {
      try {
        const { stdout } = await execFileAsync(
          "rg",
          ["-l", "--ignore-case", "--glob", "*.md", "--", project, "wiki/projects"],
          { cwd: VAULT, maxBuffer: 1024 * 1024 }
        );
        const first = stdout.split("\n").filter(Boolean)[0];
        if (first) {
          pageRel = first;
          pageText = await readFile(join(VAULT, first), "utf8");
        }
      } catch { /* no match */ }
    }
    if (pageText) {
      sc.page = pageRel;
      md.push(`# Project page: ${pageRel}`, "");
      if (pageText.length > PAGE_BUDGET) {
        const hs = extractHeadings(pageText).map((h) => `${"  ".repeat(h.level - 1)}- ${h.title}`).join("\n");
        md.push(pageText.slice(0, PAGE_BUDGET),
          `\n…[page is ${pageText.length} chars; truncated. All sections — fetch any with brain_read("${pageRel}", heading):]\n${hs}`);
      } else {
        md.push(pageText);
      }
      md.push("");
    } else {
      md.push(`# No project page found for "${project}"`, "",
        `Try brain_search("${project}") — or the page may live under a different slug (see wiki/index.md).`, "");
    }

    // 2. Most recent source digests for this project (filename convention: <slug>-*.md).
    try {
      const files = await readdir(join(VAULT, "wiki", "sources"));
      const mine = files.filter((f) => f.startsWith(slug) && f.endsWith(".md"));
      const stats = await Promise.all(
        mine.map(async (f) => ({ f, mtime: (await stat(join(VAULT, "wiki", "sources", f))).mtimeMs }))
      );
      stats.sort((a, b) => b.mtime - a.mtime);
      for (const { f } of stats.slice(0, 2)) {
        const rel = `wiki/sources/${f}`;
        const t = await readFile(join(VAULT, rel), "utf8");
        sc.sources.push(rel);
        md.push(`# Recent source: ${rel}`, "");
        md.push(t.length > SOURCE_BUDGET
          ? `${t.slice(0, SOURCE_BUDGET)}\n…[truncated; brain_read("${rel}") for the rest]`
          : t);
        md.push("");
      }
    } catch { /* sources dir optional */ }

    // 3. Project-scoped lessons from the ledger.
    try {
      const ledger = await readFile(join(VAULT, "wiki", "lessons.md"), "utf8");
      const blocks = ledger.split(/^### /m).slice(1)
        .filter((b) => b.includes(`project:${slug}`))
        .map((b) => `### ${b.trim()}`);
      if (blocks.length) {
        sc.lessonCount = blocks.length;
        md.push(`# Lessons scoped to ${slug} (do not repeat these mistakes)`, "", blocks.join("\n\n"), "");
      }
    } catch { /* ledger optional */ }

    md.push(`---`, `_Capture new findings back with brain_capture(text, project="${slug}", kind=…)._`);

    return {
      content: [{ type: "text", text: truncate(md.join("\n"), "follow up with brain_read for specifics") }],
      structuredContent: sc,
    };
  }
);

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`${BRAIN_NAME} MCP server running (vault: ${VAULT})`);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
