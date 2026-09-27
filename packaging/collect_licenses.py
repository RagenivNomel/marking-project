"""Gather the licences of everything the packaged app bundles.

Writes build/licenses/: THIRD-PARTY-NOTICES.txt (every component, its
version, licence and source) plus each component's own licence files. The
packaged app ships this folder as `licenses/`. Run by packaging/build.py
inside the pixi environment, after `pixi install`, so the package cache
holds each conda package's licence files.
"""
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "build" / "licenses"
QT_TEXTS = ROOT / "packaging" / "licenses"
# Only needed to build the app, not shipped in it.
BUILD_ONLY = {"setuptools", "pip", "wheel", "altgraph", "macholib", "pefile", "pywin32-ctypes",
              "pyinstaller-hooks-contrib"}


def _recipe_source(package_dir: Path):
    for name in ("recipe/meta.yaml", "recipe/recipe.yaml"):
        recipe = package_dir / "info" / name
        if recipe.is_file():
            text = recipe.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"source:.*?\burl:\s*(\S+)", text, re.S)
            if match and "{{" not in match.group(1) and "${{" not in match.group(1):
                return match.group(1)
    return None


def conda_packages(problems):
    entries = []
    for record_path in sorted((Path(sys.prefix) / "conda-meta").glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        name, version = record["name"], record["version"]
        package_dir = Path(record.get("extracted_package_dir") or "")
        about_path = package_dir / "info" / "about.json"
        about = json.loads(about_path.read_text(encoding="utf-8")) if about_path.is_file() else {}
        licence_dir = package_dir / "info" / "licenses"
        folder = f"conda/{name}-{version}"
        if not package_dir.is_dir():
            problems.append(f"{name} {version}: package not in the cache ({package_dir})")
        elif licence_dir.is_dir():
            shutil.copytree(licence_dir, TARGET / folder, dirs_exist_ok=True)
        else:
            folder = None  # the package itself ships no licence file (e.g. metapackages)
        entries.append({
            "name": name, "version": version,
            "license": record.get("license") or about.get("license") or "unknown",
            "home": about.get("home"), "source": _recipe_source(package_dir),
            "package": record.get("url"), "files": folder,
        })
    return entries


def python_packages():
    entries = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        if name.lower().replace("_", "-") in BUILD_ONLY:
            continue
        folder = f"python/{name}-{dist.version}"
        if name.lower().startswith(("pyside6", "shiboken6")):
            # The wheels carry only Qt's commercial licence file; this app uses
            # Qt under the LGPL, whose texts are in qt/.
            entries.append({"name": name, "version": dist.version, "license": "LGPL-3.0-only",
                            "home": "https://pyside.org", "files": "qt"})
            continue
        for file in dist.files or ():
            parts = [part.lower() for part in file.parts]
            if any(part.startswith(("license", "licence", "copying", "notice")) for part in parts) \
                    or (file.parent.name.endswith(".dist-info") and "licen" in file.name.lower()):
                source = Path(file.locate())
                if source.is_file():
                    destination = TARGET / folder / Path(*file.parts[1:] or file.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
        licence = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
        if len(licence) > 120 or not licence.strip():
            classifiers = [value.split("::")[-1].strip() for value in dist.metadata.get_all("Classifier") or ()
                           if value.startswith("License ::")]
            licence = " / ".join(classifiers) or "see licence files"
        entries.append({"name": name, "version": dist.version, "license": licence,
                        "home": dist.metadata.get("Home-page") or _project_url(dist), "files": folder})
    return entries


def _project_url(dist):
    for value in dist.metadata.get_all("Project-URL") or ():
        label, _, url = value.partition(",")
        if label.strip().lower() in {"homepage", "home", "source", "source code", "repository"}:
            return url.strip()
    return None


def write_notices(conda, python):
    lines = [
        "Marking App: third-party software notices",
        "",
        "The Marking App bundles the components below. Each keeps its own licence;",
        "the licence files are in the folder named for each component.",
        "",
        "Qt for Python (PySide6, shiboken6) is used under the GNU LGPL v3",
        "(see qt/LGPL-3.0.txt and qt/GPL-3.0.txt). Its libraries are separate files",
        "inside the app and can be replaced with a modified build of the same version.",
        "",
        "Components under the GNU GPL, such as Poppler, are included as separate",
        "programs. Their complete source code is available from the source address",
        "listed for each one, and from its conda-forge package recipe.",
        "",
        "=" * 72,
        "Native programs and libraries (conda-forge)",
        "=" * 72,
    ]
    for entry in conda:
        lines += ["", f"{entry['name']} {entry['version']}", f"  Licence: {entry['license']}"]
        if entry["home"]:
            lines.append(f"  Home:    {entry['home']}")
        if entry["source"]:
            lines.append(f"  Source:  {entry['source']}")
        lines.append(f"  Package: {entry['package']}")
        if entry["files"]:
            lines.append(f"  Files:   {entry['files']}/")
    lines += ["", "=" * 72, "Python packages", "=" * 72]
    for entry in python:
        lines += ["", f"{entry['name']} {entry['version']}", f"  Licence: {entry['license']}"]
        if entry["home"]:
            lines.append(f"  Home:    {entry['home']}")
        lines.append(f"  Files:   {entry['files']}/")
    (TARGET / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(strict=True):
    shutil.rmtree(TARGET, ignore_errors=True)
    TARGET.mkdir(parents=True)
    shutil.copytree(QT_TEXTS, TARGET / "qt")
    shutil.copy2(ROOT / "rendering" / "template" / "NotoSansSC-OFL.txt", TARGET / "NotoSansSC-OFL.txt")
    problems = []
    conda, python = conda_packages(problems), python_packages()
    write_notices(conda, python)
    print(f"    {len(conda)} native and {len(python)} Python components -> {TARGET.relative_to(ROOT)}")
    if problems and strict:
        raise SystemExit("Packages missing from the pixi package cache; run `pixi clean cache` and rebuild:\n  "
                         + "\n  ".join(problems))
    return TARGET


if __name__ == "__main__":
    main()
