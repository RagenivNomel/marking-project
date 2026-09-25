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

Install the desktop and core Python dependencies, then launch the desktop application:

```powershell
python -m pip install -r requirements-desktop.txt
python -B -m desktop
```

Scanning additionally requires the packages in `requirements-scanning.txt` and
locally installed Tesseract and Poppler executables. Real grading requires a
configured external grading provider and its locally managed credentials.

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
