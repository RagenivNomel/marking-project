"""ChatGPT-authenticated, isolated Codex CLI boundary for configured models."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Callable, Sequence
import uuid

from pdf2image import convert_from_bytes

from .sol_grader import CredentialUnavailable, ModelCallError, SUPPORTED_MODELS, SolGradingInput


def _marking_trace(message):
    if os.environ.get("MUMS_MARKING_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[codex] {message}", file=sys.stderr, flush=True)


class CodexUnavailable(CredentialUnavailable):
    """The supported Codex CLI or ChatGPT authentication is unavailable."""


class CodexInvocationError(ModelCallError):
    """The isolated Codex process failed before returning usable output."""


def _default_runner(command: Sequence[str], **kwargs):
    return subprocess.run(list(command), **kwargs)


def _minimal_environment() -> dict[str, str]:
    """Keep only values needed to start Codex and reach its saved ChatGPT auth."""
    allowed = {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
        "USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def resolve_codex_executable(configured: str) -> str:
    """Find the installed Windows CLI when the desktop launcher lacks Codex's PATH."""
    if Path(configured).is_absolute():
        return configured
    found = shutil.which(configured)
    if found:
        # CreateProcess can search a different PATH from shutil.which when a
        # minimal subprocess environment is supplied. Pass the exact file.
        return str(Path(found).resolve())
    if os.name != "nt" or configured.lower() not in {"codex", "codex.exe"}:
        return configured
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return configured
    bin_root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
    try:
        installed = [path / "codex.exe" for path in bin_root.iterdir()
                     if path.is_dir() and (path / "codex.exe").is_file()]
        if installed:
            return str(max(installed, key=lambda path: path.stat().st_mtime))
    except OSError:
        pass
    return configured


def render_pdf_pages(pdf_bytes: bytes, workspace: Path, dpi: int) -> list[Path]:
    """Render the selected PDF deterministically into ordered PNG attachments."""
    pdftoppm = shutil.which("pdftoppm")
    poppler_path = str(Path(pdftoppm).parent) if pdftoppm else None
    pages = convert_from_bytes(
        pdf_bytes,
        dpi=dpi,
        fmt="png",
        thread_count=1,
        strict=True,
        poppler_path=poppler_path,
    )
    if not pages:
        raise CodexInvocationError("PDF rendering produced no pages")
    paths = []
    for index, page in enumerate(pages, start=1):
        path = workspace / f"page_{index:03d}.png"
        page.save(path, format="PNG", optimize=False)
        paths.append(path)
    return paths


