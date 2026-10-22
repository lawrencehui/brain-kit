// Stdio smoke test: handshake, list tools, capture a note, find it, read it, clean up.
import { spawn } from "node:child_process";
import { rm, readFile } from "node:fs/promises";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const VAULT = resolve(process.env.BRAIN_VAULT || join(here, "..", ".."));
const proc = spawn("node", ["server.js"], { cwd: here, stdio: ["pipe", "pipe", "inherit"] });

let buf = "";
const pending = new Map();
proc.stdout.on("data", (d) => {
  buf += d.toString();
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i).trim();
    buf = buf.slice(i + 1);
    if (!line) continue;
    let msg;
    try { msg = JSON.parse(line); } catch { continue; }
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  }
});
let idc = 0;
const rpc = (method, params) => new Promise((res) => {
  const id = ++idc; pending.set(id, res);
  proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
});
const notify = (method, params) => proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n");

let allPass = true;
const check = (name, cond) => { allPass = allPass && !!cond; console.log(`[${cond ? "PASS" : "FAIL"}] ${name}`); };
const token = `smoketoken${Date.now()}`;
let captured = null;
let secretPath = null;
try {
  const init = await rpc("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "smoke", version: "0" } });
  check("initialize", /-mcp-server$/.test(init?.result?.serverInfo?.name || ""));
  notify("notifications/initialized", {});
  const names = ((await rpc("tools/list", {}))?.result?.tools || []).map((t) => t.name).sort();
  check(`tools/list = ${names}`, names.join() === "brain_capture,brain_context,brain_read,brain_search");
  const cap = await rpc("tools/call", { name: "brain_capture", arguments: { text: `smoke ${token}`, project: "smoke", kind: "note" } });
  captured = cap?.result?.structuredContent?.path;
  check("brain_capture writes raw/journal/", /^raw\/journal\/.+\.md$/.test(captured || ""));
  const s = await rpc("tools/call", { name: "brain_search", arguments: { query: token } });
  check("brain_search finds the capture", (s?.result?.content?.[0]?.text || "").includes(captured));
  const r = await rpc("tools/call", { name: "brain_read", arguments: { path: captured } });
  check("brain_read returns it", (r?.result?.content?.[0]?.text || "").includes(token));
  const esc = await rpc("tools/call", { name: "brain_read", arguments: { path: "../../etc/passwd" } });
  check("brain_read refuses vault escape", esc?.result?.isError === true);
  const dup = await rpc("tools/call", { name: "brain_capture", arguments: { text: `smoke ${token}`, project: "smoke", kind: "note" } });
  check("brain_capture skips an identical capture", dup?.result?.structuredContent?.duplicate === true);
  const key = "sk-ant-" + "x".repeat(30);
  const sec = await rpc("tools/call", { name: "brain_capture", arguments: { text: `secret ${token} ${key} password=hunter2hunter2`, kind: "note" } });
  secretPath = sec?.result?.structuredContent?.path;
  const secBody = secretPath ? await readFile(join(VAULT, secretPath), "utf8") : "";
  check("brain_capture redacts credentials before writing", secBody.includes("[REDACTED:api-key]") && !secBody.includes(key) && !secBody.includes("hunter2hunter2") && /redacted: 2/.test(secBody));
  const c = await rpc("tools/call", { name: "brain_context", arguments: { project: "no-such-project" } });
  check("brain_context answers for unknown project", /No project page/.test(c?.result?.content?.[0]?.text || ""));
} finally {
  for (const p of [captured, secretPath]) if (p) await rm(join(VAULT, p), { force: true });
  proc.kill();
}
console.log(allPass ? "ALL PASS" : "SOME FAILED");
process.exit(allPass ? 0 : 1);
