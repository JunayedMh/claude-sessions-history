"""pytest entry point. Run with:  python -m pytest -q

serve.py carries its own zero-dependency check (`python serve.py --selftest`)
so the tool works with nothing installed. This file reuses that check instead
of restating it, and adds the cases it does not cover: a missing or empty
projects folder, stray files, and the shape of the API payload.
"""
import json
import os
import threading
import urllib.request

import pytest

import serve


def test_parser_selftest():
    """serve.py's built-in checks: title chain, subagent exclusion, cache."""
    serve.selftest()


def test_scan_of_missing_directory_is_empty(tmp_path):
    assert serve.scan(os.path.join(str(tmp_path), "does-not-exist")) == []


def test_scan_of_directory_with_no_sessions_is_empty(tmp_path):
    assert serve.scan(str(tmp_path)) == []


def test_scan_ignores_files_that_are_not_transcripts(tmp_path):
    proj = os.path.join(str(tmp_path), "some-project")
    os.makedirs(proj)
    with open(os.path.join(proj, "notes.txt"), "w", encoding="utf-8") as fh:
        fh.write("not a transcript\n")
    assert serve.scan(str(tmp_path)) == []


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A real server on a free port, with the session scan stubbed out."""

    def start(projects_path, sessions):
        monkeypatch.setattr(serve, "PROJECTS", projects_path)
        monkeypatch.setattr(serve, "scan", lambda *a, **k: sessions)
        httpd = serve.Server(("127.0.0.1", 0), serve.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd

    started = []

    def _start(projects_path, sessions):
        httpd = start(projects_path, sessions)
        started.append(httpd)
        port = httpd.server_address[1]
        with urllib.request.urlopen(
            "http://127.0.0.1:%d/api/sessions" % port
        ) as resp:
            return json.load(resp)

    yield _start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def test_api_reports_no_history_when_the_folder_does_not_exist(api, tmp_path):
    """A first-time user: the page needs `exists: false` to say so."""
    payload = api(os.path.join(str(tmp_path), "never-created"), [])
    assert set(payload) == {"root", "exists", "sessions"}
    assert payload["exists"] is False
    assert payload["sessions"] == []


def test_api_reports_an_empty_folder_differently(api, tmp_path):
    """Ran Claude Code, no sessions yet. Must not look like the case above."""
    payload = api(str(tmp_path), [])
    assert payload["exists"] is True
    assert payload["sessions"] == []


def test_api_passes_sessions_through(api, tmp_path):
    row = {"id": "abc", "project": "/x", "title": "t", "mtime": 1.0,
           "cmd": "claude --resume abc"}
    payload = api(str(tmp_path), [row])
    assert payload["sessions"] == [row]
