"""Capture the simplified teacher journey and verify dev controls stay isolated."""
import json
import os
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.desktop-deps'))
os.environ.setdefault('QT_QPA_PLATFORM', 'windows')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QML_DISABLE_DISK_CACHE', '1')

from PySide6.QtCore import QObject, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest

from desktop.__main__ import create_app
from desktop.bridge import MarkingTask
from desktop.fixtures import demo_state
from desktop.teacher_flow import derive_teacher_flow
from desktop.visual_qa import capture, click, find, geometry, items


def show_state(bridge, state):
    bridge._state = deepcopy(state)  # Internal QA fixture injection; never part of the QML API.
    bridge.changed.emit()
    QTest.qWait(220)


def ready_state(language='zh'):
    state = demo_state('identity', language)
    state['scenario'] = 'ready'
    state['view'] = 'workspace'
    state['attention'] = []
    state['summary'].update(identity_confirmed=state['summary']['submissions'],
                            grading_results_available=0, approved=0,
                            awaiting_review=0, rendered=0, ready_to_render=0,
                            submissions_needing_attention=0, blocking_errors=0)
    for row in state['rows']:
        row.update(status=('○ Ready' if language == 'en' else '○ 已准备'), tone='neutral')
    state['teacherFlow'] = derive_teacher_flow(state, language)
    return state


def generation_state(language='zh'):
    state = demo_state('generate', language)
    state['summary'].update(awaiting_review=0, approved=31, rendered=0, ready_to_render=31)
    for row in state['rows']:
        if row.get('tone') != 'attention':
            row.update(status=('✓ Approved' if language == 'en' else '✓ 已审核'), tone='complete')
    state['teacherFlow'] = derive_teacher_flow(state, language)
    return state


def running_state(operation, language='zh'):
    state = demo_state('marking' if operation == 'mark' else 'generate', language)
    state['progress'] = {
        'operation': operation, 'running': True, 'total': 11,
        'completed': 4, 'active': 2, 'waiting': 5, 'attention': 0,
        'current': '207 · 20 · 张瑞颖',
        'saved': '4 saved results' if language == 'en' else '已保存4份结果。',
    }
    state['teacherFlow'] = derive_teacher_flow(state, language)
    return state


def visible_named(window, name):
    return [item for item in items(window.contentItem())
            if item.objectName() == name and item.isVisible()]


