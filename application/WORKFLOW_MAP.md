# Stage 1 workflow map

This map documents the production orchestration plus the Stage 3A/3A.1/3B and Stage 3C desktop adapters. Existing application/source code also exists under scanning/, grading/, excel/, rendering/, workflow/, and the root CLIs. No production workbook, job, receipt, card, scan, or grading result is changed by this documentation.

The desktop now supports real marking through teacher review, and approved-row feedback-card generation through the existing renderer. The real-batch bridge intentionally stops at validated/pending review; only the mock pipeline traverses the historical COMPLETE state machine.

## 1. State, ownership, and persistence

workflow.state.State is:

    NEW -> SCANNED -> IDENTIFIED -> TRANSCRIBED -> GRADED -> VALIDATED
        -> REVIEWED -> APPROVED -> RENDERED -> COMPLETE

transition() allows only adjacent transitions. Pipeline._advance() appends state to student_record.json and atomically replaces it. Exceptions retain the last durable state and write last_error. workflow.storage.batch_lock() creates a PID lock for one writer; stale locks require process verification before manual removal.

Normal mock flow reaches COMPLETE:

    source -> scan marker -> identity -> transcription -> grade -> validate
           -> Excel draft -> review -> approval -> render -> artifact check

The real production job reaches VALIDATED/PENDING; its isolated calibration job reaches VALIDATED/PENDING_HUMAN_REVIEW. Neither real path auto-approves or renders.

Per-student mock artifacts under jobs/<batch>/<job_key>/ are student_record.json, source.json, identity.json, essay.md, essay.json, grading_input.json, grading_result.json, validated_result.json, review.json, and output/. The default renderer adds student_card.png and render_receipt.json; tests may inject mock_render.json.

Real jobs keep nothing between attempts. Each model call runs in jobs/<task>/<job_key>/work/ (prompt and configuration snapshots, the model response, and per-call validation); that folder is deleted once the workbook row is saved, and the whole essay folder except output/ is deleted before an unfinished essay is marked again. The only completion record is the workbook: an essay is done when it has a valid result row and matching audit row. The command-line pipeline keeps its historical default at output/<batch>/results.xlsx. The desktop task adapter supplies the task's <scan folder>/Results/<scan name>-<hash>/results.xlsx to that same Pipeline and stores workbook backups under jobs/<task>/workbook_backups/. Its hidden Pipeline审计 sheet still binds job ID, class, student number, row, input digest, and pipeline status. The task identity is the continuous scan's content hash, so a replaced or neighbouring scan never resolves to another scan's workbook.

## 2. Operation map

### Scanning: new front/back material

- Functions: scanning.split_by_student.scan_anonymous; preserved root functions interleave_front_back, build_continuous_pdf, analyze_front_pages, detect_student_boundaries, split_into_students, write_manifest in split_by_student.py.
- Input: ordered (front_path, back_path) tuples and a new output directory; optional tessdata_dir.
- Prerequisites: pypdf, Poppler/pdf2image, Pillow, NumPy, pytesseract/Tesseract, and tessdata/chi_sim.traineddata for native scanning. Front/back page counts must match.
- Output/side effects: _continuous.pdf, neutral submission_###.pdf, _name_previews/, and _manifest.csv in the new directory. Raw OCR names and previews are evidence only; OCR does not set final identity.
- Repeat/resume: outdir.mkdir(..., exist_ok=False) makes repeat fail; there is no scan checkpoint or rollback. A failure can leave partial output that must not be treated as a valid pile.
- CLI note: the preserved root CLI parses front.pdf:back.pdf, which is unsafe for absolute Windows drive-letter paths. The adapter's explicit tuple interface avoids that parsing issue.

### Scanning: existing split intake

- Functions: scanning.intake.read_existing_split, _page_digest, SplitSubmission.
- Input: an existing pile containing _manifest.csv, _continuous.pdf, and non-underscore student PDFs.
- Behavior: hashes page geometry/content and matches each renamed PDF to exactly one continuous-PDF range; checks page counts, unique starts, and complete coverage.
- Output/side effects: ordered SplitSubmission records only; no scan, roster, workbook, job, or grade write. Ambiguous page-content matches fail rather than guess.
- CLI: run_pipeline.py intake --pile ... --workbook ... --decisions ... [--out ...]. Without --out it is read-only; --out writes one atomic JSON intake report.

