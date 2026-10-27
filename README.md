# book-draft-mcp-server

A small, local-first **MCP server** (Python stdlib only) for pacing a book draft:
chapters with status and target-vs-actual word counts, a session log of writing
sprints, revision-note threads per chapter, deadline dates with gentle nudge
math, and a **today's-smallest-step** suggestion on every call.

Built by [Asdale Dynamics, LLC](https://dylanasdale.github.io) to keep writing
momentum humane — one small step at a time. Distinct from
`book-bible-audit-cli` (story consistency); this tool is about *pace*, not plot.

## What it tracks

- **Chapters** — status (`not_started`, `drafting`, `revising`, `final`, `backburner`),
  target vs. actual word counts, and progress percent.
- **Sprints** — a dated log of writing sessions (words, minutes, note). Logging a
  sprint automatically bumps the chapter's `actual_words`.
- **Revision notes** — open/resolved notes per chapter, with reply threading
  (`reply_to`) so a discussion stays in one thread.
- **Deadline** — an ISO date on the book; the server does the gentle nudge math:
  days left vs. remaining words ("About 273 words a day keeps you on track.").
- **Smallest step** — `smallest_step` picks one concrete, doable action each call.

## Storage

- One JSON file (`data/draft.json`) on disk — local-first, no network, no secrets.
- **Path safety**: filenames are validated (letters, digits, `.`, `_`, `-` only;
  no `/`, `\`, null bytes, `..`) and resolved inside the data directory, so
  traversal and shell tricks are refused.
- **Auto-backup**: every save first copies the previous file to
  `data/backups/draft-YYYYmmdd-HHMMSS.json`, keeping the last 10.
- Point the server at your own data with `BOOK_DRAFT_DATA_DIR=<dir>`.

## Tools

`book_overview`, `list_chapters`, `set_chapter`, `log_sprint`, `list_sprints`,
`count_words`, `add_revision_note`, `list_revision_notes`,
`resolve_revision_note`, `set_deadline`, `deadline_status`, `smallest_step`.

## Smoke-test guide (README quickstart)

Requires Python 3.10+. Run the server over stdio from the folder:

```bash
python3 -m book_draft_mcp
```

Then send one JSON-RPC message per line on stdin. A copy-paste smoke test
(works in a bash terminal — the server answers on stdout, then exits on EOF):

```bash
printf '%s\n%s\n%s\n%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"smallest_step","arguments":{}}}' \
 | python3 -m book_draft_mcp
```

Expected: an `initialize` reply (serverInfo `book-draft-mcp`), a `tools/list`
reply naming all 12 tools, and a `tools/call` reply whose `content[0].text`
contains a one-step suggestion with a minutes estimate.

Use it in your own draft data:

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"set_chapter","arguments":{"id":"ch01","title":"What AI Actually Is","target_words":6000}}}' \
 | BOOK_DRAFT_DATA_DIR=mydata python3 -m book_draft_mcp
```

To wire it into an MCP client, add a stdio server entry pointing at
`python3 -m book_draft_mcp` with the repo folder as its working directory.

## Tests

Offline unit tests only (no network, no personal data):

```bash
python3 -m unittest discover -s tests
```

Covers word-count math, deadline/nudge math, book totals, the stdio protocol,
path-safety cases (traversal, slashes, null bytes, dot components), auto-backup,
and sprint/revision-note behavior.

## Repository layout

```
book_draft_mcp/   server package (core logic, storage, stdio server)
data/             sample draft (data/draft.json) + auto-backups/
tests/            offline unit tests
```

MIT License — Copyright (c) 2026 Asdale Dynamics, LLC.
