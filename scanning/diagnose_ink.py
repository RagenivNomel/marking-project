"""Invoke the original diagnostic script without changing its defaults."""
from pathlib import Path
import runpy


def main():
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "diagnose_ink.py"), run_name="__main__")


if __name__ == "__main__":
    main()