### Scanning: continuous PDF intake

- Functions: `scanning.split_by_student.split_continuous_anonymous` and the
  workflow's `prepare_source` adapter.
- Input: one continuous scan PDF selected by the teacher; the class roster is
  supplied separately for identity confirmation.
- Behavior: copies the scan into an app-owned working directory, detects
  submission boundaries, writes neutral `submission_###.pdf` files, and keeps
  the generated manifest/name previews internal. OCR names remain evidence
  only.
- Repeat/resume: the working directory is keyed by the continuous PDF hash and
  is validated on reopen; a partial or invalid workspace is surfaced rather
  than silently reused.

### Identity and roster decisions

- Functions: excel.workbook.read_roster, scanning.identity.confirm_identity, scanning.intake.apply_identity_decisions; interfaces IdentityCandidate and IdentityResolver are reserved, not active.
- Input: roster sheet 作文诊断输入 and a decisions JSON covering every submission exactly once.
- Behavior: roster numeric 16.0 becomes "16" while textual "016" stays "016"; duplicate (class_name, student_id) keys fail. confirm_identity() requires exactly one roster match. Decision statuses are STRONG_ROSTER_MATCH and CONFIRMATION_REQUIRED; duplicate strong identities fail.
- Output/side effects: records retain class, student, source filename, match status, and evidence. real-batch selects only strong matches. read_legacy_reference() returns exact historical workbook values for intake inspection; it does not translate or feed old ratings/scores into grading.
- Repeat/resume: decisions are input evidence, not a mutable checkpoint. Changing identity/input in an existing job fails binding checks; use a distinct batch/revision while preserving the old record.

### Mock grading and strict validation

- CLI/API: run_pipeline.py mock --input ... --batch ... [--failure ...] -> Pipeline.run_mock(source); public app.Pipeline is only a re-export.
- Input: exactly identity and essay, with optional topic. job_key() sanitizes the student-number directory component and hashes class plus number to avoid cross-class collisions. The source digest binds the job to its input and workbook path.
- Functions: GradingInput, MockGrader, Validator, Pipeline.run_mock.
- Side effects: writes staged per-student artifacts, then the companion workbook, review record, approved-row render, and checkpoint transitions. A fresh provider instance is created per student; it receives only identity and essay.
- Validation: Validator.validate() requires exact identity keys, exactly eight criteria, exactly rating/short_comment, the three configured ratings, non-empty literal feedback, and hard limits of 90 characters per criterion comment and 300 for the teacher comment. It rejects extra score/next-improvement fields and identity mismatch. It does not itself detect an Excel formula string; formula-cell rejection belongs to ExcelStore._decode().
- Repeat/resume: same source/batch resumes; cached grading_result.json is reused; COMPLETE skips work. Changed source, identity, topic, or workbook binding fails and requires a new batch. Invalid raw output remains inspectable at GRADED with no workbook/render.

### Real calibration and production bridge

- CLI/API: run_calibration.py --source ... [identity/options] [--model-profile ...] -> CalibrationPipeline.prepare() and run(); run_pipeline.py real-batch ... -> Pipeline.run_real_batch() and run_real_pdf().
- CalibrationPipeline.prepare() validates/hash-binds the PDF, copies it into the calibration job, and freezes identity, criteria, limits, rubric, schema, prompt, reference, active marker_SKILL.md, model profile, and hashes. It records direct-PDF page order; it does not OCR-transcribe.
- CalibrationPipeline.run() performs readiness checks, records live_request_attempts before the call, allows one attempt by default, saves raw_model_response.json, parses/validates with CalibrationValidator, and writes a calibration workbook only for a valid assessable response. Material reading uncertainty remains GRADED, retains reading evidence, and writes no workbook.
- Providers: CodexSolGrader renders only the selected PDF to ordered PNGs in a temporary workspace and invokes one constrained ephemeral codex exec; SolGrader makes one store:false Responses request. Neither retries internally. Live prerequisites are the configured profile, Codex ChatGPT login or API key, Poppler for Codex page rendering, and frozen prompt/rubric/reference/schema assets.
- run_real_pdf() copies and hashes the production source, bridges a validated calibration result into production grading_result.json/validated_result.json, writes a production workbook row, sets it PENDING, and returns VALIDATED. It never auto-approves, renders, or publishes.
- run_real_batch() sorts by intake sequence/page start, applies --limit, rejects duplicate selected identities, and isolates per-student failures in failed; only strong roster matches are selected.

