# brain-kit

An empty, self-maintaining second brain for Claude Code: an Obsidian-markdown wiki that
Claude curates, a ripgrep-backed MCP server so every session can search and capture into it,
a scheduled sync that ingests captures and refreshes every repo's page, and a lessons ledger
rendered into `CLAUDE.md` files so agents stop repeating mistakes.

## Install

Prereqs: `git node npm python3 rg zsh claude`.

```sh
./install.sh --vault ~/brain --dev ~/Dev            # everything
./install.sh --vault ~/brain --name work-brain --cli-name wb   # second brain on the same machine
./install.sh --vault ~/brain --skip schedule,hook   # pick and choose
```

What it does (each step idempotent; re-running refreshes engine files and never touches content):

| Step | Effect |
|---|---|
| vault | copies `template/` + `engine/` to `--vault`, writes `meta/brain.env` (gitignored), `git init` |
| npm | installs MCP deps, runs `meta/mcp/smoke-test.mjs` |
| cli | `~/.local/bin/<cli-name>` -> `<vault>/meta/brain.sh` |
| mcp | `claude mcp add -s user <name>`: tools `brain_search`, `brain_read`, `brain_context`, `brain_capture` |
| schedule | launchd (macOS) / crontab (Linux) runs `meta/sync.sh` at 00/06/12/18:02 |
| hook | PostCompact hook: compacting sessions leave a worklog digest in `raw/journal/` |
| devclaude | sentinel block in `<dev>/CLAUDE.md` telling every agent to use the brain |

## Sync

`meta/sync.sh` hashes `raw/` mtimes plus the HEAD of every repo under `DEV`. Unchanged means it
exits without calling Claude. Otherwise headless `claude -p` ingests new raw files, refreshes repo
pages, updates `wiki/lessons.md`, lints, and commits locally, then `render-lessons.py` injects
lessons into existing `CLAUDE.md` files. `--force` runs it regardless.

**Security:** the sync runs `claude -p --permission-mode bypassPermissions` with read access to
every repo under `DEV`, and ingests whatever lands in `raw/`. Only point it at trees you trust, and
never add a public git remote to the vault.

## Lesson routing

`meta/lessons-routing.json`: `inject_severities`, `repo_stacks` (repo path -> stacks it uses, for
`stack:` lessons), `project_to_repos` (slug -> repo paths). A `project:<slug>` lesson with no
mapping goes to `<DEV>/<slug>/CLAUDE.md` if that repo exists. Blocks are only written into
`CLAUDE.md` files that already exist.

## Uninstall

```sh
claude mcp remove -s user <name>
launchctl bootout gui/$(id -u)/com.brainkit.<name>.sync; rm ~/Library/LaunchAgents/com.brainkit.<name>.sync.plist
rm ~/.local/bin/<cli-name>
# remove the PostCompact entry from ~/.claude/settings.json and the BRAIN-USAGE/BRAIN-LESSONS blocks from CLAUDE.md files
```
