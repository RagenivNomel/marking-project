"""Native Qt captures and geometry/interaction checks; no production operations."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.desktop-deps'))
# Use the native Windows font backend; offscreen Qt cannot resolve YaHei here.
os.environ.setdefault('QT_QPA_PLATFORM', 'windows')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QML_DISABLE_DISK_CACHE', '1')
if __name__ == '__main__':
    # Set before Qt DLL imports; these are QA process overrides, never app defaults.
    scale_arg = sys.argv[sys.argv.index('--scale') + 1] if '--scale' in sys.argv else '1'
    os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
    os.environ['QT_SCALE_FACTOR'] = scale_arg

from PySide6.QtCore import Qt, QPoint, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtQuick import QQuickItem
from desktop.__main__ import create_app
from desktop.fixtures import DEMO_NAMES

def items(item):
    yield item
    for child in item.childItems():
        yield from items(child)

def find(window, name):
    return next((i for i in items(window.contentItem()) if i.objectName() == name), None)

def click(window, item):
    point = item.mapToScene(QPoint(round(item.width()/2), round(item.height()/2)))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
    QTest.qWait(220)

def capture(window, path):
    image = window.grabWindow()
    if image.isNull() or not image.save(str(path)):
        raise AssertionError(f'No rendered Qt image for {path}')
    return {'pixels': [image.width(), image.height()], 'windowDpr': window.devicePixelRatio(),
            'effectiveCaptureScale': image.width() / window.width()}

def geometry(window):
    problems = []
    for item in items(window.contentItem()):
        if not item.isVisible() or item.width() <= 0 or item.height() <= 0:
            continue
        # Wrapped Text must allocate its full painted height. Ignore popup internals.
        if item.metaObject().indexOfProperty('text') >= 0 and item.metaObject().indexOfProperty('contentHeight') >= 0:
            content = item.property('contentHeight')
            if content and content > item.height() + 3:
                problems.append({'text': str(item.property('text'))[:80], 'height': item.height(), 'contentHeight': content})
            point = item.mapToScene(QPoint(0, 0))
            if 0 <= point.y() < window.height() and (point.x() < -2 or point.x() + item.width() > window.width() + 2):
                problems.append({'horizontalOverflow': str(item.property('text'))[:80], 'x': point.x(), 'width': item.width()})
    return problems

def main():
    import faulthandler
    faulthandler.dump_traceback_later(45, exit=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--scale', default='1')
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--language', choices=('zh', 'en'), default='zh')
    args = parser.parse_args()
    output = ROOT / 'design' / 'stage-2b' / 'screenshots'
    output.mkdir(parents=True, exist_ok=True)
    messages = []
    def handler(kind, context, message):
        messages.append(message)
    qInstallMessageHandler(handler)
    try:
        app, engine, bridge = create_app(['visual-qa'], dev_ui=True)
    except RuntimeError:
        print('\n'.join(messages))
        raise
    window = engine.rootObjects()[0]
    bridge.setLanguage(args.language)
    bridge.setReducedMotion(True)
    window.resize(1440, 1000)
    QTest.qWait(300)
    records = []
    keys = ['marking', 'handoff', 'attention', 'stress'] if args.quick else list(DEMO_NAMES)
    for key in keys:
        bridge.selectDemo(key)
        QTest.qWait(220)
        record = {'key': key, 'logicalSize': [window.width(), window.height()], 'textOverflow': geometry(window)}
        suffix = '-en' if args.language == 'en' else ''
        record.update(capture(window, output / f'{key}-scale-{args.scale}{suffix}.png'))
        records.append(record)
    for width, height in [(1024,720),(1280,900),(1920,1080)]:
        supported_height = max(720, min(height, window.screen().availableGeometry().height() - 80))
        window.resize(width, supported_height)
        for key in (list(DEMO_NAMES) if width == 1024 and not args.quick else ['marking','attention','stress']):
            bridge.selectDemo(key)
            QTest.qWait(220)
            record = {'key': key, 'logicalSize': [window.width(), window.height()], 'textOverflow': geometry(window)}
            record.update(capture(window, output / f'{key}-{width}-scale-{args.scale}{suffix}.png'))
            records.append(record)
    result = {'scale': args.scale, 'language': args.language, 'font': app.font().family(), 'messages': messages, 'captures': records}
    target = ROOT / 'design' / 'stage-2b' / f'visual-qa-{args.scale}{"-en" if args.language == "en" else ""}.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(target), 'captures':len(records), 'messages': messages,
                      'textOverflow': sum(len(r['textOverflow']) for r in records)}, ensure_ascii=False))
    bridge.shutdown()
    window.close()
    faulthandler.cancel_dump_traceback_later()
    return 1 if messages or any(r['textOverflow'] for r in records) else 0

if __name__ == '__main__':
    raise SystemExit(main())
