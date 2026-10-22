#!/usr/bin/env python3
"""The one write path into raw/journal/: used by the `brain` CLI, brain_capture (MCP)
and the auto-capture hook, so redaction and dedup apply to every capture.

  capture.py [--project P] [--kind K] [--from F] [--cwd DIR] [--porcelain] [text...]
  (no text args: read stdin)

1. Redact: values that look like credentials are replaced with [REDACTED:<kind>]
   before anything touches disk; the count is recorded in the frontmatter.
2. Dedup: an identical capture (same project, kind and whitespace-normalised text)
   within DEDUP_WINDOW seconds is skipped. Exit status is 0 either way.
3. Write a timestamped file (never overwrites an existing one).
--porcelain prints only the vault-relative path, or DUPLICATE.
"""
import argparse
import datetime
import getpass
import hashlib
import json
import os
import pathlib
import re
import socket
import sys
import time

VAULT = pathlib.Path(__file__).resolve().parent.parent
JOURNAL = VAULT / "raw" / "journal"
DEDUP_FILE = VAULT / "meta" / ".capture-dedup"
ALIASES = VAULT / "meta" / "project-aliases.json"
DEDUP_WINDOW = 600
KINDS = {"note", "finding", "feedback", "worklog", "idea"}

# (kind, pattern, group to redact or 0 for the whole match)
SECRET_PATTERNS = [
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", 0),
    ("aws-access-key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", 0),
    ("github-token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b", 0),
    ("slack-token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b", 0),
    ("api-key", r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}\b", 0),
    ("google-api-key", r"\bAIza[0-9A-Za-z_-]{35}\b", 0),
    ("stripe-key", r"\b[rsp]k_(?:live|test)_[0-9A-Za-z]{16,}\b", 0),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", 0),
    ("url-password", r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s@/]{3,})@", 1),
    ("assigned-secret",
     r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key)"
     r"\b[\"']?\s*[:=]\s*[\"']?([^\s\"'`,;]{8,})", 1),
]


def redact(text):
    count = 0
    for kind, pat, group in SECRET_PATTERNS:
        def sub(m, kind=kind, group=group):
            nonlocal count
            if group == 0:
                count += 1
                return f"[REDACTED:{kind}]"
            val = m.group(group)
            if val.startswith("[REDACTED"):
                return m.group(0)
            count += 1
            s, e = m.span(group)
            off = m.start()
            return m.group(0)[: s - off] + f"[REDACTED:{kind}]" + m.group(0)[e - off:]
        text = re.sub(pat, sub, text)
    return text, count


def normalise_project(project):
    p = re.sub(r"-+", "-", re.sub(r"[\s_]+", "-", project.strip().lower())).strip("-")
    try:
        p = json.loads(ALIASES.read_text()).get(p, p)
    except Exception:
        pass
    return p


def is_duplicate(key):
    now = time.time()
    try:
        lines = DEDUP_FILE.read_text().splitlines()
    except OSError:
        lines = []
    recent = []
    for line in lines:
        ts, _, h = line.partition(" ")
        try:
            if now - float(ts) < DEDUP_WINDOW:
                recent.append((float(ts), h))
        except ValueError:
            continue
    dup = any(h == key for _, h in recent)
    if not dup:
        recent.append((now, key))
    DEDUP_FILE.write_text("".join(f"{ts:.0f} {h}\n" for ts, h in recent))
    return dup


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--project", "-p", default="")
    ap.add_argument("--kind", "-t", default="note")
    ap.add_argument("--from", dest="source", default=f"{getpass.getuser()}@{socket.gethostname().split('.')[0]}")
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--porcelain", action="store_true")
    ap.add_argument("text", nargs="*")
    a = ap.parse_args()

    text = " ".join(a.text) if a.text else sys.stdin.read()
    if not text.strip():
        print("brain: nothing to save (no text/stdin)", file=sys.stderr)
        return 1
    kind = a.kind if a.kind in KINDS else "note"
    project = normalise_project(a.project) if a.project else ""
    text, redacted = redact(text.strip())

    key = hashlib.sha256(f"{project}\0{kind}\0{' '.join(text.split())}".encode()).hexdigest()
    if is_duplicate(key):
        print("DUPLICATE" if a.porcelain else "🧠 skipped: identical capture saved in the last 10 minutes")
        return 0

    JOURNAL.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    fm = ["---", f"captured: {now:%Y-%m-%d %H:%M:%S}", f"from: {a.source}", f"cwd: {a.cwd}"]
    if project:
        fm.append(f"project: {project}")
    fm += [f"kind: {kind}", "status: unprocessed"]
    if redacted:
        fm.append(f"redacted: {redacted}")
    body = "\n".join(fm + ["---", "", text, ""])
    for n in range(100):
        path = JOURNAL / f"{now:%Y-%m-%d-%H%M%S}-{os.getpid()}{'' if n == 0 else f'-{n}'}.md"
        try:
            with open(path, "x") as f:
                f.write(body)
            break
        except FileExistsError:
            continue
    rel = path.relative_to(VAULT)
    if a.porcelain:
        print(rel)
    else:
        extra = f", {redacted} secret(s) redacted" if redacted else ""
        print(f"🧠 saved ({kind}{' · ' + project if project else ''}{extra}) → {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
