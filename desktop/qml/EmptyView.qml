import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

Item {
    id: empty
    property bool reducedMotion: false
    signal createRequested()
    implicitHeight: page.implicitHeight

    ColumnLayout {
        id: page
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.sectionGap
        Text { textFormat: Text.PlainText; text: I18n.tr("作文工作台"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("我的批改任务"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize; font.weight: Font.Bold; wrapMode: Text.Wrap }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("从本地作文材料开始。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize }
        NeoCard {
            Layout.fillWidth: true
            Layout.minimumHeight: 340
            fill: Theme.canvas
            padding: 32
            content: ColumnLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 16
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 56
                    Layout.preferredHeight: 64
                    color: Theme.yellow
                    border.color: Theme.ink
                    border.width: 3
                    radius: 6
                    Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: I18n.tr("文"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 36; font.weight: Font.Bold }
                }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("第一份批改任务，从这里开始。"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("准备好作文 PDF 和学生名单后，建立您的任务。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                NeoButton { Layout.alignment: Qt.AlignHCenter; text: I18n.tr("新建批改任务"); primary: true; reducedMotion: empty.reducedMotion; onClicked: empty.createRequested() }
            }
        }
    }
}
