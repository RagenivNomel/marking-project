# Mum's marking app

Status: packaging design, grounded in the current project. The marking skill integration described below is implemented. A desktop interface and installer have not yet been built. Windows is the working assumption; a Mac release would need its own build and verification.

## The experience

Mum opens a desktop shortcut and starts a batch. She selects the complete set of PDFs, the class roster, the essay question and a feedback-card design. The app remembers her usual settings.

1. **Add papers:** accept either front/back scan pairs in an explicit order or already separated student PDFs. Show page previews and counts; never guess front/back pairing from an arbitrary folder listing.
2. **Check students:** run the existing scan splitter when needed, reconcile submissions with the roster, and show missing, duplicate or uncertain identities for correction. Every source page must be accounted for, including intentionally excluded pages. Existing hand-reviewed identity decisions can be imported.
3. **Mark:** show progress per student and save each result immediately. Keep unreadable papers and failed requests visible in an attention queue. Show how many papers succeeded, need attention or have not started.
4. **Review:** show the student's PDF next to editable feedback. Preserve teacher-owned scores and require the existing review decision before export. Save corrections through one authoritative record; support the current Excel workflow through explicit import/export rather than simultaneous background writes to an open workbook.
5. **Export:** render approved feedback using the selected template, then produce individual cards and a combined printable PDF. Include an export manifest so a partial batch cannot look complete.

Resume, regrade and rerender should be different actions. Resume continues saved work. Regrade creates a new marking revision. Rerender changes presentation using approved feedback without calling a marker.

## Keep three parts separate

| Part | Contents | How it changes |
| --- | --- | --- |
| Application engine | Scan orchestration, roster matching, checkpoints, validation, review, Excel adapters and rendering logic | Versioned app updates |
| Marking settings | SKILL.md, rubric, reference example, text limits and model profile | Editable settings with saved revisions |
| Design library | Background artwork, layout field mappings, font assets and preview image | Add or revise a design pack |

Keep editable settings and jobs in Mum's writable data folder, outside the installed application. An app update must preserve both. Ship factory defaults separately and provide an explicit restore-defaults action.

## Marking instructions: implemented now

The active instructions are `grading/skills/sol-grader/SKILL.md`. This one shared skill is injected into both Sol and Luna marking requests, through either existing backend. It replaces `grading/prompts/sol_calibration_v2.txt` as the active instruction source; the old file remains for historical reference.

Edit the Chinese feedback-style section to change tone, specificity, emphasis or how suggestions are expressed. The rubric, permitted ratings, required fields and hard character limits remain separately validated by Python. Changing the set of criteria or introducing another grading system is a contract change, not just a style edit.

Every newly prepared job saves `marker_SKILL.md`, includes its content in `prompt_snapshot.txt`, and records its SHA-256 in `grading_input_manifest.json`. Both providers receive the saved prompt. Editing the source skill after preparation does not change that job. New jobs use the edited source. Tampering with a saved snapshot is rejected. Older jobs without a separate skill snapshot retain their original saved prompt.

For a controlled comparison, run the same paper under two different batch names, changing only the skill between them. Review both outputs alongside the original paper. Repeating an existing completed batch is a resume and will not test the edit. Comparing more than one paper is necessary to judge whether the change helps consistently.

An optional top-level `marker_skill_path` in `config/calibration_model.json` selects another skill file. Relative paths resolve from the configuration folder; absolute paths also work. The application can use this to point at its user-editable settings folder. The Python constructor also accepts `marker_skill_path` for tests and integration.

Current snapshot scope is one prepared student job. The packaged app should add a **batch-level settings snapshot before processing the first student** and pass that frozen configuration to every student. Edits can be saved at any time, but should apply to the next batch or an explicit new revision. This prevents half a class being marked with different settings after a mid-run edit.

## Template generation and the design library

Retain the existing renderer's field mapping, text measurement, wrapping, finite font-size fallbacks and overflow checks. It should continue rendering the exact approved text.

Each design pack should contain:

```text
designs/<design-id>/<revision>/
    manifest.json        name, revision, supported record schema and asset hashes
    background.png       artwork
    layout.json          field boxes, typography, spacing and alignment
    fonts/               pinned font files and their license notices
    preview.png          a preview produced from fictional feedback
```

Creating or editing a design is a separate authoring operation. A template generator produces a candidate pack; the app validates its field coverage, assets and text fit, then previews it with short and long sample feedback before it enters the design picker. Routine student rendering uses the saved pack without generating fresh artwork or coordinates.

The current `PillowRenderer(layout_path=...)` already accepts an alternative layout, but its validator is tied to the existing 1024×1536 card and eight criteria. The current layouts use the pinned font stored beside them in `rendering/template/`. Before portable design packs are supported, add the pack manifest and selection layer, and record the selected revision in the batch. New canvas sizes need deliberate renderer/schema support. A different purpose that retains the same fields can reuse the engine; a different set of assessment fields needs an explicit adapter/schema revision.

Preserve old design revisions for reproducing previous exports. Selecting a new design can rerender the same approved comments without regrading.

## Packaging approach

Build a small native desktop interface around the Python services, with a background worker for scanning, marking and rendering so the window remains responsive. Expose progress and errors as structured events instead of making the interface interpret console output. Define cancellation at a durable checkpoint and keep interrupted in-flight marking visible.

For a Windows first release, package the Python application and dependencies as a PyInstaller folder bundle, then wrap that folder in an installer that creates a desktop shortcut. PyInstaller supports this arrangement and requires a build for the target operating system: [official packaging documentation](https://pyinstaller.org/en/stable/operating-mode.html).

Include the PDF and OCR native dependencies, Chinese OCR data, pinned font assets, reference example and factory design. Verify redistribution licenses and retain notices. Replace machine-specific dependency paths and pin tested dependency versions. The app must work on a clean Windows account without this project's development runtime or source folder.

The current real grader depends on either an installed Codex command with its own saved login or the configured API backend. First-run setup must check the chosen backend on Mum's computer and report what needs setting up. Do not ship this machine's credentials. A local desktop interface does not make remote AI marking offline. Preserve the existing backend choice initially; validate it on the destination machine before claiming the installer is ready.

## Repeatability and remaining integration work

Fresh model output is not guaranteed identical even with identical input and instructions; [OpenAI's model optimization guidance](https://developers.openai.com/api/docs/guides/model-optimization) explicitly describes this variability. The practical guarantee is reproducible processing with recorded inputs/settings and replay of saved marking results. Record model identity and settings alongside PDF, prompt, rubric, template and software versions.

The code already supplies isolated marking, per-job snapshots, strict result validation, workbook persistence and deterministic card rendering. The production batch entry point currently consumes an existing split pile plus reviewed identity decisions and stops at `VALIDATED/PENDING`. The missing app work is:

1. A single batch service joining raw-PDF intake, identity decisions, marking, review and export, with a batch manifest and frozen settings.
2. A desktop interface for those stages, settings editing, a small before/after marking comparison and the design picker.
3. A production review/export transition and batch printable-PDF assembly using the existing validated rendering path.
4. Recovery for every real-workflow checkpoint. In particular, calibration currently refuses to continue from `GRADED`; locally saved responses should be revalidated without another model call. A lost in-flight response must be shown as uncertain before an explicit retry, rather than silently reissued.
5. Portable dependency paths, versioned design packs, installer creation and a clean-machine acceptance run.

Release verification should cover a whole multi-PDF batch, identity corrections, unreadable pages, a failed marker, app restart, a skill edit between batches, teacher edits, design changes, text overflow and complete printable export. Use fictional/synthetic papers for integration tests, then a deliberately selected real sample to assess marking quality.
