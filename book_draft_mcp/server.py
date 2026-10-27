"""Minimal MCP (Model Context Protocol) server over stdio, Python stdlib only."""
import copy
import json
import os
import sys
import traceback
from datetime import date

from . import storage
from . import core

SERVER_NAME = "book-draft-mcp"
SERVER_VERSION = "1.0.0"

TOOL_DEFS = [
    {
        "name": "book_overview",
        "description": "Overview of the book draft: totals, chapter list, deadline status.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_chapters",
        "description": "List all chapters with status and target-vs-actual word counts.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_chapter",
        "description": "Create or update a chapter (id, title, status, target_words, actual_words).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Short slug, e.g. ch01"},
                "title": {"type": "string"},
                "status": {"type": "string", "enum": list(core.STATUSES)},
                "target_words": {"type": "integer", "minimum": 0},
                "actual_words": {"type": "integer", "minimum": 0},
                "position": {"type": "integer"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "log_sprint",
        "description": "Record a writing sprint: chapter, date, words_written, minutes, note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chapter": {"type": "string", "description": "Chapter id"},
                "date": {"type": "string", "description": "ISO date, defaults to today"},
                "words_written": {"type": "integer", "minimum": 0},
                "minutes": {"type": "integer", "minimum": 0},
                "note": {"type": "string"},
            },
            "required": ["chapter", "words_written"],
        },
    },
    {
        "name": "list_sprints",
        "description": "List writing sprints, newest first.",
        "inputSchema": {
            "type": "object",
            "properties": {"chapter": {"type": "string"}, "limit": {"type": "integer"}}
        },
    },
    {
        "name": "count_words",
        "description": "Word-count a passage of text (utility for planning).",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}}, "required": ["text"],
        },
    },
    {
        "name": "add_revision_note",
        "description": "Add an open revision note attached to a chapter; reply threading via reply_to.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chapter": {"type": "string"},
                "note": {"type": "string"},
                "reply_to": {"type": "integer", "description": "Note id this replies to (optional)"},
            },
            "required": ["chapter", "note"],
        },
    },
    {
        "name": "list_revision_notes",
        "description": "List revision-note threads for a chapter (or all chapters).",
        "inputSchema": {
            "type": "object",
            "properties": {"chapter": {"type": "string"}, "status": {"type": "string", "enum": ["open", "resolved"]}}
        },
    },
    {
        "name": "resolve_revision_note",
        "description": "Mark a revision note resolved (or reopen it).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "reopened": {"type": "boolean", "default": False}},
            "required": ["id"],
        },
    },
    {
        "name": "set_deadline",
        "description": "Set or clear the manuscript deadline (ISO date).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deadline": {"type": "string", "description": "ISO date, or empty string to clear"},
            },
            "required": [],
        },
    },
    {
        "name": "deadline_status",
        "description": "Days left vs remaining words, with gentle nudge math.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "smallest_step",
        "description": "Today's smallest-step suggestion (one concrete, doable action).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


class DraftStore:
    def __init__(self, data_dir=None, today=None):
        self.data_dir = data_dir
        self.today = today
        self._draft = None

    def draft(self):
        if self._draft is None:
            raw = storage.load(self.data_dir)
            if raw is None:
                raw = copy.deepcopy(core.NEW_DRAFT)
            self._draft, errs = core.ensure_draft(raw)
            self._draft["_errors"] = errs
        return self._draft

    def commit(self):
        path = storage.save(self.draft(), self.data_dir)
        return {"saved": path}

    def refresh(self):
        self._draft = None
        return self.draft()


class Handlers:
    def __init__(self, store, today=None):
        self.store = store
        self.today = today or date.today()

    def _chapter_list(self):
        return [ {k: c.get(k) for k in
                  ("id", "title", "status", "target_words", "actual_words", "position", "progress")}
                 for c in self.store.draft()["chapters"] ]

    def h_book_overview(self, _args):
        d = self.store.draft()
        return {
            "book": d["book"],
            "totals": core.book_totals(d),
            "deadline": core.deadline_status(d, self.today),
            "chapters": self._chapter_list(),
            "open_revision_notes": sum(1 for n in d["revision_notes"] if n.get("status") == "open"),
            "sprints_logged": len(d["sprints"]),
        }

    def h_list_chapters(self, _args):
        d = self.store.draft()
        return {"totals": core.book_totals(d), "chapters": self._chapter_list()}

    def h_set_chapter(self, args):
        d = self.store.draft()
        cid = str(args.get("id", "")).strip()
        if not cid:
            raise ValueError("Chapter id is required.")
        ch = core.find_chapter(d, cid)
        status = args.get("status")
        if status and status not in core.STATUSES:
            raise ValueError("status must be one of %s" % (core.STATUSES,))
        if ch is None:
            ch = {
                "id": cid,
                "title": cid,
                "status": "not_started",
                "target_words": 0,
                "actual_words": 0,
                "position": len(d["chapters"]) + 1,
            }
            d["chapters"].append(ch)
        for key, cast in (("title", str), ("status", str),
                          ("target_words", int), ("actual_words", int), ("position", int)):
            if key in args and args[key] is not None:
                ch[key] = cast(args[key])
        if args.get("status") in core.STATUSES:
            ch["status"] = args["status"]
        ch["progress"] = core.chapter_progress(ch)
        out = dict(ch)
        out.update(self.store.commit())
        return out

    def h_log_sprint(self, args):
        d = self.store.draft()
        words = int(args.get("words_written", 0))
        if words < 0:
            raise ValueError("words_written must be >= 0.")
        when = args.get("date") or self.today.isoformat()
        if core.parse_date(when) is None:
            raise ValueError("date must be an ISO date like 2026-10-27.")
        chapter = args.get("chapter")
        ch = core.find_chapter(d, chapter) if chapter else None
        if chapter and ch is None:
            raise ValueError("Unknown chapter id: %r. Use set_chapter first." % chapter)
        sprint = {
            "id": core.next_sprint_id(d),
            "chapter": ch["id"] if ch else chapter,
            "date": when,
            "words_written": words,
            "minutes": int(args.get("minutes", 0) or 0),
            "note": str(args.get("note", "")),
        }
        d["sprints"].append(sprint)
        if ch is not None:
            ch["actual_words"] = (ch.get("actual_words", 0) or 0) + words
            if ch["status"] == "not_started":
                ch["status"] = "drafting"
            ch["progress"] = core.chapter_progress(ch)
        out = core.summarize_sprint(sprint)
        out["chapter_progress"] = core.chapter_progress(ch) if ch else None
        out.update(self.store.commit())
        return out

    def h_list_sprints(self, args):
        d = self.store.draft()
        try:
            limit = max(1, int(args.get("limit", 20)))
        except (TypeError, ValueError):
            limit = 20
        sprints = d["sprints"]
        if args.get("chapter"):
            sprints = [s for s in sprints if s.get("chapter") == args["chapter"]]
        sprints = sorted(sprints, key=lambda s: (str(s.get("date", "")), str(s.get("id", "0"))), reverse=True)
        return {"sprints": [core.summarize_sprint(s) for s in sprints[:limit]]}

    def h_count_words(self, args):
        return {"words": core.count_words(args.get("text", ""))}

    def h_add_revision_note(self, args):
        d = self.store.draft()
        note_text = str(args.get("note", "")).strip()
        if not note_text:
            raise ValueError("note text is required.")
        chapter = args.get("chapter")
        if core.find_chapter(d, chapter) is None:
            raise ValueError("Unknown chapter id: %r. Use set_chapter first." % chapter)
        reply_to = args.get("reply_to")
        if reply_to is not None:
            parent = next((n for n in d["revision_notes"] if n.get("id") == int(reply_to)), None)
            if parent is None:
                raise ValueError("reply_to references unknown note id %r." % reply_to)
        note = {
            "id": core.next_note_id(d),
            "chapter": chapter,
            "note": note_text,
            "reply_to": int(reply_to) if reply_to is not None else None,
            "status": "open",
        }
        d["revision_notes"].append(note)
        out = dict(note)
        out.update(self.store.commit())
        return out

    def h_list_revision_notes(self, args):
        notes = self.store.draft()["revision_notes"]
        if args.get("chapter"):
            notes = [n for n in notes if n.get("chapter") == args["chapter"]]
        if args.get("status") in core.NOTE_STATUSES:
            notes = [n for n in notes if n.get("status") == args["status"]]
        return {"notes": notes}

    def h_resolve_revision_note(self, args):
        d = self.store.draft()
        nid = int(args["id"])
        note = next((n for n in d["revision_notes"] if n.get("id") == nid), None)
        if note is None:
            raise ValueError("Unknown note id %r." % nid)
        note["status"] = "open" if args.get("reopened") else "resolved"
        out = dict(note)
        out.update(self.store.commit())
        return out

    def h_set_deadline(self, args):
        d = self.store.draft()
        raw = (args.get("deadline") or "").strip()
        if not raw:
            d["book"]["deadline"] = None
        else:
            if core.parse_date(raw) is None:
                raise ValueError("deadline must be an ISO date like 2026-12-31.")
            d["book"]["deadline"] = raw
        result = core.deadline_status(d, self.today)
        result.update(self.store.commit())
        return result

    def h_deadline_status(self, _args):
        return core.deadline_status(self.store.draft(), self.today)

    def h_smallest_step(self, _args):
        return core.smallest_step(self.store.draft(), self.today)
