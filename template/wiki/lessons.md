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

**Schema (one `### L###` block per lesson, parsed by `meta/lessonlib.py`; keep the field names):**
- `scope:` `universal` · `stack:<name>` (e.g. `stack:supabase`) · `repo:<path-under-DEV>` · `project:<slug>`
- `trigger:` the situation that should surface this lesson ("when ...")
- `mistake:` what went wrong
- `rule:` what to do instead (imperative)
- `summary:` one self-contained line under 200 characters ("When X, do Y"); this is what goes into `CLAUDE.md`
- `severity:` `high` | `med` | `low`
- `hits:` times observed · `last_seen:` YYYY-MM-DD it was last observed
- `status:` `proposed` (new, not injected) · `active` · `retired`. Missing means active.
- `match:` optional. Tool-call conditions that fire the lesson just before the call (PreToolUse hook).
  Alternatives joined by ` || `, conditions by ` && `, each `kind:regex` with kind `tool` (tool name),
  `cmd` (Bash command), `path` (file path) or `text` (whole tool input). Case-insensitive.
  Example: `cmd:git\s+filter-repo || tool:^(Write|Edit)$ && path:\.sql$`
- `superseded_by:` L### that replaces this lesson · `graduated:` it became a hook/lint/test
- `source:` where it came from

Injection (`meta/render-lessons.py`): live lessons (active, not superseded, graduated or stale) without a `match:`
go into `CLAUDE.md` as one line each, ranked severity > hits > recency and cut at the token budget in
`meta/lessons-routing.json`. Lessons with a `match:` are injected just in time instead.

---
