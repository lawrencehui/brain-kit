"""Shared parsing and routing for the lessons ledger (wiki/lessons.md).

Used by render-lessons.py, lessons.py and the hooks, so there is exactly one
definition of what a lesson is, whether it is live, and where it applies.

Ledger format: one `### L### — title` block per lesson, with `- key: value` field lines.
Fields: scope, trigger, mistake, rule, severity, hits, source, plus the optional
  status         proposed | active | retired   (missing = active, for older ledgers)
  summary        one-line, self-contained rule used in CLAUDE.md blocks
  match          tool-call matchers for just-in-time injection (see parse_match)
  last_seen      YYYY-MM-DD the mistake was last observed
  superseded_by  L### that replaces this lesson
  graduated      the lesson became a hook/lint/test; never injected
"""
import datetime
import json
import os
import pathlib
import re

VAULT = pathlib.Path(__file__).resolve().parent.parent
LESSONS = VAULT / "wiki" / "lessons.md"
ROUTING_PATH = VAULT / "meta" / "lessons-routing.json"
MANIFEST = VAULT / "meta" / "lessons-manifest.json"

SEV_ALIASES = {"medium": "med"}
SEV_ORDER = {"high": 0, "med": 1, "low": 2}
HEADER_RE = re.compile(r"^### (L\d+)\b.*$", re.M)
FIELD_RE = re.compile(r"^- (\w+):[ \t]*(.*)$", re.M)


def load_env():
    out = {}
    p = VAULT / "meta" / "brain.env"
    if p.exists():
        for line in p.read_text().splitlines():
            m = re.match(r"^\s*([A-Z_]+)=(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


ENV = load_env()
DEV = pathlib.Path(ENV.get("DEV", str(pathlib.Path.home() / "Dev"))).expanduser()
NAME = ENV.get("BRAIN_NAME", "brain")


def load_routing():
    r = json.loads(ROUTING_PATH.read_text()) if ROUTING_PATH.exists() else {}
    return {
        "inject_severities": set(r.get("inject_severities", ["high"])),
        "jit_severities": set(r.get("jit_severities", ["high", "med"])),
        "inject_token_budget": int(r.get("inject_token_budget", 2000)),
        "stale_days": int(r.get("stale_days", 180)),
        "repo_stacks": {k: set(v) for k, v in r.get("repo_stacks", {}).items()},
        "project_to_repos": r.get("project_to_repos", {}),
        "legacy_markers": r.get("legacy_markers", []),
        "session_context_chars": int(r.get("session_context_chars", 6000)),
    }


def parse(text):
    """Return a list of lesson dicts, each with `id`, `title`, `start`, `end` (char offsets) and fields."""
    heads = list(HEADER_RE.finditer(text))
    lessons = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end]
        d = {m.group(1): m.group(2).strip() for m in FIELD_RE.finditer(body)}
        d["id"] = h.group(1)
        d["title"] = h.group(0)[4:].strip()
        d["start"], d["end"] = h.start(), end
        sev = d.get("severity", "low").strip().lower()
        d["severity"] = SEV_ALIASES.get(sev, sev)
        d["status"] = d.get("status", "active").strip().lower() or "active"
        lessons.append(d)
    return lessons


def is_stale(lesson, stale_days, today=None):
    ls = lesson.get("last_seen", "").strip()
    if not ls:
        return False  # never recorded: treat as current rather than silently dropping old ledgers
    try:
        seen = datetime.date.fromisoformat(ls[:10])
    except ValueError:
        return False
    return ((today or datetime.date.today()) - seen).days > stale_days


def live(lesson, routing, today=None):
    """Whether a lesson may be injected anywhere at all."""
    return (lesson["status"] == "active"
            and not lesson.get("graduated")
            and not lesson.get("superseded_by")
            and not is_stale(lesson, routing["stale_days"], today))


def target_repos(lesson, routing):
    """Repo directories a lesson applies to; [DEV] for universal; [] if unrouted."""
    scope = lesson.get("scope", "").strip()
    if scope == "universal":
        return [DEV]
    if scope.startswith("stack:"):
        stack = scope[len("stack:"):]
        return [DEV / r for r, s in routing["repo_stacks"].items() if stack in s]
    if scope.startswith("repo:"):
        return [DEV / scope[len("repo:"):]]
    if scope.startswith("project:"):
        slug = scope[len("project:"):]
        if slug in routing["project_to_repos"]:
            return [DEV / r for r in routing["project_to_repos"][slug]]
        return [DEV / slug] if (DEV / slug / ".git").exists() else []
    return []


def parse_match(spec):
    """`match:` syntax: alternatives joined by ' || ', each a set of conditions joined by ' && ',
    each condition `kind:regex` with kind in tool|cmd|path|text. Case-insensitive.
      tool  the tool name (Bash, Edit, Write, mcp__...)
      cmd   a Bash command
      path  file_path / path / notebook_path of the tool input
      text  the whole tool input serialised as JSON
    Example: `cmd:git\\s+filter-repo || tool:^(Write|Edit)$ && path:\\.sql$`
    Returns [[(kind, regex_str), ...], ...]; raises ValueError on bad syntax, a bad regex, or a
    regex that matches the empty string."""
    # Split only where the next token is a condition prefix, so `cmd:a|| cmd:b` (no space before
    # ||) splits correctly and a regex's own `|` alternation is never mistaken for a separator.
    alts = []
    for alt in re.split(r"\s*\|\|\s*(?=(?:tool|cmd|path|text):)", spec.strip()):
        conds = []
        for cond in re.split(r"\s*&&\s*(?=(?:tool|cmd|path|text):)", alt.strip()):
            kind, sep, rx = cond.strip().partition(":")
            rx = rx.strip()
            if not sep or kind not in ("tool", "cmd", "path", "text") or not rx:
                raise ValueError(f"bad matcher condition: {cond!r}")
            re.compile(rx, re.I)
            conds.append((kind, rx))
        # An alternative whose every condition matches the empty string matches every call
        # (e.g. `cmd:a|` or `text:.*`); refuse it. A lone negative lookahead is fine when
        # another condition in the same alternative does the narrowing.
        if all(re.search(rx, "", re.I) for _, rx in conds):
            raise ValueError(f"matcher matches everything: {alt.strip()!r}")
        alts.append(conds)
    return alts


def one_line(lesson, limit=320):
    """Compact, self-contained rule line for a CLAUDE.md block."""
    s = lesson.get("summary", "").strip()
    if not s:
        trig = re.sub(r"^[Ww]hen\s+", "", lesson.get("trigger", "").strip()).rstrip(".")
        s = f"When {trig}: {lesson.get('rule', '').strip().rstrip('.')}."
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def rank_key(lesson):
    try:
        hits = int(re.sub(r"\D", "", lesson.get("hits", "1")) or 1)
    except ValueError:
        hits = 1
    return (SEV_ORDER.get(lesson["severity"], 3), -hits,
            "".join(chr(255 - ord(c)) for c in lesson.get("last_seen", "")), lesson["id"])


def set_field(text, lesson, key, value):
    """Return ledger text with `- key: value` set on one lesson (replaced, or appended after its last field)."""
    block = text[lesson["start"]:lesson["end"]]
    line = f"- {key}: {value}"
    pat = re.compile(rf"^- {re.escape(key)}:.*$", re.M)
    if pat.search(block):
        block = pat.sub(lambda _: line, block, count=1)
    else:
        fields = list(FIELD_RE.finditer(block))
        at = fields[-1].end() if fields else block.find("\n") + 1
        block = block[:at] + "\n" + line + block[at:]
    return text[:lesson["start"]] + block + text[lesson["end"]:]
