import QtQuick 2.15
import "."
import QtQuick.Controls 2.15

Button {
    id: tab
    property bool selected: false
    property bool reducedMotion: false
    signal tabSelected()

    implicitHeight: Theme.controlHeight
    implicitWidth: Math.max(112, contentItem.implicitWidth + 28)
    leftPadding: 14
    rightPadding: 14
    topPadding: 8
    bottomPadding: 8
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    onClicked: tab.tabSelected()
    contentItem: Text { textFormat: Text.PlainText;
        text: tab.text
        color: Theme.ink
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        font.weight: tab.selected ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
    background: Rectangle {
        color: tab.hovered ? Theme.card : "transparent"
        border.color: tab.activeFocus ? Theme.deepBlue : "transparent"
        border.width: tab.activeFocus ? 3 : 0
        radius: 7
        Rectangle {
            visible: tab.selected
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 3
            color: Theme.ink
        }
    }
    Accessible.name: tab.text
    Accessible.role: Accessible.PageTab
}
