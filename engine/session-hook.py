#!/usr/bin/env python3
"""SessionStart hook: load this repo's brain page into the session automatically.

Agents are told to call brain_context at the start of work, and often don't. This
hook does it for them: it finds the wiki/projects/ page for the current repo and
injects it (capped at session_context_chars), plus a one-line note when lessons are
waiting for approval. Skips resumed sessions (their context is already loaded) and
sessions inside the vault itself. Any error exits 0 silently.

Page lookup: wiki/projects/<repo-dir-name>.md (kebab-cased), else the project page
that mentions the repo's absolute path (refresh pages record the on-disk path).
"""
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


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
    needle = str(root)
    best = None
    for f in sorted(projects.glob("*.md")):
        try:
            t = f.read_text(errors="replace")
        except OSError:
            continue
        # prefer the page whose recorded path is exactly this repo, not a parent folder of it
        for m in re.finditer(re.escape(needle) + r"(/[^\s`)]*)?", t):
            if not m.group(1):
                return f
            best = best or f
    return best


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

    root = repo_root(cwd)
    page = find_page(L.VAULT, root) if root else None
    if page:
        text = page.read_text(errors="replace")
        cap = routing["session_context_chars"]
        rel = page.relative_to(L.VAULT)
        if len(text) > cap:
            heads = [h for h in re.findall(r"^#{1,3} .+$", text, re.M)]
            text = (text[:cap] + f"\n…[truncated at {cap} chars. Sections: " + " | ".join(h.lstrip("# ") for h in heads[:30])
                    + f'. Use brain_read("{rel}", heading) for any section.]')
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
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n\n".join(out)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
