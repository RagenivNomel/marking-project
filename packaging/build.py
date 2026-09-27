"""Build a release of the Marking App for this computer: `pixi run build`.

1. Run the unit tests (skip with --skip-tests).
2. Package the app with PyInstaller from the locked pixi environment.
3. Run the packaged app's --self-check with a bare PATH, as a Finder or
   desktop-shortcut launch would get, so it must rely on what it bundles.
4. Write the release file to dist/: a .dmg on macOS, a .zip on Windows.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = ROOT / "dist"
APP_NAME = "Marking App"


def step(message):
    print(f"\n==> {message}", flush=True)


def run(command, **kwargs):
    print("   ", " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], check=True, **kwargs)


def version():
    with open(ROOT / "pixi.toml", "rb") as handle:
        return tomllib.load(handle)["workspace"]["version"]


def warn_about_local_changes():
    try:
        changes = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                                 capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return
    if changes:
        print("WARNING: building with uncommitted changes; this build will not match GitHub:\n" + changes)


def run_tests():
    step("Running unit tests")
    for folder in ("tests", "desktop/tests"):
        run([sys.executable, "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", folder], cwd=ROOT)


def package(app_version):
    step("Packaging with PyInstaller")
    env = dict(os.environ, MARKING_APP_VERSION=app_version)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", BUILD / "dist", "--workpath", BUILD / "work",
         ROOT / "packaging" / "marking_app.spec"], cwd=ROOT, env=env)
    if sys.platform == "darwin":
        app = BUILD / "dist" / f"{APP_NAME}.app"
        # Ad-hoc signature: required on Apple Silicon. Not notarised, so the
        # first launch needs Open Anyway in System Settings.
        run(["codesign", "--force", "--deep", "--sign", "-", app])
        run(["codesign", "--verify", "--deep", "--strict", app])
        return app, app / "Contents" / "MacOS" / APP_NAME
    folder = BUILD / "dist" / APP_NAME
    return folder, folder / f"{APP_NAME}.exe"


def bare_environment():
    keep = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
            "HOME", "TMPDIR", "USER", "LOGNAME", "LANG"}
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env["PATH"] = os.pathsep.join([str(Path(system_root) / "System32"), system_root])
    else:
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    return env


def self_check(executable):
    step("Self-checking the packaged app with a bare PATH")
    with tempfile.TemporaryDirectory(prefix="marking-build-") as folder:
        report_path = Path(folder) / "self-check.json"
        result = subprocess.run([str(executable), "--self-check", str(report_path)],
                                env=bare_environment(), timeout=300)
        if not report_path.is_file():
            raise SystemExit(f"Self-check wrote no report (exit code {result.returncode})")
        report = json.loads(report_path.read_text(encoding="utf-8"))
    for name, outcome in report["checks"].items():
        print(f"    {name:16} {outcome}")
    if result.returncode != 0 or not report.get("ok"):
        for name, trace in report.get("tracebacks", {}).items():
            print(f"\n--- {name} ---\n{trace}")
        raise SystemExit("Self-check failed; no release was written.")


def release(bundle, app_version):
    step("Writing the release file")
    DIST.mkdir(exist_ok=True)
    if sys.platform == "darwin":
        target = DIST / f"Marking-App-{app_version}-mac.dmg"
        with tempfile.TemporaryDirectory(prefix="marking-dmg-") as folder:
            stage = Path(folder)
            shutil.copytree(bundle, stage / bundle.name, symlinks=True)
            (stage / "Applications").symlink_to("/Applications")
            target.unlink(missing_ok=True)
            run(["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", stage,
                 "-format", "UDZO", "-ov", target])
    else:
        target = DIST / f"Marking-App-{app_version}-windows.zip"
        target.unlink(missing_ok=True)
        shutil.make_archive(str(target.with_suffix("")), "zip", bundle.parent, bundle.name)
    print(f"\nRelease ready: {target}  ({target.stat().st_size / 1e6:.0f} MB)")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-tests", action="store_true", help="package without running the unit tests")
    args = parser.parse_args()
    if not (Path(sys.prefix) / "conda-meta").is_dir():
        raise SystemExit("Run this through pixi: pixi run build")
    app_version = version()
    print(f"Building {APP_NAME} {app_version} for {sys.platform}")
    warn_about_local_changes()
    if not args.skip_tests:
        run_tests()
    bundle, executable = package(app_version)
    self_check(executable)
    release(bundle, app_version)


if __name__ == "__main__":
    main()
