# Handoff

Last checked: 2026-09-26. This handoff describes the current working tree,
including the uncommitted changes; it is not a description of `origin/main`
alone.

## 1. What the app does and who it is for

This is a Windows-first desktop workflow for a teacher marking Secondary 2
Higher Chinese composition. The intended operator selects a continuous class
scan and roster, confirms student identities, runs isolated AI marking, reviews
and approves the results in Excel, and generates one feedback-card PNG per
approved essay.

The app is not offline: the configured real grader uses the Codex CLI and its
local ChatGPT/Codex authentication, or the separate Responses API backend when
configured. Excel remains the teacher-owned review and approval surface.

## 2. Tech stack and project structure

- Python, with `unittest` as the test framework. There is no `pyproject.toml`,
  package build, formatter, or linter configuration.
- PySide6 6.8.3 and Qt Quick/QML for the desktop shell. `desktop/__main__.py`
  creates the Qt application; `desktop/bridge.py` owns the Qt bridge and
  background workers; `desktop/qml/` contains the bilingual teacher UI and
  developer/QA views.
- `application/` is the application boundary for the supported
  `sec2_hcl_composition_v1` workflow. `controller.py` dispatches inspection,
  source preparation, marking, and approved-card rendering; `models.py` holds
  immutable source/inspection/action models; `workflows/` contains task storage,
  card evidence, rendering adapters, and the main composition workflow.
- `workflow/` contains durable state transitions, atomic JSON persistence and
  locks (`state.py`, `storage.py`), the mock/real batch pipeline
  (`pipeline.py`), and the one-student calibration pipeline.
- `scanning/` contains scan intake, identity matching, existing split-pile
  validation, and the new continuous-scan splitter. The root
  `split_by_student.py` is the older multi-pile CLI; do not confuse it with
  `scanning/split_by_student.py`.
- `grading/` contains schemas/validation, the mock grader, the Responses API
  grader, the Codex CLI grader, calibration schemas, and review interfaces.
  The active marking instructions are
  `grading/skills/sol-grader/SKILL.md`; the older prompt files remain for
  historical reference.
- `excel/` contains the authoritative workbook writer/reader, calibration
  workbook support, schema, and legacy roster/reference adapters.
- `rendering/` contains the Pillow feedback-card renderer and the pinned
  layout/font/visual-master assets under `rendering/template/`.
- `config/` contains criteria, text limits, rubric/schema, and
  `calibration_model.json` model profiles. `tessdata/chi_sim.traineddata` is
  the bundled Chinese OCR data.
- `tests/` is the backend/unit/regression suite; `desktop/tests/` covers Qt
  bridge, identity, Stage 3B execution, Stage 3C rendering, output paths, and
  teacher-flow projection. `examples/mock_student.json` is the fictional mock
  input.
- Root entry points: `app.py` only re-exports `Pipeline`; `run_pipeline.py`
  exposes mock, roster, intake, real-batch, and rerender CLI commands;
  `run_calibration.py` runs one controlled calibration; `launch-desktop.cmd`
  and `launch-desktop.ps1` launch the UI.

## 3. Install, run, and test locally

Run these from the project root in PowerShell:

```powershell
python -m pip install -r requirements-desktop.txt
python -B -X utf8 -m desktop
```

Equivalent launcher commands:

```powershell
.\launch-desktop.cmd
.\launch-desktop.cmd --language en
.\launch-desktop.cmd --dev-ui --demo marking
```

`requirements-desktop.txt` includes the core and scanning requirements and
pins `PySide6==6.8.3`. Continuous-scan intake additionally needs native
Tesseract and Poppler executables available on `PATH`; this repository does not
provide a system-package installation command for them. Real marking also
needs an authenticated/configured grading provider.

Repository tests:

```powershell
python -B -X utf8 -m unittest discover -s tests -v
python -B -X utf8 -m unittest discover -s desktop/tests -v
```

Useful CLI smoke commands that do not call a live model:

```powershell
python -B -X utf8 run_pipeline.py mock --input examples/mock_student.json --batch demo
python -B -X utf8 run_pipeline.py roster <path-to-roster.xlsx>
python -B -X utf8 run_pipeline.py intake --pile <split-pile> --workbook <roster.xlsx> --decisions <decisions.json>
```

