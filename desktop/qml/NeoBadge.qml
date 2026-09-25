import QtQuick 2.15
import "."

Rectangle {
    id: badge
    property string label: I18n.tr("状态")
    property string tone: "neutral"
    property int fontSize: 14

    implicitHeight: 29
    implicitWidth: labelText.implicitWidth + 20
    radius: 5
    color: tone === "green" || tone === "complete" ? Theme.green : tone === "pink" || tone === "attention" ? Theme.magenta : tone === "blue" || tone === "active" ? Theme.cyan : tone === "yellow" || tone === "pending" ? Theme.yellow : Theme.neutral
    border.color: Theme.ink
    border.width: 2

    Text { textFormat: Text.PlainText;
        id: labelText
        anchors.centerIn: parent
        width: parent.width - 20
        text: badge.label
        color: Theme.ink
        font.family: Theme.fontFamily
        font.pixelSize: badge.fontSize
        font.weight: Font.DemiBold
        wrapMode: Text.NoWrap
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
}
