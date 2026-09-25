import QtQuick 2.15
import QtQuick.Layouts 1.15
import "."

Item {
    id: progress
    property int currentStage: 0
    property bool finished: false
    property var labels: [I18n.choose("作文准备", "Preparation"), I18n.choose("批改", "Marking"), I18n.choose("教师审核", "Teacher Review"), I18n.choose("生成反馈", "Generate Feedback")]
    implicitHeight: 76
    Accessible.role: Accessible.ProgressBar
    Accessible.name: I18n.choose("任务进度", "Task progress")
    Accessible.description: String(labels[Math.max(0, Math.min(3, currentStage))])

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Repeater {
            model: progress.labels
            delegate: Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Rectangle {
                    visible: index < 3
                    x: parent.width / 2 + 17
                    y: 16
                    width: parent.width - 34
                    height: 4
                    color: index < progress.currentStage || progress.finished ? Theme.green : Theme.ink
                }
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 2
                    width: 32; height: 32; radius: 16
                    color: index < progress.currentStage || (progress.finished && index === 3) ? Theme.green : index === progress.currentStage ? Theme.yellow : Theme.canvas
                    border.width: 2; border.color: Theme.ink
                    Text {
                        anchors.centerIn: parent
                        text: index < progress.currentStage || (progress.finished && index === 3) ? "✓" : String(index + 1)
                        color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 16; font.weight: Font.Bold
                    }
                }
                Text {
                    x: 4; width: parent.width - 8; y: 42
                    text: String(modelData)
                    textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    color: Theme.ink; font.family: Theme.fontFamily
                    font.pixelSize: Theme.metaSize
                    font.weight: index === progress.currentStage ? Font.Bold : Font.Normal
                }
            }
        }
    }
}