The real CLI requires confirmed split-pile input and provider credentials:

```powershell
python -B -X utf8 run_pipeline.py real-batch --pile <split-pile> --workbook <roster.xlsx> --decisions <decisions.json> --model-profile luna_xhigh
```

Do not run that command against real student data as a smoke test. It can call
the configured model and writes jobs/workbooks.

## 4. Current state

### Working

- The normal teacher journey is implemented in the desktop shell: continuous
  scan PDF + roster intake, app-owned anonymous split workspace, identity
  confirmation, Stage 3B marking, Excel review handoff, and Stage 3C approved
  feedback-card generation.
- A new continuous-scan task currently writes teacher-facing outputs under the
  selected scan's containing folder:
  `Results/results.xlsx` and `Results/Feedback Cards/`. Historical tasks using
  `output/<batch>/results.xlsx` are still supported. If both locations exist,
  inspection blocks instead of guessing.
- Marking is isolated per student, can use up to three concurrent grader
  workers, and serializes authoritative workbook persistence. Saved rows are
  excluded from a later Continue operation.
- The renderer uses the current approved Excel values, fixed eight-criterion
  layout, pinned font/layout/visual-master assets, and receipts/hashes. It does
  not call the grader.
- Inspection is intended to be read-only. Opening the workbook or feedback-card
  folder through the desktop bridge must not execute workflow actions or mutate
  the selected file.

### Partially done / in progress

- The uncommitted work is the continuous-scan intake and deterministic task
  output change, plus diagnostic trace logging and related docs/tests. It has
  not been committed or split onto a feature branch.
- The broader product is not finished: no verified installer/portable release,
  no review-beside-the-paper view, no teacher settings editor or batch settings
  snapshot, no explicit regrading revision UI, no combined printable-PDF/export
  manifest, and no persistent recent-task index.
- Real production jobs intentionally stop at `VALIDATED` with a `PENDING` Excel
  row. Teacher approval is not automated, and a real batch is not marked
  `COMPLETE` by the current production path.
- Calibration jobs stopped at `GRADED` still need a safe saved-response
  revalidation path; the current pipeline refuses to continue that state.

### Broken or failing now

The available dependency-bearing Python runtime was used for the latest local
verification. The backend suite ran 127 tests with 8 failures, 11 errors, and
2 expected local-fixture skips. The desktop suite ran 58 tests with 4 failures
and 1 error. The plain system `python` in this environment has no third-party
packages, so the README test commands fail at import time until dependencies
are installed.

The failures include real current-worktree issues: malformed workbook rows hit
the wrong error path, validated/missing checkpoint inspection can advertise the
wrong next action, some real-batch resume/parallel cases lose a student result,
and several desktop Stage 3B cases mishandle cancellation, preflight failure,
or invalid workbook/audit evidence. Some backend errors are Windows
`PermissionError` failures during `workflow/storage.py` atomic `os.replace()`
operations, so verify whether file locking/antivirus/test cleanup is involved
before treating every one as a pure pipeline regression.

There is a definite bug at `application/workflows/sec2_hcl_composition_v1.py`
around line 329: the workbook-row `except Exception:` block references `exc`
without binding `except Exception as exc`. That turns malformed-row reporting
into a `NameError` and must be fixed before trusting workbook diagnostics.

No live model call or real-student production run was performed during this
handoff inspection.

## 5. Feature implementation report: direct continuous-scan intake

### Status at handoff

**Status: uncommitted work in progress; implemented across UI, application,
scanner adapter, tests, and documentation, but not ready to ship or commit.**

The feature-specific tests for creating/reusing an app-owned scan workspace,
inspecting a continuous scan without a teacher-supplied manifest, exporting
neutral submission names, and requiring scan + roster in the normal dialog are
passing. The complete backend and desktop suites still have regressions listed
below and in sections 4 and 8.

### Problem being solved

Before this change, the normal desktop journey expected the teacher to select a
folder that had already been split into student PDFs and contained the internal
continuous-PDF/manifest structure. That exposed implementation details and
required preparation outside the normal UI.

