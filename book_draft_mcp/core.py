"""Core book-draft domain logic: chapters, sprints, revision notes, deadline math."""
from datetime import date, timedelta

DRAFT_SCHEMA_VERSION = 1

STATUSES = ("not_started", "drafting", "revising", "final", "backburner")
NOTE_STATUSES = ("open", "resolved")

NEW_DRAFT = {
    "schema_version": DRAFT_SCHEMA_VERSION,
    "book": {
        "title": "Untitled Draft",
        "subtitle": "",
        "word_target_total": 60000,
        "deadline": None,
    },
    "chapters": [],
    "sprints": [],
    "revision_notes": [],
}


def ensure_draft(data):
    """Validate/normalize a draft dict; return (draft, errors)."""
    errors = []
    d = dict(data or {})
    if "schema_version" not in d:
        d["schema_version"] = DRAFT_SCHEMA_VERSION
    for key in ("book", "chapters", "sprints", "revision_notes"):
        if key not in d:
            d[key] = NEW_DRAFT[key]
    if not isinstance(d["chapters"], list):
        d["chapters"] = []
        errors.append("chapters reset: expected list")
    if not isinstance(d["sprints"], list):
        d["sprints"] = []
        errors.append("sprints reset: expected list")
    if not isinstance(d["revision_notes"], list):
        d["revision_notes"] = []
        errors.append("revision_notes reset: expected list")
    return d, errors


def count_words(text):
    """Whitespace-based word count."""
    if not isinstance(text, str):
        return 0
    return len(text.split())


def parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def find_chapter(draft, chapter_id):
    cid = str(chapter_id).strip().lower()
    for ch in draft["chapters"]:
        if str(ch.get("id", "")).lower() == cid:
            return ch
    return None


def chapter_progress(chapter):
    actual = chapter.get("actual_words", 0) or 0
    target = chapter.get("target_words", 0) or 0
    return round((actual / target) * 100, 1) if target > 0 else 0.0


def book_totals(draft, chapter_id=None):
    chapters = draft["chapters"]
    if chapter_id is not None:
        ch = find_chapter(draft, chapter_id)
        chapters = [ch] if ch else []
    target = sum(c.get("target_words", 0) or 0 for c in chapters)
    actual = sum(c.get("actual_words", 0) or 0 for c in chapters)
    return {
        "chapters": len(chapters),
        "target_words": target,
        "actual_words": actual,
        "remaining_words": max(0, target - actual),
        "percent_complete": round((actual / target) * 100, 1) if target > 0 else 0.0,
    }


def deadline_status(draft, today=None):
    """Gentle nudge math: how many days left, pace check, gentle message."""
    today = today or date.today()
    dl = parse_date((draft.get("book") or {}).get("deadline"))
    if dl is None:
        return {"deadline": None, "days_left": None, "message": "No deadline set. That is fine; the draft will wait for you."}
    days_left = (dl - today).days
    totals = book_totals(draft)
    remaining = totals["remaining_words"]
    if days_left > 0:
        per_day = remaining / days_left
        message = "%s days left. About %s words a day keeps you on track. Totally doable." % (
            days_left, round(per_day))
    else:
        message = ("Deadline day has come (or passed). No guilt. "
                   "Reduce the target or set a fresh deadline and keep going.")
    return {
        "deadline": dl.isoformat(),
        "days_left": days_left,
        "remaining_words": remaining,
        "message": message,
    }


def smallest_step(draft, today=None):
    """Today's smallest step suggestion: one concrete, doable action."""
    today = today or date.today()
    dl_status = deadline_status(draft, today)
    open_notes = [n for n in draft["revision_notes"] if n.get("status") == "open"]
    stuck = find_chapter(draft, next(
        (c["id"] for c in draft["chapters"] if c.get("status") == "revising"), None))
    behind = [
        c for c in draft["chapters"]
        if chapter_progress(c) < 50.0 and c.get("status") not in ("final",)
    ]
    behind.sort(key=lambda c: (c.get("position", 9999), c.get("id", "")))

    if open_notes and stuck is not None:
        note = open_notes[0]["note"]
        return {
            "step": "Open chapter '%s' and apply one revision note: %s" % (stuck.get("title", stuck["id"]), note),
            "why": "The chapter is in revision and has %d open note(s). One note each session keeps it humane." % len(open_notes),
            "minutes": 20,
        }
    if stuck is not None:
        return {
            "step": "Spend 15 minutes revising the outline of chapter '%s'." % stuck.get("title", stuck["id"]),
            "why": "It is in revision; start with a reread, not a rewrite.",
            "minutes": 15,
        }
    if behind:
        ch = behind[0]
        target = ch.get("target_words", 0) or 0
        actual = ch.get("actual_words", 0) or 0
        remaining = max(0, target - actual)
        return {
            "step": "Write %s words on chapter '%s' (that is about one screen)." % (min(300, max(50, remaining)), ch.get("title", ch["id"])),
            "why": "It is the earliest chapter still under 50%% complete at %.0f%%." % chapter_progress(ch),
            "minutes": 25,
        }
    started = next((c for c in draft["chapters"] if c.get("status") == "drafting"), None)
    if started is not None:
        return {
            "step": "Draft the next subsection of chapter '%s' in a 15-minute sprint." % started.get("title", started["id"]),
            "why": "Momentum matters more than length.",
            "minutes": 15,
        }
    if days_hint := dl_status.get("days_left"):
        return {
            "step": "Outline or add the next chapter (target ~%s words)." % (dl_status.get("remaining_words") or 500),
            "why": "No active work-in-progress, and %s days remain." % days_hint,
            "minutes": 20,
        }
    return {
        "step": "Open the draft and list the next three chapter titles.",
        "why": "A short outline today makes tomorrow's writing easier.",
        "minutes": 10,
    }


def next_note_id(draft):
    ids = [int(n["id"]) for n in draft["revision_notes"] if str(n.get("id", "")).isdigit()]
    return (max(ids) + 1) if ids else 1


def next_sprint_id(draft):
    ids = [int(s["id"]) for s in draft["sprints"] if str(s.get("id", "")).isdigit()]
    return (max(ids) + 1) if ids else 1


def summarize_sprint(s):
    return {
        "id": s["id"],
        "chapter": s.get("chapter"),
        "date": s.get("date"),
        "words_written": s.get("words_written"),
        "minutes": s.get("minutes"),
        "note": s.get("note", ""),
    }
