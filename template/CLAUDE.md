# Second-Brain Wiki — Operating Schema

This repository is an Obsidian vault and a Karpathy-style LLM-maintained wiki.
When working here, you (Claude) maintain a curated **synthesis layer** so knowledge
compounds over time. Follow this schema exactly.

## Layers
- `raw/` — immutable source record. Provenance. Never rewrite a source's meaning here.
- `wiki/` — the synthesis you maintain. Entity pages linked with `[[wiki-links]]`.
- `meta/` — `log.md` (append-only ingestion log) and `inbox.md` (quick capture).

## Page model (frontmatter on EVERY wiki page)
```
---
type: source | concept | person | project
tags: [kebab-case, tags]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[raw-or-source-page]]"]   # where this knowledge came from
status: active | stub | archived
---
```

## Rules
1. **Cite everything.** Every non-trivial claim on a wiki page links to the `raw/` source or `wiki/sources/` digest it came from.
2. **One entity, one page.** New people, concepts, and projects get their own page in the right `wiki/` subfolder — don't bury them inline.
3. **Link liberally** with `[[wiki-links]]`. A link to a page that doesn't exist yet is fine — it marks a page worth writing.
4. **Filenames are kebab-case and stable.** Renaming breaks links; prefer adding aliases over renaming.
5. **Synthesize, don't copy.** Especially for code repos: capture understanding + the on-disk path, never mirror source files into the vault.
6. **Voice:** concise, factual, second-brain tone. No filler, no hedging.

## Operations
The three slash commands in `.claude/commands/` (`/ingest`, `/query`, `/lint`) define the
detailed contracts. In short: `/ingest` turns sources into cited, cross-linked pages and
logs them; `/query` answers from the wiki with citations; `/lint` keeps the wiki coherent.

## Privacy
This is a personal brain. Do not push to public remotes. Treat all content as private.