The intended experience is now:

1. Teacher chooses one continuous class-scan PDF.
2. Teacher chooses the class roster workbook.
3. The app copies and splits the scan into an internal workspace.
4. The app shows unresolved submissions for roster-backed identity confirmation.
5. After every submission is confirmed, the existing marking, Excel review,
   approval, and feedback-card stages continue unchanged.

Selecting the files must not start AI grading. It does perform local writes to
create the internal split workspace, so it is no longer a strictly read-only
inspection operation on first use.

### Implemented data flow

1. `desktop/qml/InspectPathsDialog.qml` presents a continuous-PDF picker and a
   roster picker in normal mode. Workbook, job, receipt, and legacy split-pile
   fields remain visible only in developer/import mode.
2. `DesktopBridge.inspectPaths()` normalizes QML file URLs into absolute
   `Path` values and constructs `AssignmentSource(continuous_scan=..., roster=...)`.
3. `ReadTask.run()` calls `WorkflowController.prepare_source()`, then
   `bind_source()`, before running normal inspection. This stays on a Qt worker
   so OCR/PDF preparation does not block the GUI thread.
4. `CompositionWorkflow.prepare_source()` verifies that the selected input is
   an existing `.pdf`, hashes its bytes, sanitizes its stem, and chooses:

       <scan folder>/.<safe scan stem>.essay-work-<first 12 SHA-256 characters>/

5. On first use, `scanning.split_by_student.split_continuous_anonymous()`:
   copies the source to `_continuous.pdf`, analyzes front pages with the
   existing OCR/ink heuristic, detects essay boundaries, writes neutral
   `submission_001.pdf` names, and writes `_manifest.csv` plus name previews.
   OCR text remains evidence and never becomes authoritative identity.
6. On reopen, the app does not split again. It verifies that `_continuous.pdf`
   has the same hash as the selected scan and calls `read_existing_split()` to
   validate page counts, ordering, uniqueness, and complete page coverage.
7. The prepared `AssignmentSource` receives the generated directory as
   `split_pile`. Existing identity review code then derives a deterministic
   decision-file path, reads the roster, and lets the teacher save partial or
   complete roster-backed decisions.
8. `marking_source()` derives the app-owned job root and resolves the current or
   historical workbook. The existing Stage 3B and 3C code receives a normal
   split-pile source and therefore does not need a second grading/rendering
   implementation.

### Files and artifacts created by the feature

For a selected scan `C:/Class Work/class-scan.pdf`, the current implementation
produces this shape:

```text
C:/Class Work/
    class-scan.pdf                         original; never modified
    .class-scan.essay-work-<content-hash>/
        _continuous.pdf                   byte-for-byte copied source
        _manifest.csv                     internal page/submission map
        _name_previews/                    OCR evidence for identity review
        submission_001.pdf
        submission_002.pdf
        ...
    Results/
        results.xlsx                      authoritative teacher workbook
        Feedback Cards/
            <class>-<number>-<name>-作文体检卡.png

<project>/
    jobs/teacher_<path-hash>/              checkpoints and model evidence
    config/<generated-workspace>_identity_decisions.json
```

Generated scan workspaces start with `.` so they stay out of the ordinary
teacher-facing folder view where the platform honors hidden names. Jobs,
receipts, raw model responses, and workbook backups remain internal; the
teacher-facing `Results/` folder contains the workbook and published cards.

### Source changes by responsibility

- Source model and application seam:
  `application/models.py`, `application/controller.py`, and
  `application/workflows/sec2_hcl_composition_v1.py` add `continuous_scan`,
  preparation, stable task binding, reuse validation, and scan-parent output
  resolution.
- Scan adapter: `scanning/split_by_student.py` adds
  `split_continuous_anonymous()` while retaining the old multi-pile root CLI.
- Desktop integration: `desktop/__main__.py`, `desktop/bridge.py`,
  `desktop/projection.py`, and the five changed QML files add the new input and
  keep work off the GUI thread.
- Runtime: `requirements-desktop.txt` now includes the scanning dependency
  chain because scanning is part of the normal journey.
