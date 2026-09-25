# 作文工作台 — Stage 3B

Native PySide6 / Qt Quick desktop shell using the approved Stage 2A visual system.
The normal teacher experience is a single guided workspace: evidence determines
the current stage and the interface presents one clear next action. Stage 3B
connects **Start AI Marking** to the existing production pipeline; teacher Excel
review and feedback-card generation remain outside this stage.

## Launch the normal teacher interface

Double-click `launch-desktop.cmd`, or run this from the project folder:

```powershell
.\launch-desktop.cmd
```

The normal interface opens with **Choose Essays / 选择作文**. Its new-task selector asks for the essay PDF folder and class roster only; results and card destinations are managed by the app. After existing evidence is loaded,
the same workspace advances through preparation, AI marking, teacher review and
feedback generation. The four stages are a progress indicator, not navigation.
The Chinese/English switch sits in the teacher workspace. The developer header
retains its inspection controls; Windows keeps native dragging and window buttons.

To start in English:

```powershell
.\launch-desktop.cmd --language en
```

The launcher uses an isolated `.desktop-deps` folder. It does not change
production `app.py` or production requirements. Its direct equivalent is:

```powershell
python -B -X utf8 -m desktop
```

## Developer and QA interface

The original fourteen-state selector, navigation sidebar and workflow tabs are
preserved only in the clearly marked developer interface:

```powershell
.\launch-desktop.cmd --dev-ui
```

Open a specific fixture with `--demo`, for example:

```powershell
.\launch-desktop.cmd --dev-ui --demo marking
```

`--demo` is intentionally ignored unless `--dev-ui` is also present, so fixture
states cannot replace the normal teacher journey accidentally.

## Stage 3A: confirm student information

When a submission folder contains split PDFs, the normal **选择作文** dialog
also asks for **学生名册 / Class Roster**. It can use a local class roster
workbook. The app also attaches an existing project-owned identity-decision
file using the folder's deterministic name.

If Stage 1 has already received strong roster decisions, the read is immediately
resolved. Otherwise the workspace shows **学生资料确认** rather than one error
card per submission. Each row keeps its source PDF identity, shows the available
name-field preview, and offers a selector from the actual roster. **保存已确认**
supports a partial pass; **确认并继续** requires every remaining row to be
selected. Both actions persist through the production identity validators and
re-inspect the same source. A roster student cannot be assigned to two rows.

After all rows are confirmed the workspace displays `The essays are ready ✓` /
`作文已经准备好 ✓`. **Start AI marking** is now available when all submissions
are confirmed and the selected task has no blocking issue.

## Stage 3B: real marking

Marking runs in a Qt worker thread. It uses the production `run_real_batch` /
`run_real_pdf` / `CalibrationPipeline` path, one fresh isolated Luna xhigh model
context per student. Results are validated and written to the assignment's
single results workbook as `PENDING`, one student at a time. Each task uses a
stable app-owned batch folder under `jobs/`; new tasks write the authoritative
workbook to `<essay-folder>/Results/results.xlsx`. Reopening the same essay
folder rediscovers that workbook automatically. Historical tasks with only
`output/<batch>/results.xlsx` continue to use that workbook without moving it.

Start resumes only unfinished work. Saved validated results are not sent to the
model again, and existing `APPROVED` rows and teacher-edited wording are left
unchanged. An explicit Retry action is offered only when the calibration
checkpoint proves that its one model attempt failed before a response was saved;
the existing single retry limit still applies. Other uncertain attempts remain
blocked for inspection. Successful essays stay saved when a later essay fails.
While marking runs, **Cancel Marking** stops the queue from starting more essays.
The essays already in progress finish and save before the batch stops; the UI
shows **Stopping…** during that interval. Reopening the task retains saved work.
The workspace ends at **Teacher review is ready**. It does not open Excel or
approve rows. After the teacher saves an `APPROVED` row in Excel and rereads it,
Stage 3C can generate a feedback card from that exact saved row.

## Stage 3C: approved feedback cards

**Generate Feedback** runs on the existing Qt worker pool and calls the
production `Pipeline.rerender()` path. Only unrendered `APPROVED` rows are
eligible; `PENDING` rows stay untouched. Each card uses the latest teacher-edited
Excel values and keeps the filename `班级-班号-姓名-作文体检卡.png`. The card,
receipt, and render-attempt record remain under
`jobs/<batch>/<student_job>/output/`. The app also publishes a byte-identical PNG
to `<essay-folder>/Results/Feedback Cards/`; the internal receipt verifies both
copies against the approved workbook row. The teacher-facing folder contains PNG
files only. Progress counts a card only after a fresh inspection verifies its PNG
and receipt. A failed card can be retried without rerunning grading, and already
verified cards remain saved.

**Open results.xlsx** uses Qt's desktop URL service to open the authoritative
file in the operating system's registered application. **Open feedback-card
folder** opens the task folder in the operating system's file manager. If a
location disappears, the app shows a concise message and leaves task data
unchanged.

The loaded assignment workspace also exposes the shared
`BackNavigation.qml` control as `← 我的批改任务` / `← My Marking Tasks`. It
returns to the existing normal task-selection page without clearing the loaded
source, identity decisions, roster, or preparation evidence. Reopening a pile
re-inspects those persisted artifacts.

## Inspect an existing assignment

The normal **选择作文** dialog accepts a submission folder and class roster.
Results are discovered automatically. Workbook and evidence selectors remain
available in the developer recovery/import workflow. Explicit existing
locations can also be supplied at launch:

```powershell
.\launch-desktop.cmd --workbook $env:LOCAL_RESULTS_WORKBOOK --job-root $env:LOCAL_JOB_ROOT
```

Optional arguments include `--receipt-root` (repeatable), `--split-pile`,
`--roster`, `--identity-decisions`, `--language`, and `--reduced-motion`.
Returning home does not create a persistent recent-task database. The current
assignment view is rebuilt from the selected files and saved marking artifacts.

## Safety boundary

QML calls `DesktopBridge`; reads, real marking and card rendering run away from
the GUI thread. The bridge dispatches `RUN_MARKING` and `RENDER_APPROVED` only
when Stage 1 advertises the matching safe action. The workflow adapter rechecks
identities and saved evidence immediately before it calls the production
pipeline. It does not expose a force-rerun or Excel approval action. Results
and feedback-folder open actions use Qt's desktop URL service. Technical file evidence stays behind
**View details / 查看详情**.

Rows retain `submission_id`, so duplicate student identities remain separate.
Review and output counts overlap rather than being added together. Stage 3B and
3C progress comes from persisted results and the active per-student operation;
demo progress remains clearly marked as a fixture.

## Checks

On another development machine, install `requirements.txt` and
`requirements-desktop.txt` into a suitable Python environment. This is a
development launcher, not a packaged release.

```powershell
python -B -m unittest discover -s tests -v
python -B -m unittest desktop.tests.test_teacher_flow desktop.tests.test_bridge desktop.tests.test_stage3b_execution -v
python -B -m desktop.normal_visual_qa
python -B -m desktop.visual_qa
python -B -m desktop.interaction_qa
python -B -m desktop.integrity
```

The visual checks use the native Windows font backend and briefly show the Qt
window. Simplified-journey screenshots and results go to `design/stage-2b1/`;
the full developer harness remains in `design/stage-2b/`. Existing backend tests
use synthetic fixtures and do not make live provider calls.
