# Marking Project

Desktop workflow for Secondary 2 Higher Chinese composition marking.

## Workflow

PDF/roster intake → identity resolution → marking → results workbook → teacher review → APPROVED → feedback generation

## Source layout

- `application/` — application workflows and task coordination.
- `desktop/` — desktop interface, UI assets, and desktop integration.
- `workflow/`, `scanning/`, `grading/`, and `excel/` — workflow state, input handling, grading, and workbook logic.
- `rendering/` — feedback-card renderer and its templates.
- `config/` — workflow and grading configuration.
- `tests/` — automated tests; `examples/` — fictional input data.
- `tessdata/` — Chinese OCR language data.

## Development setup

[Pixi](https://pixi.sh) installs everything, including Python, Poppler and
Tesseract, from the versions locked in `pixi.lock`. No admin rights or
Homebrew are needed.

```
pixi run app     # start the app from source
pixi run test    # run the unit tests
```

Without pixi, install `requirements-desktop.txt` with pip and provide Tesseract
and Poppler yourself. Real marking uses the Codex CLI signed in with ChatGPT on
the same computer (`codex login`).

## Building a release

Releases are built on the computer they are for: the macOS `.dmg` on a Mac,
the Windows `.zip` on Windows. From a fresh clone:

1. Install pixi.
   - macOS: `curl -fsSL https://pixi.sh/install.sh | sh`, then open a new Terminal.
   - Windows: `winget install prefix-dev.pixi`, then open a new terminal.
2. `pixi run build`

The build runs the tests, packages the app with PyInstaller, bundles Poppler
and Tesseract, and self-checks the packaged app with a bare PATH, as a Finder
or desktop-shortcut launch would have. The release file lands in `dist/`.
Raise `version` in `pixi.toml` before building a new release.

On Windows, clone into a short folder path such as `C:\src\marking-project`: Qt's
plugin paths inside the environment otherwise pass Windows' 260-character limit.

Installing a release:

- macOS: open the `.dmg` and drag Marking App to Applications. The app is not
  notarised, so the first launch is blocked once: open System Settings →
  Privacy & Security and choose Open Anyway.
- Windows: unzip anywhere and run `Marking App.exe`.

The installed app keeps its work in `~/Library/Application Support/Marking App`
(macOS) or `%LOCALAPPDATA%\Marking App` (Windows), so replacing the app with a
newer version keeps it.

## Tests

The repository-safe unit tests are expected to run on a clean clone:

```powershell
python -B -X utf8 -m unittest discover -s tests -v
python -B -X utf8 -m unittest discover -s desktop/tests -v
```

Some historical regression and acceptance checks optionally use local-only
fixtures from `output/`, `backups/phase1_originals/`, pile folders, and roster
files. These datasets are intentionally excluded from Git. Affected tests report
`SKIPPED: local regression fixture not installed` when the authorized local
fixtures are absent; with those fixtures installed, the existing assertions run
normally. Renderer regression workbooks can be selected with
`PHASE1_RENDER_MOCK_WORKBOOK` and `PHASE1_RENDER_TEACHER_WORKBOOK`. Acceptance
report scripts use the same explicit skip message.

## Privacy

Never commit real student data, jobs, outputs, or grading records. Operational data is intentionally local-only.

## Third-party software

The packaged app bundles Qt for Python (PySide6, LGPL-3.0), Poppler (GPL-2.0-or-later),
Tesseract (Apache-2.0), the Noto Sans SC font (OFL-1.1) and other open-source
components. Each build collects their licences, versions and source locations into
`licenses/THIRD-PARTY-NOTICES.txt` inside the app (`packaging/collect_licenses.py`).
