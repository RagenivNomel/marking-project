"""Explicit skip helpers for optional local-only regression fixtures."""

from pathlib import Path


SKIP_REASON = "local regression fixture not installed"


def local_fixtures_available(paths):
    return all(Path(path).exists() for path in paths)


def require_local_fixtures(test_case, paths):
    if not local_fixtures_available(paths):
        test_case.skipTest(SKIP_REASON)


def report_local_fixture_skip(paths):
    if local_fixtures_available(paths):
        return False
    print(f"SKIPPED: {SKIP_REASON}")
    return True
