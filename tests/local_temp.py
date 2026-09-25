"""Project-local test directories that work in the managed Windows sandbox."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import uuid

from grading.schemas import ROOT


@contextmanager
def local_test_directory(prefix="case"):
    base = Path(os.environ.get("PHASE1_TEST_TEMP", ROOT / "test-workspace-temp")).resolve()
    base.relative_to(ROOT.resolve())
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{prefix}-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path)
