# UI polish screenshot inventory

The review group contains eleven extensionless PNG files in `design references/UI elements to fix` and two related extensionless PNG files one directory above it. All thirteen were opened as images before the UI edits.

| Screenshot filename | View and marked issue | Responsible UI | UI correction |
| --- | --- | --- | --- |
| `fix wacky chinese rendering` | Workspace title and Chinese subtitle have inconsistent glyph styling, especially in English mode | `Theme.qml`, `desktop/__main__.py`, shared QML text | Keep the installed Microsoft YaHei Chinese family for shared text in both interface languages, including mixed Chinese/English lines. |
| `get rid of this white bar at the top and this entire top section is unneccessary` | Marking view has native white caption and redundant app header/notice | `Main.qml`, `desktop/__main__.py` | Remove the teacher header and notice; request a cream Windows native caption. |
| `non live counter and ugly turn it into something related to the animation` | Progress card shows elapsed time as a static value | `ProgressPanel.qml` | Remove elapsed display; use motion only while the existing progress state says running. |
| `remove` | Reduce motion control in teacher header | `Main.qml` | Remove it from normal teacher mode; developer mode retains the setting. |
| `remove the white border at the top and make this window rounded  instead of square` | Choose Submissions dialog has a white default title strip and square looking top | `InspectPathsDialog.qml` | Replace default dialog header with a cream in-content title and rounded existing background. |
| `remove this` | Home shows a stale resume feature note | `HomeView.qml` | Remove the note and its layout gap. |
| `remove this entire header section from the end product` | Marking view has redundant status prose above the work area | `Main.qml` | Hide the normal teacher header/notice and reclaim its height. |
| `rename to just say marking instead of ai marking` | Marking card advertises AI in its normal heading | `ProgressPanel.qml`, `WorkflowProgress.qml`, `WorkspaceView.qml`, `teacher_flow.py` | Use Marking/批改 for stage, headline, and start/resume action copy. |
| `this isnt correct when generating the feedback cards` | Render in progress is shown with an old stage; completion can appear early | `WorkspaceView.qml`, `WorkflowProgress.qml`, `TeacherFlowSection.qml` | Show Generate Feedback while existing render progress is running; hide completion action until rendering stops and show final check only after completion. |
| `too much empty space at the bottom` | Completed workspace leaves excessive blank area on a tall desktop | `Main.qml`, `HomeView.qml` | Use a shorter default window and center the short completed page in the available viewport; remove redundant Home spacer. |
| `very boring loading screen add some dancing animations here` | Marking progress card lacks a clear active motif | `ProgressPanel.qml` | Add restrained bouncing paper, pencil, and check motifs driven only by the existing `running` flag. |
| `messed up chinese font` | Student name in progress card falls back to a different Chinese style | `Theme.qml`, `desktop/__main__.py` | Apply the installed Microsoft YaHei family consistently in both language modes; no image or bundled font. |
| `remove this section as well` | Workspace has a Local Assignment badge | `WorkspaceView.qml` | Remove the badge from normal teacher mode; retain only the demo indicator in developer mode. |

The native Windows frame remains for dragging, resizing, minimize, and close. Rounded native corners depend on Windows DWM support; the application requests them without using a fragile frameless window.
