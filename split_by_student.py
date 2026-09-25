#!/usr/bin/env python3
"""
Full pipeline for a class set of double-sided essays scanned in multiple
piles on a simplex-only ADF, split into one named PDF per student.

STEP 1 - Merge each pile's front/back batch into correct reading order,
then concatenate all piles (in scan order) into one continuous master PDF.
(The back batch of each pile comes out reversed because the whole stack
was flipped as a unit before the second scanning pass.)

STEP 2 - Every front-facing page (0-indexed 0, 2, 4, ...) carries the
printed header template (school crest + "姓名(中文):" name line + grading
box). Only the TRUE first page of each student's essay has an actual
handwritten name in that zone; continuation pages reuse the blank
template. For each front-facing page we:
    - measure ink density in a generous "name zone" crop (wide enough to
      catch a name written slightly above/around the printed line, which
      happens in practice)
    - OCR that zone to get a best-effort name string

STEP 3 - Walk front-facing pages in order. A page starts a NEW student
when its name zone has ink AND the OCR'd name is not a close match to the
immediately preceding student's name (handles students who habitually
rewrite their name on every page — that repeat is deduped, not split).
A blank name zone never starts a new student (it's a continuation page).

STEP 4 - Split the master PDF at the detected boundaries and save each
student's pages as a PDF named after their (sanitized) recognized name,
disambiguating collisions. A manifest CSV records the OCR confidence
situation for quick manual double-checking, since handwriting OCR is not
perfectly reliable.

Requirements: pypdf, pdf2image (poppler/pdftoppm), pytesseract + a Chinese
tesseract language pack (chi_sim.traineddata under TESSDATA_PREFIX), pillow,
numpy.

Usage:
    python3 split_by_student.py \
        --piles front1.pdf:back1.pdf front2.pdf:back2.pdf ... \
        --outdir /path/to/output_folder \
        --tessdata /path/to/tessdata/dir
"""

import argparse
import csv
import difflib
import os
import re
import sys

from pypdf import PdfReader, PdfWriter


# ---- Layout constants (as fractions of page width/height) --------------
# Tight crop on just the "姓名(中文):____" line itself (excludes the school
# crest/title text above, which is printed on every front page and would
# otherwise wash out the signal between a written name and a blank page).
# Tight zone on just the handwritten name itself (below the school crest/
# title, which is printed on every front page and must NOT be included here
# — including it makes every OCR'd string share "NANYANG GIRLS HIGH SCHOOL"
# and falsely look "similar" to every other student's name during dedup).
NAME_ZONE = (0.19, 0.070, 0.51, 0.118)  # (x0, y0, x1, y1) as fractions
OCR_ZONE = NAME_ZONE
INK_BG_THRESHOLD = 225
INK_FRACTION_THRESHOLD = 0.042
NAME_SIMILARITY_THRESHOLD = 0.5
OCR_DPI = 250


def interleave_front_back(front_pages, back_pages):
    n = len(front_pages)
    if n != len(back_pages):
        raise ValueError(
            f"Front pile has {n} pages but back pile has {len(back_pages)} pages; "
            "they must match one-to-one."
        )
    ordered = []
    for i in range(n):
        ordered.append(front_pages[i])
        ordered.append(back_pages[n - 1 - i])
    return ordered


def build_continuous_pdf(pile_specs, out_path):
    writer = PdfWriter()
    total = 0
    for front_path, back_path in pile_specs:
        front_reader = PdfReader(front_path)
        back_reader = PdfReader(back_path)
        ordered = interleave_front_back(front_reader.pages, back_reader.pages)
        for page in ordered:
            writer.add_page(page)
            total += 1
    with open(out_path, "wb") as f:
        writer.write(f)
    return total


def _zone_box_px(img_size, zone_fractions):
    w, h = img_size
    x0, y0, x1, y1 = zone_fractions
    return (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))


def ink_fraction(img, box):
    import numpy as np
    crop = img.crop(box).convert("RGB")
    arr = np.array(crop).astype(int)
    non_bg = (arr < INK_BG_THRESHOLD).any(axis=2)
    return float(non_bg.mean())


