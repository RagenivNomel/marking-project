import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

NeoCard {
    id: progress
    objectName: "progressPanel"
    property var progressState: ({})
    property bool reducedMotion: false
    property bool canCancel: false
    property bool rendering: progress.progressState.operation === "render"
    property bool stopping: Boolean(progress.progressState.cancelRequested)
    property string mascotMode: progress.progressState.running === true
        || (progress.progressState.running === undefined && Number(progress.progressState.active || 0) > 0)
        ? "working"
        : (Number(progress.progressState.total || 0) > 0
           && Number(progress.progressState.completed || 0) >= Number(progress.progressState.total || 0)
           && Number(progress.progressState.attention || 0) === 0) ? "completed" : "idle"
    signal cancelRequested()
    property string operationName: rendering ? I18n.choose("体检卡生成进度", "Feedback Card Progress") : I18n.choose("批改进度", "Marking Progress")
    hero: true
    raised: false
    fill: Theme.blue
    content: ColumnLayout {
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: progress.operationName; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; font.weight: Font.DemiBold }
            NeoBadge { label: progress.stopping ? I18n.choose("● 停止中", "● Stopping") : progress.rendering ? I18n.choose("● 生成中", "● Rendering") : progress.mascotMode === "completed" ? I18n.choose("✓ 批改完成", "✓ Marking complete") : progress.mascotMode === "idle" ? I18n.choose("○ 等待批改", "○ Marking paused") : I18n.choose("● 批改中", "● Marking"); tone: progress.stopping || progress.rendering ? "yellow" : progress.mascotMode === "completed" ? "complete" : "blue" }
        }
        Text { textFormat: Text.PlainText; text: progress.stopping ? I18n.choose("先完成当前作文再停止；尚未开始的作文会保留", "Finishing current essays before stopping; essays not started will remain") : progress.rendering ? I18n.choose("正在生成作文体检卡", "Generating feedback cards") : progress.mascotMode === "completed" ? I18n.choose("作文批改已完成", "Marking is complete") : progress.mascotMode === "idle" ? I18n.choose("批改已暂停", "Marking is paused") : I18n.choose("正在批改作文", "Marking each essay"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.bold: true }
        MascotScene {
            Layout.fillWidth: true
            Layout.preferredHeight: 92
            visible: !progress.rendering
            mode: progress.mascotMode
            reducedMotion: progress.reducedMotion
        }
        Item {
            Layout.fillWidth: true; Layout.preferredHeight: 86
            visible: progress.rendering && !progress.reducedMotion && progress.progressState.running === true
            Row {
                anchors.centerIn: parent; spacing: 16
                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        width: 56; height: 66; radius: 8
                        color: index === 0 ? Theme.pink : index === 1 ? Theme.yellow : Theme.cyan
                        border.color: Theme.ink; border.width: 2
                        SequentialAnimation on y {
                            running: progress.progressState.running === true && !progress.reducedMotion
                            loops: Animation.Infinite
                            PauseAnimation { duration: index * 150 }
                            NumberAnimation { from: 0; to: -12; duration: 360; easing.type: Easing.OutQuad }
                            NumberAnimation { from: -12; to: 0; duration: 420; easing.type: Easing.InQuad }
                            PauseAnimation { duration: (2 - index) * 150 }
                        }
                        Text { anchors.centerIn: parent; text: index === 0 ? "文" : index === 1 ? "✎" : "✓"; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 28; font.bold: true }
                    }
                }
            }
        }
        RowLayout {
            spacing: 10
            Text { textFormat: Text.PlainText; text: String(progress.progressState.completed || 0); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 48; font.bold: true }
            Text { textFormat: Text.PlainText; text: "/ " + String(progress.progressState.total || 0) + (progress.rendering ? I18n.choose(" 张体检卡", " cards in total") : I18n.choose(" 份作文", " essays in total")); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: 20 }
        }
        Rectangle {
            Accessible.role: Accessible.ProgressBar
            Accessible.name: (progress.rendering ? I18n.choose("体检卡生成进度：", "Card generation progress: ") : I18n.choose("批改进度：", "Marking progress: ")) + String(progress.progressState.completed || 0) + I18n.choose(" 已完成，共 ", " completed out of ") + String(progress.progressState.total || 0) + (progress.rendering ? I18n.choose(" 张", " cards") : I18n.choose(" 份", " essays"))
            Layout.fillWidth: true
            height: 16
            color: Theme.canvas
            border.color: Theme.ink
            border.width: 2
            radius: 2
            Rectangle {
                width: parent.width * ((Number(progress.progressState.completed || 0)) / Math.max(1, Number(progress.progressState.total || 1)))
                height: parent.height
                color: Theme.deepBlue
                Behavior on width { NumberAnimation { duration: progress.reducedMotion ? 0 : 200; easing.type: Easing.OutCubic } }
            }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 10
            Text { textFormat: Text.PlainText; text: "✓ " + String(progress.progressState.completed || 0) + (progress.rendering ? I18n.choose("张完成", " completed") : I18n.choose("份完成", " completed")); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; font.weight: Font.DemiBold }
            Text { textFormat: Text.PlainText; text: "● " + String(progress.progressState.active || 0) + (progress.rendering ? I18n.choose("张生成中", " generating") : I18n.choose("份处理中", " in progress")); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
            Text { textFormat: Text.PlainText; text: "○ " + String(progress.progressState.waiting || 0) + (progress.stopping && Number(progress.progressState.remaining_not_started || 0) > 0 ? I18n.choose("份尚未开始，会保留", " essays not started will remain") : progress.rendering ? I18n.choose("张等待", " waiting") : I18n.choose("份等待", " waiting")); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
            Text { textFormat: Text.PlainText; text: "△ " + String(progress.progressState.attention || 0) + (progress.rendering ? I18n.choose("张需检查", " need attention") : I18n.choose("份需要处理", " need attention")); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.ink }
        RowLayout {
            Layout.fillWidth: true
            visible: progress.rendering || progress.mascotMode !== "completed" || Boolean(progress.progressState.current)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Text { textFormat: Text.PlainText; text: progress.rendering ? I18n.choose("正在生成", "Currently rendering") : progress.mascotMode === "completed" ? I18n.choose("最后批改", "Last marked") : progress.mascotMode === "idle" ? I18n.choose("上次批改", "Last marked") : I18n.choose("正在批改", "Currently marking"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(progress.progressState.current || (progress.rendering ? I18n.choose("等待生成", "Waiting for the next card") : I18n.choose("当前作文", "Waiting for the next essay"))); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
            }
        }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(progress.progressState.saved || ""); visible: text.length > 0; color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
        RowLayout {
            Layout.fillWidth: true
            visible: progress.canCancel && !progress.rendering && progress.progressState.running === true
            spacing: 12
            NeoButton {
                objectName: "cancelMarkingButton"
                text: progress.stopping ? I18n.choose("正在停止…", "Stopping…") : I18n.choose("取消批改", "Cancel Marking")
                danger: !progress.stopping
                enabled: !progress.stopping
                reason: I18n.choose("停止提交新的作文；正在批改的作文会完成并保存。", "Stop starting new essays; current essays finish and save.")
                reducedMotion: progress.reducedMotion
                onClicked: progress.cancelRequested()
            }
            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: I18n.choose("当前正在批改的作文会完成并保存。", "Current essays will finish and save.")
                color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
                wrapMode: Text.Wrap
            }
        }
    }
}
