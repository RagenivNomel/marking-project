# Phase B mascot integration report

The approved orange and cream cat now lives inside the application's existing blue Marking Progress panel. This is presentation only. All preview counters and names were injected into a local QML fixture; no marking request was run.

## Sprite Maker investigation

The [Sprite Maker repository](https://github.com/JohnKinyanjui/sprite-maker) is cloned in `design/sprite-maker-tooling/`. The official Windows v0.3.2 GUI release was downloaded and installed to `design/sprite-maker-tooling/isolated-install/`, outside the teacher application's dependency folders. Its `sprite-maker.exe` launches successfully when allowed outside the filesystem sandbox, so the earlier claim that the native application itself could not run was too broad. The initial sandboxed launch exited with Windows status `0xC0000409`. The installed release contains only the GUI executable and uninstaller; it does not contain the separate `sprite-studio-mcp` binary required by the native `/pack` automation workflow. Building that binary from the source requires Rust/Cargo, which is absent here; Bun is also absent for the source development setup. The GUI's native folder picker did not expose a controllable target to the available Windows app-control interface. No teacher-app dependencies or environment were changed.

I therefore kept the documented compatible workflow: approved master art as identity anchor, fixed 64×64 cells and foot baseline, transparent PNGs, one frame map, development-only source/pack files, and local runtime sprites. The Phase A pack manifest remains ready for future decorative assets. These exports are not represented as native `/pack` output.

## Requested 43-point handoff

1. **Animation families:** idle, working, completed.
2. **Reusable sub-actions:** sleep, walk, read, mark, play with pen, happy jump, dust transition.
3. **Frames:** sleep 3; walk 4; read 4; mark 4; play 3; happy 4.
4. **Playback:** sleep 1.1 fps; walk 4; read 1.5; mark 3; play 2.5; happy 5. A 250 ms visual sequence timer selects sub-actions.
5. **Sheet sizes:** 64 pixels high; three-frame sheets 192×64, four-frame sheets 256×64.
6. **Runtime format:** transparent, fixed-cell PNG sheets plus `sprites.json`. No network or runtime image generation.
7. **Master identity:** Phase A master and contact sheet guided all poses; cells share a fixed baseline, palette, outline, face, and head/body proportion.
8. **Walking length:** the walk sequence was reviewed against the compact approved silhouette; conversion uses one common box across its four poses instead of stretching frames separately.
9. **Cream bib:** read, mark, play, walk, sleep, and happy sheets all keep the light bib visible at runtime size.
10. **Other markings:** forehead stripes, muzzle, cream paws, orange/cream boundary, and curled tail remain visible in the reviewed frames.
11. **Work accessories:** glasses and graduation cap appear in read, mark, and play; ordinary walk, sleep, and happy poses omit them.
12. **Work transformation:** a small QML pixel dust cloud briefly obscures the cat, then reveals Professor Cat. No spin.
13. **Duration:** four 250 ms sequence steps, approximately one second including the brief reveal.
14. **Working sequence:** walk to desk; transform; read; mark; read; mark; brief pen play; read; mark; then repeat a longer work cycle.
15. **Reading:** four-frame, 1.5 fps paper inspection loop.
16. **Marking:** four-frame, 3 fps red-pen motion loop.
17. **Play:** three-frame, 2.5 fps pen pawing interlude inside the working family; the cat resumes reading and marking.
18. **Completion:** workwear cat finishes; checked paper stack appears; four-frame happy hop plays briefly.
19. **Reverse transformation:** the same small dust effect conceals removal of glasses and cap.
20. **Settled state:** ordinary cat displays a static seated happy frame; the celebration does not loop indefinitely.
21. **House:** remains fixed on the left as the idle home landmark while the cat moves to the right for work.
22. **New QML:** `desktop/qml/MascotScene.qml`.
23. **Modified QML:** `desktop/qml/ProgressPanel.qml` and `desktop/qml/TeacherFlowSection.qml`.
24. **Assets:** six cat sprite sheets, four reused props, `sprites.json`, six development source strips, and preview captures.
25. **Integration:** existing ProgressPanel inside the real blue TeacherFlowSection panel.
26. **Safe zones:** scene occupies a dedicated 92-pixel-high row between the heading and real counters. No cat or prop crosses status, progress, errors, or controls.
27. **Clipping:** MascotScene sets `clip: true`; it has no mouse handlers.
28. **Resize:** work position derives from actual scene width with a lower bound; movement narrows with the panel.
29. **Pixel rendering:** offline conversion uses nearest-neighbor resizing; QML `Image.smooth` and `AnimatedSprite.interpolate` are disabled.
30. **Performance:** small local sheets, one 250 ms QML sequence timer, built-in sprite playback, and five dust rectangles. No Python animation loop at runtime.
31. **Python changes:** none in production application code. New `design/mascot/phase-b/build_assets.py` is an offline asset converter; `capture_states.py` is an offline visual QA helper. Neither is imported by the teacher app.
32. **Backend tests:** 118 passed in the offline unit suite on the final full run. One earlier full run had an intermittent assertion in the existing parallel retry test; its seven-test module passed on an isolated rerun, followed by the full 118-test pass.
33. **Desktop tests:** 51 passed in the offline unit suite.
34. **QML validation:** `qmllint` exited successfully; remaining warnings are pre-existing unqualified-reference warnings in the surrounding panels. The real QML root loaded and all eight fixture states rendered.
35. **Real grading calls:** zero.
36. **Grading semantics:** untouched.
37. **Parallel orchestration:** untouched.
38. **Excel persistence:** untouched.
39. **Workbook/storage paths:** untouched.
40. **Feedback rendering/card generation:** untouched.
41. **Open Results/Open Feedback Cards:** untouched.
42. **Real-panel screenshots:** `previews/01-idle.png`, `02-starting-work.png`, `03-transformation.png`, `04-reading.png`, `05-marking.png`, `06-play-interlude.png`, `07-completed-celebration.png`, `08-completed-settled.png`.
43. **Motion preview:** `previews/mascot-in-real-panel.gif` (26 distinct display frames, 1431×455, 250 ms per frame).

The existing progress counters and completion condition remain authoritative. The mascot only observes panel presentation state and cannot advance counters or alter marking work.
