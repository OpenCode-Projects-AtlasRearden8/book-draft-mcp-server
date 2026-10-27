# STATUS.md — book-draft-mcp-server

Built 2026-10-27 by Asdale Dynamics, LLC.

## What was built

A minimal MCP (Model Context Protocol) server over **stdio**, written with
**Python stdlib only** (no third-party packages), designed for pacing a book
draft:

- **Chapters** with status (`not_started` / `drafting` / `revising` / `final` /
  `backburner`) plus target-vs-actual word counts and progress percent.
- **Sprint log** — dated writing sessions with words, minutes, and a note;
  logging a sprint automatically adds words to that chapter's `actual_words`.
- **Revision-note threads** per chapter — open/resolved status and reply
  threading (`reply_to`).
- **Deadline with gentle nudge math** — days left vs. remaining words, stated as
  a light, non-guilt daily pace (e.g. "155 days left. About 170 words a day...").
- **`smallest_step`** — one concrete, low-energy (ADHD-friendly) suggested
  action per call: an open revision note, or ~300 words on the earliest
  behind-target chapter, etc.
- **JSON storage** — single `data/draft.json`, path-safety validation
  (rejects traversal, slashes, null bytes, non-safe characters), and
  auto-backup of the previous file into `data/backups/` (last 10 kept).
- **Sample draft** included at `data/draft.json` (sample chapters of an
  AI-manual-style book, sprints, and notes).

12 tools: `book_overview`, `list_chapters`, `set_chapter`, `log_sprint`,
`list_sprints`, `count_words`, `add_revision_note`, `list_revision_notes`,
`resolve_revision_note`, `set_deadline`, `deadline_status`, `smallest_step`.

Deliberately distinct from `book-bible-audit-cli`, which is about story
consistency; this server is about **pace** (progress, deadlines, next steps).

## How to run

```bash
python3 -m book_draft_mcp              # stdio JSON-RPC server
python3 -m unittest discover -s tests  # offline unit tests
```

Point it at your own draft with `BOOK_DRAFT_DATA_DIR=<dir>` (defaults to the
repo's `data/`). A full copy-paste smoke test is in `README.md`.

## Verification results

- `python3 -m unittest discover -s tests` — **29 tests, OK** (word-count math,
  deadline/nudge math, book totals, path-safety cases, auto-backup + pruning,
  sprint/revision-note behavior, sample-draft load).
- Smoke test over stdio — verified live:
  - `initialize` → correct `serverInfo` handshake.
  - `tools/list` → all 12 tools advertised.
  - `tools/call` on the sample draft → `smallest_step` suggested applying one
    open revision note on chapter ch02; `deadline_status` reported
    "155 days left. About 170 words a day keeps you on track.".
  - `set_chapter` + `log_sprint` in a scratch data dir persisted correctly to
    JSON; sprint bumped the chapter's `actual_words` and status.
  - Malformed line → `-32700 Parse error`; unknown tool → error, server keeps
    running (loop does not die on bad input).
- Confirmed reads on the sample draft do not create spurious backup files;
  backups only appear on overwrite.

## Known gaps

- No `content reject` / schema validation on JSON-RPC `id` types; the server is
  permissive rather than strict.
- `smallest_step` is heuristic (first-ordered open notes / chapters), not
  learned from sprint history.
- Backups are timestamped to the second, so rapid back-to-back saves can replace
  a backup from the same second; pruning keeps at most 10.
- No concurrency locking (single-writer assumption, fine for a local stdio
  server).
- Markdown/HTML exports and per-chapter notes pages are not included.
- Privacy note: the draft file is local-only, but anything you paste into
  chapters is your responsibility to keep off shared machines.

## License

MIT — Copyright (c) 2026 Asdale Dynamics, LLC. See `LICENSE`. Credited in
`README.md`. Local-first: no secrets, no API keys, no personal data in the repo.
