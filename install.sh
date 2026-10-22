#!/bin/zsh
# brain-kit installer: creates an EMPTY second-brain vault and wires it into Claude Code.
#
#   ./install.sh --vault ~/brain [--dev ~/Dev] [--name brain] [--cli-name brain]
#                [--model sonnet] [--skip mcp,cli,schedule,hook,devclaude]
#
# Steps (each idempotent; skip any with --skip):
#   vault      copy template + engine into --vault, write meta/brain.env, git init   (always)
#   npm        install MCP server deps and run its smoke test                        (always)
#   cli        symlink <vault>/meta/brain.sh to ~/.local/bin/<cli-name>
#   mcp        claude mcp add -s user <name> (stdio, node <vault>/meta/mcp/server.js)
#   schedule   launchd job (macOS) or crontab line (Linux): sync at 00/06/12/18:02
#   hook       PostCompact auto-capture hook in ~/.claude/settings.json
#   devclaude  sentinel block in <dev>/CLAUDE.md telling every agent to use the brain
#
# Re-running against an existing brain refreshes the engine files only; content is untouched.
set -e
KIT="${0:A:h}"

VAULT=""; DEV="$HOME/Dev"; NAME="brain"; CLI=""; MODEL="sonnet"; SKIP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault) VAULT="$2"; shift 2 ;;
    --dev) DEV="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --cli-name) CLI="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --skip) SKIP=",$2,"; shift 2 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$VAULT" ]] || { echo "--vault is required" >&2; exit 2; }
[[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "--name must be lowercase kebab-case" >&2; exit 2; }
CLI="${CLI:-$NAME}"
VAULT="${VAULT:a}"; DEV="${DEV:a}"
skip() { [[ "$SKIP" == *",$1,"* ]]; }
say() { print -P "%F{cyan}==>%f $*"; }
warn() { print -P "%F{yellow}!!%f $*" >&2; }

# --- prerequisites -----------------------------------------------------------
for bin in git node npm python3 rg; do
  command -v $bin >/dev/null || { echo "missing prerequisite: $bin (rg = ripgrep, used by brain_search)" >&2; exit 1; }
done
CLAUDE_BIN="$(command -v claude || true)"
[[ -n "$CLAUDE_BIN" ]] || { skip mcp && skip schedule || { echo "claude CLI not on PATH (needed for mcp + schedule; or --skip them)" >&2; exit 1; } }

# --- vault ------------------------------------------------------------------
UPGRADE=0
if [[ -f "$VAULT/meta/brain.env" ]]; then
  UPGRADE=1; say "existing brain at $VAULT: refreshing engine files only"
elif [[ -d "$VAULT" && -n "$(ls -A "$VAULT" 2>/dev/null)" ]]; then
  echo "$VAULT exists and is not empty; refusing to install into it" >&2; exit 1
else
  say "creating empty vault at $VAULT"
  mkdir -p "$VAULT"
  cp -R "$KIT/template/." "$VAULT/"
  today="$(date +%F)"
  for f in "$VAULT/wiki/index.md" "$VAULT/wiki/lessons.md"; do
    sed -i.bak "s/__DATE__/$today/g" "$f" && rm -f "$f.bak"
  done
  cp "$KIT/engine/lessons-routing.json" "$VAULT/meta/"
fi

mkdir -p "$VAULT/meta/mcp"
cp "$KIT/engine/sync.sh" "$KIT/engine/brain.sh" "$KIT/engine/autocapture-hook.sh" \
   "$KIT/engine/render-lessons.py" "$KIT/engine/digest.py" "$VAULT/meta/"
cp "$KIT/engine/mcp/server.js" "$KIT/engine/mcp/package.json" "$KIT/engine/mcp/smoke-test.mjs" "$VAULT/meta/mcp/"
chmod +x "$VAULT/meta/"*.sh "$VAULT/meta/render-lessons.py"

# Machine-specific config; gitignored so the vault itself stays portable.
cat > "$VAULT/meta/brain.env" <<EOF
BRAIN_NAME="$NAME"
DEV="$DEV"
CLAUDE_BIN="$CLAUDE_BIN"
SYNC_MODEL="$MODEL"
EOF

# --- npm + smoke test -------------------------------------------------------
say "installing MCP server deps"
(cd "$VAULT/meta/mcp" && npm install --silent --no-fund --no-audit)
(cd "$VAULT/meta/mcp" && node smoke-test.mjs) || { echo "MCP smoke test failed" >&2; exit 1; }
python3 "$VAULT/meta/render-lessons.py" >/dev/null

if [[ ! -d "$VAULT/.git" ]]; then
  git -C "$VAULT" init -q
  git -C "$VAULT" add -A
  git -C "$VAULT" commit -qm "chore: new brain from brain-kit"
  say "git initialised (local only; never add a public remote)"
fi


# --- cli --------------------------------------------------------------------
if ! skip cli; then
  mkdir -p "$HOME/.local/bin"
  link="$HOME/.local/bin/$CLI"
  if [[ -e "$link" || -L "$link" ]] && [[ "${link:A}" != "$VAULT/meta/brain.sh" ]]; then
    warn "$link already exists and points elsewhere (${link:A}); pass --cli-name to pick another name. Skipped."
  else
    ln -sf "$VAULT/meta/brain.sh" "$link"
    say "CLI: $CLI \"note\"  (ensure ~/.local/bin is on PATH)"
  fi
fi

# --- mcp --------------------------------------------------------------------
if ! skip mcp; then
  if "$CLAUDE_BIN" mcp get "$NAME" >/dev/null 2>&1; then
    warn "an MCP server named '$NAME' is already registered; left as is (claude mcp remove -s user $NAME to redo)"
  else
    "$CLAUDE_BIN" mcp add -s user "$NAME" -e BRAIN_VAULT="$VAULT" -e BRAIN_NAME="$NAME" -- node "$VAULT/meta/mcp/server.js"
    say "MCP '$NAME' registered at user scope (new sessions pick it up)"
  fi
fi

# --- schedule ---------------------------------------------------------------
if ! skip schedule; then
  if [[ "$OSTYPE" == darwin* ]]; then
    label="com.brainkit.$NAME.sync"
    plist="$HOME/Library/LaunchAgents/$label.plist"
    mkdir -p "${plist:h}"
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$VAULT/meta/sync.sh</string></array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>2</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>2</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>2</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>2</integer></dict>
  </array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>${CLAUDE_BIN:h}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StandardOutPath</key><string>$VAULT/meta/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$VAULT/meta/launchd.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$plist"
    say "launchd job $label loaded (00/06/12/18:02; skips when nothing changed)"
  else
    line="2 0,6,12,18 * * * /usr/bin/env zsh $VAULT/meta/sync.sh # brainkit:$NAME"
    (crontab -l 2>/dev/null | grep -v "# brainkit:$NAME\$"; echo "$line") | crontab -
    say "crontab entry installed (00/06/12/18:02)"
  fi
fi

# --- hook -------------------------------------------------------------------
if ! skip hook; then
  python3 - "$HOME/.claude/settings.json" "$VAULT/meta/autocapture-hook.sh" <<'PY'
import json, pathlib, sys
path, cmd = pathlib.Path(sys.argv[1]), sys.argv[2]
cfg = json.loads(path.read_text()) if path.exists() else {}
groups = cfg.setdefault("hooks", {}).setdefault("PostCompact", [])
if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
    print("hook already registered")
else:
    groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 30}]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("PostCompact auto-capture hook registered")
