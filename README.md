# brain-kit

**A second brain for Claude Code that maintains itself.**

You get a private markdown wiki (it opens in Obsidian) that Claude writes and keeps current, plus:

- an **MCP server**, so every Claude Code session in every repo can search the brain and write to it
- a **scheduled sync**, which turns your captured notes into linked wiki pages and keeps a page for each of your repos
- a **lessons ledger**: mistakes your agents made become rules. You approve each one, and it then shows up either in your `CLAUDE.md` files or right before the tool call it guards
- **hooks** that load the current repo's page when a session starts, and save a worklog when a long session compacts

The brain starts empty. It fills up as you work.

## Install

**npm** (needs Node 18+):

```sh
npx create-second-brain
```

**curl**:

```sh
curl -fsSL https://raw.githubusercontent.com/lawrencehui/brain-kit/main/get.sh | sh
```

**Claude Code plugin** (the MCP server and hooks come from the plugin; `/brain-kit:init` then creates the vault and the sync schedule):

```sh
claude plugin marketplace add lawrencehui/brain-kit
claude plugin install brain-kit@brain-kit
# then, in Claude Code:  /brain-kit:init
```

**from a clone**:

```sh
git clone https://github.com/lawrencehui/brain-kit && ./brain-kit/install.sh
```

All of them run the same installer. With no flags, it creates the brain at `~/brain` and watches the repos under `~/Dev`. To change that, pass flags. Flags work with every method; for curl, put them after `sh -s --`:

```sh
npx create-second-brain --vault ~/notes/brain --dev ~/code
curl -fsSL .../get.sh | sh -s -- --vault ~/notes/brain --dev ~/code
```

Once it finishes, **start a new Claude Code session** so the MCP tools load.

### Requirements

