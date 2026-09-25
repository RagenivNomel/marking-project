"""Exercise native controls, demo/real boundary and explicit real read-only examples."""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.desktop-deps'))
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QML_DISABLE_DISK_CACHE', '1')

from PySide6.QtCore import Qt, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtCore import QCoreApplication
from application import AssignmentSource
from desktop.__main__ import create_app
from desktop.visual_qa import find, click, capture, items

def wait_read(bridge):
    deadline = time.monotonic() + 60
    while bridge.busy and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert not bridge.busy, 'Read-only inspection did not finish'
    QTest.qWait(200)


def configured_local_scenarios():
    manifest = os.environ.get('PHASE1_INTERACTION_QA_SCENARIOS')
    if not manifest or not Path(manifest).is_file():
        print('SKIPPED: local regression fixture not installed', flush=True)
        return []
    scenarios = json.loads(Path(manifest).read_text(encoding='utf-8'))
    if not isinstance(scenarios, list):
        raise ValueError('Local interaction QA scenarios must be a JSON list')
    required = []
    for scenario in scenarios:
        required.extend([scenario['workbook'], *scenario.get('job_roots', []),
                         *scenario.get('receipt_roots', [])])
        if not isinstance(scenario.get('expected_summary'), dict):
            raise ValueError('Each local interaction QA scenario needs expected_summary')
    if not scenarios or not all(Path(path).exists() for path in required):
        print('SKIPPED: local regression fixture not installed', flush=True)
        return []
    return scenarios


def main():
    import faulthandler
    faulthandler.dump_traceback_later(60, exit=True)
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    app, engine, bridge = create_app(['interaction-qa'], dev_ui=True)
    window = engine.rootObjects()[0]
    window.resize(1440, 1000)
    bridge.setReducedMotion(True)
    checks = []
    QTest.qWait(300)
    assert app.font().family() == 'Microsoft YaHei'
    checks.append('Native Windows Microsoft YaHei resolved')
    inspect_button = find(window, 'inspectButton')
    assert inspect_button is not None
    inspect_button.forceActiveFocus()
    assert inspect_button.hasActiveFocus()
    QTest.keyClick(window, Qt.Key_Space)
    QTest.qWait(200)
    capture(window, ROOT / 'design/stage-2b/screenshots/inspect-dialog.png')
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.qWait(150)
    checks.append('Inspection control accepts keyboard focus and Space; dialog closes with Escape')
    bridge.selectDemo('workspace')
    QTest.qWait(200)
    button = find(window, 'primaryAction')
    assert button is not None and not button.isEnabled()
    before = bridge.state
    click(window, button)
    assert bridge.state == before
    checks.append('Disabled production action ignores clicks without changing state')
    tab = find(window, 'sectionTab0')
    assert tab is not None
    tab.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_Space)
    QTest.qWait(150)
    assert bridge.state['section'] == 0
    checks.append('Keyboard activates preparation tab including zero index')
    details = find(window, 'detailsToggle')
    if details:
        details.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Space)
        QTest.qWait(180)
        checks.append('Details disclosure keyboard activation exercised')
    bridge.selectDemo('stress')
    QTest.qWait(200)
    listing = find(window, 'submissionList')
    assert listing is not None
    listing.setProperty('currentIndex', 39)
    listing.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_End)
    QTest.qWait(200)
    assert len(bridge.state['rows']) == 40
    assert listing.property('count') == 40 and listing.property('currentIndex') == 39
    checks.append('40 distinct submission rows remain available through scrolling')
    evidence = []
    scenarios = configured_local_scenarios()
    for scenario in scenarios:
        label = str(scenario['label'])
        if Path(label).name != label:
            raise ValueError('Local interaction QA label must be a basename')
        source = AssignmentSource(
            workbook=Path(scenario['workbook']),
            job_roots=tuple(Path(path) for path in scenario.get('job_roots', [])),
            receipt_roots=tuple(Path(path) for path in scenario.get('receipt_roots', [])),
        )
        print('Inspecting configured local scenario ' + label, flush=True)
        bridge.inspect_source(source)
        wait_read(bridge)
        state = bridge.state
        assert not state['demo'] and state['progress'] == {}
        for name, expected in scenario['expected_summary'].items():
            assert state['summary'][name] == expected
        if 'expected_row_count' in scenario:
            assert len({row['id'] for row in state['rows']}) == scenario['expected_row_count']
        if 'expected_attention_count' in scenario:
            assert len(state['attention']) == scenario['expected_attention_count']
        capture(window, ROOT / f'design/stage-2b/screenshots/{label}.png')
        evidence.append({'source': label, 'summary': state['summary'], 'attentionCount': len(state['attention'])})
        bridge.refresh()
        wait_read(bridge)
        assert bridge.state['summary'] == state['summary']
    if scenarios:
        checks.append('Configured local regression sources inspect and refresh without live progress claims')
    else:
        checks.append('SKIPPED: local regression fixture not installed')
    bridge.selectDemo('marking')
    before = bridge.state
    bridge.refresh()
    assert bridge.state == before and not bridge.busy
    bridge.selectDemo('real')
    assert not bridge.state['demo']
    checks.append('Demo refresh cannot read a prior real source; real snapshot can be restored')
    result = {'checks': checks, 'realInspections': evidence, 'qmlWarnings': warnings}
    (ROOT / 'design/stage-2b/interaction-qa.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    bridge.shutdown()
    window.close()
    assert not warnings, warnings
    faulthandler.cancel_dump_traceback_later()

if __name__ == '__main__':
    main()
