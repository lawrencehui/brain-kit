#!/usr/bin/env python3
"""`brain lessons ...`: review and manage the lessons ledger.

  list [--proposed|--active|--retired|--all]   (default: proposed, then a count of the rest)
  show L012
  approve L073 [L074 ...]                       proposed -> active
  retire L012 [--superseded-by L080]            active -> retired (kept in the ledger, never injected)
  render                                        re-render CLAUDE.md blocks and the hook manifest

approve and retire re-render immediately, so the change reaches the next session.
"""
import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lessonlib as L  # noqa: E402


def render():
    subprocess.run([sys.executable, str(L.VAULT / "meta" / "render-lessons.py"), "--apply"], check=False)


def find(lessons, ids):
    by_id = {l["id"]: l for l in lessons}
    missing = [i for i in ids if i.upper() not in by_id]
    if missing:
        sys.exit(f"no such lesson: {', '.join(missing)}")
    return [by_id[i.upper()] for i in ids]


def update(ids, changes):
    """Apply field changes to each lesson, re-parsing between edits so offsets stay correct."""
    text = L.LESSONS.read_text()
    for i in ids:
        for key, value in changes(i):
            lesson = next(l for l in L.parse(text) if l["id"] == i)
            text = L.set_field(text, lesson, key, value)
    L.LESSONS.write_text(text)


def main():
    ap = argparse.ArgumentParser(prog="brain lessons")
    sub = ap.add_subparsers(dest="cmd")
    ls = sub.add_parser("list")
    g = ls.add_mutually_exclusive_group()
    for s in ("proposed", "active", "retired", "all"):
        g.add_argument(f"--{s}", action="store_const", const=s, dest="which")
    sub.add_parser("show").add_argument("id")
    sub.add_parser("approve").add_argument("ids", nargs="+")
    rt = sub.add_parser("retire")
    rt.add_argument("ids", nargs="+")
    rt.add_argument("--superseded-by", dest="by")
    sub.add_parser("render")
    a = ap.parse_args()

    lessons = L.parse(L.LESSONS.read_text())
    routing = L.load_routing()

    if a.cmd in (None, "list"):
        which = getattr(a, "which", None) or "proposed"
        if which == "active":
            rows = [l for l in lessons if L.live(l, routing)]
        elif which == "retired":
            rows = [l for l in lessons if l["status"] == "retired" or l.get("superseded_by")]
        elif which == "all":
            rows = lessons
        else:
            rows = [l for l in lessons if l["status"] == "proposed"]
        for l in rows:
            jit = " [jit]" if l.get("match") else ""
            print(f"{l['id']:6} {l['status']:9} {l['severity']:4} {l.get('scope', '?')[:28]:28}{jit} {L.one_line(l, 110)}")
        if which == "proposed":
            print(f"\n{len(rows)} proposed · {sum(L.live(l, routing) for l in lessons)} live · {len(lessons)} total. "
                  "Approve with: brain lessons approve L### ...")
        return 0

    if a.cmd == "show":
        l = find(lessons, [a.id])[0]
        print(L.LESSONS.read_text()[l["start"]:l["end"]].rstrip())
        return 0

    if a.cmd == "approve":
        targets = find(lessons, a.ids)
        not_proposed = [l["id"] for l in targets if l["status"] == "active"]
        if not_proposed:
            print(f"already active: {', '.join(not_proposed)}")
        update([l["id"] for l in targets], lambda i: [("status", "active")])
        print(f"approved: {', '.join(l['id'] for l in targets)}")
        render()
        return 0

    if a.cmd == "retire":
        targets = find(lessons, a.ids)
        if a.by:
            find(lessons, [a.by])
        update([l["id"] for l in targets],
               lambda i: [("status", "retired")] + ([("superseded_by", a.by.upper())] if a.by else []))
        print(f"retired: {', '.join(l['id'] for l in targets)}")
        render()
        return 0

    if a.cmd == "render":
        render()
        return 0


if __name__ == "__main__":
    sys.exit(main())
