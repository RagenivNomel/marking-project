"""Deterministic student-card rendering over the approved raster master."""
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

from grading.schemas import CRITERIA, RATINGS, ValidationError
from workflow.storage import atomic_json


RENDERER_VERSION = "pillow-renderer-v1.3"
TEMPLATE_DIR = Path(__file__).resolve().parent / "template"
LAYOUT_PATH = TEMPLATE_DIR / "layout_v1_2.json"
REQUIRED_FIELDS = {
    "class_name", "student_id", "student_name", "topic", "content_score",
    "language_structure_score", "total_score", "teacher_comment",
    *(f"criteria.{name}.{part}" for name in CRITERIA for part in ("rating", "short_comment")),
}


class Renderer(Protocol):
    def render(self, record, output_dir: Path, audit: dict | None = None) -> Path: ...


class RenderLayoutError(ValidationError):
    """The fixed layout cannot represent the approved source record safely."""


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _validate_layout(layout: dict) -> dict:
    if not isinstance(layout, dict):
        raise RenderLayoutError("Layout must be an object")
    layout_version = layout.get("layout_version")
    if layout_version not in ("layout-v1", "layout-v1.1", "layout-v1.2"):
        raise RenderLayoutError("Unsupported layout version")
    if layout_version == "layout-v1.2":
        alignment = layout.get("vertical_alignment", {})
        expected_fields = [
            "class_name", "student_id", "student_name", "topic",
            "content_score", "language_structure_score", "total_score",
        ]
        if (set(alignment) != {"glyph_center_fields"}
                or alignment["glyph_center_fields"] != expected_fields):
            raise RenderLayoutError("Layout v1.2 glyph-centering fields are invalid")
    canvas = layout.get("canvas", {})
    if canvas != {"width": 1024, "height": 1536}:
        raise RenderLayoutError("Layout canvas must be exactly 1024x1536")
    master = layout.get("master", {})
    if set(master) != {"filename", "version", "sha256", "width", "height"}:
        raise RenderLayoutError("Layout master metadata is incomplete")
    if master["width"] != 1024 or master["height"] != 1536 or len(master["sha256"]) != 64:
        raise RenderLayoutError("Layout master dimensions or hash are invalid")
    if layout.get("criteria_order") != list(CRITERIA):
        raise RenderLayoutError("Layout criterion order does not match the fixed contract")
    font = layout.get("font", {})
    if (set(font) != {"path", "family", "fallback", "sha256", "weight", "rating_weight"}
            or font["fallback"] is not False):
        raise RenderLayoutError("Layout must pin one font, explicit weights and fallback disabled")
    if not isinstance(font["sha256"], str) or len(font["sha256"]) != 64:
        raise RenderLayoutError("Layout font SHA-256 is invalid")
    if (type(font["weight"]) is not int or not 100 <= font["weight"] <= 900
            or type(font["rating_weight"]) is not int or not 100 <= font["rating_weight"] <= 900):
        raise RenderLayoutError("Layout font weights must be integers from 100 through 900")
    rating_control = layout.get("rating_control", {})
    if set(rating_control) != {"arrow_x", "min_arrow_clearance"}:
        raise RenderLayoutError("Layout rating control geometry is incomplete")
    if (type(rating_control["arrow_x"]) is not int or not 0 <= rating_control["arrow_x"] <= 1024
            or type(rating_control["min_arrow_clearance"]) is not int
            or rating_control["min_arrow_clearance"] <= 0):
        raise RenderLayoutError("Layout rating control geometry is invalid")
    fields = layout.get("fields", {})
    if set(fields) != REQUIRED_FIELDS:
        missing = sorted(REQUIRED_FIELDS - set(fields))
        extra = sorted(set(fields) - REQUIRED_FIELDS)
        raise RenderLayoutError(f"Layout field mapping mismatch; missing={missing}, extra={extra}")
    base_field_keys = {"box", "padding", "font_size", "line_height", "align", "wrap", "max_lines"}
    for name, spec in fields.items():
        if set(spec) not in (base_field_keys, base_field_keys | {"font_tiers"}):
            raise RenderLayoutError(f"Layout field specification incomplete: {name}")
        box = spec["box"]
        padding = spec["padding"]
        if (not isinstance(box, list) or len(box) != 4 or any(type(value) is not int for value in box)
                or box[0] < 0 or box[1] < 0 or box[2] <= 0 or box[3] <= 0
                or box[0] + box[2] > 1024 or box[1] + box[3] > 1536):
            raise RenderLayoutError(f"Layout field box is invalid: {name}")
        if (not isinstance(padding, list) or len(padding) != 4 or any(type(value) is not int or value < 0 for value in padding)
                or padding[0] + padding[2] >= box[2] or padding[1] + padding[3] >= box[3]):
            raise RenderLayoutError(f"Layout field padding is invalid: {name}")
        if (type(spec["font_size"]) is not int or spec["font_size"] <= 0
                or type(spec["line_height"]) is not int or spec["line_height"] <= 0
                or spec["align"] not in ("left", "center") or type(spec["wrap"]) is not bool
                or type(spec["max_lines"]) is not int or spec["max_lines"] <= 0):
            raise RenderLayoutError(f"Layout field typography is invalid: {name}")
        if "font_tiers" in spec:
            tiers = spec["font_tiers"]
            if not isinstance(tiers, list) or not tiers:
                raise RenderLayoutError(f"Layout font tiers are invalid: {name}")
            expected_first = {
                "font_size": spec["font_size"],
                "line_height": spec["line_height"],
                "max_lines": spec["max_lines"],
            }
            if tiers[0] != expected_first:
                raise RenderLayoutError(f"Layout font tiers must start with the base tier: {name}")
            for tier in tiers:
                if (set(tier) != {"font_size", "line_height", "max_lines"}
                        or type(tier["font_size"]) is not int or tier["font_size"] <= 0
                        or type(tier["line_height"]) is not int or tier["line_height"] <= 0
                        or type(tier["max_lines"]) is not int or tier["max_lines"] <= 0):
                    raise RenderLayoutError(f"Layout font tier is invalid: {name}")
    return layout


