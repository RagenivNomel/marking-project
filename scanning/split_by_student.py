"""Adapter to the untouched known-good root splitter.

OCR is retained for its existing boundary-deduplication heuristic only.
Final identity is never inferred here. Native scan dependencies remain optional.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def legacy_splitter():
    spec = importlib.util.spec_from_file_location("_preserved_splitter", ROOT / "split_by_student.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan_anonymous(piles, outdir, tessdata_dir=ROOT / "tessdata"):
    """Use a new output directory to prevent overwriting working scans."""
    engine = legacy_splitter()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=False)
    master = outdir / "_continuous.pdf"
    pages = engine.build_continuous_pdf(piles, master)
    analysis = engine.analyze_front_pages(master, tessdata_dir=str(tessdata_dir))
    boundaries = engine.detect_student_boundaries(analysis)
    neutral = [(page, f"submission{index:03d}") for index, (page, _) in enumerate(boundaries, 1)]
    written = engine.split_into_students(master, neutral, str(outdir))
    for index, (entry, (_, raw_name)) in enumerate(zip(written, boundaries), 1):
        target = outdir / f"submission_{index:03d}.pdf"
        Path(entry["file"]).rename(target)
        entry.update(file=str(target), raw_ocr_name=raw_name)
    manifest = engine.write_manifest(written, str(outdir))
    return {"continuous_pages": pages, "boundaries": boundaries, "written": written, "manifest_path": manifest}
