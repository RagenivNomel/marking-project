# PyInstaller recipe for the Marking App. Run through `pixi run build`, which
# supplies Python, Poppler and Tesseract from the locked pixi environment.
import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
APP_NAME = "Marking App"
VERSION = os.environ.get("MARKING_APP_VERSION", "0.0.0")
# PyInstaller converts this PNG to .icns/.ico (made by packaging/make_icon.py).
ICON = str(ROOT / "desktop" / "assets" / "app-icon.png")

# Read-only resources, placed at the same relative paths as in the repository.
# Only files tracked in git belong here: config/ also collects local identity
# decisions, so its files are listed by name.
datas = [
    (str(ROOT / "desktop" / "qml"), "desktop/qml"),
    (str(ROOT / "desktop" / "assets"), "desktop/assets"),
    (str(ROOT / "grading" / "skills"), "grading/skills"),
    (str(ROOT / "grading" / "references"), "grading/references"),
    (str(ROOT / "grading" / "prompts"), "grading/prompts"),
    (str(ROOT / "rendering" / "template"), "rendering/template"),
    (str(ROOT / "tessdata" / "chi_sim.traineddata"), "tessdata"),
    # Loaded by file path from scanning/split_by_student.py.
    (str(ROOT / "split_by_student.py"), "."),
]
for name in ("calibration_model.json", "calibration_rubric_v1.json", "calibration_rubric_v2.json",
             "criteria.json", "models.json", "text_limits.json"):
    datas.append((str(ROOT / "config" / name), "config"))

# Poppler and Tesseract from the pixi environment. PyInstaller collects the
# libraries they link against and rewrites their paths for the bundle.
tool_dir = Path(sys.prefix) / ("Library/bin" if os.name == "nt" else "bin")
suffix = ".exe" if os.name == "nt" else ""
binaries = [(str(tool_dir / f"{tool}{suffix}"), "vendor/bin") for tool in ("pdftoppm", "pdfinfo", "tesseract")]

hiddenimports = []
for package in ("application", "desktop", "excel", "grading", "rendering", "scanning", "workflow"):
    hiddenimports += [name for name in collect_submodules(package) if ".tests" not in name and not name.endswith("_qa")]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    excludes=["tkinter"],
    noarchive=False,
)

# PyInstaller collects every QML module PySide6 ships. The interface imports
# only QtQuick, Controls, Layouts and Dialogs, so drop the large unused ones
# (WebEngine alone is ~150 MB). The packaged self-check loads the real QML.
UNUSED_QT = ("3D", "Charts", "DataVisualization", "Graphs", "Location", "Multimedia", "Positioning",
             "Quick3D", "QuickTest", "RemoteObjects", "Scxml", "Sensors", "SpatialAudio", "Test",
             "TextToSpeech", "WebChannel", "WebEngine", "WebSockets", "WebView", "Pdf", "VirtualKeyboard")
UNUSED_QTQUICK_QML = {"Pdf", "VirtualKeyboard", "Scene2D"}


def _unused_qt(dest):
    parts = Path(dest).parts
    for index, part in enumerate(parts):
        if index and parts[index - 1] == "QtQuick" and part in UNUSED_QTQUICK_QML:
            return True
        for prefix in ("libQt6", "Qt6", "Qt"):
            if part.startswith(prefix):
                if part[len(prefix):].startswith(UNUSED_QT):
                    return True
                break
    return False


a.binaries = [entry for entry in a.binaries if not _unused_qt(entry[0])]
a.datas = [entry for entry in a.datas if not _unused_qt(entry[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    icon=ICON,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=ICON,
        bundle_identifier="local.marking-app",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
