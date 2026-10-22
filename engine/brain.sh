#!/bin/zsh
# The `brain` CLI. Usually symlinked onto PATH as `brain` (or the --cli-name you chose).
#
# Capture (secrets are redacted, identical captures within 10 minutes are skipped):
#   brain "a quick note"
#   brain -p my-app -t finding "v2 beats v1 out-of-sample"
#   some_command | brain -p my-app -t worklog
#     -p <project>   tag the source project
#     -t <kind>      note | finding | feedback | worklog | idea  (default: note)
#
# Lessons:
#   brain lessons list [--proposed|--active|--retired|--all]
#   brain lessons show L012
#   brain lessons approve L073 [L074 ...]       make proposed lessons live
#   brain lessons retire L012 [--superseded-by L080]
#   brain lessons render                          re-render CLAUDE.md blocks + hook manifest
#
# Sync now:  brain sync [--force]
set -e
VAULT="${0:A:h:h}"          # resolves the symlink: <vault>/meta/brain.sh -> <vault>

case "$1" in
  lessons) shift; exec python3 "$VAULT/meta/lessons.py" "$@" ;;
  sync)    shift; exec zsh "$VAULT/meta/sync.sh" "$@" ;;
  -h|--help|help) sed -n '2,20p' "$0"; exit 0 ;;
esac
# Parse flags here and pass the text after `--`, so a note that starts with "-" is still text.
args=()
while [[ "$1" == -* && "$1" != "--" ]]; do
  case "$1" in
    -p|-t) args+=("$1" "$2"); shift 2 ;;
    *) break ;;
  esac
done
[[ "$1" == "--" ]] && shift
exec python3 "$VAULT/meta/capture.py" "${args[@]}" -- "$@"
