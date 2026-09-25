"""Read-only validation of one rendered feedback card receipt."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from workflow.storage import read_json


def _resolved(value: object, base: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path claim is missing")
    path = Path(value)
    return (base / path if not path.is_absolute() else path).resolve()


def inspect_card(
    receipt_path: Path,
    workbook: Path,
    job_id: str,
    excel_row: int,
    input_digest: str,
    approved_values: dict,
    expected_teacher_output: Path | None = None,
) -> tuple[bool, str, str]:
    """Validate a receipt and its claimed PNG against current approved values."""
    receipt_path = Path(receipt_path)
    try:
        if not receipt_path.is_file():
            return False, "CARD_MISSING", f"Receipt does not exist: {receipt_path}"
        receipt = read_json(receipt_path)
        if not isinstance(receipt, dict):
            raise ValueError("receipt must be an object")
        if receipt.get("status") != "PASS":
            raise ValueError("receipt status is not PASS")
        source = receipt.get("source")
        if not isinstance(source, dict) or source.get("source_of_truth") != "approved_excel_row":
            raise ValueError("receipt source_of_truth is not approved_excel_row")

        if (source.get("job_id") != job_id
                or source.get("excel_row") != excel_row
                or source.get("input_digest") != input_digest):
            return False, "RECEIPT_SOURCE_MISMATCH", "Receipt source job, Excel row, or input digest differs"
        expected_workbook = Path(workbook).resolve()
        actual_workbook = _resolved(source.get("workbook"), receipt_path.parent)
        if actual_workbook != expected_workbook:
            return False, "RECEIPT_SOURCE_MISMATCH", (
                f"Receipt workbook is {actual_workbook}; expected {expected_workbook}"
            )
        if receipt.get("approved_excel_values") != approved_values:
            return False, "CARD_STALE", "Receipt approved_excel_values differ from the current approved row"

        output = receipt.get("output")
        if not isinstance(output, dict):
            raise ValueError("receipt output must be an object")
        card_path = _resolved(output.get("artifact"), receipt_path.parent)
        if not card_path.is_file():
            return False, "CARD_MISSING", f"Claimed card does not exist: {card_path}"
        claimed_hash = output.get("sha256")
        if not isinstance(claimed_hash, str) or not claimed_hash:
            raise ValueError("claimed card SHA-256 is missing")
        image_bytes = card_path.read_bytes()
        actual_hash = hashlib.sha256(image_bytes).hexdigest()
        if actual_hash != claimed_hash:
            return False, "CARD_HASH_MISMATCH", "Claimed card SHA-256 does not match the file"

        width, height = output.get("width"), output.get("height")
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError("claimed card dimensions are invalid")
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format != "PNG":
                raise ValueError("claimed card is not a PNG")
            image.verify()
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format != "PNG" or image.size != (width, height):
                raise ValueError("PNG dimensions do not match the receipt")

        teacher_output = receipt.get("teacher_output")
        if expected_teacher_output is not None:
            expected_teacher_output = Path(expected_teacher_output).resolve()
            if not isinstance(teacher_output, dict):
                return False, "CARD_PUBLISH_MISSING", "Teacher-facing card publication is not recorded"
            published_path = _resolved(teacher_output.get("artifact"), receipt_path.parent)
            if published_path != expected_teacher_output:
                return False, "CARD_PUBLISH_MISMATCH", (
                    f"Published card is {published_path}; expected {expected_teacher_output}"
                )
            if not published_path.is_file():
                return False, "CARD_PUBLISH_MISSING", f"Teacher-facing card does not exist: {published_path}"
            published_hash = teacher_output.get("sha256")
            if not isinstance(published_hash, str) or not published_hash:
                raise ValueError("published card SHA-256 is missing")
            actual_published_hash = hashlib.sha256(published_path.read_bytes()).hexdigest()
            if actual_published_hash != published_hash or actual_published_hash != actual_hash:
                return False, "CARD_PUBLISH_HASH_MISMATCH", "Teacher-facing card differs from the verified render"
        elif teacher_output is not None:
            if not isinstance(teacher_output, dict):
                raise ValueError("teacher_output must be an object")
            published_path = _resolved(teacher_output.get("artifact"), receipt_path.parent)
            if not published_path.is_file():
                return False, "CARD_PUBLISH_MISSING", f"Teacher-facing card does not exist: {published_path}"
            published_hash = teacher_output.get("sha256")
            if not isinstance(published_hash, str) or hashlib.sha256(published_path.read_bytes()).hexdigest() != published_hash:
                return False, "CARD_PUBLISH_HASH_MISMATCH", "Teacher-facing card hash does not match the receipt"
        return True, "", ""
    except Exception as exc:
        return False, "CARD_INVALID", str(exc)
