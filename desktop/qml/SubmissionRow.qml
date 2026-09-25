import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."
FocusScope {
    id: row
    property var rowData: ({})
    property bool selected: false
    property bool reducedMotion: false
    property bool expanded: false
    signal opened(string submissionId)
    implicitHeight: line.implicitHeight + 24 + (expanded ? detail.implicitHeight + 16 : 0)
    activeFocusOnTab: true
    Accessible.role: Accessible.ListItem
    Accessible.name: String(rowData.label) + " " + String(rowData.identity) + " " + String(rowData.status)
    Keys.onReturnPressed: row.expanded = !row.expanded
    Keys.onEnterPressed: row.expanded = !row.expanded
    Keys.onUpPressed: if (ListView.view) ListView.view.decrementCurrentIndex()
    Keys.onDownPressed: if (ListView.view) ListView.view.incrementCurrentIndex()
    Rectangle { anchors.fill: parent; color: row.rowData.tone === "active" ? Theme.cyan : row.selected ? Theme.card : Theme.canvas }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.ink }
    Rectangle { anchors.fill: parent; color: "transparent"; border.width: row.activeFocus ? 3 : 0; border.color: Theme.deepBlue }
    RowLayout {
        id: line
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 12
        spacing: 12
        Text { textFormat: Text.PlainText; Layout.preferredWidth: 42; text: String(row.rowData.ordinal || ""); font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; color: Theme.secondaryInk }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 2
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(row.rowData.identity || I18n.tr("身份待核对")); font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold; color: Theme.ink; wrapMode: Text.Wrap }
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(row.rowData.label || I18n.tr("作文")); font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; color: Theme.secondaryInk; wrapMode: Text.Wrap }
        }
        NeoBadge { label: String(row.rowData.status || I18n.tr("○ 尚无结果")); tone: String(row.rowData.tone || "neutral") }
        Button {
            objectName: "detailsToggle"
            text: row.expanded ? I18n.tr("收起详情") : I18n.tr("查看详情")
            implicitWidth: 88; implicitHeight: Theme.controlHeight
            font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
            focusPolicy: Qt.StrongFocus
            Accessible.name: text + " · " + String(row.rowData.label)
            onClicked: row.expanded = !row.expanded
            contentItem: Text { textFormat: Text.PlainText; text: parent.text; font: parent.font; color: Theme.ink; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            background: Rectangle { color: "transparent"; border.width: parent.activeFocus ? 3 : 0; border.color: Theme.deepBlue; radius: 5 }
        }
    }
    ColumnLayout {
        id: detail
        visible: row.expanded
        x: 12; y: line.height + 36; width: parent.width - 24
        spacing: 8
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: (row.rowData.facets || []).join(" · "); font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; color: Theme.ink; wrapMode: Text.Wrap }
        TextEdit { Layout.fillWidth: true; readOnly: true; selectByMouse: true; text: String(row.rowData.details || ""); textFormat: TextEdit.PlainText; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; color: Theme.secondaryInk; wrapMode: TextEdit.Wrap }
    }
}
