# brain-kit

**A second brain for Claude Code that maintains itself.**

You get a private markdown wiki (it opens in Obsidian) that Claude writes and keeps current, plus:

- an **MCP server**, so every Claude Code session in every repo can search the brain and write to it
- a **scheduled sync**, which turns your captured notes into linked wiki pages and keeps a page for each of your repos
- a **lessons ledger**: mistakes your agents made get turned into rules, and those rules are written into your `CLAUDE.md` files so the same mistake isn't repeated

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

**from a clone**:

```sh
git clone https://github.com/lawrencehui/brain-kit && ./brain-kit/install.sh
```

All three run the same installer. With no flags, it creates the brain at `~/brain` and watches the repos under `~/Dev`. To change that, pass flags. Flags work with all three methods; for curl, put them after `sh -s --`:

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
| hook | Adds a Claude Code `PostCompact` hook: when a long session compacts, a digest of it is saved as a worklog | `hook` |
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
```

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
- **Lessons** are blocks in `wiki/lessons.md`. Each has a `scope`, which decides which `CLAUDE.md` files it is written into:

  | Scope | Written into |
  |---|---|
  | `universal` | `<dev>/CLAUDE.md`, which every repo inherits |
  | `project:<slug>` | `<dev>/<slug>/CLAUDE.md` |
  | `repo:<path>` | that repo's `CLAUDE.md` |
  | `stack:<name>` | repos you've mapped to that stack in `meta/lessons-routing.json` |

  By default only `high` severity lessons are written into files; the rest can still be found with search. Lessons are only added to `CLAUDE.md` files that already exist; the renderer never creates one.

## Configuration

| File | Purpose |
|---|---|
| `meta/brain.env` | Brain name, `DEV` folder, path to `claude`, sync model. Machine-specific, not committed. |
| `meta/lessons-routing.json` | Which severities get injected, the repo→stack map, and project→repo overrides. |
| `CLAUDE.md` (vault root) | The rules Claude follows when maintaining the wiki. Edit it to change how pages are written. |
| `.claude/commands/*.md` | Definitions of `/ingest`, `/query` and `/lint`. |

## Security and privacy

- To run unattended, the sync calls `claude -p --permission-mode bypassPermissions`. It can read every repo under `--dev` and acts on anything that lands in `raw/`, so only point it at code and notes you trust.
- The vault is a local git repo. Don't add a public remote: the brain fills up with private details of your work.
- Never put secrets into captures. The MCP tool descriptions tell agents the same.

## Several brains on one machine

Give each brain its own `--name` and `--cli-name`. Each gets its own MCP server, scheduled job, hook and marked block in `CLAUDE.md`, so they don't overwrite each other:

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

Then remove the `PostCompact` entry pointing at `<vault>/meta/autocapture-hook.sh` from `~/.claude/settings.json`, and delete the `BRAIN-USAGE:brain` and `BRAIN-LESSONS:brain` blocks from your `CLAUDE.md` files. The vault is ordinary markdown in git: keep it or delete it.

## License

MIT
