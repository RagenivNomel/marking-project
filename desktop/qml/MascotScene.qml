pragma ComponentBehavior: Bound
import QtQuick 2.15

// Presentation only: observes a three-value mode supplied by the parent panel.
Item {
    id: scene
    objectName: "mascotScene"
    property string mode: "idle" // idle, working, completed
    property bool reducedMotion: false
    property int step: 0
    readonly property int workX: Math.max(78, width - 190)
    readonly property bool dust: !reducedMotion && ((mode === "working" && step >= 16 && step < 20)
                                           || (mode === "completed" && step >= 4 && step < 7))
    readonly property bool dustObscures: dust && (step % 4 === 2 || step % 4 === 3)
    readonly property string action: reducedMotion ? (mode === "completed" ? "happy" : mode === "working" ? "read" : "sleep")
        : mode === "idle" ? "sleep"
        : mode === "completed" ? (step < 7 ? "mark" : "happy")
        : step < 16 ? "walk" : step < 20 ? "walk"
        : step >= 69 && step < 78 ? "play"
        : (step >= 36 && step < 48) || (step >= 56 && step < 69)
          || (step >= 82 && step < 94) ? "mark" : "read"
    readonly property int catX: mode === "idle" ? 45
        : reducedMotion ? workX
        : mode === "completed" ? workX
        : step < 16 ? Math.round(45 + (workX - 45) * step / 15)
        : (step >= 69 && step < 78 ? workX + (step < 74 ? 8 : 3) : workX)
    readonly property real rate: action === "sleep" ? 1.1 : action === "walk" ? 4
        : action === "mark" ? 3 : action === "play" ? 2.5 : action === "happy" ? 5 : 1.5
    readonly property bool staticCat: reducedMotion || (mode === "completed" && step >= 12)

    implicitHeight: 92
    clip: true
    onModeChanged: step = 0

    function advance() {
        if (mode === "idle") step = (step + 1) % 36
        else if (mode === "working") step = step >= 97 ? 20 : step + 1
        else if (step < 12) step += 1
    }

    Timer {
        interval: 250
        repeat: true
        running: scene.visible && !scene.reducedMotion
        onTriggered: scene.advance()
    }

    Image {
        source: "../assets/mascot/cat-house.png"
        x: 0; y: 12; width: 76; height: 76
        smooth: false
    }
    Image {
        source: "../assets/mascot/composition-paper.png"
        x: scene.workX + 96; y: 48; width: 36; height: 44
        smooth: false
        visible: scene.mode === "working" && scene.step < 20
    }
    Image {
        source: "../assets/mascot/red-pen.png"
        x: scene.workX + 127; y: 51; width: 28; height: 28
        smooth: false
        visible: scene.mode === "working" && scene.step < 20
    }
    Image {
        source: "../assets/mascot/paper-stack.png"
        x: scene.workX + 78; y: 56; width: 42; height: 36
        smooth: false
        visible: scene.mode === "completed" && (scene.reducedMotion || scene.step >= 7)
    }

    AnimatedSprite {
        id: cat
        objectName: "mascotCat"
        x: scene.catX
        y: scene.mode === "completed" && scene.step >= 8 && scene.step <= 10 ? 15 : 28
        width: 64; height: 64
        source: "../assets/mascot/cat-" + scene.action + ".png"
        frameWidth: 64; frameHeight: 64
        frameCount: scene.action === "sleep" || scene.action === "play" ? 3 : 4
        frameRate: scene.rate
        loops: AnimatedSprite.Infinite
        interpolate: false
        running: scene.visible && !scene.staticCat
        visible: !scene.staticCat && !scene.dustObscures
    }
    Image {
        x: scene.catX
        y: 28
        width: 64; height: 64
        source: "../assets/mascot/cat-" + scene.action + ".png"
        sourceClipRect: Qt.rect(0, 0, 64, 64)
        smooth: false
        visible: scene.staticCat
    }

    // A short restrained pixel cloud hides the instant accessory swap.
    Item {
        id: puff
        x: scene.workX + 4; y: 31
        width: 68; height: 55
        visible: scene.dust
        Rectangle { x: 5; y: 20; width: 30; height: 23; color: "#FFF0C7"; border.color: "#302F3B"; border.width: 2 }
        Rectangle { x: 21; y: 8; width: 33; height: 29; color: "#FFF0C7"; border.color: "#302F3B"; border.width: 2 }
        Rectangle { x: 40; y: 19; width: 23; height: 22; color: "#FFF0C7"; border.color: "#302F3B"; border.width: 2 }
        Rectangle { x: 3; y: 9; width: 7; height: 7; color: "#D9C29E"; border.color: "#302F3B"; border.width: 1 }
        Rectangle { x: 58; y: 5; width: 6; height: 6; color: "#D9C29E"; border.color: "#302F3B"; border.width: 1 }
    }
}