### Excel draft, teacher handoff, and approval reread

- Functions: ExcelStore.ensure_draft, _open, _save, _decode, get, get_render_source, set_status; ExcelStudentRecord; CalibrationWorkbookRepository.write_initial.
- Input/output: the normalized companion workbook uses Phase1批改结果 plus hidden Pipeline审计; original teacher workbook access through read_roster/read_legacy_reference is read-only. Scores are blank unless explicitly imported/owned by the teacher; grader output cannot supply scores.
- Side effects: ensure_draft() validates and inserts literal values with PENDING, or validates/preserves an existing row with the same audit digest. _save() writes a temporary workbook, backs up an existing workbook, and replaces it atomically. Excel should be closed; concurrent external/background writes are unsupported.
- Approval flow in run_mock(): reread the current row, send it to the reviewer, save a digest in review.json, set REVIEWED, reread again, re-review if the row changed, then set the Excel cell and audit state to APPROVED.
- Formula boundary: ExcelStore._decode() rejects cells whose data_type is "f", then passes literal decoded values to Validator. A dict containing a formula-looking string is not equivalent to a formula cell.
- Handoff rule: the workbook remains the teacher handoff/approval record. The current safety requirement is no concurrent pipeline write while it is open; this map does not propose replacing Excel with an app-owned assessment store or changing the handoff model.

### Approved-row render and rerender

- Functions: PillowRenderer, load_layout, _record_values, _wrap_text; Pipeline._render, _render_artifact_exists, rerender; CLI run_pipeline.py rerender --input ... --batch ....
- Input/prerequisites: an APPROVED ExcelStudentRecord, unique audit row, matching checkpoint digest when a checkpoint exists, pinned Visual Master/layout/font hashes, and the fixed eight-criterion field mapping.
- Behavior/output: exact approved cell values are measured inside fixed boxes; finite font tiers, glyph bounds, rating-arrow clearance, and overflow are checked. Success atomically writes student_card.png and render_receipt.json, whose audit includes approved values, source workbook/row, layout/font/master versions, and output hash. No grader is called.
- Rerender source: get_render_source() rereads Excel, prefers the job ID, otherwise requires a unique class/student match, and requires APPROVED. Cached grade/validated JSON is never the feedback source. Invalid/unapproved/overflow input leaves the previous receipt/card in place; card and receipt are atomic individually, not one transaction.
- Repeat/resume: a local checkpoint may be absent for an imported approved workbook. When present, identity, workbook path, state (VALIDATED/APPROVED/RENDERED/COMPLETE), and digest checks apply.

### Stage 3C application execution

- Entry: `WorkflowController.execute(Action.RENDER_APPROVED, source, progress_callback=...)` -> `CompositionWorkflow.execute_feedback_generation()` -> `Pipeline.rerender(identity)`.
- Eligibility: the workflow binds the workbook to the task's `Results/<scan name>-<hash>/results.xlsx`, re-inspects the current workbook and only selects entries with a valid `APPROVED` row, no current card, and no blocking provenance issue. It performs a second inspection while holding a per-batch Stage 3C lock, so duplicate windows cannot act on stale readiness.
- Source of truth: `Pipeline.rerender()` calls `ExcelStore.get_render_source()` for the current approved row and matching audit. It never reads cached grading output as card content. A present checkpoint must match identity, workbook, and Excel audit digest; Stage 3B's `VALIDATED` checkpoint is allowed because Excel approval is the human gate.
- Rendering: `ApprovedFeedbackRenderer` adds a safe deterministic basename to audit metadata and delegates all drawing to `PillowRenderer`. Default Pipeline calls retain `student_card.png`; Stage 3C uses `班级-班号-姓名-作文体检卡.png`. Visual Master v1.2, layout, font, eight criteria, and line-fitting logic are unchanged.
- Output: the matching internal task folder `jobs/<batch>/<job_key>/output/` stores the rendered PNG, `render_receipt.json`, and `render_attempt.json`. For desktop tasks, the adapter atomically publishes a byte-identical PNG to the task's `Results/<scan name>-<hash>/Feedback Cards/`; the publication path and hash are recorded in the internal receipt and checked together with the original render. Receipts and attempt records stay internal. The receipt retains the approved Excel values, workbook/row/job/digest, layout/font/master hashes, PNG dimensions, and image hashes. The directory beside the workbook contains only results.xlsx and Feedback Cards (with PNG files).
- Progress and completion: progress events are emitted per student. A completion is counted only after a new Stage 1 inspection verifies the receipt and PNG against the current Excel row. Rendering does not call grading, Codex, or a model and does not write to the workbook or source PDF.
- Partial failure: each row is isolated. Completed outputs remain; a failed row keeps its approved Excel state and writes technical failure details to `render_attempt.json`. A later action re-inspects and targets only rows still ready to render. Duplicate visible filenames are rejected before any card is rendered.
- Safe rerender: sequential repeat action finds no eligible row and cannot overwrite a verified card. Teacher edits after an existing render make the old receipt stale and Stage 1 blocks the automatic action. The existing direct `Pipeline.rerender()` API can safely regenerate from current approved Excel when explicitly called; the teacher UI does not bypass the stale-receipt warning in this stage.

