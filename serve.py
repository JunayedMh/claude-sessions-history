#!/usr/bin/env python3
"""Browse and resume local Claude Code sessions.

Serves one page (index.html) plus GET /api/sessions, reading the JSONL
transcripts under ~/.claude/projects. Stdlib only, read-only, localhost only.

    python serve.py            # start + open browser
    python serve.py --no-open  # start only
    python serve.py --selftest # check the parser
"""
import glob
import json
import os
import sys
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8737
MAX_TITLE = 120

_CACHE = {}  # path -> ((mtime, size), record); avoids re-parsing on refresh


def _load(line):
    try:
        return json.loads(line)
    except ValueError:
        return {}


def _text(content):
    """Plain text out of a message content field (a string or a block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _read(path):
    """Parse one transcript into a session record, or None if unreadable.

    Subagent transcripts are never passed here: they live at
    <project>/<session>/subagents/agent-*.jsonl and are not resumable.
    """
    sid = os.path.basename(path)[:-6]
    cwd = first = ai_title = last_prompt = None

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                # Assistant turns are the bulk of the file. Matching the value
                # token (not an exact `"type":"assistant"` spelling) keeps this
                # fast and immune to how the JSON happens to be spaced.
                if '"assistant"' in line:
                    continue
                d = _load(line)
                t = d.get("type")
                if t == "ai-title":
                    ai_title = d.get("aiTitle") or ai_title
                elif t == "last-prompt":
                    last_prompt = d.get("lastPrompt") or last_prompt
                elif first is None and t == "user" and not d.get("isSidechain"):
                    txt = _text((d.get("message") or {}).get("content"))
                    # skip command wrappers / hook noise
                    if txt.strip() and not txt.lstrip().startswith("<"):
                        first = txt
                if cwd is None and d.get("cwd"):
                    cwd = d["cwd"]
    except OSError:
        return None

    title = " ".join(str(ai_title or last_prompt or first or "").split())
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE] + "\u2026"

    return {
        "id": sid,
        "project": cwd or os.path.basename(os.path.dirname(path)),
        "title": title or "(untitled)",
        "mtime": os.path.getmtime(path),
        "cmd": "claude --resume " + sid,
    }


def scan(root=PROJECTS):
    """One record per real session, newest first."""
    out = []
    for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
        try:
            st = os.stat(path)
            key = (st.st_mtime, st.st_size)
        except OSError:
            continue

        cached = _CACHE.get(path)
        if cached and cached[0] == key:
            rec = cached[1]
        else:
            rec = _read(path)
            _CACHE[path] = (key, rec)
        if rec:
            out.append(rec)

    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def do_GET(self):
        if self.path.split("?")[0] != "/api/sessions":
            return super().do_GET()  # index.html, favicon, ...
        body = json.dumps(
            {
                "root": PROJECTS,
                "exists": os.path.isdir(PROJECTS),
                "sessions": scan(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass  # keep the terminal clean


class Server(HTTPServer):
    # On Windows, SO_REUSEADDR lets two processes listen on the same port, so a
    # stale server silently keeps answering with old data instead of failing.
    # POSIX needs it on for fast restarts, where it cannot double-bind.
    allow_reuse_address = os.name != "nt"


def serve(open_browser=True):
    port = PORT
    for _ in range(20):  # ponytail: linear probe, fine for a localhost tool
        try:
            httpd = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            port += 1
    else:
        sys.exit("no free port near %d" % PORT)

    url = "http://127.0.0.1:%d/" % port
    print(
        "claude-sessions -> %s\nreading %s\nCtrl+C to stop" % (url, PROJECTS),
        flush=True,
    )
    if open_browser:
        threading.Timer(0.4, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def selftest():
    """Title fallback chain, subagent exclusion, cache, JSON-spacing immunity.

    The fixture is written with json.dumps defaults (spaces after colons) on
    purpose: real transcripts are compact, so this also proves the parser does
    not depend on how the JSON happens to be spaced.
    """
    import shutil
    import tempfile
    import time

    tmp = tempfile.mkdtemp()
    try:
        proj = os.path.join(tmp, "C--Users-x")
        os.makedirs(os.path.join(proj, "abc", "subagents"))
        now = time.time()

        def w(p, rows):
            with open(p, "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
            os.utime(p, (now, now))

        w(os.path.join(proj, "abc.jsonl"), [
            {"type": "user", "cwd": "C:\\Users\\x", "message": {"content": "hi"}},
            {"type": "user", "message": {"content": [{"type": "tool_result"}]}},
            {"type": "assistant", "message": {"content": "ignored"}},
            {"type": "ai-title", "aiTitle": "  My   Title "},
            {"type": "ai-title", "aiTitle": "Final Title"},  # last one wins
            {"type": "last-prompt", "lastPrompt": "later"},
        ])
        w(os.path.join(proj, "noTitle.jsonl"), [
            {"type": "user", "cwd": "D:\\y", "message": {"content": "<command-name>x"}},
            {"type": "user", "message": {"content": "  the  first ask "}},
        ])
        w(os.path.join(proj, "abc", "subagents", "agent-1.jsonl"),
          [{"type": "user", "cwd": "Z:\\", "message": {"content": "sub"}}])

        got = scan(tmp)
        sid = {s["id"]: s for s in got}
        assert len(got) == 2, got                       # subagent file excluded
        assert sid["abc"]["title"] == "Final Title", sid["abc"]
        assert sid["abc"]["cmd"] == "claude --resume abc"
        assert sid["abc"]["project"] == "C:\\Users\\x"
        # wrapper skipped, falls back to first real user message, collapsed
        assert sid["noTitle"]["title"] == "the first ask", sid["noTitle"]
        assert sid["noTitle"]["project"] == "D:\\y"
        assert "noTitle" not in [s["id"] for s in scan(tmp) if s["title"] == "Final Title"]
        assert got == sorted(got, key=lambda s: s["mtime"], reverse=True)

        # second pass is served from the cache and must be identical
        _CACHE.clear()
        first_pass = scan(tmp)
        assert _CACHE and scan(tmp) == first_pass

        # a second server must not be able to share the port (see Server).
        # Only meaningful on Windows; POSIX allows the double bind by design.
        if os.name == "nt":
            a = Server(("127.0.0.1", 0), Handler)
            try:
                Server(("127.0.0.1", a.server_address[1]), Handler).server_close()
                raise AssertionError("two servers bound the same port")
            except OSError:
                pass
            finally:
                a.server_close()

        print("selftest ok (%d fixture sessions)" % len(got))
    finally:
        _CACHE.clear()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        serve(open_browser="--no-open" not in sys.argv)