def ocr_name(img, box, tessdata_dir=None):
    import pytesseract
    crop = img.crop(box).convert("L")
    crop = crop.resize((crop.width * 2, crop.height * 2))

    # Set TESSDATA_PREFIX only for the duration of this call, then restore
    # whatever was there before. This avoids the config-string approach,
    # which breaks when tessdata_dir contains spaces (common on Windows,
    # e.g. "C:\Users\...\marking project\tessdata") because pytesseract
    # splits the config string on whitespace without shell-style quoting.
    previous = os.environ.get("TESSDATA_PREFIX")
    try:
        if tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = tessdata_dir
        text = pytesseract.image_to_string(crop, lang="chi_sim", config="--psm 6")
    finally:
        if tessdata_dir:
            if previous is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = previous

    cleaned = re.sub(r"[^\u4e00-\u9fff A-Za-z]", "", text).strip()
    return cleaned


def analyze_front_pages(pdf_path, tessdata_dir=None):
    from pdf2image import convert_from_path

    images = convert_from_path(pdf_path, dpi=OCR_DPI)
    results = []
    for i, img in enumerate(images):
        is_front = (i % 2 == 0)
        entry = {"page_idx": i, "is_front": is_front, "ink_frac": None, "name_text": None}
        if is_front:
            box = _zone_box_px(img.size, NAME_ZONE)
            entry["ink_frac"] = ink_fraction(img, box)
            if entry["ink_frac"] >= INK_FRACTION_THRESHOLD:
                ocr_box = _zone_box_px(img.size, OCR_ZONE)
                entry["name_text"] = ocr_name(img, ocr_box, tessdata_dir=tessdata_dir)
        results.append(entry)
    return results


def names_similar(a, b):
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= NAME_SIMILARITY_THRESHOLD


def detect_student_boundaries(page_analysis):
    """A new boundary starts at every ink-positive front page UNLESS it is
    immediately adjacent (no blank continuation page in between) to the
    previous boundary's ink-positive page AND the name text matches — that
    specific combination is the signature of a student habitually rewriting
    their name on every page of the SAME essay.

    Critically: if there is a blank continuation page anywhere in between,
    the next ink-positive page is always a new boundary, even if the name
    text is identical to a previous student's — because that's exactly what
    a second, separate submission from the same person looks like (their own
    essay ended with the usual blank continuation pages, then a fresh header
    with their name starts again). Matching name text alone must never
    merge two submissions that have a real gap between them.
    """
    boundaries = []
    current_name = None
    seen_blank_since_last_boundary = False

    for entry in page_analysis:
        if not entry["is_front"]:
            continue
        has_ink = entry["ink_frac"] is not None and entry["ink_frac"] >= INK_FRACTION_THRESHOLD
        if not has_ink:
            seen_blank_since_last_boundary = True
            continue

        name_text = entry["name_text"] or ""

        if not boundaries or seen_blank_since_last_boundary:
            is_new_boundary = True
        else:
            is_new_boundary = not (current_name is not None and names_similar(current_name, name_text))

        if is_new_boundary:
            boundaries.append((entry["page_idx"], name_text))
            current_name = name_text
        seen_blank_since_last_boundary = False

    if not boundaries or boundaries[0][0] != 0:
        first_name = page_analysis[0].get("name_text") or ""
        boundaries.insert(0, (0, first_name))

    return boundaries


def sanitize_filename(name, fallback):
    name = name.strip()
    if not name:
        return fallback
    name = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", name)
    return name if name else fallback


def save_name_preview(pdf_path, page_idx, outdir):
    """Save a crop of the name zone for a given page, for quick manual
    eyeballing/correction of the OCR'd filename."""
    from pdf2image import convert_from_path

    preview_dir = os.path.join(outdir, "_name_previews")
    os.makedirs(preview_dir, exist_ok=True)
    images = convert_from_path(pdf_path, dpi=OCR_DPI, first_page=page_idx + 1, last_page=page_idx + 1)
    img = images[0]
    box = _zone_box_px(img.size, OCR_ZONE)
    crop = img.crop(box)
    preview_path = os.path.join(preview_dir, f"page{page_idx + 1}_name.png")
    crop.save(preview_path)
    return preview_path


