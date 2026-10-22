#!/bin/zsh
# Scheduled brain sync. Skips instantly (no Claude spend) when nothing changed: the
# change signature covers every raw/ file plus the HEAD of every git repo under $DEV.
# Otherwise runs headless Claude to ingest, refresh repos, update lessons, lint, commit.
# Local-only; never pushes. Config: <vault>/meta/brain.env (written by install.sh).

VAULT="${0:A:h:h}"
cd "$VAULT" || exit 1
source meta/brain.env || exit 1      # BRAIN_NAME, DEV, CLAUDE_BIN, SYNC_MODEL, optional SYNC_EXCLUDE (regex)
SIG_FILE="meta/.sync-state"
VAULT_NAME="${VAULT:t}"

current_sig=$(
  {
    if [[ "$OSTYPE" == darwin* ]]; then
      find raw -type f -name '*.md' -exec stat -f '%N %m' {} + 2>/dev/null
    else
      find raw -type f -name '*.md' -printf '%p %T@\n' 2>/dev/null
    fi
    find "$DEV" -maxdepth 4 -type d -name .git -not -path '*/node_modules/*' 2>/dev/null \
      | sed 's#/\.git$##' | grep -v "^${VAULT}\$" | { [[ -n "$SYNC_EXCLUDE" ]] && grep -vE "$SYNC_EXCLUDE" || cat; } \
      | while read -r r; do echo "$r $(git -C "$r" rev-parse HEAD 2>/dev/null)"; done
  } | sort | shasum | awk '{print $1}'
)
prev_sig=$(cat "$SIG_FILE" 2>/dev/null)
if [[ "$current_sig" == "$prev_sig" && "$1" != "--force" ]]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') no changes (sig ${current_sig:0:12}) - skip" >> meta/sync.log
  exit 0
fi
echo "===== brain-sync $(date '+%Y-%m-%d %H:%M:%S') (sig ${current_sig:0:12}) =====" >> meta/sync.log

read -r -d '' PROMPT <<'PROMPT_EOF'
Scheduled brain sync for this Obsidian second-brain wiki. Obey CLAUDE.md. Be concise; this is unattended.

1. INGEST: For every file under raw/ whose exact full path is NOT already a line in meta/ingested-files.txt (the ground-truth ledger; do NOT grep meta/log.md prose for this, it abbreviates filenames and gives false positives), ingest it per .claude/commands/ingest.md: create a wiki/sources/ digest, create/update entity pages with [[wiki-links]], append a line to meta/log.md, append its full path as a new line to meta/ingested-files.txt, and update the "Recently ingested" list in wiki/index.md. Every file you touch this run, whether it got a new page or was confirmed already covered, gets its full path appended to meta/ingested-files.txt.

2. REFRESH REPOS: For each git repo under __DEV__ EXCEPT "__VAULT_NAME__"__EXCLUDE_NOTE__ (repos may be nested; search up to 4 levels deep, skip node_modules): run `git -C <repo> rev-parse --short HEAD`. If that HEAD differs from the hash in the repo's most recent meta/log.md refresh line (or it has never been refreshed), re-read its high-signal files (README, manifests, structure, `git log --oneline -10`) and create or update wiki/projects/<slug>.md in place, then append a log line like `YYYY-MM-DD - refresh <repo> @<HEAD> -> wiki/projects/<slug>.md`. Never copy source code.

3. LESSONS: Update wiki/lessons.md so agents stop repeating mistakes. (a) In repos refreshed this run, scan `git log --oneline -15` for commits signalling a fixed mistake (revert, rollback, hotfix, `fix:`, "regression"). (b) Scan newly-ingested raw/ captures of kind=feedback or explicit user corrections. For each genuine, generalisable mistake add or update a `### L###` block following the schema at the TOP of wiki/lessons.md. Rules:
   - A NEW lesson takes the next unused L number (check the highest existing id first; ids must be unique) and always gets `- status: proposed` (a human approves it with `brain lessons approve`), `- last_seen: <today>`, and `- summary:` (one self-contained imperative line under 200 characters, starting "When ...").
   - Add `- match:` ONLY when the mistake happens at a recognisable tool call (a command, a file type, a tool), so the lesson can fire just before it. Keep matchers specific: a matcher that would fire on ordinary everyday commands is worse than none. Syntax is in the schema header.
   - Do NOT duplicate a lesson: bump its `hits:` and set `last_seen:` to today instead. If a new lesson replaces an old one, set `- superseded_by: L###` on the old one.
   - Never change the `status:` of an existing lesson. If the same class of mistake appears in 2+ repos, promote `scope:` to `universal`. Keep lessons atomic and few. If nothing qualifies, leave the ledger unchanged.

4. LINT: Run the consistency pass per .claude/commands/lint.md and fix only SAFE issues automatically (missing frontmatter fields, broken [[links]] to a clearly-intended existing page). Do NOT delete pages. If a wiki/projects/ page exceeds ~450 lines, move dated history into that project's wiki/sources/ worklog pages, leaving a short summary + [[link]].

5. COMMIT: If `git status --porcelain` is non-empty, run `git add -A && git commit -m "chore: brain sync $(date +%F)"`. Never push.
PROMPT_EOF
PROMPT="${PROMPT//__DEV__/$DEV}"
PROMPT="${PROMPT//__VAULT_NAME__/$VAULT_NAME}"
PROMPT="${PROMPT//__EXCLUDE_NOTE__/${SYNC_EXCLUDE:+ and any path matching the regex $SYNC_EXCLUDE}}"

"$CLAUDE_BIN" -p "$PROMPT" --permission-mode bypassPermissions --model "${SYNC_MODEL:-sonnet}" >> meta/sync.log 2>&1
rc=$?

python3 meta/render-lessons.py --apply >> meta/sync.log 2>&1

# Advance the signature only on a clean run, so failures retry next time.
[[ $rc -eq 0 ]] && echo "$current_sig" > "$SIG_FILE"
echo "----- done $(date '+%H:%M:%S') rc=$rc -----" >> meta/sync.log
