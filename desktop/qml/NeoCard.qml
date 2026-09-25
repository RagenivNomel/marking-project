import QtQuick 2.15
import QtQuick.Layouts 1.15
import "."

Item {
    id: card
    property color fill: Theme.canvas
    property bool hero: false
    property bool raised: false
    property int padding: Theme.cardPadding
    property int cornerRadius: 12
    property alias content: contentColumn.data

    implicitWidth: 320
    implicitHeight: contentColumn.implicitHeight + padding * 2

    Rectangle {
        id: offset
        x: card.raised || card.hero ? 5 : 0
        y: card.raised || card.hero ? 5 : 0
        width: surface.width
        height: surface.height
        color: card.raised || card.hero ? Theme.ink : "transparent"
        radius: card.cornerRadius
    }
    Rectangle {
        id: surface
        anchors.fill: parent
        color: card.fill
        border.color: Theme.ink
        border.width: card.hero ? 3 : 2
        radius: card.cornerRadius
    }
    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: card.padding
        spacing: 12
    }
}
