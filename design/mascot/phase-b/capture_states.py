"""Offline visual QA of the real QML ProgressPanel using presentation fixtures.

No grader, pipeline, workbook, or feedback generation is invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".desktop-deps"))

from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PIL import Image

from desktop.__main__ import create_app
from desktop.fixtures import demo_state
from desktop.teacher_flow import derive_teacher_flow
from desktop.visual_qa import items


OUT = Path(__file__).resolve().parent / "previews"
OUT.mkdir(exist_ok=True)


def main() -> None:
    app, engine, bridge = create_app(dev_ui=False)
    bridge.setLanguage("en")
    window = engine.rootObjects()[0]
    window.show()

    def show_fixture(completed: bool) -> None:
        state = demo_state("marking", "en")
        state["progress"] = {
            "operation": "mark", "running": not completed,
            "total": 11, "completed": 11 if completed else 4,
            "active": 0 if completed else 2,
            "waiting": 0 if completed else 5,
            "attention": 0,
            "current": "" if completed else "207 · 20 · Demo Student",
            "saved": "11 saved results" if completed else "4 saved results",
        }
        state["teacherFlow"] = derive_teacher_flow(state, "en")
        bridge._state = state  # QA-only presentation injection.
        bridge.changed.emit()
        QTest.qWait(240)

    def save(name: str, step: int) -> None:
        visible = [item for item in items(window.contentItem()) if item.isVisible()]
        scenes = [item for item in visible if item.objectName() == "mascotScene"]
        panels = [item for item in visible if item.objectName() == "progressPanel"]
        assert len(scenes) == len(panels) == 1, (len(scenes), len(panels))
        scene, panel = scenes[0], panels[0]
        scene.setProperty("step", step)
        QTest.qWait(60)
        screenshot = window.grabWindow()
        scale = screenshot.width() / window.width()
        origin = panel.mapToScene(QPointF(0, 0))
        rect = (round(origin.x() * scale), round(origin.y() * scale),
                round(panel.width() * scale), round(panel.height() * scale))
        crop = screenshot.copy(*rect)
        path = OUT / f"{name}.png"
        assert crop.save(str(path)), path
        print(name, scene.property("mode"), scene.property("action"), path)

    def gif_frame(step: int) -> Image.Image:
        visible = [item for item in items(window.contentItem()) if item.isVisible()]
        scene = next(item for item in visible if item.objectName() == "mascotScene")
        panel = next(item for item in visible if item.objectName() == "progressPanel")
        scene.setProperty("step", step)
        QTest.qWait(220)
        screenshot = window.grabWindow()
        scale = screenshot.width() / window.width()
        origin = panel.mapToScene(QPointF(0, 0))
        crop = screenshot.copy(round(origin.x() * scale), round(origin.y() * scale),
                               round(panel.width() * scale), min(700, round(panel.height() * scale)))
        temp = OUT / "_gif-frame.png"
        assert crop.save(str(temp))
        with Image.open(temp) as raw:
            image = raw.convert("RGB")
        temp.unlink()
        return image.resize((round(image.width * 0.65), round(image.height * 0.65)),
                            Image.Resampling.NEAREST)

    show_fixture(False)
    # A paused fixture proves the static home/sleep presentation.
    state = dict(bridge._state)
    state["progress"] = {**state["progress"], "running": False, "active": 0}
    state["teacherFlow"] = derive_teacher_flow(state, "en")
    bridge._state = state
    bridge.changed.emit()
    QTest.qWait(160)
    save("01-idle", 5)

    show_fixture(False)
    save("02-starting-work", 12)
    save("03-transformation", 18)
    save("04-reading", 28)
    save("05-marking", 42)
    save("06-play-interlude", 72)

    motion = [gif_frame(step) for step in
              (8, 12, 15, 16, 17, 18, 19, 20, 24, 28, 32, 36,
               40, 44, 48, 54, 58, 63, 69, 72, 75, 78, 84)]

    show_fixture(True)
    save("07-completed-celebration", 9)
    save("08-completed-settled", 12)
    motion += [gif_frame(step) for step in (0, 2, 4, 5, 6, 7, 8, 9, 10, 12)]
    motion[0].save(OUT / "mascot-in-real-panel.gif", save_all=True,
                   append_images=motion[1:], duration=250, loop=0, optimize=True)
    print("gif", OUT / "mascot-in-real-panel.gif")
    app.quit()


if __name__ == "__main__":
    main()