- Diagnostics: `grading/codex_sol_grader.py` and `workflow/pipeline.py` add
  optional `MUMS_MARKING_TRACE` messages around provider readiness, student
  execution, and persistence failures.
- Tests: `tests/test_application_workflow.py`,
  `tests/test_scanning_regression.py`, and
  `desktop/tests/test_open_actions.py` add direct feature coverage.
- Documentation: the six modified Markdown files are being reconciled with the
  new normal flow and the already-built desktop application.

### Safety and compatibility decisions

- The selected source PDF is copied, never edited or renamed.
- OCR cannot assign final identity; only roster-backed teacher confirmation can.
- A pre-existing generated workspace is reused only after hash and structural
  validation. An incomplete or mismatched workspace blocks instead of being
  repaired or overwritten automatically.
- Stable batch binding uses the resolved original scan path. Existing split-pile
  and explicit workbook/job imports remain available for developer and legacy
  recovery work.
- Historical `output/<batch>/results.xlsx` remains supported. If both it and the
  new `Results/results.xlsx` exist, the app reports a conflict rather than
  selecting one silently.
- The feature reuses the existing identity, grading, workbook, approval,
  rendering, and receipt contracts; it does not add another database or result
  format.

### Verified feature behavior

The newly added focused tests currently verify that:

- a continuous scan creates an app-owned split workspace exactly once;
- calling preparation on an already prepared source is idempotent;
- inspection accepts a continuous scan without a teacher-created manifest;
- the copied `_continuous.pdf` matches the selected source bytes;
- generated student files have neutral names;
- the internal manifest is created and accepted by existing intake validation;
- normal UI submission requires a continuous PDF and roster while hiding
  workbook/job/receipt fields;
- developer/import mode retains the legacy selectors.

No real OCR acceptance run, live model call, or full teacher end-to-end run was
completed for this feature during the current work session.

### Open defects and design risks specific to this feature

1. **Output collision between scans in one folder.** `_teacher_root()` returns
   the continuous scan's parent directory. Two different class-scan PDFs in the
   same folder therefore resolve to the same `Results/results.xlsx` and
   `Results/Feedback Cards/`, even though their job batch IDs differ. Decide
   whether each scan must live in its own folder or whether outputs should use
   a scan-specific task directory; add a blocking test before shipping.
2. **Replacing a PDF at the same path can mix generations.** The split workspace
   name includes a content hash, but `marking_batch_id()` hashes the resolved
   path, not the file contents. Replacing the scan bytes at the same path creates
   a new split workspace while reusing the old job batch and teacher workbook.
   This needs an explicit task identity decision and regression coverage.
3. **Partial split recovery is manual.** The splitter creates its directory
   before OCR/splitting finishes. A crash can leave a partial workspace; the next
   run correctly blocks it as invalid but offers no audited cleanup/rebuild UI.
4. **First inspection is mutating.** Some desktop wording and older docs describe
   inspection as read-only. Continuous-scan preparation creates local files, and
   an error can occur after some files exist. Update all user-facing error copy
   and documentation to distinguish source immutability from workspace writes.
5. **Native dependency readiness is not checked up front.** Missing Tesseract,
   Poppler, pytesseract, or OCR data currently fails during preparation. The
   installer/first-run experience still needs a clear preflight and repair path.
6. **Full-suite regressions remain.** Fix the unbound `exc` workbook-inspection
   bug and triage the checkpoint, parallel persistence, cancellation, preflight,
   and Windows atomic-replace failures before accepting this feature.

### Exact takeover plan

1. Preserve the current working tree; do not reset or check out the 23 modified
   files.
2. Fix `except Exception:` to `except Exception as exc` in workbook-row
   inspection and rerun the focused malformed-workbook tests.
3. Add tests for two scans in one directory and for changed bytes at the same
   scan path. Decide the task/output identity contract before changing paths.
4. Add a recovery test for a partially created scan workspace, then implement
   an explicit safe rebuild/remove action rather than deleting automatically.
5. Run both complete suites sequentially in an installed dependency environment;
   do not run backend and desktop suites concurrently against the same test root.
