# Application workflow adapter

Stage 3B wires `RUN_MARKING`, and Stage 3C wires `RENDER_APPROVED` for
`sec2_hcl_composition_v1`. This document describes the current adapter contract;
historical operational records remain local-only.

The workflow adapter observes saved artifacts, orchestrates production marking,
and renders teacher-approved feedback cards through the existing renderer. The only supported workflow is
`sec2_hcl_composition_v1` (中二高华作文批改).

## Application boundary

```python
from pathlib import Path
from application import AssignmentSource, WorkflowController

controller = WorkflowController()
source = AssignmentSource(
    workbook=Path("local-assignment/results.xlsx"),
    receipt_roots=(Path("local-assignment/receipts"),),
)
inspection = controller.inspect(source)
print(inspection.summary)
print([item.action.value for item in inspection.available_actions])

# The teacher edits and saves Excel externally. This performs another read only:
updated = controller.refresh_review_status(source)
```

Paths above are relative to the project working directory. Application callers
should normally supply absolute paths. Select only the roots belonging to the
assignment; this API does not search the entire repository or infer ownership
from student names. `job_roots` optionally adds saved grading jobs; `receipt_roots`
adds rendering receipts. A continuous scan, roster and identity decisions can
describe pre-marking work. When a continuous scan is supplied, the workflow
creates and validates an app-owned split workspace before inspection; its
manifest is internal metadata, not a teacher prerequisite. These are
references, not a new assignment database.

The delivered workbook above has a different path from the workbook recorded in
the historical card receipts. Strict inspection reports that provenance mismatch;
it must not silently treat a relocated copy as the original approved source.

## Meaning of the projection

- Each submission has its own source/audit identity; a student may appear twice.
- Excel is authoritative for current feedback and saved approval. Checkpoint
  approval fields do not override it.
- `grading_available` means a validated attempt artifact is readable. It is
  diagnostic evidence only; `grading_results_available` and the saved/done
  counts are derived from the matching workbook result and audit rows.
- `rendered` means a matching, current approved-source receipt and output were
  verified. It is not inferred from a filename or checkpoint alone.
- `ready_to_render` describes source-data/provenance eligibility, not a guarantee
  that the renderer's layout can fit the text. No layout or rendering is executed.
- Counts describe the supplied evidence, not unseen directories or unsaved Excel
  edits. Independent submissions can be at different stages simultaneously.
- Attention separates stable codes, severity, Chinese teacher-facing messages,
  diagnostic details and the affected submission. Pending review is an intentional
  human gate, not an error or permission to approve automatically.

## Stage 3B marking execution

`WorkflowController.execute(Action.RUN_MARKING, source, ...)` is the narrow
execution seam. It re-inspects the selected assignment, requires complete
roster-backed identities, and calls `Pipeline.run_real_batch` with the existing
`luna_xhigh` profile. Each successful student result is validated and persisted
to the existing Excel workflow before the next student starts. Approval, Excel
handoff, and opening output folders remain teacher-controlled or outside the
current execution boundary.

The assignment's normalized pile path selects a stable app-owned batch name.
For a new desktop task, the authoritative workbook is automatically created at
`<essay-folder>/Results/results.xlsx`; reopening that essay folder rediscovers
it. Jobs and checkpoints remain under the app's internal `jobs/<batch>/` tree.
An existing workbook at the historical `output/<batch>/results.xlsx` remains in
place and is reused when no new-layout workbook exists. If both workbook paths
exist, inspection blocks the task rather than choosing between two editable
files. Only a matching workbook result row and audit row count as completed;
approved rows are preserved. Raw, parsed, validated, interrupted, and
persistence-receipt artifacts remain diagnostic evidence and do not block
ordinary marking. A new model attempt is isolated from any unfinished prior
attempt.

## Stage 3C approved-row rendering

`WorkflowController.execute(Action.RENDER_APPROVED, source, ...)` re-inspects
the selected task, selects only unrendered `APPROVED` workbook rows, and invokes
the existing `Pipeline.rerender()` path in the Qt worker. A thin renderer adapter
supplies the `班级-班号-姓名-作文体检卡.png` filename; PillowRenderer still owns
all painting, layout, typography, fit checks, and receipts. The renderer reads
  the current approved Excel row, including teacher edits, and does not call a
  grader or modify the workbook. The rendered PNG and receipts stay in the
  internal `jobs/<batch>/<student_job>/output/` directory. For new desktop tasks,
  an identical PNG is atomically published to
  `<essay-folder>/Results/Feedback Cards/`; its path and hash are part of the
  internal receipt. Stage 1 verifies the internal render, published copy and
  approved row before the app reports completion.

The app serializes Stage 3C batches, rejects duplicate output filenames, keeps
successful cards when another render fails, and offers only still-ready approved
rows on a retry. The existing safe `Pipeline.rerender()` route supports
checkpointless approved workbooks and `VALIDATED` Stage 3B checkpoints; current
Excel approval and digest checks still apply. A stale existing receipt remains
blocked by Stage 1's provenance checks rather than being silently overwritten.

## Application actions

`available_actions` includes submission targets and an `execution_wired` flag.
Preparation and confirmation remain separate from `execute(...)`, which accepts
only `RUN_MARKING` and `RENDER_APPROVED`; other actions raise
`NotImplementedError`. The desktop bridge handles opening the authoritative
workbook and teacher-facing feedback folder through Qt's operating-system URL
service. The read-only `refresh_review_status(...)` method remains available.

See `WORKFLOW_MAP.md` for the full production execution seams and their
repeat/resume hazards.

## Evidence limits and conservative stops

- An existing real production job at `TRANSCRIBED` does not prove zero model
  attempts: its nested calibration job owns that counter. Inspection therefore
  reports uncertainty rather than suggesting a blind retry.
- Audit input digests identify original inputs, not edited teacher feedback.
  They cannot be recomputed from the approved row. Without supplied job evidence,
  inspection verifies the existing workbook/receipt contract, not cryptographic
  authenticity or the complete original grading history.
- Calibration bridge targets linked by each real-job bridge artifact are followed
  directly, without searching unrelated project job folders.
- Relocated submissions require explicit linkage; identical student names or
  matching content alone cannot distinguish two legitimate submissions.
- Conflicting receipts, stale cards, or missing artifacts require attention.
  They are not automatically replaced or selected as the current output.

## Non-goals and safety

Stages 3B and 3C reuse the proven grader and renderer behind bounded worker
actions. They do not add a database, generalized job engine, approval writer,
or new card design.

Inspection is a snapshot, not a transaction or execution authorization. Future
executors must recheck source data, ownership, locks and prerequisites immediately
before an operation. An attention item reports a problem; it does not repair it.

## Verification

The repository README documents the clean-clone test tier and the optional
local-data regression checks. Operational inspection examples and historical
results are intentionally kept in local-only records, not in repository docs.
