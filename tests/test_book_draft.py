import os
import sys
import unittest
from datetime import date
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from book_draft_mcp import core
from book_draft_mcp import storage
from book_draft_mcp.server import DraftStore, Handlers


def make_draft(book_deadline=None, chapters=None):
    d = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
         for k, v in core.NEW_DRAFT.items()}
    d["sprints"] = []
    d["revision_notes"] = []
    d["book"]["deadline"] = None
    if book_deadline:
        d["book"]["deadline"] = book_deadline
    for ch in chapters or []:
        d["chapters"].append(dict(ch, progress=core.chapter_progress(ch)))
    return d


class WordCountTests(unittest.TestCase):
    def test_simple_words(self):
        self.assertEqual(core.count_words("one two three"), 3)

    def test_extra_whitespace(self):
        self.assertEqual(core.count_words("  spaced   out\t words \n here "), 4)

    def test_empty(self):
        self.assertEqual(core.count_words(""), 0)
        self.assertEqual(core.count_words(None), 0)
        self.assertEqual(core.count_words("   "), 0)
        self.assertEqual(core.count_words(42), 0)

    def test_punctuation_attached(self):
        self.assertEqual(core.count_words("Hello, world! Hi."), 3)

    def test_chapter_progress_math(self):
        ch = {"target_words": 200, "actual_words": 50}
        self.assertEqual(core.chapter_progress(ch), 25.0)

    def test_chapter_progress_no_target(self):
        self.assertEqual(core.chapter_progress({"actual_words": 999}), 0.0)

    def test_book_totals(self):
        d = make_draft(chapters=[
            {"id": "a", "target_words": 100, "actual_words": 40},
            {"id": "b", "target_words": 300, "actual_words": 60},
        ])
        t = core.book_totals(d)
        self.assertEqual(t["chapters"], 2)
        self.assertEqual(t["target_words"], 400)
        self.assertEqual(t["actual_words"], 100)
        self.assertEqual(t["remaining_words"], 300)
        self.assertEqual(t["percent_complete"], 25.0)


class DeadlineTests(unittest.TestCase):
    def test_days_left_future(self):
        d = make_draft(book_deadline="2026-10-20")
        s = core.deadline_status(d, today=date(2026, 10, 13))
        self.assertEqual(s["days_left"], 7)

    def test_deadline_today_is_zero(self):
        d = make_draft(book_deadline="2026-10-13")
        s = core.deadline_status(d, today=date(2026, 10, 13))
        self.assertEqual(s["days_left"], 0)
        self.assertIn("passed", s["message"])

    def test_deadline_past_negative(self):
        d = make_draft(book_deadline="2026-10-01")
        s = core.deadline_status(d, today=date(2026, 10, 13))
        self.assertEqual(s["days_left"], -12)

    def test_nudge_math_on_track(self):
        d = make_draft(book_deadline="2026-10-20", chapters=[
            {"id": "a", "target_words": 700, "actual_words": 0},
        ])
        s = core.deadline_status(d, today=date(2026, 10, 13))
        self.assertEqual(s["days_left"], 7)
        self.assertEqual(s["remaining_words"], 700)
        self.assertIn("100", s["message"])  # 700 words / 7 days

    def test_no_deadline_is_gentle(self):
        s = core.deadline_status(make_draft(), today=date(2026, 10, 13))
        self.assertIsNone(s["days_left"])
        self.assertIn("No deadline", s["message"])

    def test_bad_date_string(self):
        self.assertIsNone(core.parse_date("not-a-date"))
        self.assertIsNone(core.parse_date("2026-13-45"))


class StorageSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()

    def test_rejects_traversal(self):
        with self.assertRaises(ValueError):
            storage.safe_path(self.tmp.name, "../escape.json")

        with self.assertRaises(ValueError):
            storage.safe_path(self.tmp.name, "sub/../../escape.json")

    def test_rejects_dot_and_dotdot(self):
        for bad in (".", "..", "", None):
            with self.assertRaises(ValueError):
                storage.safe_path(self.tmp.name, bad)

    def test_rejects_slashes_and_null(self):
        for bad in ("a/b.json", "a\\b.json", "x\x00.json"):
            with self.assertRaises(ValueError):
                storage.safe_path(self.tmp.name, bad)

    def test_rejects_unexpected_chars(self):
        with self.assertRaises(ValueError):
            storage.safe_path(self.tmp.name, "file;rm-rf.json")

    def test_stays_inside_data_dir(self):
        good = storage.safe_path(self.tmp.name, "ok-file_1.2.json")
        self.assertTrue(os.path.realpath(good).startswith(
            os.path.realpath(self.tmp.name) + os.sep))

    def test_missing_file_returns_none(self):
        self.assertIsNone(storage.load(self.tmp.name, "nope.json"))

    def test_save_and_reload(self):
        payload = {"hello": "world"}
        storage.save(payload, self.tmp.name, "draft.json")
        self.assertEqual(storage.load(self.tmp.name, "draft.json"), payload)

    def test_auto_backup_created_on_overwrite(self):
        storage.save({"v": 1}, self.tmp.name, "draft.json")
        storage.save({"v": 2}, self.tmp.name, "draft.json")
        backups = os.path.join(self.tmp.name, "backups")
        self.assertTrue(os.path.isdir(backups))
        self.assertEqual(len([f for f in os.listdir(backups) if f.endswith(".json")]), 1)

    def test_backup_prune_keeps_ten(self):
        for i in range(15):
            storage.save({"v": i}, self.tmp.name, "draft.json")
        backups = os.path.join(self.tmp.name, "backups")
        self.assertLessEqual(len(os.listdir(backups)), 10)

    def test_corrupt_backup_never_loses_data(self):
        # saving over a live file always leaves a valid JSON file behind
        storage.save({"v": 1}, self.tmp.name, "draft.json")
        try:
            storage.save({"v": 2}, self.tmp.name, "draft.json")
        finally:
            self.assertEqual(storage.load(self.tmp.name, "draft.json"), {"v": 2})


class ServerHandlerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = DraftStore(data_dir=self.tmp.name, today=date(2026, 10, 13))
        self.h = Handlers(self.store, date(2026, 10, 13))

    def test_smallest_step_nonempty(self):
        step = self.h.h_smallest_step({})
        self.assertIn("step", step)
        self.assertIn("minutes", step)

    def test_set_chapter_and_log_sprint_updates_counts(self):
        self.h.h_set_chapter({"id": "ch01", "title": "T", "target_words": 1000})
        out = self.h.h_log_sprint({"chapter": "ch01", "words_written": 250})
        ch = core.find_chapter(self.store.draft(), "ch01")
        self.assertEqual(ch["actual_words"], 250)
        self.assertEqual(ch["status"], "drafting")
        self.assertEqual(out["words_written"], 250)

    def test_log_sprint_rejects_unknown_chapter(self):
        with self.assertRaises(ValueError):
            self.h.h_log_sprint({"chapter": "ghost", "words_written": 10})

    def test_revision_note_thread(self):
        self.h.h_set_chapter({"id": "ch02"})
        n1 = self.h.h_add_revision_note({"chapter": "ch02", "note": "tighten intro"})
        n2 = self.h.h_add_revision_note({"chapter": "ch02", "note": "agreed", "reply_to": n1["id"]})
        self.assertEqual(n2["reply_to"], n1["id"])
        with self.assertRaises(ValueError):
            self.h.h_add_revision_note({"chapter": "ch02", "note": "x", "reply_to": 9999})
        self.h.h_resolve_revision_note({"id": n1["id"]})
        notes = self.h.h_list_revision_notes({"chapter": "ch02", "status": "open"})["notes"]
        self.assertEqual([n["id"] for n in notes], [n2["id"]])

    def test_deadline_validation(self):
        with self.assertRaises(ValueError):
            self.h.h_set_deadline({"deadline": "tomorrow"})
        self.h.h_set_deadline({"deadline": "2027-01-15"})
        self.assertEqual(self.store.draft()["book"]["deadline"], "2027-01-15")
        self.h.h_set_deadline({"deadline": ""})
        self.assertIsNone(self.store.draft()["book"]["deadline"])

    def test_sample_draft_loads(self):
        real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        d, errs = core.ensure_draft(storage.load(real) or {})
        self.assertEqual(errs, [])
        self.assertEqual(len(d["chapters"]), 6)
        overview = Handlers(DraftStore(data_dir=real), date(2026, 10, 13)).h_book_overview({})
        self.assertEqual(overview["totals"]["chapters"], 6)

    def tearDown(self):
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
