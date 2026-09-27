"""Where the app keeps its working data and finds the native tools it runs.

An installed app cannot write beside its own code, and an app opened from
Finder or a desktop shortcut does not get the PATH of a terminal. Everything
that depends on either of those facts goes through this module.
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
APP_NAME = "Marking App"
DATA_DIR_ENV = "MARKING_APP_DATA"
BUNDLED_BIN = ROOT / "vendor" / "bin"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> Path:
    """The per-user folder an installed app keeps its jobs and outputs in."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def data_root() -> Path:
    """Writable root for jobs, outputs and identity confirmations.

    Running from source keeps the project folder, so existing tasks stay where
    they are. An installed app uses the per-user folder. ``MARKING_APP_DATA``
    overrides both, which lets the installed layout be tried from source.
    """
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return user_data_dir() if is_frozen() else ROOT


def _well_known_tool_dirs() -> list[Path]:
    if sys.platform == "darwin":
        return [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    if os.name == "nt":
        return [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR"]
    return []


def add_native_tools_to_path() -> None:
    """Let pdf2image, pytesseract and Codex find their executables.

    Tools bundled with the app come first; the usual install locations are
    appended so a launcher with a minimal PATH still finds Homebrew or the
    Windows Tesseract installer.
    """
    current = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    bundled = [BUNDLED_BIN]
    if is_frozen() and os.name == "nt":
        # PyInstaller puts the tools' DLLs beside the app's own, one level up.
        bundled.append(ROOT)
    bundled = [str(path) for path in bundled if path.is_dir() and str(path) not in current]
    known = [str(path) for path in _well_known_tool_dirs() if path.is_dir() and str(path) not in current]
    os.environ["PATH"] = os.pathsep.join(bundled + current + known)
