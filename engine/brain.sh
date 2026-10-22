#!/bin/zsh
# Quick-capture into the brain from any terminal. Writes a timestamped markdown file
# into <vault>/raw/journal/ (no git ops, safe for concurrent sessions). The next
# sync ingests it. Usually symlinked onto PATH as `brain` (or the --cli-name you chose).
#
# Usage:
#   brain "a quick note"
#   brain -p my-app -t finding "v2 beats v1 out-of-sample"
#   some_command | brain
# Flags:  -p <project>   tag the source project
#         -t <kind>      note | finding | feedback | worklog | idea  (default: note)
set -e
VAULT="${0:A:h:h}"          # resolves the symlink: <vault>/meta/brain.sh -> <vault>
DEST="$VAULT/raw/journal"

kind="note"; project=""
while [[ "$1" == -* ]]; do
  case "$1" in
    -p) project="$2"; shift 2 ;;
    -t) kind="$2";   shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) break ;;
  esac
done

# Normalise the slug so one project doesn't fragment across pages (my_app / My App / my-app).
if [[ -n "$project" ]]; then
  project="$(echo "$project" | tr '[:upper:]' '[:lower:]' | tr ' _' '--' | sed -E 's/-+/-/g; s/^-//; s/-$//')"
fi

text="$*"
if [[ -z "$text" ]]; then text="$(cat)"; fi
if [[ -z "${text// }" ]]; then echo "brain: nothing to save (no text/stdin)"; exit 1; fi

mkdir -p "$DEST"
file="$DEST/$(date +%Y-%m-%d-%H%M%S)-$$.md"
{
  echo "---"
  echo "captured: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "from: $(whoami)@$(hostname -s)"
  echo "cwd: $PWD"
  [[ -n "$project" ]] && echo "project: $project"
  echo "kind: $kind"
  echo "status: unprocessed"
  echo "---"
  echo
  echo "$text"
} > "$file"
echo "🧠 saved ($kind${project:+ · $project}) → ${file/#$VAULT\//}"
