"""Stage 3A.1 back navigation over existing read-only assignment evidence."""

import hashlib
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DEPS = ROOT / ".desktop-deps"
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

from PySide6.QtCore import QCoreApplication, QEventLoop

from application import AssignmentSource, WorkflowController
from desktop.bridge import DesktopBridge
from desktop.identity_confirmation import resolve_identity_companions
from grading.schemas import ROOT as PROJECT_ROOT
from tests.local_fixtures import require_local_fixtures


class BackNavigationTests(unittest.TestCase):
    def setUp(self):
        pile1 = PROJECT_ROOT / "pile1_test"
        pile2 = PROJECT_ROOT / "pile2_test"
        roster = PROJECT_ROOT / "中二高华作文3评改终稿.xlsx"
        decisions1 = PROJECT_ROOT / "config" / "pile1_identity_decisions.json"
        decisions2 = PROJECT_ROOT / "config" / "pile2_identity_decisions.json"
        pile1_pdfs = list(pile1.glob("*.pdf"))
        pile2_pdfs = list(pile2.glob("*.pdf"))
        if not pile1_pdfs or not pile2_pdfs:
            self.skipTest("local regression fixture not installed")
        require_local_fixtures(self, [pile1, pile2, roster, decisions1, decisions2, *pile1_pdfs, *pile2_pdfs])
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.bridge = DesktopBridge(controller=WorkflowController())

    def tearDown(self):
        self.bridge.shutdown()

    def _wait(self):
        deadline = time.monotonic() + 15
        while self.bridge.busy and time.monotonic() < deadline:
            self.app.processEvents(QEventLoop.AllEvents, 50)
            time.sleep(0.005)
        self.app.processEvents(QEventLoop.AllEvents, 50)
        self.assertFalse(self.bridge.busy)

    @staticmethod
    def _pdf_hashes(pile):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in Path(pile).glob("*.pdf")}

    def _inspect(self, name):
        source = resolve_identity_companions(
            AssignmentSource(split_pile=PROJECT_ROOT / name)
        )
        self.bridge.inspect_source(source)
        self._wait()
        return source

    def test_pile_switch_back_and_reopen_preserves_persisted_state(self):
        pile1 = PROJECT_ROOT / "pile1_test"
        pile2 = PROJECT_ROOT / "pile2_test"
        before_pile1 = self._pdf_hashes(pile1)
        before_pile2 = self._pdf_hashes(pile2)
        roster_before = hashlib.sha256(
            (PROJECT_ROOT / "中二高华作文3评改终稿.xlsx").read_bytes()
        ).hexdigest()
        decisions = PROJECT_ROOT / "config" / "pile1_identity_decisions.json"
        decisions_before = hashlib.sha256(decisions.read_bytes()).hexdigest()

        source1 = self._inspect("pile1_test")
        self.assertEqual(self.bridge.state["view"], "workspace")
        self.assertEqual(self.bridge.state["summary"]["submissions"], 11)
        self.assertEqual(self.bridge.state["summary"]["identities"], 11)
        initial_step = self.bridge.state["teacherFlow"]["step"]
        self.assertIn(initial_step, ("ready_to_mark", "marking_start_failed"))
        self.assertTrue(self.bridge.state["teacherFlow"]["primaryActionEnabled"])

        self.bridge.navigate("home")
        self.assertEqual(self.bridge.state["view"], "home")
        self.assertEqual(self.bridge._source.split_pile, source1.split_pile)

        self._inspect("pile2_test")
        self.assertEqual(self.bridge.state["summary"]["submissions"], 11)
        self.assertEqual(self.bridge.state["summary"]["identities"], 11)
        self.assertTrue(self.bridge.state["teacherFlow"]["primaryActionEnabled"])

        self.bridge.navigate("home")
        self._inspect("pile1_test")
        self.assertEqual(self.bridge.state["summary"]["submissions"], 11)
        self.assertEqual(self.bridge.state["summary"]["identities"], 11)
        self.assertEqual(self.bridge.state["teacherFlow"]["step"], initial_step)
        self.assertTrue(self.bridge.state["teacherFlow"]["primaryActionEnabled"])

        self.assertEqual(before_pile1, self._pdf_hashes(pile1))
        self.assertEqual(before_pile2, self._pdf_hashes(pile2))
        self.assertEqual(roster_before, hashlib.sha256(
            (PROJECT_ROOT / "中二高华作文3评改终稿.xlsx").read_bytes()
        ).hexdigest())
        self.assertEqual(decisions_before, hashlib.sha256(decisions.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