### Publication and persistence boundary

Current persistence is per-job files, one companion workbook per batch, workbook backups, and per-card receipts/cards. Existing approved workbooks/cards demonstrate the downstream artifact path. There is no unified app command that performs intake through review and complete-batch publication, no combined printable export manifest, and no production transition that currently marks a real batch COMPLETE. A card or old receipt alone does not prove a complete batch publication.

## 3. Repeat, resume, and reset hazards

| Case | Current behavior and risk |
| --- | --- |
| Same mock command | Resumes by exact input/identity/workbook binding; completed job skips; teacher edits already saved before interruption are reread. |
| Teacher edit after mock COMPLETE | Plain mock still skips; explicit rerender is required to use the approved edit. |
| Same real job at VALIDATED | **run_real_pdf() re-enters its VALIDATED branch, calls ensure_draft(), then set_status(..., VALIDATED, "PENDING"). It does not call the model, but it can reset a previously approved row from APPROVED to PENDING. Never use run_real_pdf() as an approval-preserving post-review resume.** |
| Calibration job at GRADED | Saved raw output is not revalidated by current run(); it refuses to continue from GRADED. Do not delete the raw response or silently authorize a new call. |
| Provider process interruption | Attempt is recorded before the call; an in-flight result can be uncertain and automatically retrying is unsafe. |
| Skill edit after preparation | Existing prepared jobs retain their frozen marker_SKILL.md/prompt snapshots and can resume if saved hashes and input bindings remain valid. A new namespace/batch is needed only for a deliberate comparison or newly prepared job; editing the source skill does not rewrite an existing job. |
| Moved approved workbook | Checkpoints store the exact workbook path and receipts store the original resolved path. Moving/renaming a delivered workbook can report a strict mismatch even when contents and the captured production source hash are unchanged. Preserve artifacts; use targeted audited handling, not bulk path replacement. |
| Changed design/settings/input | Existing snapshots and delivered artifacts are historical evidence. Do not reset a completed job or reuse COMPLETE as publication; a changed input or deliberate comparison is a separate revision. |
| Scan failure/repeat | Partial scan output has no rollback, and reuse of the same output directory is rejected. Treat failed output as invalid until independently checked. |
| Lock recovery | PID locks have no lease/heartbeat. Age alone is not evidence that a lock is stale. |

## 4. Safe regression evidence

The discovered test_*.py suite was checked for side effects before running: test-created jobs/workbooks/PDFs/PNGs/receipts use tests/local_temp.py under per-test test-workspace-temp directories and are cleaned up; provider tests use fake transports/process runners; rendering regression fixtures are read-only. No live Responses API or live codex exec grading call was used.

Exact command:

    $env:PYTHONDONTWRITEBYTECODE='1'; python -X utf8 -m unittest discover -s tests -v

Recorded result: 70 passed, 0 failed, 0 errors; 23.809 seconds; exit code 0; OK output. No pip install, environment setup/change, live grading, production CLI, or new production card/publication run was performed.
