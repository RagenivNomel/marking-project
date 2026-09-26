"""Roster guesses pre-select the teacher's dropdown; they never confirm identity."""

import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

from application import AssignmentSource, WorkflowController
from desktop.identity_confirmation import (
    build_identity_review,
    prepare_identity_suggestions,
    resolve_identity_companions,
    save_identity_confirmations,
)
from excel.workbook import read_roster
from grading.schemas import ROOT, Identity
from scanning.roster_matcher import (
    NO_MATCH, SUGGESTIONS_FILE, CodexImageReader, CodexRosterMatcher, ensure_suggestions,
    header_preview_path,
)
from scanning.intake import read_existing_split
from tests.local_fixtures import require_local_fixtures


ROSTER = [Identity("1", "甲同学", "207"), Identity("26", "乙同学", "207")]


class FakeGrader:
    def __init__(self, students):
        self.students = students
        self.calls = []

    def ensure_ready(self):
        pass

    def read_images(self, prompt, schema, images):
        self.calls.append((prompt, schema, list(images)))
        # Answer out of order: the matcher must sort by image number.
        answer = [{"image": i, "read": "", "student": s} for i, s in enumerate(self.students, 1)]
        return json.dumps({"assignments": list(reversed(answer))})


class GuessTests(unittest.TestCase):
    def test_one_call_for_all_images_limited_to_roster_keys(self):
        grader = FakeGrader(["207|26", NO_MATCH, "207|1"])
        images = [Path("a.png"), Path("b.png"), Path("c.png")]
        found = CodexRosterMatcher(grader).guess_all(images, ROSTER)
        self.assertEqual([item.student_id if item else None for item in found], ["26", None, "1"])
        self.assertEqual(len(grader.calls), 1)
        prompt, schema, sent = grader.calls[0]
        assignments = schema["properties"]["assignments"]
        self.assertEqual((assignments["minItems"], assignments["maxItems"]), (3, 3))
        self.assertEqual(assignments["items"]["properties"]["student"]["enum"], ["207|1", "207|26", NO_MATCH])
        self.assertIn("乙同学", prompt)
        self.assertEqual(sent, images)

    def test_missing_or_repeated_image_number_is_rejected(self):
        class Bad(FakeGrader):
            def read_images(self, prompt, schema, images):
                return json.dumps({"assignments": [
                    {"image": 1, "read": "", "student": NO_MATCH},
                    {"image": 1, "read": "", "student": NO_MATCH}]})
        with self.assertRaises(ValueError):
            CodexRosterMatcher(Bad([])).guess_all([Path("a.png"), Path("b.png")], ROSTER)

    def test_reader_runs_one_isolated_read_only_codex_call(self):
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"], seen["files"] = command, sorted(p.name for p in Path(kwargs["cwd"]).iterdir())
            Path(command[command.index("--output-last-message") + 1]).write_text(
                json.dumps({"assignments": [{"image": 1, "read": "", "student": "207|26"},
                                            {"image": 2, "read": "", "student": NO_MATCH}]}),
                encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        previews = ROOT / "pile1_test" / "_name_previews"
        images = [previews / "page5_name.png", previews / "page9_name.png"]
        if not all(image.is_file() for image in images):
            self.skipTest("local regression fixture not installed")
        with mock.patch("scanning.roster_matcher.subprocess.run", fake_run):
            found = CodexRosterMatcher(CodexImageReader()).guess_all(images, ROSTER)
        self.assertEqual(found[0].student_id, "26")
        self.assertIsNone(found[1])
        command = seen["command"]
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-luna")
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command.count("--image"), 2)
        self.assertEqual(seen["files"], ["image_001.png", "image_002.png", "schema.json"])


class ByOrderMatcher:
    """Guesses roster students in submission order; counts calls."""

    def __init__(self, roster, fail=False):
        self.roster, self.fail = roster, fail
        self.calls = 0

    def ensure_ready(self):
        pass

    def guess_all(self, images, roster):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model call failed")
        return [self.roster[index] for index, _ in enumerate(images)]


class SuggestionTests(unittest.TestCase):
    def setUp(self):
        pile_source = ROOT / "pile1_test"
        roster_source = ROOT / "中二高华作文3评改终稿.xlsx"
        pile_pdfs = list(pile_source.glob("*.pdf"))
        if not pile_pdfs:
            self.skipTest("local regression fixture not installed")
        require_local_fixtures(self, [pile_source, roster_source, *pile_pdfs])
        self.root = ROOT / f".roster-match-test-{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.pile = self.root / "pile1_test"
        shutil.copytree(pile_source, self.pile, ignore=shutil.ignore_patterns(".*", "Results"))
        self.roster_path = self.root / "roster.xlsx"
        shutil.copy2(roster_source, self.roster_path)
        self.roster = read_roster(self.roster_path)
        self.source = AssignmentSource(split_pile=self.pile, roster=self.roster_path,
                                       identity_decisions=self.root / "config" / "decisions.json")
        self.submissions = read_existing_split(self.pile)

    def test_one_call_per_scan_and_crop_shows_header(self):
        matcher = ByOrderMatcher(self.roster)
        prepare_identity_suggestions(self.source, matcher)
        self.assertEqual(matcher.calls, 1)
        self.assertTrue((self.pile / SUGGESTIONS_FILE).is_file())
        self.assertTrue(all(header_preview_path(self.pile, item).is_file() for item in self.submissions))
        prepare_identity_suggestions(self.source, matcher)
        self.assertEqual(matcher.calls, 1, "reopening must not call the model again")

    def test_failed_call_is_not_saved_so_it_is_retried(self):
        with self.assertRaises(RuntimeError):
            ensure_suggestions(self.pile, self.submissions, self.roster, ByOrderMatcher(self.roster, fail=True))
        self.assertFalse((self.pile / SUGGESTIONS_FILE).exists())

    def test_guess_pre_selects_but_does_not_confirm(self):
        prepare_identity_suggestions(self.source, ByOrderMatcher(self.roster))
        inspection = WorkflowController(project_dir=self.root).inspect(resolve_identity_companions(self.source))
        self.assertEqual(sum(item.identity_confirmed for item in inspection.submissions), 0)
        review = build_identity_review(self.source, inspection)
        self.assertEqual(len(review["rows"]), 11)
        first = review["rows"][0]
        guessed = self.roster[0]
        self.assertEqual(first["selectedKey"], f"{guessed.class_name}␟{guessed.student_id}")
        self.assertTrue(first["previewUrl"].endswith("_header.png"))

    def test_teacher_choice_wins_over_guess(self):
        prepare_identity_suggestions(self.source, ByOrderMatcher(self.roster))
        first = self.submissions[0].source_pdf
        chosen = self.roster[-1]
        source, _ = save_identity_confirmations(self.source, [
            {"sourcePdf": first, "className": chosen.class_name, "studentId": chosen.student_id}])
        inspection = WorkflowController(project_dir=self.root).inspect(source)
        self.assertEqual(sum(item.identity_confirmed for item in inspection.submissions), 1)
        review = build_identity_review(source, inspection)
        self.assertNotIn(first, [row["sourcePdf"] for row in review["rows"]])


if __name__ == "__main__":
    unittest.main()
