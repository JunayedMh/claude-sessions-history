# claude-sessions

A local page listing every Claude Code session on this machine, with a
one-click copy of the command to resume it.
Browse every Claude Code session on your machine in a local web page, and copy
the command to resume one with a click.

![claude-sessions](screenshot.png)

Two files, no build step, no dependencies beyond the Python standard library.

```
claude-sessions/
├── serve.py     # reads ~/.claude/projects, serves the page + /api/sessions
└── index.html   # the whole frontend
```

## Run it

```bash
python serve.py              # start + open the browser
python serve.py --no-open    # start only
python serve.py --selftest   # check the parser
```

Then open <http://127.0.0.1:8737/> (it opens on its own).

## Add a `claude-sessions` command

Bash / Linux, appended to `~/.bashrc`:

```bash
alias claude-sessions='python3 ~/claude-sessions/serve.py'
```

PowerShell / Windows, appended to `$PROFILE` (find it with `$PROFILE` in a
prompt; create it with `New-Item -ItemType File -Path $PROFILE -Force`):

```powershell
function claude-sessions { python "$HOME\claude-sessions\serve.py" }
```

Either one starts the server and opens the browser in one word.

## Using the page

- **Filter** matches the title, the project path, and the session ID at once.
  Press `/` to jump to the box, `Esc` to clear it.
- **Copy** puts `claude --resume <session-id>` on the clipboard. The command is
  printed in full on the card too, so you can read or select it by hand.
- **Refresh** re-reads the files. Only sessions whose files changed get
  re-parsed, so this is near-instant.

## What it reads, and what it skips

Sessions come from `~/.claude/projects/<project>/<session-id>.jsonl`.

Only files at that exact depth are read. Subagent transcripts live deeper, at
`<project>/<session-id>/subagents/agent-*.jsonl`, and are skipped on purpose:
they are not resumable, so `claude --resume` fails on them. On this machine
that is 215 real sessions out of 363 total `.jsonl` files.

Each card's title comes from the first of these that exists:

1. the last `ai-title` record (a generated short title)
2. the last `last-prompt` record (what the chat was last about)
3. the first real user message

The project path is the real `cwd` recorded in the transcript, not the folder
name. Folder names encode `C:\Users\Junayed` and `C--Users-Junayed`
identically, so they lose information.

Sessions whose files cannot be read are skipped rather than failing the page.

## Notes

- Binds `127.0.0.1` only, and is read-only: the server never writes to your
  session files and is not reachable from the network.
- If port 8737 is taken it walks upward to the first free one and prints the
  URL it settled on.
- `serve.py --selftest` covers the title fallback chain, the subagent
  exclusion, and the cache. The fixture is written with spaces in the JSON on
  purpose, to catch any parser that depends on exact JSON formatting.
