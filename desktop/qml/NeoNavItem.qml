import QtQuick 2.15
import "."
import QtQuick.Controls 2.15

Button {
    id: nav
    property bool selected: false
    property bool reducedMotion: false
    signal navigated()

    implicitHeight: Math.max(Theme.fieldHeight, contentItem.implicitHeight + topPadding + bottomPadding)
    leftPadding: 14
    rightPadding: 14
    topPadding: 8
    bottomPadding: 8
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    onClicked: nav.navigated()

    contentItem: Text { textFormat: Text.PlainText;
        text: nav.text
        color: Theme.ink
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        font.weight: nav.selected ? Font.DemiBold : Font.Normal
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
    background: Item {
        Rectangle {
            x: nav.selected ? 3 : 0
            y: nav.selected ? 3 : 0
            width: selectedSurface.width
            height: selectedSurface.height
            color: nav.selected ? Theme.ink : "transparent"
            radius: 7
        }
        Rectangle {
            id: selectedSurface
            anchors.fill: parent
            color: nav.selected ? Theme.pink : nav.hovered ? Theme.cyan : "transparent"
            border.color: nav.selected || nav.activeFocus ? Theme.ink : "transparent"
            border.width: nav.selected ? 2 : nav.activeFocus ? 3 : 0
            radius: 7
            Behavior on color { ColorAnimation { duration: nav.reducedMotion ? 0 : 120 } }
        }
        Rectangle {
            anchors.fill: selectedSurface
            anchors.margins: -4
            color: "transparent"
            border.color: nav.activeFocus ? Theme.deepBlue : "transparent"
            border.width: 3
            radius: 9
        }
    }
    Accessible.name: nav.text
    Accessible.role: Accessible.ListItem
}
