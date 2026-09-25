import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

NeoCard {
    id: panel
    property string kicker: I18n.tr("下一步")
    property string title: ""
    property string subtitle: ""
    property string tone: "pending"
    property string actionText: I18n.tr("查看详情")
    property string reason: I18n.tr("此操作在生产连接完成前不可用。")
    property bool reducedMotion: false
    property bool actionEnabled: false
    property bool completed: false
    signal actionRequested()

    hero: true
    raised: true
    fill: tone === "active" ? Theme.blue : tone === "attention" ? Theme.magenta : tone === "card" || tone === "complete" ? Theme.card : Theme.yellow
    padding: Theme.cardPadding
    content: ColumnLayout {
        spacing: 10
        Rectangle {
            visible: panel.completed
            width: 76; height: 76; radius: 38
            color: Theme.green; border.color: Theme.ink; border.width: 3
            Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: "✓"; font.pixelSize: 40; color: Theme.ink }
        }
        Text { textFormat: Text.PlainText; text: panel.kicker; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; font.weight: Font.DemiBold }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: panel.title; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold; wrapMode: Text.Wrap }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; visible: panel.subtitle.length > 0; text: panel.subtitle; color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
        RowLayout {
            spacing: 12
            NeoButton {
                objectName: "primaryAction"
                text: panel.actionText
                primary: true
                enabled: panel.actionEnabled
                onClicked: panel.actionRequested()
                reason: panel.reason
                reducedMotion: panel.reducedMotion
            }
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: panel.reason; color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
        }
    }
}