class CodexSolGrader:
    """Structural Grader implementation backed by a fresh `codex exec` process."""

    def __init__(
        self,
        *,
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "medium",
        timeout_seconds: int = 180,
        codex_executable: str = "codex",
        render_dpi: int = 200,
        process_runner: Callable = _default_runner,
        page_renderer: Callable[[bytes, Path, int], list[Path]] = render_pdf_pages,
        workspace_parent: Path | None = None,
    ):
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported Codex calibration model: {model}")
        if reasoning_effort not in SUPPORTED_MODELS[model]:
            raise ValueError(f"Unsupported reasoning effort {reasoning_effort!r} for {model}")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.codex_executable = resolve_codex_executable(codex_executable)
        self.render_dpi = render_dpi
        self.process_runner = process_runner
        self.page_renderer = page_renderer
        self.workspace_parent = Path(workspace_parent) if workspace_parent else None

    def _check(self, arguments: list[str]):
        _marking_trace(f"preflight executable={self.codex_executable!r} args={arguments!r}")
        try:
            result = self.process_runner(
                [self.codex_executable, *arguments],
                cwd=None,
                input=None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=_minimal_environment(),
                check=False,
            )
            _marking_trace(f"preflight returncode={result.returncode}")
            return result
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            _marking_trace(f"preflight exception={type(exc).__name__}: {exc}")
            if os.environ.get("MUMS_MARKING_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}:
                traceback.print_exc(file=sys.stderr)
            raise CodexUnavailable(f"Codex CLI preflight failed: {type(exc).__name__}") from None

    def ensure_ready(self):
        status = self._check(["login", "status"])
        if status.returncode != 0 or "logged in using chatgpt" not in (status.stdout + status.stderr).lower():
            raise CodexUnavailable("Codex CLI is not authenticated with ChatGPT")
        catalog = self._check(["debug", "models", "--bundled"])
        if catalog.returncode != 0:
            raise CodexUnavailable("Codex CLI model catalog is unavailable")
        try:
            models = json.loads(catalog.stdout)["models"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise CodexUnavailable("Codex CLI returned an invalid bundled model catalog") from None
        model_entry = next((item for item in models if item.get("slug") == self.model), None)
        if model_entry is None or "image" not in model_entry.get("input_modalities", []):
            raise CodexUnavailable(f"Codex CLI does not advertise image-capable {self.model}")
        supported_levels = {
            level.get("effort") for level in model_entry.get("supported_reasoning_levels", [])
            if isinstance(level, dict)
        }
        if supported_levels and self.reasoning_effort not in supported_levels:
            raise CodexUnavailable(f"Codex CLI does not advertise {self.reasoning_effort} reasoning for {self.model}")

    def _command(self, workspace: Path, schema_path: Path, output_path: Path, images: list[Path]) -> list[str]:
        command = [
            self.codex_executable,
            "--ask-for-approval", "never",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--strict-config",
            "--model", self.model,
            "--config", f'model_reasoning_effort="{self.reasoning_effort}"',
            "--config", 'web_search="disabled"',
            "--config", "features.shell_tool=false",
            "--config", "features.multi_agent=false",
            "--config", "features.plugins=false",
            "--config", "features.hooks=false",
            "--config", 'history.persistence="none"',
            "--sandbox", "read-only",
            "--cd", str(workspace),
            "--output-schema", str(schema_path),
            "--output-last-message", str(output_path),
            "--color", "never",
        ]
        for path in images:
            command.extend(["--image", str(path)])
        command.append("-")
        return command

    def grade(self, request: SolGradingInput) -> dict:
        """Run one ephemeral process. This method has no retry path."""
        parent = self.workspace_parent or Path(tempfile.gettempdir())
        parent.mkdir(parents=True, exist_ok=True)
        workspace = (parent / f"marking-codex-sol-{uuid.uuid4().hex}").resolve()
        workspace.mkdir()
        try:
            schema_path = workspace / "schema.json"
            output_path = workspace / "result.json"
            schema_path.write_text(
                json.dumps(request.response_schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            images = self.page_renderer(request.pdf_bytes, workspace, self.render_dpi)
            expected = {schema_path.resolve(), *(Path(path).resolve() for path in images)}
            actual = {path.resolve() for path in workspace.iterdir()}
            if actual != expected or any(path.parent != workspace for path in expected):
                raise CodexInvocationError("Isolated workspace contains unexpected input files")
            command = self._command(workspace, schema_path, output_path, images)
            try:
                completed = self.process_runner(
                    command,
                    cwd=str(workspace),
                    input=request.prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    env=_minimal_environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise CodexInvocationError(f"Codex CLI timed out after {self.timeout_seconds} seconds") from None
            except (FileNotFoundError, OSError) as exc:
                raise CodexInvocationError(f"Codex CLI failed to start: {type(exc).__name__}") from None
            if completed.returncode != 0:
                diagnostic = (completed.stderr or completed.stdout or "").strip()
                detail = f": {diagnostic[:2000]}" if diagnostic else ""
                raise CodexInvocationError(f"Codex CLI exited with code {completed.returncode}{detail}")
            if not output_path.is_file():
                raise CodexInvocationError("Codex CLI produced no final output file")
            return {
                "provider": "codex_cli_chatgpt",
                "model": self.model,
                "status": "completed",
                "output_text": output_path.read_text(encoding="utf-8"),
            }
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