6. Run a local end-to-end acceptance pass with non-student fixture PDFs:
   select scan + roster, inspect generated files, confirm identities, mark with
   a fake provider, review/approve the workbook, render cards, and reopen.
7. Only after the suites and acceptance pass are clean, update the recorded test
   evidence, commit the feature on a dedicated branch, and open a PR.

## 6. Key decisions and abandoned approaches

- Keep one concrete workflow ID, `sec2_hcl_composition_v1`; this is not a
  generalized plugin framework.
- Keep Excel as the authoritative teacher-edit/approval record. The app rereads
  saved Excel state and does not add a competing database or write the workbook
  concurrently while a teacher has it open.
- Treat OCR as evidence only. Final identity comes from roster-backed decisions;
  unresolved, duplicate, or ambiguous identities stop marking rather than being
  guessed.
- Bind jobs and receipts to identity, source digests, workbook paths, audit rows,
  and approved values. Do not select artifacts by filename alone, silently
  overwrite stale cards, or auto-approve model output.
- Keep resume, regrade, and rerender separate. Resume reuses durable evidence;
  regrade needs a new job/revision; rerender reads approved Excel and does not
  call a model.
- Use the configured `luna_xhigh` Codex profile for the desktop real-marking
  action, with a fresh isolated model context per student and serialized
  workbook commits. `grading/skills/sol-grader/SKILL.md` replaced the older
  calibration prompt as the active instruction source; each prepared job keeps
  a frozen snapshot.
- New desktop tasks use `Results/` beside the selected essay material. The old
  `output/<batch>/` layout is retained for historical compatibility, not moved
  or silently migrated.
- The old normal UI accepted a prepared split-PDF folder. The current
  uncommitted direction makes the normal journey accept a continuous scan PDF
  and roster instead; split-pile selectors remain in developer/import mode.
- The root multi-pile CLI's `front.pdf:back.pdf` syntax is retained for legacy
  use but is unsafe for absolute Windows drive-letter paths. The application
  adapter uses explicit `Path` arguments to avoid that parsing problem.

## 7. Conventions to preserve

- Use `Path`, UTF-8, dataclasses, type hints, and small pure helpers where the
  surrounding code does. Keep teacher-facing text bilingual through the QML
  `I18n` helpers and preserve Chinese strings exactly when they are part of a
  workflow contract.
- Use `unittest`, `tests.local_temp`, fake model/process transports, and isolated
  temporary workspaces for tests. Do not point tests at real `jobs/`, `output/`,
  scan, roster, or student-data folders.
- Use `atomic_json`, `batch_lock`, and `exclusive_lock` for durable writes and
  retain the existing per-student checkpoint semantics. Keep workbook writes
  behind `ExcelStore`; do not add ad-hoc openpyxl writes in workflow code.
- Reuse `Validator`, `CalibrationValidator`, `PillowRenderer`, existing layouts,
  and existing receipt/provenance checks. Do not introduce another grading
  schema, score source, renderer, or approval store without an explicit contract
  change.
- Keep operational data local and ignored. Never commit student PDFs, rosters,
  workbooks, jobs, outputs, receipts, generated cards, credentials, or model
  responses.
- There is no formatter/linter to run. Match the existing compact Python style,
  QML component style, and explicit error/attention codes.

## 8. Known bugs, gotchas, and fragile areas

- Fix the unbound `exc` bug in workbook inspection first.
- `workflow/storage.py` uses an atomic temp-file + `os.replace()` strategy. On
  Windows, open handles, antivirus, or concurrent tests can produce
  `PermissionError`; do not weaken atomicity without a replacement recovery
  design.
- A real `VALIDATED` checkpoint without a valid persisted result is not done
  work. A saved persistence receipt is diagnostic evidence, not an authoritative
  workbook commit.
- A stale/active `.pipeline.lock` must not be deleted based on age alone; verify
  the owner process. App-owned scan workspaces are hash-keyed and invalid or
  partial workspaces must be surfaced, not reused blindly.
- `.desktop-deps/` is ignored development state, not a reproducible virtual
  environment. In this checkout it contains the Qt/PySide6 files but not the
  core Python packages; install `requirements-desktop.txt` into the Python
  interpreter used by the launcher.
