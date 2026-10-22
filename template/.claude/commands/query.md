---
description: Answer a question from the wiki, with citations
argument-hint: "<your question>"
---

You are running the **query** operation. Read `CLAUDE.md` first.

Question: `$ARGUMENTS`

1. Search the synthesis layer: glob/grep over `wiki/` for relevant pages (try concepts, people, projects, sources). Read the pages that match.
2. Synthesize a direct answer from what the wiki actually says. Do NOT invent — if the wiki is silent or thin on this, say so and point to which `raw/` sources might need ingesting.
3. Cite as you go: reference the `wiki/` pages used and, through them, the underlying `raw/` sources.
4. If the answer represents a genuinely new synthesis worth keeping, offer to file it as a new `wiki/concepts/` page (with citations) so the insight compounds.
