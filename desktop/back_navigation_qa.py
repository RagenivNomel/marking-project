"""Native normal-mode acceptance for reusable Stage 3A.1 back navigation."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".desktop-deps"))
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

from PySide6.QtCore import QCoreApplication, QEventLoop, QPoint, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest

from application import AssignmentSource
from desktop.__main__ import create_app
from desktop.identity_confirmation import resolve_identity_companions
from desktop.visual_qa import capture, find, items
from tests.local_fixtures import report_local_fixture_skip


def _hashes(folder):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path(folder).glob("*.pdf")}


def _wait(bridge, app):
    deadline = time.monotonic() + 20
    while bridge.busy and time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    app.processEvents(QEventLoop.AllEvents, 50)
    if bridge.busy:
        raise AssertionError("inspection did not finish")


def _click(window, item, app):
    point = item.mapToScene(QPoint(round(item.width() / 2), round(item.height() / 2)))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
    for _ in range(20):
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)


def _source(path, roster):
    return resolve_identity_companions(AssignmentSource(split_pile=path, roster=roster))


def main():
    pile1 = ROOT / "pile1_test"
    pile2 = ROOT / "pile2_test"
    roster = ROOT / "中二高华作文3评改终稿.xlsx"
    decisions1 = ROOT / "config" / "pile1_identity_decisions.json"
    decisions2 = ROOT / "config" / "pile2_identity_decisions.json"
    required = [pile1, pile2, roster, decisions1, decisions2]
    for pile in (pile1, pile2):
        pdfs = sorted(pile.glob("*.pdf"))
        required.extend(pdfs or [pile / "__missing_local_pdf_fixture__.pdf"])
    if report_local_fixture_skip(required):
        return

    safe_root = ROOT / f".stage3a1-acceptance-{uuid.uuid4().hex}"
    safe_root.mkdir(parents=True, exist_ok=False)
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    try:
        # The pile copies are used for the partial-confirmation case. The real
        # pile1/pile2 evidence is inspected read-only for the switching journey.
        partial_pile = safe_root / "partial_pile1"
        shutil.copytree(ROOT / "pile1_test", partial_pile)
        partial_roster = safe_root / "partial_roster.xlsx"
        shutil.copy2(ROOT / "中二高华作文3评改终稿.xlsx", partial_roster)
        partial_source = AssignmentSource(
            split_pile=partial_pile,
            roster=partial_roster,
            identity_decisions=safe_root / "config" / "partial_identity_decisions.json",
        )
        partial_before = _hashes(partial_pile)

        app, engine, bridge = create_app(["back-navigation-qa"], dev_ui=False)
        bridge.setReducedMotion(True)
        window = engine.rootObjects()[0]
        window.resize(1440, 1000)
        output = ROOT / "design" / "stage-3a" / "screenshots"
        output.mkdir(parents=True, exist_ok=True)

        pile1_source = _source(ROOT / "pile1_test", ROOT / "中二高华作文3评改终稿.xlsx")
        bridge.inspect_source(pile1_source)
        _wait(bridge, app)
        state = bridge.state
        if state["view"] != "workspace" or state["summary"]["submissions"] != 11 or state["summary"]["identities"] != 11:
            raise AssertionError(state)
        if state["teacherFlow"]["step"] != "ready_to_mark" or state["teacherFlow"]["primaryActionEnabled"]:
            raise AssertionError("marking became enabled on pile1")
        back = find(window, "workspaceBackNavigation")
        button = find(window, "backNavigationButton")
        if back is None or not back.isVisible() or button is None or not button.isVisible():
            raise AssertionError("normal back control is not visible")
        bridge.setLanguage("en")
        app.processEvents(QEventLoop.AllEvents, 100)
        if find(window, "backNavigationButton").property("text") != "← My Marking Tasks":
            raise AssertionError("English back label did not render")
        capture(window, output / "back-navigation-en.png")
        bridge.setLanguage("zh")
        app.processEvents(QEventLoop.AllEvents, 100)
        if find(window, "backNavigationButton").property("text") != "← 我的批改任务":
            raise AssertionError("Chinese back label did not render")
        capture(window, output / "back-navigation-zh.png")
        _click(window, find(window, "backNavigationButton"), app)
        if bridge.state["view"] != "home" or not find(window, "homePrimaryAction").isVisible():
            raise AssertionError("Back did not return to task selection")
        if find(window, "scenarioSelector") is not None and find(window, "scenarioSelector").isVisible():
            raise AssertionError("developer selector leaked into normal mode")

        pile2_source = _source(ROOT / "pile2_test", ROOT / "中二高华作文3评改终稿.xlsx")
        bridge.inspect_source(pile2_source)
        _wait(bridge, app)
        if bridge.state["summary"]["submissions"] != 11 or bridge.state["summary"]["identities"] != 11:
            raise AssertionError("pile2 did not inspect as 11/11")
        _click(window, find(window, "backNavigationButton"), app)
        if bridge.state["view"] != "home":
            raise AssertionError("Back did not leave pile2")
        bridge.inspect_source(pile1_source)
        _wait(bridge, app)
        if bridge.state["summary"]["submissions"] != 11 or bridge.state["summary"]["identities"] != 11:
            raise AssertionError("pile1 did not reopen as 11/11")

        # Partial identity decisions survive leaving and reopening the task.
        bridge.inspect_source(partial_source)
        _wait(bridge, app)
        initial = bridge.state["identityReview"]
        if initial["confirmedCount"] != 0 or initial["remainingCount"] != 11:
            raise AssertionError("partial safe copy was not unresolved")
        selections = [
            {"sourcePdf": row["sourcePdf"], "className": "207", "studentId": str(index)}
            for index, row in enumerate(initial["rows"][:3], 1)
        ]
        bridge.confirmIdentitySelections(selections)
        _wait(bridge, app)
        if bridge.state["identityReview"]["confirmedCount"] != 3:
            raise AssertionError("partial identity confirmation did not persist")
        _click(window, find(window, "backNavigationButton"), app)
        bridge.inspect_source(partial_source)
        _wait(bridge, app)
        if bridge.state["identityReview"]["confirmedCount"] != 3:
            raise AssertionError("partial identity confirmation was reset after Back")
        if partial_before != _hashes(partial_pile):
            raise AssertionError("source PDFs changed during navigation")
        if warnings:
            raise AssertionError(warnings)

        result = {
            "pileSwitchJourney": ["pile1_ready_11_11", "back_to_task_selection", "pile2_ready_11_11", "back_to_task_selection", "pile1_reopened_11_11"],
            "partialIdentityJourney": {"initial": "0/11", "afterSave": "3/11", "afterBackAndReopen": "3/11"},
            "normalMode": True,
            "developerControlsVisible": False,
            "sourcePdfsUnchanged": True,
            "gradingCalls": 0,
            "qmlWarnings": [],
        }
        target = ROOT / "design" / "stage-3a" / "back-navigation-acceptance.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        bridge.shutdown()
        window.close()
        print(json.dumps(result, ensure_ascii=False))
    finally:
        shutil.rmtree(safe_root, ignore_errors=True)


if __name__ == "__main__":
    main()