def split_into_students(pdf_path, boundaries, outdir, tessdata_dir=None):
    reader = PdfReader(pdf_path)
    n_pages = len(reader.pages)
    bounds = boundaries + [(n_pages, None)]

    os.makedirs(outdir, exist_ok=True)
    written = []
    used_names = {}

    for idx in range(len(bounds) - 1):
        start, raw_name = bounds[idx]
        end = bounds[idx + 1][0]
        if start >= end:
            continue

        fallback = f"student_{idx + 1:02d}"
        base_name = sanitize_filename(raw_name or "", fallback)

        count = used_names.get(base_name, 0)
        used_names[base_name] = count + 1
        final_name = base_name if count == 0 else f"{base_name}_{count + 1}"

        writer = PdfWriter()
        for p in range(start, end):
            writer.add_page(reader.pages[p])
        out_path = os.path.join(outdir, f"{final_name}.pdf")
        with open(out_path, "wb") as f:
            writer.write(f)

        preview_path = save_name_preview(pdf_path, start, outdir)

        written.append({
            "file": out_path,
            "pages": end - start,
            "raw_ocr_name": raw_name or "",
            "start_page_idx": start,
            "name_preview": preview_path,
        })
    return written


def write_manifest(written, outdir):
    manifest_path = os.path.join(outdir, "_manifest.csv")
    with open(manifest_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "pages", "raw_ocr_name", "start_page_idx", "name_preview"])
        for row in written:
            writer.writerow([row["file"], row["pages"], row["raw_ocr_name"],
                              row["start_page_idx"], row["name_preview"]])
    return manifest_path


def run_pipeline(pile_specs, outdir, tessdata_dir=None, continuous_path=None):
    """Deterministic end-to-end pipeline: same pile_specs + outdir + tessdata_dir
    always produce the same boundaries, the same output files, and the same
    manifest content. No hidden state (no randomness, no wall-clock-dependent
    behavior, no reliance on filesystem iteration order) — every input that
    affects the result is an explicit argument.

    pile_specs: list of (front_path, back_path) tuples, in scan order.
    outdir: folder for per-student PDFs + manifest + name previews.
    tessdata_dir: directory containing chi_sim.traineddata.
    continuous_path: where to write the full merged PDF; if None, a
        temporary path inside outdir is used and removed afterward.

    Returns a dict with keys: 'continuous_pages', 'boundaries', 'written',
    'manifest_path'.
    """
    os.makedirs(outdir, exist_ok=True)
    keep_continuous = continuous_path is not None
    resolved_continuous_path = continuous_path or os.path.join(outdir, "_continuous.pdf")

    total_pages = build_continuous_pdf(pile_specs, resolved_continuous_path)

    page_analysis = analyze_front_pages(resolved_continuous_path, tessdata_dir=tessdata_dir)
    boundaries = detect_student_boundaries(page_analysis)

    written = split_into_students(resolved_continuous_path, boundaries, outdir, tessdata_dir=tessdata_dir)
    manifest_path = write_manifest(written, outdir)

    if not keep_continuous:
        os.remove(resolved_continuous_path)

    return {
        "continuous_pages": total_pages,
        "boundaries": boundaries,
        "written": written,
        "manifest_path": manifest_path,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--piles", nargs="+", required=True,
                         help="One or more 'front.pdf:back.pdf' pairs, in scan order.")
    parser.add_argument("--outdir", required=True, help="Folder for per-student PDFs.")
    parser.add_argument("--tessdata", default=None,
                         help="Directory containing chi_sim.traineddata (sets TESSDATA_PREFIX).")
    parser.add_argument("--continuous-out", default=None,
                         help="Optional path to also keep the full continuous merged PDF.")
    args = parser.parse_args()

    pile_specs = []
    for pile in args.piles:
        try:
            front_path, back_path = pile.split(":")
        except ValueError:
            print(f"Bad --piles entry (need front.pdf:back.pdf): {pile}", file=sys.stderr)
            sys.exit(1)
        pile_specs.append((front_path, back_path))

    result = run_pipeline(
        pile_specs,
        args.outdir,
        tessdata_dir=args.tessdata,
        continuous_path=args.continuous_out,
    )

    print(f"Built continuous PDF: {result['continuous_pages']} pages")
    print(f"Detected {len(result['boundaries'])} students at page boundaries: "
          f"{[(b[0], b[1]) for b in result['boundaries']]}")

    print(f"Wrote {len(result['written'])} student files (manifest: {result['manifest_path']}):")
    for row in result["written"]:
        print(f"  {row['file']}  ({row['pages']} pages, OCR name: {row['raw_ocr_name']!r})")


if __name__ == "__main__":
    main()
