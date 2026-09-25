# Project build and remaining scope

Reviewed 24 September 2026. This is a source, documentation, test-definition and saved-screenshot review, not a fresh runtime acceptance run. No live grading, student-file changes or application changes were performed.

The project has an implemented desktop marking workflow. The remaining work is completing the intended product and making it portable, rather than building the application from scratch.

## What is already built

| Area | Evidence and current scope |
| --- | --- |
| Desktop interface | `desktop/qml/` and `desktop/bridge.py`: PySide6/Qt Quick, Chinese/English interface, guided teacher flow, background workers, progress, cancellation, details and reduced-motion support. |
| Student preparation | Split-PDF folder and roster selection, identity confirmation, duplicate checks and persisted decisions. Raw scan splitting exists separately in `scanning/`. |
| Marking | `workflow/pipeline.py`: isolated per-student grading, up to three concurrent graders, validation, serialized workbook persistence, saved progress and guarded retries. |
| Review | Excel remains the authoritative teacher review/edit surface; the app opens results and rereads saved approval. |
| Feedback cards | `application/controller.py` dispatches approved-row rendering; the existing renderer uses approved text and records provenance. New desktop tasks publish cards into `Results/Feedback Cards/`. |
| Task storage | A task's `Results/results.xlsx` is rediscovered when its essay folder is reopened; internal jobs and workbook backups are retained. |
| Cat scene | `MascotScene.qml` is integrated into `ProgressPanel.qml`: sleep, walk, read, mark, pen play, transformation and completion. Six sprite sheets use 64×64 cells with three or four frames each. |
| Verification assets | Backend and desktop tests cover parallel marking, failures, resume, identity, output paths and approved rendering; saved visual fixtures show the actual progress-panel layout. |

The mascot Phase B report records 118 backend and 51 desktop tests passing during that earlier work. These are historical results, not tests rerun for this review.

## Remaining scope, in suggested order

### 1. Finish and verify the existing teacher journey

- Run a fresh end-to-end acceptance pass: choose papers, correct identities, mark, stop/resume, edit and approve in Excel, generate cards, reopen the task and verify outputs.
- Add a supported recovery path for calibration jobs stopped at `GRADED`: `CalibrationPipeline.run()` currently accepts `TRANSCRIBED` or returns an existing `VALIDATED` result, but rejects `GRADED`. Revalidate a saved response without another model request where appropriate; retain uncertainty cases for review.
- Expose an explicit, audited rerender action for teacher edits made after a card was generated. The rendering API exists, but the documented teacher flow blocks stale receipts rather than automatically replacing them.
- Freeze settings for a whole batch before the first student. Existing per-student snapshots are valuable, but do not by themselves guarantee that a mid-batch settings edit cannot affect subsequently prepared jobs.

### 2. Make the app installable on Mum's computer

- Package Python, Qt, PDF/OCR dependencies and required data with a reproducible build and desktop shortcut.
- Replace development-runtime assumptions in `launch-desktop.ps1` and absolute font references in `rendering/template/layout_v1*.json`.
- Put editable settings and jobs in a writable application-data location and preserve them across updates.
- Add first-run backend/dependency checks and clear setup errors; verify on a clean destination account.

No verified installer or clean-machine release was established by this review. The current desktop README explicitly calls this a development launcher.

### 3. Complete the broader scope in the packaging plan

| Planned feature | Remaining integration |
| --- | --- |
| Raw front/back scans | Guided pairing, page previews/accounting and recoverable scanning inside the app; the current normal journey begins with split PDFs. |
| Review beside the paper | PDF and editable feedback in one app view, if still desired; Excel review already provides the current workflow. |
| Settings and marking comparison | Teacher-facing settings editor, revisions and controlled before/after comparison. |
| Design library | Versioned design packs, portable fonts, previews, validation and a design picker. |
| Printable batch export | Combined PDF, export manifest and explicit complete/partial batch accounting. Individual PNG cards already exist. |
| Task history | Persistent recent-task index and remembered preferences; reopening a selected folder works without this. |
| Regrading | Explicit new marking revisions, clearly separated from resume and presentation-only rerender. |

For a narrow first release, the existing split-PDF intake and Excel review can remain. The broader features above should not all be treated as prerequisites unless they are required for Mum's daily use.

## Cat/loading-screen scope

The existing cat is a progress-panel mascot, not a separately verified app-startup loading screen. Its working sequence already walks from its house, changes into workwear, reads, marks, briefly plays, and celebrates completion; reduced motion selects static poses.

The saved `design/mascot/phase-b/previews/05-marking.png` shows the cat quite small near the far right of a wide panel. Improving its prominence, placement and animation readability is a focused presentation task. A dedicated startup loading screen would be additional UI work.

The supplied Sprite Studio brief describes new 128×128 animations at 12 FPS. The current app expects 64×64 sheet cells and per-action frame rates, so new assets need an explicit sheet/export and QML integration change. The existing report does not establish saved version-3 deterministic rigs for those old sprites; do not describe them as meeting the new rig provenance contract without checking.

## Documentation discrepancies

- Root `README.md` and `APP_PACKAGING_PLAN.md` still say the desktop interface has not been built; the desktop code demonstrates otherwise.
- Some desktop documentation describes marking as sequential; current pipeline code uses three concurrent workers.
- `application/WORKFLOW_MAP.md` warns that resuming a validated real job resets approval to pending. Current `_persist_real_result()` instead reads the existing review status after `ensure_draft()`; that warning needs reconciliation with current code and its preservation tests.

Use current implementation and fresh acceptance evidence to update these documents before using them as the next development brief.
