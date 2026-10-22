---
type: reference
tags: [lessons, meta, agent-memory, guardrails]
created: __DATE__
updated: __DATE__
sources: []
status: active
---

# Lessons Ledger

Cross-repo lessons so agent sessions don't repeat the same mistakes. Maintained by the sync job
(mines `raw/` corrections + `git log` revert/fix commits), rendered into `CLAUDE.md` files by
`meta/render-lessons.py`.

**Schema (one `### L###` block per lesson, parsed by `render-lessons.py`; keep the field names):**
- `scope:` `universal` · `stack:<name>` (e.g. `stack:supabase`) · `repo:<path-under-DEV>` · `project:<slug>`
- `trigger:` the situation that should surface this lesson ("when ...")
- `mistake:` what went wrong (1 line)
- `rule:` what to do instead (1 line, imperative)
- `severity:` `high` | `med` | `low`
- `hits:` times observed
- `source:` where it came from

Ranking for injection: `severity` then `hits`. Only severities listed in `meta/lessons-routing.json`
are injected; the rest stay search-only. A `graduated:` field (lesson became a hook/lint/test/CI
guardrail) excludes it from injection.

---