PY
fi

# --- devclaude --------------------------------------------------------------
if ! skip devclaude; then
  mkdir -p "$DEV"
  python3 - "$DEV/CLAUDE.md" "$NAME" "$VAULT" <<'PY'
import pathlib, re, sys
path, name, vault = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
begin, end = f"<!-- BRAIN-USAGE:{name} BEGIN -->", f"<!-- BRAIN-USAGE:{name} END -->"
block = f"""{begin}
# Second brain ({name})

A persistent second-brain wiki lives at `{vault}`, covering every repo under this folder. It is
kept current by a scheduled sync. The `{name}` MCP server is registered at user scope:

- **Before** non-trivial work in a repo: `brain_context("<project-slug>")` returns the project page,
  latest worklogs and project-scoped lessons in one call. Otherwise `brain_search("<topic>")` then
  `brain_read(path)` (or `brain_read(path, heading)` for one section of a big page).
- **After** a meaningful finding, decision, mistake or fix: `brain_capture(text, project="<slug>",
  kind=note|finding|feedback|worklog|idea)`. Never pass secrets.
- The auto-generated **Lessons** block (if present below) comes from the brain's lessons ledger.
  Treat it as hard-won rules.

Privacy: the brain is personal. Do not push it to public remotes or leak its contents.
{end}
"""
old = path.read_text() if path.exists() else ""
if begin in old and end in old:
    new = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", lambda m: block, old, flags=re.S)
else:
    new = (old.rstrip("\n") + "\n\n" if old else "") + block
if new != old:
    path.write_text(new); print(f"brain usage block written to {path}")
else:
    print(f"{path} already up to date")
PY
fi

say "done. Brain: $VAULT"
[[ $UPGRADE -eq 1 ]] || cat <<EOF

Next:
  - start a NEW Claude Code session so the '$NAME' MCP tools load
  - drop sources into $VAULT/raw/ (or capture with: $CLI "first note")
  - run a sync now instead of waiting:  zsh $VAULT/meta/sync.sh --force
  - lesson routing (stacks/projects -> repos): $VAULT/meta/lessons-routing.json
EOF
