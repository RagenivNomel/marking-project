"""Check that a packaged app can find and run everything it bundles.

Run as ``Marking App --self-check result.json``. Nothing is shown and no task
data is touched: it renders and OCRs a generated page in a temporary folder,
loads the card layout and the QML interface off-screen, and writes one JSON
report. Exit code 0 means every check passed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback

OCR_SAMPLE = "中文测试"


def _check_tools(report):
    from app_paths import ROOT, is_frozen
    found = {name: shutil.which(name) for name in ("pdftoppm", "pdfinfo", "tesseract")}
    missing = [name for name, path in found.items() if not path]
    if missing:
        raise RuntimeError(f"not found: {', '.join(missing)}")
    if is_frozen():
        # A macOS .app splits its files between Contents/Frameworks and
        # Contents/Resources, so accept anything inside Contents.
        bundle = ROOT.resolve().parent if sys.platform == "darwin" else ROOT.resolve()
        outside = [name for name, path in found.items() if bundle not in Path(path).resolve().parents]
        if outside:
            raise RuntimeError(f"not taken from the app bundle: {', '.join(outside)}")
    report["tools"] = found


def _check_render_and_ocr(report):
    from PIL import Image, ImageDraw, ImageFont
    from pdf2image import convert_from_path
    import pytesseract
    from rendering.renderer import TEMPLATE_DIR
    from scanning.split_by_student import ROOT

    font = ImageFont.truetype(str(TEMPLATE_DIR / "NotoSansSC-VF.ttf"), 120)
    page = Image.new("RGB", (1240, 1754), "white")
    ImageDraw.Draw(page).text((150, 300), OCR_SAMPLE, fill="black", font=font)
    with tempfile.TemporaryDirectory(prefix="marking-self-check-") as folder:
        pdf = Path(folder) / "sample.pdf"
        page.save(pdf, resolution=150)
        rendered = convert_from_path(str(pdf), dpi=150, first_page=1, last_page=1)[0]
    os.environ["TESSDATA_PREFIX"] = str(ROOT / "tessdata")
    text = pytesseract.image_to_string(rendered, lang="chi_sim", config="--psm 6")
    matched = sum(char in text for char in OCR_SAMPLE)
    if matched < len(OCR_SAMPLE) - 1:
        raise RuntimeError(f"OCR read {text.strip()!r}, expected {OCR_SAMPLE!r}")
    report["ocr_text"] = text.strip()


def _check_resources(report):
    from grading.schemas import ROOT, Validator
    from rendering.renderer import PillowRenderer
    Validator(ROOT / "config")
    PillowRenderer()
    for relative in ("grading/skills/sol-grader/SKILL.md", "grading/references/reference_example_v1.md",
                     "tessdata/chi_sim.traineddata", "split_by_student.py"):
        if not (ROOT / relative).is_file():
            raise RuntimeError(f"missing {relative}")


def _check_interface(report):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import qInstallMessageHandler
    from desktop.__main__ import create_app
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    try:
        app, engine, bridge = create_app([sys.argv[0]])
    except RuntimeError as exc:
        raise RuntimeError("; ".join([str(exc), *messages])) from None
    finally:
        qInstallMessageHandler(None)
    report["qml_windows"] = len(engine.rootObjects())
    bridge.shutdown()


def run(result_path: Path) -> int:
    from app_paths import ROOT, data_root, is_frozen
    report = {"frozen": is_frozen(), "bundle": str(ROOT), "data_root": str(data_root()), "checks": {}}
    for name, check in (("tools", _check_tools), ("render_and_ocr", _check_render_and_ocr),
                        ("resources", _check_resources), ("interface", _check_interface)):
        try:
            check(report)
            report["checks"][name] = "ok"
        except Exception as exc:  # the report must name every failure, not just the first
            report["checks"][name] = f"FAILED: {type(exc).__name__}: {exc}"
            report.setdefault("tracebacks", {})[name] = traceback.format_exc()
    report["ok"] = all(value == "ok" for value in report["checks"].values())
    Path(result_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
