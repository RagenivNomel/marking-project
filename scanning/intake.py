"""Read an existing split pile without rescanning or assigning grades."""
from dataclasses import asdict, dataclass
import csv
import hashlib
from pathlib import Path

from pypdf import PdfReader

from grading.schemas import ValidationError
from scanning.identity import confirm_identity


MATCH_STATUSES = ("STRONG_ROSTER_MATCH", "CONFIRMATION_REQUIRED")


@dataclass(frozen=True)
class SplitSubmission:
    sequence: int
    source_pdf: str
    start_page_idx: int
    pages: int
    raw_ocr_name: str
    name_preview: str


def _page_digest(page):
    contents = page.get_contents()
    data = contents.get_data() if contents is not None else b""
    geometry = ":".join(str(value) for value in (
        page.mediabox.left, page.mediabox.bottom, page.mediabox.right, page.mediabox.top,
        page.get("/Rotate", 0),
    )).encode("ascii")
    return hashlib.sha256(geometry + b"\0" + data).hexdigest()


def read_existing_split(pile_dir):
    """Join renamed student PDFs back to manifest rows by PDF page content."""
    pile_dir = Path(pile_dir)
    manifest_path = pile_dir / "_manifest.csv"
    continuous_path = pile_dir / "_continuous.pdf"
    if not manifest_path.is_file() or not continuous_path.is_file():
        raise FileNotFoundError("Existing split requires _manifest.csv and _continuous.pdf")

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    by_start = {int(row["start_page_idx"]): row for row in manifest}
    if len(by_start) != len(manifest):
        raise ValidationError("Manifest contains duplicate start_page_idx values")

    continuous = PdfReader(str(continuous_path))
    continuous_hashes = [_page_digest(page) for page in continuous.pages]
    submissions = []
    used_starts = set()
    source_pdfs = sorted(path for path in pile_dir.glob("*.pdf") if not path.name.startswith("_"))
    for source_pdf in source_pdfs:
        reader = PdfReader(str(source_pdf))
        hashes = [_page_digest(page) for page in reader.pages]
        matches = [
            start for start in range(len(continuous_hashes) - len(hashes) + 1)
            if continuous_hashes[start:start + len(hashes)] == hashes
        ]
        if len(matches) != 1:
            raise ValidationError(f"{source_pdf.name}: expected one continuous-PDF match, found {matches}")
        start = matches[0]
        row = by_start.get(start)
        if row is None or int(row["pages"]) != len(hashes):
            raise ValidationError(f"{source_pdf.name}: PDF content does not agree with manifest")
        if start in used_starts:
            raise ValidationError(f"Duplicate submission at page index {start}")
        used_starts.add(start)
        submissions.append(SplitSubmission(
            sequence=0,
            source_pdf=source_pdf.name,
            start_page_idx=start,
            pages=len(hashes),
            raw_ocr_name=row.get("raw_ocr_name", ""),
            name_preview=Path(row.get("name_preview", "")).name,
        ))

    if used_starts != set(by_start):
        raise ValidationError("Manifest and student PDFs contain different submission starts")
    return [SplitSubmission(index, **{k: v for k, v in asdict(item).items() if k != "sequence"})
            for index, item in enumerate(sorted(submissions, key=lambda item: item.start_page_idx), 1)]


def apply_identity_decisions(submissions, roster, decisions, require_complete=True):
    """Attach reviewed roster candidates while retaining confirmation status.

    Production intake keeps the historical all-or-nothing contract by default.
    The teacher confirmation workspace may persist a reviewed subset and ask
    Stage 1 to project the remaining submissions as unresolved.  Unknown files,
    duplicate decision rows, invalid roster identities, and duplicate strong
    assignments remain rejected in both modes.
    """
    by_file = {item["source_pdf"]: item for item in decisions}
    submission_files = {item.source_pdf for item in submissions}
    if len(by_file) != len(decisions) or not set(by_file).issubset(submission_files):
        raise ValidationError("Identity decisions contain duplicate or unknown submissions")
    if require_complete and set(by_file) != submission_files:
        raise ValidationError("Identity decisions must cover every submission exactly once")
    result = []
    strong_keys = set()
    for submission in submissions:
        if submission.source_pdf not in by_file:
            continue
        decision = by_file[submission.source_pdf]
        status = decision.get("match_status")
        if status not in MATCH_STATUSES:
            raise ValidationError(f"{submission.source_pdf}: invalid match status")
        identity = confirm_identity(roster, str(decision["class_name"]), str(decision["student_id"]))
        key = (identity.class_name, identity.student_id)
        if status == "STRONG_ROSTER_MATCH":
            if key in strong_keys:
                raise ValidationError(f"Duplicate strong roster match: {key}")
            strong_keys.add(key)
        result.append({
            **asdict(submission),
            **identity.to_dict(),
            "match_status": status,
            "evidence": str(decision["evidence"]),
        })
    return result
