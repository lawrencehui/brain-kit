#!/bin/zsh
# PostCompact hook: when an interactive Claude Code session compacts, write a digest of
# its transcript into this brain's raw/journal/ as a worklog. Compaction is the trigger
# because it only happens once a session has done real work. Best-effort and silent.
set -u
VAULT="${0:A:h:h}"
BRAIN="$VAULT/meta/brain.sh"
DIGEST="$VAULT/meta/digest.py"
PY="$(command -v python3)" || exit 0

input="$(cat)"
field() { printf '%s' "$input" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get(sys.argv[1],""))' "$1" 2>/dev/null; }
tp="$(field transcript_path)"; cwd="$(field cwd)"
[ -n "$tp" ] && [ -f "$tp" ] || exit 0

# Never capture sessions running inside the vault (the sync itself runs there).
case "${cwd:-$PWD}" in "$VAULT"|"$VAULT"/*) exit 0 ;; esac
proj="$(basename "${cwd:-$PWD}")"

tmp="$(mktemp -t brain-autocap.XXXXXX)" || exit 0
trap 'rm -f "$tmp"' EXIT
"$PY" "$DIGEST" "$tp" "$tmp" >/dev/null 2>&1 || exit 0
bytes="$(wc -c < "$tmp" 2>/dev/null || echo 0)"
[ "${bytes:-0}" -ge 200 ] || exit 0
"$BRAIN" -t worklog -p "$proj" "$(head -c 16000 "$tmp")" >/dev/null 2>&1
exit 0
