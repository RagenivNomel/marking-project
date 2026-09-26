"""Run with python -B -m desktop; optional explicit read-only source arguments."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = ROOT / '.desktop-deps'
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

def prefers_reduced_motion():
    if sys.platform == 'win32':
        import ctypes
        enabled = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return not bool(enabled.value)
    return False

def polish_native_window(window):
    """Ask Windows to use the app's cream caption and rounded native corners."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        for attribute, value in ((33, 2), (35, 0x00C7F1FF), (36, 0x00000000)):
            setting = ctypes.c_int(value)
            dwm(hwnd, attribute, ctypes.byref(setting), ctypes.sizeof(setting))
    except (AttributeError, OSError, ValueError):
        pass

def create_app(argv=None, dev_ui=False, controller=None):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from desktop.bridge import DesktopBridge
    existing_app = QGuiApplication.instance()
    if existing_app is None:
        QQuickStyle.setStyle('Basic')
    app = existing_app or QGuiApplication(argv or sys.argv)
    app.setApplicationName('作文工作台')
    app.setOrganizationName('TeacherWorkspace')
    families = QFontDatabase.families()
    font_name = next((f for f in ('Microsoft YaHei', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei UI', 'Noto Sans CJK SC') if f in families), app.font().family())
    font = QFont(font_name)
    font.setPixelSize(16)
    app.setFont(font)
    bridge = DesktopBridge(controller=controller)
    bridge.setReducedMotion(prefers_reduced_motion())
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge', bridge)
    engine.rootContext().setContextProperty('uiFontFamily', font_name)
    engine.rootContext().setContextProperty('devUi', bool(dev_ui))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        raise RuntimeError('QML application failed to load')
    polish_native_window(engine.rootObjects()[0])
    app.aboutToQuit.connect(bridge.shutdown)
    return app, engine, bridge

def main():
    import argparse
    from application import AssignmentSource, WorkflowController
    parser = argparse.ArgumentParser(description='作文工作台：只读检查与演示')
    parser.add_argument('--demo', default='home')
    parser.add_argument('--dev-ui', action='store_true', help='show the internal fixture and state review controls')
    parser.add_argument('--language', choices=('zh', 'en'), default='zh')
    parser.add_argument('--workbook', type=Path)
    parser.add_argument('--job-root', type=Path, action='append', default=[])
    parser.add_argument('--receipt-root', type=Path, action='append', default=[])
    parser.add_argument('--split-pile', type=Path)
    parser.add_argument('--continuous-scan', type=Path)
    parser.add_argument('--roster', type=Path)
    parser.add_argument('--identity-decisions', type=Path)
    parser.add_argument('--project-dir', type=Path, help='isolated output and job root for a local verification task')
    parser.add_argument('--reduced-motion', action='store_true')
    args = parser.parse_args()
    controller = WorkflowController(project_dir=args.project_dir) if args.project_dir else None
    app, engine, bridge = create_app([sys.argv[0]], dev_ui=args.dev_ui, controller=controller)
    bridge.setLanguage(args.language)
    if args.dev_ui:
        bridge.selectDemo(args.demo)
    bridge.setReducedMotion(args.reduced_motion or prefers_reduced_motion())
    if any((args.workbook, args.job_root, args.receipt_root, args.split_pile, args.continuous_scan)):
        bridge.inspect_source(AssignmentSource(workbook=args.workbook, job_roots=tuple(args.job_root),
            receipt_roots=tuple(args.receipt_root), continuous_scan=args.continuous_scan,
            split_pile=args.split_pile, roster=args.roster,
            identity_decisions=args.identity_decisions))
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())
