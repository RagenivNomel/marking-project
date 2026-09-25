"""Thin naming adapter for the existing approved-Excel diagnostic renderer."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from workflow.storage import atomic_json, read_json


_INVALID_WINDOWS_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _filename_part(value: object) -> str:
    value = "" if value is None else str(value).strip()
    value = _INVALID_WINDOWS_FILENAME.sub("_", value).rstrip(" .")
    if not value or value in {".", ".."}:
        raise ValueError("Student identity cannot form a safe feedback-card filename")
    return value


def feedback_card_filename(record) -> str:
    """Return the frozen Stage 3C filename for one Excel-approved student."""
    if getattr(record, "review_status", None) != "APPROVED":
        raise ValueError("Only an APPROVED Excel row can be named for rendering")
    parts = (_filename_part(record.class_name), _filename_part(record.student_id),
             _filename_part(record.student_name))
    return "-".join(parts) + "-作文体检卡.png"


def feedback_card_filename_for_identity(identity) -> str:
    """Build the same stable name from Stage 1's already-verified identity."""
    parts = (_filename_part(identity.class_name), _filename_part(identity.student_id),
             _filename_part(identity.student_name))
    return "-".join(parts) + "-作文体检卡.png"


def publish_card_receipt(receipt_path, published_output_dir, filename):
    """Publish the verified PNG while keeping its receipt beside the internal render."""
    receipt_path = Path(receipt_path).resolve()
    published_output_dir = Path(published_output_dir).resolve()
    receipt = read_json(receipt_path)
    output = receipt.get("output")
    if not isinstance(output, dict):
        raise ValueError("Renderer receipt has no output record")
    artifact = Path(output["artifact"])
    if not artifact.is_absolute():
        artifact = receipt_path.parent / artifact
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise FileNotFoundError("Rendered feedback card is missing")

    published_output_dir.mkdir(parents=True, exist_ok=True)
    published = published_output_dir / filename
    data = artifact.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{published.stem}-", suffix=".tmp", dir=published.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, published)
    finally:
        Path(temporary).unlink(missing_ok=True)

    receipt["teacher_output"] = {
        "artifact": str(published.resolve()),
        "sha256": digest,
    }
    atomic_json(receipt_path, receipt)
    return receipt_path


class ApprovedFeedbackRenderer:
    """Pass deterministic output naming through to the production renderer.

    Rendering and layout remain entirely in PillowRenderer. This adapter only
    supplies the Stage 3C artifact basename in its audit metadata.
    """

    def __init__(self, renderer, published_output_dir=None):
        self.renderer = renderer
        self.published_output_dir = (Path(published_output_dir).resolve()
                                     if published_output_dir is not None else None)

    def render(self, record, output_dir, audit=None):
        metadata = dict(audit or {})
        metadata["artifact_filename"] = feedback_card_filename(record)
        receipt_path = Path(self.renderer.render(record, output_dir, metadata)).resolve()
        if self.published_output_dir is None:
            return receipt_path
        return publish_card_receipt(
            receipt_path, self.published_output_dir, feedback_card_filename(record),
        )