- Moving or renaming a task workbook after jobs/receipts exist can fail strict
  provenance checks because checkpoints and receipts store the resolved path.
- `config/calibration_model.json` has `sol_medium` as its active profile, while
  the desktop composition workflow explicitly requests `luna_xhigh`; check the
  caller before changing the default profile.
- The renderer is fixed to the current 1024x1536 card, pinned font/layout, and
  eight criteria. New designs or canvas sizes need deliberate schema/renderer
  support, not just a replacement PNG.
- The root and `scanning/` splitters are separate implementations. The root
  script's colon-delimited Windows CLI is especially fragile with drive letters.
- Local regression fixtures are intentionally ignored. A missing fixture should
  produce the documented skip, while a present but stale fixture can produce
  hash mismatches; distinguish those cases.

## 9. Environment variables and config

Names only; do not copy secrets into this file or into the repository:

- `OPENAI_API_KEY` — used only by the Responses API backend.
- `OPENAI_BASE_URL` — optional Responses API endpoint override.
- `CODEX_HOME` — may affect the authenticated Codex CLI environment.
- `USERPROFILE` and `LOCALAPPDATA` — used by the Windows launcher/Codex CLI
  discovery logic.
- `MUMS_MARKING_TRACE` — optional stderr tracing for marking/provider startup,
  failures, and persistence.
- `TESSDATA_PREFIX` — scan-time OCR data location; the split code temporarily
  sets/restores it when a tessdata directory is supplied.
- `PHASE1_TEST_TEMP` — optional test workspace root.
- `PHASE1_RENDER_MOCK_WORKBOOK` and `PHASE1_RENDER_TEACHER_WORKBOOK` — optional
  local renderer regression fixtures.
- `PHASE1_INTERACTION_QA_SCENARIOS` — optional local desktop interaction-QA
  manifest.
- `QT_QPA_PLATFORM`, `QT_QUICK_BACKEND`, `QML_DISABLE_DISK_CACHE`,
  `QT_ENABLE_HIGHDPI_SCALING`, and `QT_SCALE_FACTOR` — QA/visual-run settings.

Important config files:

- `config/calibration_model.json`
- `config/criteria.json`
- `config/text_limits.json`
- `config/calibration_rubric_v1.json` and `config/calibration_rubric_v2.json`
- `grading/skills/sol-grader/SKILL.md`
- `grading/references/reference_example_v1.md`
- `tessdata/chi_sim.traineddata`

The configured Codex profile expects the `codex` executable and valid local
authentication. Do not put its credentials in environment examples or commit
them.

## 10. GitHub and local Git state

- Remote: https://github.com/RagenivNomel/marking-project.git
- Visibility: private.
- Default/main branch: `main`.
- Current working branch: `main`; there is no separate feature branch.
- Local refs visible in this checkout: `main` and `origin/main` only. Live
  GitHub API and `git ls-remote` checks on 2026-09-26 confirm that `main` is also
  the only remote branch, at `7d31c72`.
- `HEAD` is `7d31c72` (`Simplify marking save-state lifecycle`) and matches
  `origin/main`; the local commit is neither ahead nor behind the fetched remote
  (`0 0`). There are no unpushed commits.
- Before creating this file, 23 tracked files were modified and there were no
  other untracked files. `HANDOFF.md` is intentionally a new uncommitted file;
  after this write it is also part of the uncommitted working set.
- Open pull requests: none (live GitHub API check on 2026-09-26).
- Open issues: none (live GitHub API check on 2026-09-26).
- GitHub Actions/CI: no workflows are configured, no local
  `.github/workflows/` files exist, and the repository has no recorded workflow
  runs (live GitHub API check on 2026-09-26). Nothing runs automatically on
  push at this handoff point.
- GitHub CLI authentication for `RagenivNomel` was refreshed successfully on
  2026-09-26 with repository and workflow access. In the current managed tool
  environment, stale `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` values point to an
  unavailable local proxy; remove those variables for an individual `gh` or
  `git` command if it reports a proxy connection refusal. Do not store tokens or
  credential values in this repository.

