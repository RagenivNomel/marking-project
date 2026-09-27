"""Suggest one roster student per submission from its paper header.

A vision model reads every header crop of a scan (name, class and
seat-number boxes) in one call and guesses one roster entry per submission. The guess only pre-selects the teacher's dropdown;
it is never a confirmed identity. Guesses are saved once per scan workspace,
so reopening a task makes no model calls.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from pdf2image import convert_from_path

from app_paths import data_root
from grading.schemas import Identity
from workflow.storage import atomic_json, read_json


# (x0, y0, x1, y1) as page fractions: the 姓名 / 班级 / 班号 lines on the
# front page, excluding the score box on the right.
HEADER_ZONE = (0.03, 0.065, 0.60, 0.165)
HEADER_DPI = 150
HEADER_DIR = "_header_previews"
SUGGESTIONS_FILE = "_identity_suggestions.json"
NO_MATCH = "NONE"


def _trace(message):
    if os.environ.get("MUMS_MARKING_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[roster-match] {message}", file=sys.stderr, flush=True)


def header_preview_path(pile: Path, submission) -> Path:
    return Path(pile) / HEADER_DIR / f"page{submission.start_page_idx + 1}_header.png"


def save_header_crop(pile: Path, submission) -> Path:
    target = header_preview_path(pile, submission)
    if target.is_file():
        return target
    page = submission.start_page_idx + 1
    image = convert_from_path(str(Path(pile) / "_continuous.pdf"), dpi=HEADER_DPI,
                              first_page=page, last_page=page)[0]
    width, height = image.size
    x0, y0, x1, y1 = HEADER_ZONE
    target.parent.mkdir(parents=True, exist_ok=True)
    image.crop((int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height))).save(target)
    return target


def _roster_key(identity: Identity) -> str:
    return f"{identity.class_name}|{identity.student_id}"


class CodexImageReader:
    """Run one isolated `codex exec` over a single image.

    Reuses the marking grader's readiness check and locked-down command line
    without changing the marking code itself.
    """

    def __init__(self, model="gpt-5.6-luna", reasoning_effort="low", timeout_seconds=300):
        from grading.codex_sol_grader import CodexSolGrader
        self.codex = CodexSolGrader(model=model, reasoning_effort=reasoning_effort,
                                    timeout_seconds=timeout_seconds)
        self.workspace_parent = data_root() / "jobs" / ".codex-workspaces"

    def ensure_ready(self):
        self.codex.ensure_ready()

    def read_images(self, prompt: str, schema: dict, images) -> str:
        from grading.codex_sol_grader import CodexInvocationError, _minimal_environment
        self.workspace_parent.mkdir(parents=True, exist_ok=True)
        workspace = (self.workspace_parent / f"roster-match-{uuid.uuid4().hex}").resolve()
        workspace.mkdir()
        try:
            schema_path, output_path = workspace / "schema.json", workspace / "result.json"
            schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            copies = []
            for index, source in enumerate(images, start=1):
                copies.append(workspace / f"image_{index:03d}{Path(source).suffix.lower()}")
                shutil.copyfile(source, copies[-1])
            try:
                completed = subprocess.run(
                    self.codex._command(workspace, schema_path, output_path, copies),
                    cwd=str(workspace), input=prompt, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=self.codex.timeout_seconds,
                    env=_minimal_environment(self.codex.codex_executable), check=False,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                raise CodexInvocationError(f"Codex CLI failed: {type(exc).__name__}") from None
            if completed.returncode != 0 or not output_path.is_file():
                detail = (completed.stderr or completed.stdout or "").strip()[:500]
                raise CodexInvocationError(f"Codex CLI exited with code {completed.returncode}: {detail}")
            return output_path.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(workspace, ignore_errors=True)


class CodexRosterMatcher:
    """One isolated Codex call that reads every header of a scan at once."""

    def __init__(self, grader=None):
        self.grader = grader or CodexImageReader()

    def ensure_ready(self):
        self.grader.ensure_ready()

    def guess_all(self, images: list[Path], roster: list[Identity]) -> list[Identity | None]:
        """Return one roster guess (or None) per image, in image order."""
        by_key = {_roster_key(item): item for item in roster}
        count = len(images)
        schema = {
            "type": "object",
            "properties": {"assignments": {
                "type": "array", "minItems": count, "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "integer", "minimum": 1, "maximum": count},
                        "read": {"type": "string"},
                        "student": {"type": "string", "enum": [*by_key, NO_MATCH]},
                    },
                    "required": ["image", "read", "student"],
                    "additionalProperties": False,
                },
            }},
            "required": ["assignments"],
            "additionalProperties": False,
        }
        lines = "\n".join(f"{key}  班级 {item.class_name}  班号 {item.student_id}  {item.student_name}"
                          for key, item in by_key.items())
        prompt = (
            f"The {count} attached images, numbered 1 to {count} in attachment order, are the "
            "headers of handwritten essays from one class: 姓名 (name), 班级 (class) and "
            "班号 (seat number). For each image, write what you can read in `read`, then "
            "pick the roster student who wrote it. Each student wrote at most one essay, "
            f"so avoid giving two images the same student. Use {NO_MATCH} when nothing is "
            "readable enough to guess. Return exactly one entry per image.\n\n"
            "Roster (key, class, seat number, name):\n" + lines
        )
        answer = json.loads(self.grader.read_images(prompt, schema, images))["assignments"]
        if sorted(item["image"] for item in answer) != list(range(1, count + 1)):
            raise ValueError("The model did not answer every image exactly once")
        for item in sorted(answer, key=lambda item: item["image"]):
            _trace(f"image {item['image']}: read {item['read']!r} -> {item['student']}")
        return [by_key.get(item["student"]) for item in sorted(answer, key=lambda item: item["image"])]


def read_suggestions(pile: Path) -> dict[str, dict | None]:
    path = Path(pile) / SUGGESTIONS_FILE
    if not path.is_file():
        return {}
    value = read_json(path)
    return value if isinstance(value, dict) else {}


def ensure_suggestions(pile: Path, submissions, roster: list[Identity], matcher):
    """Guess the whole scan in one call; reuse the saved guesses afterwards."""
    pile = Path(pile)
    files = [item.source_pdf for item in submissions]
    saved = read_suggestions(pile)
    if saved and set(saved) == set(files):
        return saved
    crops = [save_header_crop(pile, item) for item in submissions]
    matcher.ensure_ready()
    guesses = matcher.guess_all(crops, roster)
    suggestions = {
        source_pdf: ({"class_name": found.class_name, "student_id": found.student_id} if found else None)
        for source_pdf, found in zip(files, guesses)
    }
    atomic_json(pile / SUGGESTIONS_FILE, suggestions)
    return suggestions
