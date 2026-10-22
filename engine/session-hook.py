#!/usr/bin/env python3
"""SessionStart hook: load this repo's brain page into the session automatically.

Agents are told to call brain_context at the start of work, and often don't. This
hook does it for them: it finds the wiki/projects/ page for the current repo and
injects it (capped at session_context_chars), plus a one-line note when lessons are
waiting for approval. Skips resumed sessions (their context is already loaded) and
sessions inside the vault itself. Any error exits 0 silently.

Page lookup, for the git root (or the folder itself when it is not a repo, e.g. an umbrella
folder): wiki/projects/<dir-name>.md (kebab-cased), else the project page that records exactly
that absolute path (refresh pages record the on-disk path). Only folders under DEV are looked up.
"""
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Claude Code drops SessionStart context somewhere between 9,500 and 12,000 characters
# (measured 2026-10-23: a 9,500-char payload arrived, a 12,000-char one did not). Stay under.
MAX_INJECT = 9000


def repo_root(cwd):
    p = pathlib.Path(cwd)
    for d in [p, *p.parents]:
        if (d / ".git").exists():
            return d
    return None


def find_page(vault, root):
    projects = vault / "wiki" / "projects"
    slug = re.sub(r"-+", "-", re.sub(r"[\s_]+", "-", root.name.lower())).strip("-")
    direct = projects / f"{slug}.md"
    if direct.exists():
        return direct
    # Otherwise the page that records exactly this path (a mention of a sub-path is a page about
    # something else inside it, so it does not count).
    exact = re.compile(re.escape(str(root)) + r"(?![\w./-])")
    for f in sorted(projects.glob("*.md")):
        try:
            if exact.search(f.read_text(errors="replace")):
                return f
        except OSError:
            continue
    return None


def main():
    event = json.load(sys.stdin)
    if event.get("source") == "resume":
        return
    import lessonlib as L

    cwd = os.path.realpath(event.get("cwd") or os.getcwd())
    vault = os.path.realpath(L.VAULT)
    if cwd == vault or cwd.startswith(vault + "/"):
        return
    routing = L.load_routing()
    out = []

    # The git root, or the folder itself for umbrella folders that hold several repos. Never
    # the DEV folder or anything above it: that would match whichever page mentions it first.
    root = repo_root(cwd) or pathlib.Path(cwd)
    dev = os.path.realpath(L.DEV)
    # No page for this repo: fall back to the nearest parent folder under DEV that has one
    # (a repo inside an umbrella folder gets the umbrella's page).
    page = None
    d = root
    while str(d).startswith(dev + "/") and page is None:
        page = find_page(L.VAULT, d)
        d = d.parent
    if page:
        text = page.read_text(errors="replace")
        # Drop YAML frontmatter: on big pages the `sources:` list alone can fill the whole budget.
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                text = text[end + 4:].lstrip("\n")
        cap = min(routing["session_context_chars"], MAX_INJECT - 1500)
        rel = page.relative_to(L.VAULT)
        if len(text) > cap:
            heads = [h.lstrip("# ") for h in re.findall(r"^#{1,3} .+$", text, re.M)]
            index = ""
            for h in heads:  # as many section names as fit in a fixed allowance
                if len(index) + len(h) + 3 > 900:
                    index += " | …"
                    break
                index += (" | " if index else "") + h
            text = (text[:cap] + f"\n…[page truncated at {cap} chars. Sections: {index}. "
                    f'Use brain_read("{rel}", heading) for any section.]')
        slug = page.stem
        out.append(f"Brain context for this repo, loaded automatically from {L.NAME} ({rel}). "
                   f'For recent worklogs and scoped lessons call brain_context("{slug}").\n\n{text}')

    try:
        proposed = json.loads(L.MANIFEST.read_text()).get("proposed", [])
    except Exception:
        proposed = []
    # Mention pending lessons at most once a day, so it is a nudge rather than noise in every session.
    stamp = L.VAULT / "meta" / ".proposed-notified"
    import datetime
    today = datetime.date.today().isoformat()
    already = stamp.exists() and stamp.read_text().strip() == today
    if proposed and not already:
        stamp.write_text(today)
        out.append(f"Note for the user: {len(proposed)} brain lesson(s) are proposed and not active yet "
                   f"({', '.join(proposed[:8])}{'…' if len(proposed) > 8 else ''}). Review with `brain lessons list --proposed`.")
    if out:
        ctx = "\n\n".join(out)[:MAX_INJECT]
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": ctx}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
