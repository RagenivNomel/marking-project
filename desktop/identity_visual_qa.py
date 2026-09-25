"""Native normal-mode check for the Stage 3A identity workspace."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".desktop-deps"))
import os
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, qInstallMessageHandler
import time
from PySide6.QtTest import QTest
from desktop.__main__ import create_app
from desktop.identity_confirmation import build_identity_review
from desktop.visual_qa import capture, find, items
from application import AssignmentSource
from tests.local_fixtures import report_local_fixture_skip


def _hashes(pile):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in pile.glob("*.pdf")}


def _visible(window, name):
    return any(item.objectName() == name and item.isVisible() for item in items(window.contentItem()))


def main():
    pile_source = ROOT / "pile1_test"
    roster_source = ROOT / "中二高华作文3评改终稿.xlsx"
    pdfs = sorted(pile_source.glob("*.pdf"))
    required = [pile_source, roster_source, *(pdfs or [pile_source / "__missing_local_pdf_fixture__.pdf"])]
    if report_local_fixture_skip(required):
        return

    safe_root = ROOT / f".stage3a-visual-{uuid.uuid4().hex}"
    safe_root.mkdir(parents=True, exist_ok=False)
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    try:
        pile = safe_root / "pile1_test"
        shutil.copytree(ROOT / "pile1_test", pile)
        roster = safe_root / "roster.xlsx"
        shutil.copy2(ROOT / "中二高华作文3评改终稿.xlsx", roster)
        decisions = safe_root / "config" / "pile1_identity_decisions.json"
        source = AssignmentSource(split_pile=pile, roster=roster, identity_decisions=decisions)
        before = _hashes(pile)

        app, engine, bridge = create_app(["identity-visual-qa"], dev_ui=False)
        bridge.setReducedMotion(True)
        window = engine.rootObjects()[0]
        window.resize(1440, 1000)
        bridge.inspect_source(source)
        for _ in range(300):
            QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
            time.sleep(0.01)
            if not bridge.busy:
                break
        panel = find(window, "identityConfirmationPanel")
        if panel is None or not panel.isVisible():
            raise AssertionError("normal identity confirmation panel is not visible")
        if _visible(window, "scenarioSelector") or _visible(window, "developerSidebar"):
            raise AssertionError("developer controls leaked into normal identity flow")
        initial = bridge.state["identityReview"]
        if initial["totalCount"] != 11 or initial["confirmedCount"] != 0 or len(initial["rows"]) != 11:
            raise AssertionError(initial)
        output = ROOT / "design" / "stage-3a" / "screenshots"
        output.mkdir(parents=True, exist_ok=True)
        capture(window, output / "identity-confirmation.png")

        selections = []
        for index, row in enumerate(initial["rows"], 1):
            selections.append({"sourcePdf": row["sourcePdf"], "className": "207", "studentId": str(index)})
        bridge.confirmIdentitySelections(selections)
        for _ in range(300):
            QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
            time.sleep(0.01)
            if not bridge.busy:
                break
        final = bridge.state
        if final["identityReview"]["visible"] or final["teacherFlow"]["step"] != "ready_to_mark":
            raise AssertionError(final.get("teacherFlow"))
        if final["teacherFlow"]["primaryActionEnabled"]:
            raise AssertionError("start-marking action became executable")
        capture(window, output / "identity-ready-to-mark.png")
        if before != _hashes(pile):
            raise AssertionError("source PDFs changed")
        bridge.shutdown()
        window.close()
        result = {"normalMode": True, "initialConfirmed": 0, "initialRemaining": 11,
                  "finalConfirmed": 11, "readyToMark": True, "gradingEnabled": False,
                  "sourcePdfsUnchanged": True, "qmlWarnings": warnings}
        target = ROOT / "design" / "stage-3a" / "identity-visual-qa.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        if warnings:
            raise AssertionError(warnings)
    finally:
        shutil.rmtree(safe_root, ignore_errors=True)


if __name__ == "__main__":
    main()
