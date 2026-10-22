#!/usr/bin/env python3
"""Extract a compact handoff digest from a Claude Code session transcript."""
import json, sys, os

def texts(content):
    out = []
    if isinstance(content, str):
        out.append(content)
    elif isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(b.get("text",""))
    return out

def digest(path, out_path):
    cwd = model = None
    first_user = None
    last_summary = None
    last_todos = None
    user_msgs, asst_msgs = [], []
    last_ts = None
    n = 0
    with open(path, errors="replace") as fh:
        for line in fh:
            try: rec = json.loads(line)
            except: continue
            t = rec.get("type")
            if t == "summary":
                last_summary = rec.get("summary")
                continue
            if rec.get("isSidechain"): continue
            if t not in ("user","assistant"): continue
            n += 1
            cwd = rec.get("cwd") or cwd
            last_ts = rec.get("timestamp") or last_ts
            msg = rec.get("message") or {}
            if t == "assistant":
                model = msg.get("model") or model
                for b in (msg.get("content") or []):
                    if isinstance(b, dict) and b.get("type")=="tool_use" and b.get("name")=="TodoWrite":
                        last_todos = b.get("input",{}).get("todos")
                tx = " ".join(texts(msg.get("content")))
                if tx.strip():
                    asst_msgs.append((rec.get("timestamp",""), tx.strip()))
            else:
                c = msg.get("content")
                # skip tool_result-only user records
                if isinstance(c, list) and all(isinstance(b,dict) and b.get("type")=="tool_result" for b in c):
                    continue
                tx = " ".join(texts(c))
                if tx.strip() and not tx.startswith("<") and "command-name" not in tx:
                    if first_user is None: first_user = tx.strip()
                    user_msgs.append((rec.get("timestamp",""), tx.strip()))

    def clip(s, k=400): return s[:k] + ("…" if len(s)>k else "")
    # The session's conclusion is the highest-value payload of a handoff: the
    # closing recommendation or decision usually lives in the last assistant
    # message and tends to be the longest, most structured one (tables, code,
    # numbered next steps). A tight per-message clip destroys exactly that. So
    # the final exchange is emitted VERBATIM (up to VERBATIM chars) in a section
    # placed HIGH in the digest, above the clipped chronological logs. Placement
    # matters: the brain worklog path only ingests `head -c 16000` of this file,
    # so a full final message at the bottom would just be re-truncated there.
    # VERBATIM=4000 covers a detailed closing message with headroom; the whole
    # verbatim block (last user + last 2 assistant) stays bounded well under 16k
    # even in the worst case, so it survives the 16k brain cut.
    VERBATIM = 4000
    with open(out_path, "w") as o:
        o.write(f"# {os.path.basename(path)}\ncwd: {cwd}\nmodel: {model}\nrecords: {n}\nlast_activity: {last_ts}\n\n")
        if first_user: o.write(f"## First user message (task)\n{clip(first_user,600)}\n\n")
        if last_summary: o.write(f"## Latest compaction summary\n{clip(last_summary,1500)}\n\n")
        if last_todos:
            o.write("## Last todo list\n")
            for td in last_todos:
                o.write(f"- [{td.get('status','?')}] {td.get('content','')}\n")
            o.write("\n")

        # Final exchange, verbatim. Last user message for what was asked, then
        # the last two assistant replies for what was concluded (kept in order).
        tail = []
        if user_msgs: tail.append(("user", user_msgs[-1]))
        for m in asst_msgs[-2:]: tail.append(("assistant", m))
        if tail:
            o.write("## Session conclusion (final exchange, verbatim)\n")
            for role, (ts, m) in tail:
                o.write(f"### {role} ({ts[5:16]})\n{clip(m, VERBATIM)}\n\n")

        o.write("## Last 12 user messages\n")
        for ts, m in user_msgs[-12:]:
            o.write(f"- ({ts[5:16]}) {clip(m,400)}\n")
        o.write("\n## Last 8 assistant replies\n")
        for ts, m in asst_msgs[-8:]:
            o.write(f"- ({ts[5:16]}) {clip(m,900)}\n")

if __name__ == "__main__":
    digest(sys.argv[1], sys.argv[2])
    print("ok", sys.argv[2])
