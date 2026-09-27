"""Task identity and teacher-facing output paths for one composition task.

A task is identified by the bytes of its continuous scan, never by where the
file lives. A split pile's ``_continuous.pdf`` is a byte copy of that scan, so
the developer import path and the normal upload resolve to the same task.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from application.models import AssignmentSource


@dataclass(frozen=True)
class TaskOutputPaths:
    results_directory: Path
    workbook: Path
    feedback_cards_directory: Path


_digests: dict[tuple[str, int, int], str] = {}


def content_digest(path) -> str:
    """SHA-256 of a file, cached while its size and modification time hold."""
    path = Path(path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _digests:
        digest = sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        _digests[key] = digest.hexdigest()
    return _digests[key]


def safe_name(stem: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.\-一-鿿]+", "_", stem).strip("._") or "scan"


def task_scan(source: AssignmentSource) -> Path:
    """The continuous scan whose bytes identify this task."""
    if source.continuous_scan is not None:
        return Path(source.continuous_scan)
    if source.split_pile is not None:
        return Path(source.split_pile) / "_continuous.pdf"
    raise ValueError("A continuous scan or prepared composition folder is required")


def task_id(source: AssignmentSource) -> str:
    return "task_" + content_digest(task_scan(source))[:20]


def task_output_paths(source: AssignmentSource) -> TaskOutputPaths:
    """Place one task's teacher outputs beside its scan, named for that scan.

    ``<folder>/Results/<scan name>-<8 hash characters>/`` keeps each scan's
    workbook and cards apart even when several scans share a folder or a
    scan is replaced at the same path.
    """
    digest = content_digest(task_scan(source))
    if source.continuous_scan is not None:
        scan = Path(source.continuous_scan).expanduser().resolve()
        parent, stem = scan.parent, scan.stem
    else:
        pile = Path(source.split_pile).expanduser().resolve()
        parent, stem = pile, pile.name
    results = parent / "Results" / f"{safe_name(stem)}-{digest[:8]}"
    return TaskOutputPaths(
        results_directory=results,
        workbook=results / "results.xlsx",
        feedback_cards_directory=results / "Feedback Cards",
    )