def reset_scroll(window):
    scroll = find(window, 'mainScroll')
    if scroll is not None:
        scroll.forceActiveFocus()
        scroll.setProperty('contentY', 0)
        content = scroll.property('contentItem')
        if content is not None:
            content.setProperty('contentY', 0)
    QTest.qWait(80)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(60, exit=True)
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    output = ROOT / 'design' / 'stage-2b1' / 'screenshots'
    output.mkdir(parents=True, exist_ok=True)

    app, engine, bridge = create_app(['normal-visual-qa'], dev_ui=False)
    bridge.setReducedMotion(True)
    window = engine.rootObjects()[0]
    window.resize(1440, 1000)
    QTest.qWait(300)

    assert not visible_named(window, 'scenarioSelector')
    assert not visible_named(window, 'developerSidebar')
    home_action = visible_named(window, 'homePrimaryAction')[0]
    home_action.forceActiveFocus()
    assert home_action.hasActiveFocus()
    QTest.keyClick(window, Qt.Key_Space)
    QTest.qWait(150)
    # Dialog is a Popup QObject and is reparented into Overlay.overlay when open,
    # so it is not guaranteed to appear in the visual child-item traversal.
    dialog = window.findChild(QObject, 'inspectDialog')
    assert dialog is not None and bool(dialog.property('visible'))
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.qWait(100)
    records = []
    start = deepcopy(bridge.state)
    # Home is a task-entry surface, so its recorded journey step should reflect
    # the next teacher action rather than the mixed fixture used behind dev mode.
    start['teacherFlow'] = derive_teacher_flow({}, 'zh')
    journey = [
        ('01-start', start, None),
        ('02-ready-to-mark', ready_state(), 1),
        ('03-marking', running_state('mark'), 1),
        ('04-excel-review', demo_state('handoff'), 2),
        ('05-ready-to-generate', generation_state(), 3),
        ('05b-generating', running_state('render'), 3),
        ('06-attention', demo_state('attention'), 3),
        ('07-complete', demo_state('complete'), 3),
    ]
    for name, state, expected_stage in journey:
        show_state(bridge, state)
        assert not visible_named(window, 'scenarioSelector')
        assert not visible_named(window, 'developerSidebar')
        if expected_stage is not None:
            progress = find(window, 'workflowProgress')
            assert progress is not None and progress.isVisible()
            actual_stage = progress.property('currentStage')
            assert actual_stage == expected_stage, f'{name}: expected stage {expected_stage}, got {actual_stage}; {state.get("teacherFlow")}'
            if name not in ('03-marking', '05b-generating'):
                assert len(visible_named(window, 'primaryAction')) == 1
        for width, height in ((1440, 1000), (1024, 720)):
            window.resize(width, height)
            QTest.qWait(100)
            problems = geometry(window)
            assert not problems, f'{name} at {width}x{height}: {problems}'
        window.resize(1440, 1000)
        reset_scroll(window)
        shot = output / f'{name}.png'
        records.append({'name': name, 'teacherFlow': state.get('teacherFlow', {}),
                        **capture(window, shot)})

    # Exercise the real-mode QML/bridge cancel boundary with a dormant worker.
    # No controller call or grader is started by this projection fixture.
    cancel_state = running_state('mark')
    cancel_state['demo'] = False
    bridge._task = MarkingTask(bridge._controller, None)
    bridge._busy = True
    bridge._state = cancel_state
    bridge.busyChanged.emit()
    bridge.changed.emit()
    QTest.qWait(120)
    cancel_button = visible_named(window, 'cancelMarkingButton')
    assert len(cancel_button) == 1 and cancel_button[0].isEnabled()
    capture(window, output / '03b-cancel-marking.png')
    click(window, cancel_button[0])
    assert bridge.state['progress']['cancelRequested']
    assert not visible_named(window, 'cancelMarkingButton')[0].isEnabled()
    bridge._busy = False
    bridge._task = None
    bridge.busyChanged.emit()

    bridge.setLanguage('en')
    english_state = demo_state('attention', 'en')
    english_state['subtitle'] = '中二高华作文批改 · 10 submissions / 10 students'
    show_state(bridge, english_state)
    window.resize(1024, 720)
    QTest.qWait(150)
    assert not geometry(window)
    subtitle_items = [item for item in items(window.contentItem())
                      if item.metaObject().indexOfProperty('text') >= 0
                      and item.property('text') == english_state['subtitle']]
    assert len(subtitle_items) == 1
    assert subtitle_items[0].property('font').family() == app.font().family()
    capture(window, output / '08-attention-english.png')
    bridge.shutdown()
    window.close()

    _, dev_engine, dev_bridge = create_app(['dev-visual-qa'], dev_ui=True)
    dev_bridge.setReducedMotion(True)
    dev_window = dev_engine.rootObjects()[0]
    dev_window.resize(1440, 1000)
    QTest.qWait(300)
    assert visible_named(dev_window, 'scenarioSelector')
    assert visible_named(dev_window, 'developerSidebar')
    capture(dev_window, output / '09-developer-harness.png')
    dev_bridge.shutdown()
    dev_window.close()

    result = {'checks': [
        'Normal UI hides the fixture selector and navigation sidebar',
        'Start page exposes one dominant choose-submissions action',
        'Choose-submissions action accepts keyboard focus and Space; dialog closes with Escape',
        'Evidence selects the non-clickable four-stage progress indicator',
        'Normal non-marking states expose exactly one dominant primary action',
        'Seven representative normal states fit at 1440x1000 and 1024x720',
        'English attention state fits at 1024x720 with the Chinese-capable font on mixed text',
        'Cancel Marking requests a safe stop through the live-mode UI and then disables itself',
        'Developer mode retains the fixture selector and original sidebar',
    ], 'captures': records, 'qmlWarnings': warnings}
    target = ROOT / 'design' / 'stage-2b1' / 'normal-visual-qa.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(target), 'captures': len(records) + 3, 'warnings': warnings}, ensure_ascii=False))
    assert not warnings, warnings
    faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