def load_layout(path=LAYOUT_PATH) -> dict:
    path = Path(path)
    layout = _validate_layout(json.loads(path.read_text(encoding="utf-8")))
    master_path = path.parent / layout["master"]["filename"]
    if not master_path.is_file():
        raise RenderLayoutError(f"Visual master is missing: {master_path.name}")
    with Image.open(master_path) as master:
        if master.size != (layout["master"]["width"], layout["master"]["height"]):
            raise RenderLayoutError(f"Visual master dimensions changed: {master.size}")
    actual_hash = _file_sha256(master_path)
    if actual_hash != layout["master"]["sha256"]:
        raise RenderLayoutError("Visual master SHA-256 does not match Layout v1")
    font_path = Path(layout["font"]["path"])
    if not font_path.is_absolute():
        font_path = path.parent / font_path
    if not font_path.is_file():
        raise RenderLayoutError(f"Pinned Chinese font is unavailable: {font_path}")
    if _file_sha256(font_path) != layout["font"]["sha256"]:
        raise RenderLayoutError("Pinned Chinese font SHA-256 does not match Layout v1")
    return {**layout, "_path": str(path.resolve()), "_master_path": str(master_path.resolve()), "_font_path": str(font_path.resolve())}


def _display_value(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _record_values(record) -> dict:
    if getattr(record, "review_status", None) != "APPROVED":
        raise RenderLayoutError("Only an APPROVED Excel record can be rendered")
    criteria = getattr(record, "criteria", None)
    if not isinstance(criteria, dict) or tuple(criteria) != CRITERIA:
        raise RenderLayoutError("Approved record must contain exactly eight criteria in contract order")
    values = {
        "class_name": record.class_name,
        "student_id": record.student_id,
        "student_name": record.student_name,
        "topic": record.topic,
        "content_score": record.content_score,
        "language_structure_score": record.language_structure_score,
        "total_score": record.total_score,
        "teacher_comment": record.teacher_comment,
    }
    for name in CRITERIA:
        item = criteria[name]
        rating = getattr(item, "rating", None)
        comment = getattr(item, "short_comment", None)
        if rating not in RATINGS:
            raise RenderLayoutError(f"{name}: invalid rating {rating!r}")
        if not isinstance(comment, str) or not comment.strip():
            raise RenderLayoutError(f"{name}: comment is empty")
        values[f"criteria.{name}.rating"] = rating
        values[f"criteria.{name}.short_comment"] = comment
    for name in ("class_name", "student_id", "student_name", "topic", "teacher_comment"):
        if values[name] is not None and not isinstance(values[name], str):
            raise RenderLayoutError(f"{name}: expected text")
    return values


def _wrap_text(draw, text, font, width, max_lines, wrap, field_name):
    if not text:
        return []
    paragraphs = text.split("\n")
    lines = []
    for paragraph in paragraphs:
        if not paragraph:
            lines.append("")
            continue
        if not wrap:
            if draw.textlength(paragraph, font=font) > width:
                raise RenderLayoutError(f"{field_name}: text exceeds assigned width")
            lines.append(paragraph)
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and draw.textlength(candidate, font=font) > width:
                lines.append(current)
                current = char
            elif not current and draw.textlength(candidate, font=font) > width:
                raise RenderLayoutError(f"{field_name}: one character exceeds assigned width")
            else:
                current = candidate
        lines.append(current)
    if len(lines) > max_lines:
        raise RenderLayoutError(f"{field_name}: {len(lines)} lines exceed maximum {max_lines}")
    return lines


def _atomic_png(image: Image.Image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".png")
    os.close(fd)
    try:
        image.save(temporary, format="PNG", optimize=False, compress_level=6)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class PillowRenderer:
    """Render approved Excel values onto the fixed Visual Master v1."""
    def __init__(self, layout_path=LAYOUT_PATH):
        self.layout = load_layout(layout_path)

    def _font(self, spec, is_rating):
        weight_key = "rating_weight" if is_rating else "weight"
        weight = self.layout["font"][weight_key]
        font = ImageFont.truetype(
            self.layout["_font_path"], spec["font_size"], layout_engine=ImageFont.Layout.BASIC
        )
        try:
            font.set_variation_by_axes([weight])
        except (AttributeError, OSError) as exc:
            raise RenderLayoutError("Pinned Noto Sans SC font does not expose the required weight axis") from exc
        return font, weight

    @staticmethod
    def _font_tiers(spec):
        return spec.get("font_tiers", [{
            "font_size": spec["font_size"],
            "line_height": spec["line_height"],
            "max_lines": spec["max_lines"],
        }])

    def _draw_field(self, draw, values, name, spec, field_status):
        raw = values[name]
        text = _display_value(raw)
        box_x, box_y, box_w, box_h = spec["box"]
        pad_left, pad_top, pad_right, pad_bottom = spec["padding"]
        width = box_w - pad_left - pad_right
        height = box_h - pad_top - pad_bottom
        is_rating = name.endswith(".rating")
        selected = None
        last_error = None
        for tier_index, tier in enumerate(self._font_tiers(spec)):
            tier_spec = {**spec, **tier}
            try:
                font, font_weight = self._font(tier_spec, is_rating)
                lines = _wrap_text(draw, text, font, width, tier_spec["max_lines"], spec["wrap"], name)
                if lines and len(lines) * tier_spec["line_height"] > height:
                    raise RenderLayoutError(f"{name}: text line height exceeds assigned bounds")
                # The complete wrapped block is measured first. Its Y is derived only
                # from this field's own fixed box; no previous row participates.
                block_height = len(lines) * tier_spec["line_height"]
                start_y = box_y + pad_top
                visual_centered = (
                    name in self.layout.get("vertical_alignment", {}).get("glyph_center_fields", [])
                    and len(lines) == 1
                )
                if lines and not visual_centered:
                    start_y += (height - block_height) // 2
                content_bounds = (box_x + pad_left, box_y + pad_top,
                                  box_x + box_w - pad_right, box_y + box_h - pad_bottom)
                # Pillow's glyph bearings can extend a pixel beyond the text
                # origin. The full fixed field box is the clipping boundary;
                # padding remains part of the layout measurement, not a crop.
                allowed = (box_x, box_y, box_x + box_w, box_y + box_h)
                line_widths = []
                line_positions = []
                glyph_bounds = []
                if visual_centered:
                    line_width = draw.textlength(lines[0], font=font)
                    start_x = box_x + pad_left
                    if spec["align"] == "center":
                        start_x += (width - line_width) / 2
                    probe_bounds = draw.textbbox((start_x, 0), lines[0], font=font, anchor="lt")
                    glyph_height = probe_bounds[3] - probe_bounds[1]
                    visual_start_y = box_y + pad_top + (height - glyph_height) / 2 - probe_bounds[1]
                    start_y = int(round(visual_start_y))
                for index, line in enumerate(lines):
                    line_width = draw.textlength(line, font=font)
                    line_widths.append(line_width)
                    start_x = box_x + pad_left
                    if spec["align"] == "center":
                        start_x += (width - line_width) / 2
                    y = start_y + index * tier_spec["line_height"]
                    line_positions.append({"x": start_x, "y": y})
                    bounds = draw.textbbox((start_x, y), line, font=font, anchor="lt")
                    glyph_bounds.append(list(bounds))
                    if (bounds[0] < allowed[0] or bounds[1] < allowed[1]
                            or bounds[2] > allowed[2] or bounds[3] > allowed[3]):
                        raise RenderLayoutError(f"{name}: rendered glyphs leave assigned bounds")
                arrow_clearance = None
                if is_rating and lines:
                    arrow_x = self.layout["rating_control"]["arrow_x"]
                    arrow_clearance = arrow_x - max(bounds[2] for bounds in glyph_bounds)
                    if arrow_clearance < self.layout["rating_control"]["min_arrow_clearance"]:
                        raise RenderLayoutError(f"{name}: rating text is too close to the fixed arrow")
                selected = (tier_index, tier_spec, font, font_weight, lines, block_height,
                            start_y, content_bounds, line_widths, line_positions,
                            glyph_bounds, arrow_clearance)
                break
            except RenderLayoutError as exc:
                last_error = exc
        if selected is None:
            raise last_error or RenderLayoutError(f"{name}: no approved font tier fits")
        (tier_index, tier_spec, font, font_weight, lines, block_height, start_y,
         content_bounds, line_widths, line_positions, glyph_bounds, arrow_clearance) = selected
        visual_top = min(bounds[1] for bounds in glyph_bounds) if glyph_bounds else None
        visual_bottom = max(bounds[3] for bounds in glyph_bounds) if glyph_bounds else None
        visual_centered = (
            name in self.layout.get("vertical_alignment", {}).get("glyph_center_fields", [])
            and len(lines) == 1
        )
        for index, line in enumerate(lines):
            position = line_positions[index]
            draw.text((position["x"], position["y"]), line, font=font,
                      fill=(8, 39, 82), anchor="lt")
        field_status[name] = {
            "source_value": raw,
            "rendered_text": text,
            "line_count": len(lines),
            "block_top": start_y if lines else None,
            "block_height": block_height,
            "block_bottom": start_y + block_height if lines else None,
            "free_space_top": start_y - content_bounds[1] if lines else None,
            "free_space_bottom": content_bounds[3] - (start_y + block_height) if lines else None,
            "vertical_alignment": "glyph_center" if visual_centered else "block_center",
            "visual_free_space_top": visual_top - box_y if lines else None,
            "visual_free_space_bottom": box_y + box_h - visual_bottom if lines else None,
            "line_widths": line_widths,
            "line_positions": line_positions,
            "glyph_bounds": glyph_bounds,
            "font_weight": font_weight,
            "font_tier": tier_index,
            "font_size": tier_spec["font_size"],
            "line_height": tier_spec["line_height"],
            "max_lines": tier_spec["max_lines"],
            "text_box": list(spec["box"]),
            "arrow_x": self.layout["rating_control"]["arrow_x"] if is_rating else None,
            "arrow_clearance": arrow_clearance,
            "fits": True,
        }

    def render(self, record, output_dir: Path, audit: dict | None = None) -> Path:
        values = _record_values(record)
        master_path = Path(self.layout["_master_path"])
        with Image.open(master_path) as master:
            image = master.convert("RGB")
        draw = ImageDraw.Draw(image)
        field_status = {}
        for name in ("class_name", "student_id", "student_name", "topic", "content_score", "language_structure_score", "total_score"):
            self._draw_field(draw, values, name, self.layout["fields"][name], field_status)
        for criterion in CRITERIA:
            for part in ("rating", "short_comment"):
                name = f"criteria.{criterion}.{part}"
                self._draw_field(draw, values, name, self.layout["fields"][name], field_status)
        self._draw_field(draw, values, "teacher_comment", self.layout["fields"]["teacher_comment"], field_status)

        output_dir = Path(output_dir)
        artifact_filename = (audit or {}).get("artifact_filename", "student_card.png")
        if (not isinstance(artifact_filename, str) or not artifact_filename.endswith(".png")
                or Path(artifact_filename).name != artifact_filename
                or any(char in artifact_filename for char in '<>:"/\\|?*')
                or artifact_filename.rstrip(" .") != artifact_filename):
            raise RenderLayoutError("Artifact filename must be a safe PNG basename")
        card_path = output_dir / artifact_filename
        receipt_path = output_dir / "render_receipt.json"
        _atomic_png(image, card_path)
        output_hash = _file_sha256(card_path)
        receipt = {
            "renderer": RENDERER_VERSION,
            "status": "PASS",
            "source": dict(audit or {}),
            "master": {
                "version": self.layout["master"]["version"],
                "filename": self.layout["master"]["filename"],
                "sha256": self.layout["master"]["sha256"],
                "width": self.layout["master"]["width"],
                "height": self.layout["master"]["height"],
            },
            "layout_version": self.layout["layout_version"],
            "layout_sha256": _file_sha256(Path(self.layout["_path"])),
            "font": {
                "family": self.layout["font"]["family"],
                "path": self.layout["_font_path"],
                "sha256": self.layout["font"]["sha256"],
                "weight": self.layout["font"]["weight"],
                "rating_weight": self.layout["font"]["rating_weight"],
            },
            "rating_control": dict(self.layout["rating_control"]),
            "fields": field_status,
            "approved_excel_values": record.to_dict(),
            "output": {
                "artifact": str(card_path.resolve()),
                "sha256": output_hash,
                "width": image.width,
                "height": image.height,
            },
        }
        atomic_json(receipt_path, receipt)
        return receipt_path


class MockRenderer:
    """Phase 1 JSON-only test renderer retained for existing workflow tests."""
    def render(self, record, output_dir: Path, audit: dict | None = None) -> Path:
        path = Path(output_dir) / "mock_render.json"
        payload = {"renderer": "mock-json-v1", "approved_excel_values": record.to_dict()}
        if audit:
            payload["source"] = dict(audit)
        atomic_json(path, payload)
        return path