`git`, `node`/`npm`, `python3`, `zsh`, [`rg` (ripgrep)](https://github.com/BurntSushi/ripgrep) and the [`claude` CLI](https://docs.claude.com/en/docs/claude-code), on macOS or Linux. The installer checks for these and tells you which are missing.

### Flags

| Flag | Default | Meaning |
|---|---|---|
| `--vault <dir>` | `~/brain` | Where the brain lives. Must be empty or not exist yet. |
| `--dev <dir>` | `~/Dev` | Folder whose git repos the brain tracks. |
| `--name <name>` | `brain` | Name of the MCP server and of the scheduled job. |
| `--cli-name <name>` | same as `--name` | Name of the capture command put on your PATH. |
| `--model <model>` | `sonnet` | Model the sync uses. |
| `--skip <steps>` | none | Comma-separated list of steps not to run (see below). |

## What the installer sets up

| Step | What it does | Skip with |
|---|---|---|
| vault | Copies the empty wiki template into `--vault` and runs `git init` (local only, no remote is ever added) | — |
| mcp server | Installs the server's dependencies and runs its self-test | — |
| cli | Adds a `brain "note"` capture command at `~/.local/bin/brain` | `cli` |
| mcp | Registers the MCP server with `claude mcp add -s user` | `mcp` |
| schedule | Runs the sync four times a day (00:02, 06:02, 12:02, 18:02): launchd on macOS, crontab on Linux | `schedule` |
| hook | Adds three Claude Code hooks to `~/.claude/settings.json` (see [Hooks](#hooks)) | `hook` |
| devclaude | Adds a short block to `<dev>/CLAUDE.md` telling every agent to use the brain | `devclaude` |

Every step can be re-run safely. Running the installer again on an existing brain updates the engine files and leaves your content alone. This is also how you upgrade.

## Using it

**In Claude Code**, agents get four tools:

| Tool | Use |
|---|---|
| `brain_context("my-app")` | Run at the start of a session. Returns the project's page, its latest worklogs and its lessons in one call. |
| `brain_search("topic")` | Full-text search across the brain. |
| `brain_read("wiki/projects/my-app.md")` | Read a page. Add a heading argument to read just that section. |
| `brain_capture(text, project, kind)` | Save a finding, decision, mistake or worklog. |

**From a terminal**:

```sh
brain "Postgres connection pool tops out at 20, not 100"
brain -p my-app -t feedback "don't run migrations without a backup"
git log -5 | brain -p my-app -t worklog
brain sync --force                      # run the sync now
```

Every capture, from the CLI, MCP or a hook, goes through one script (`meta/capture.py`). It replaces anything that looks like a credential (API keys, tokens, JWTs, private keys, `password=...`, passwords in URLs) with `[REDACTED:<kind>]` before writing, and skips a capture identical to one saved in the last 10 minutes.

**Reviewing lessons**:

```sh
brain lessons list                      # proposed lessons waiting for you
brain lessons show L073
brain lessons approve L073 L074         # make them live
brain lessons retire L012 --superseded-by L080
brain lessons list --active             # what's live now
```

New lessons from the sync are `proposed` and are never injected until you approve them. Once a day, the session-start hook mentions any that are waiting.

**Inside the vault**, Claude Code has three slash commands:

- `/ingest [path]`: turn sources into wiki pages
- `/query <question>`: answer from the wiki, with citations
- `/lint`: find broken links, orphan pages and contradictions

**In Obsidian**, open the vault folder as a vault to browse it.

## How it works

```
 capture ─────────────┐
  brain CLI           │
  brain_capture (MCP) ├──► raw/journal/*.md ──┐
  PostCompact hook    │                       │
 your repos (~/Dev) ──┴── git HEADs ──────────┤
                                              ▼
                     meta/sync.sh  (4x a day; skips if nothing changed)
                       1 ingest new raw files → wiki/sources, entity pages
                       2 refresh pages for repos whose HEAD moved
                       3 update wiki/lessons.md from corrections and fix commits
                       4 lint
                       5 git commit (local)
                                              │
                     meta/render-lessons.py ──┴──► lessons block in CLAUDE.md files
```

- **Cheap when idle.** Before calling Claude, the sync computes a fingerprint from the timestamps of your raw files and the current commit of every repo. If nothing has changed it exits straight away, at no cost. To run it on demand: `zsh ~/brain/meta/sync.sh --force`.
- **Vault layout:**
  - `raw/` holds what came in and is never rewritten
  - `wiki/` holds what Claude wrote (`sources/`, `projects/`, `concepts/`, `people/`, `index.md`, `lessons.md`)
  - `meta/` holds the engine, the logs and `brain.env` (this machine's settings, not committed)
- **Search** uses ripgrep over the markdown files. There is no vector database and nothing to re-index.
- **Lessons** are blocks in `wiki/lessons.md` (the schema is at the top of that file). A lesson is *live* when it is `active`, not superseded, not graduated, and has been seen within `stale_days`. Each live lesson reaches agents in one of two ways:
  - **Just in time.** A lesson with a `match:` field (for example `cmd:git\s+push.*--force` or `tool:^Edit$ && path:\.sql$`) is injected by the PreToolUse hook right before a matching tool call, and only in repos it is scoped to. It isn't shown again in the same session for 40 tool calls.
  - **Always on.** A lesson without a matcher goes into `CLAUDE.md` as one line. Lines are ranked by severity, then hits, then recency, and cut at `inject_token_budget` (2,000 tokens by default). Lessons over the budget stay searchable.

  The `scope` decides where a lesson applies:

  | Scope | Written into |
  |---|---|
  | `universal` | `<dev>/CLAUDE.md`, which every repo inherits |
  | `project:<slug>` | `<dev>/<slug>/CLAUDE.md` |
  | `repo:<path>` | that repo's `CLAUDE.md` |
  | `stack:<name>` | repos you've mapped to that stack in `meta/lessons-routing.json` |

  By default only `high` lessons go into `CLAUDE.md`, and `high` and `med` lessons can fire just in time. Lessons are only added to `CLAUDE.md` files that already exist; the renderer never creates one.

## Hooks

| Hook | What it does | Cost |
|---|---|---|
| `SessionStart` | Finds this repo's `wiki/projects/` page and loads it into the session (capped at `session_context_chars`). Skips resumed sessions and the vault. | One page per new session |
| `PreToolUse` | Injects the matching lessons before a tool call, at most 2 per call. Silent when nothing matches, and silent on any error. | About 40 ms per tool call; usually zero tokens |
| `PostCompact` | Saves a digest of the session as a worklog in `raw/journal/`. | None until the next sync |

## Configuration

| File | Purpose |
|---|---|
| `meta/brain.env` | Brain name, `DEV` folder, path to `claude`, sync model. Optional `SYNC_EXCLUDE` (a regex of repo paths the sync ignores). Machine-specific, not committed. |
| `meta/lessons-routing.json` | `inject_severities`, `jit_severities`, `inject_token_budget`, `stale_days`, `session_context_chars`, the repo→stack map (`repo_stacks`) and project→repo overrides (`project_to_repos`). |
| `meta/project-aliases.json` | Optional `{"alias": "canonical-slug"}` map, so captures for one project don't split across names. |
| `CLAUDE.md` (vault root) | The rules Claude follows when maintaining the wiki. Edit it to change how pages are written. |
| `.claude/commands/*.md` | Definitions of `/ingest`, `/query` and `/lint`. |

## Security and privacy

- To run unattended, the sync calls `claude -p --permission-mode bypassPermissions`. It can read every repo under `--dev` and acts on anything that lands in `raw/`, so only point it at code and notes you trust.
- The vault is a local git repo. Don't add a public remote: the brain fills up with private details of your work.
- Captures are redacted before they're written, but the patterns only catch credential-shaped strings. Don't paste secrets in on purpose.
- The PreToolUse hook only adds context. It never blocks or changes a tool call.

## Several brains on one machine

Give each brain its own `--name` and `--cli-name`. Each gets its own MCP server, scheduled job, hooks and marked block in `CLAUDE.md`, so they don't overwrite each other. (The plugin always serves the brain named `brain`, or the one in `$BRAIN_VAULT`.)

```sh
npx create-second-brain --vault ~/work-brain --name work-brain --cli-name wb
```

## Uninstall

```sh
claude mcp remove -s user brain
launchctl bootout gui/$(id -u)/com.brainkit.brain.sync                # macOS
rm ~/Library/LaunchAgents/com.brainkit.brain.sync.plist               # macOS
crontab -l | grep -v '# brainkit:brain$' | crontab -                 # Linux
rm ~/.local/bin/brain
```

Then remove the three hook entries that point into `<vault>/meta/` (`PostCompact`, `PreToolUse`, `SessionStart`) from `~/.claude/settings.json`, or run `claude plugin uninstall brain-kit@brain-kit` if you installed the plugin. Delete the `BRAIN-USAGE:brain` and `BRAIN-LESSONS:brain` blocks from your `CLAUDE.md` files. The vault is ordinary markdown in git: keep it or delete it.

## Credits

Ideas taken from other projects:
- [lessons-learned](https://github.com/joeblackwaslike/lessons-learned): lessons that fire right before the tool call they guard
- [claude-reflect](https://github.com/BayramAnnakov/claude-reflect) and [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain): a human approves rules before they go live
- [agentmemory](https://github.com/rohitg00/agentmemory): a token budget on injection, redacting secrets, dropping duplicate captures, retiring stale memories
- [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler): loading context automatically at session start
- Andrej Karpathy's LLM-wiki pattern: the `raw/` → `wiki/` layout

## License

MIT
