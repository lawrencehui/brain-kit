---
description: Consistency pass over the wiki — contradictions, orphans, broken links, frontmatter
argument-hint: "(no arguments)"
---

You are running the **lint** operation. Read `CLAUDE.md` first. Produce a report, then apply fixes only after the user confirms.

Check across `wiki/`:
1. **Contradictions** — claims on different pages that conflict. List both with citations.
2. **Stale / superseded** — older claims a newer source has overtaken. Propose marking `status: archived` or updating.
3. **Orphans** — pages with no inbound `[[wiki-links]]`. Propose where to link them from (often `wiki/index.md`).
4. **Broken links** — `[[links]]` whose target file doesn't exist. Either create a stub (`status: stub`) or fix the link.
5. **Frontmatter** — pages missing required fields (`type`, `created`, `updated`, `sources`, `status`). Fill them in.

Output a numbered report grouped by category. Ask before editing. After fixes, update `wiki/index.md` Maps of Content if structure changed.
