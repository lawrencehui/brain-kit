#!/usr/bin/env python3
"""PreToolUse hook: inject a lesson right before the tool call it guards.

Reads meta/lessons-manifest.json (compiled by render-lessons.py), matches the
pending tool call against each lesson's `match:` conditions, and returns the
matching lessons as additionalContext. Never blocks or alters the tool call.

Noise control:
  - only lessons scoped to the session's repo (or universal) are considered
  - at most MAX_PER_CALL lessons per call
  - a lesson shown in this session is not shown again for REPEAT_AFTER tool calls
Any error exits 0 silently: a broken hook must never get in the way of work.
"""
import json
import os
import pathlib
import re
import sys
import tempfile

MAX_PER_CALL = 2
REPEAT_AFTER = 40
MANIFEST = pathlib.Path(__file__).resolve().parent / "lessons-manifest.json"


def field_values(tool, inp):
    path = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
    return {
        "tool": tool,
        "cmd": inp.get("command", "") if isinstance(inp.get("command"), str) else "",
        "path": path if isinstance(path, str) else "",
        "text": json.dumps(inp, ensure_ascii=False),
    }


def matches(alts, vals):
    for conds in alts:
        if all(vals[k] and re.search(rx, vals[k], re.I) for k, rx in conds):
            return True
    return False


def in_scope(dirs, cwd):
    for d in dirs:
        d = d.rstrip("/")
        if cwd == d or cwd.startswith(d + "/"):
            return True
    return False


def main():
    event = json.load(sys.stdin)
    manifest = json.loads(MANIFEST.read_text())
    cwd = os.path.realpath(event.get("cwd") or os.getcwd())
    vault = os.path.realpath(manifest.get("vault", ""))
    if cwd == vault or cwd.startswith(vault + "/"):
        return
    vals = field_values(event.get("tool_name", ""), event.get("tool_input") or {})

    sid = re.sub(r"[^A-Za-z0-9_-]", "", event.get("session_id", "nosession"))[:80]
    state_path = pathlib.Path(tempfile.gettempdir()) / f"brain-lessons-{manifest.get('name','brain')}-{sid}.json"
    try:
        state = json.loads(state_path.read_text())
    except Exception:
        state = {"calls": 0, "shown": {}}
    state["calls"] += 1

    hits = []
    for l in manifest.get("lessons", []):
        last = state["shown"].get(l["id"])
        if last is not None and state["calls"] - last < REPEAT_AFTER:
            continue
        if in_scope(l["dirs"], cwd) and matches(l["match"], vals):
            hits.append(l)
            if len(hits) == MAX_PER_CALL:
                break
    for l in hits:
        state["shown"][l["id"]] = state["calls"]
    state_path.write_text(json.dumps(state))
    if not hits:
        return

    parts = [f"Lesson {l['id']} [{l['severity']}] from the brain applies to this {vals['tool']} call: "
             f"{l['summary']}" + (f"\nDetail: {l['rule']}" if l["rule"] and l["rule"] not in l["summary"] else "")
             for l in hits]
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "additionalContext": "\n\n".join(parts)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
