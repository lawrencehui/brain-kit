---
description: Ingest a source (file, folder of docs, or folder of git repos) into the wiki
argument-hint: "[path]  (omit to process everything new under raw/)"
---

You are running the **ingest** operation for this second-brain wiki. Read `CLAUDE.md` first; obey its page model and rules.

Target: `$ARGUMENTS` — if empty, process every source under `raw/` not already recorded in `meta/log.md`.

## 1. Detect mode
- **Single document** (a file): one source.
- **Folder of documents** (md/pdf/txt): iterate each file as a source.
- **Folder of git repos** (subdirs containing `.git`): repo-ingest mode (Section 4).

## 2. Per source (documents)
1. Read it fully. For PDFs, read page ranges; for long files, read in chunks.
2. Surface the key findings to the user in 3–6 bullets.
3. Create `wiki/sources/<kebab-slug>.md` — a digest page: what it is, the key points, and `[[links]]` to the entity pages it touches. Add frontmatter (`type: source`, `sources` pointing at the `raw/` path).
4. Create or update entity pages under `wiki/concepts/`, `wiki/people/`, `wiki/projects/`. Add new claims with citations; add `[[wiki-links]]` both directions.
5. If a new claim contradicts an existing page, do NOT silently overwrite — add a `> ⚠️ Contradiction:` note on the page citing both sources and tell the user.
6. Update `updated:` dates on every page you touch.

## 3. After all sources
- Append one line per source to `meta/log.md`: `YYYY-MM-DD — <source path> → <pages created/updated>`.
- Add the newest source digests to the "Recently ingested" list in `wiki/index.md`.
- Summarize what changed.

## 4. Repo-ingest mode (folder of git repos)
Process **repo by repo** so it's resumable. Skip any repo already in `meta/log.md`.
For each repo, ignore `node_modules`, build outputs, and `.git`. Read only high-signal files: `README*`, package/manifest files (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, etc.), the directory structure, and entry points / notable modules.
Produce `wiki/projects/<repo>.md` with: purpose, stack, architecture in one paragraph, `status` (active | experiment | archived), key ideas worth remembering, and the absolute on-disk path. Create shared `wiki/concepts/` pages for techniques that recur across repos and link them.
**Never copy source code into the vault.** Log each repo as you finish it.

Calibration: if the user points you at a large tree for the first time, do the first 1–2 repos, show the result, and confirm depth/voice before continuing.
