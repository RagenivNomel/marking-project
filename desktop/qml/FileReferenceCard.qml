import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

NeoCard {
    id: fileCard
    property string title: I18n.tr("审核工作簿")
    property string path: I18n.tr("尚未选择文件")
    property string subtitle: I18n.tr("本地文件引用")
    property bool selected: false
    property bool reducedMotion: false
    property string actionText: I18n.tr("检查路径")
    property bool actionEnabled: true
    property bool actionOpensFile: false
    signal inspectRequested()
    signal openRequested()

    fill: Theme.canvas
    padding: 16
    content: ColumnLayout {
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Rectangle {
                Layout.preferredWidth: 34
                Layout.preferredHeight: 40
                color: Theme.green
                border.color: Theme.ink
                border.width: 2
                radius: 4
                Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: "X"; color: Theme.ink; font.pixelSize: 20; font.weight: Font.Bold }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: fileCard.title; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: fileCard.subtitle; color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
            }
        }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true
            text: fileCard.path
            color: Theme.ink
            font.family: Theme.fontFamily
            font.pixelSize: 15
            wrapMode: Text.WrapAnywhere
        }
        NeoButton {
            Layout.alignment: Qt.AlignLeft
            text: fileCard.actionText
            enabled: fileCard.actionEnabled
            primary: false
            reducedMotion: fileCard.reducedMotion
            onClicked: fileCard.actionOpensFile ? fileCard.openRequested() : fileCard.inspectRequested()
        }
    }
}
