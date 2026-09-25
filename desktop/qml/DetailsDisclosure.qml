import QtQuick 2.15
import "."
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: disclosure
    property string summary: I18n.tr("查看详情")
    property string detailText: ""
    property bool expanded: false
    property bool reducedMotion: false
    property alias content: detailColumn.data

    implicitWidth: 300
    implicitHeight: summaryButton.height + (expanded ? detailColumn.implicitHeight + 12 : 0)
    clip: true

    NeoButton {
        id: summaryButton
        objectName: "detailsToggle"
        width: Math.max(128, summaryText.implicitWidth + 54)
        text: (disclosure.expanded ? "⌄ " : "› ") + disclosure.summary
        primary: false
        reviewOnly: false
        reducedMotion: disclosure.reducedMotion
        reason: I18n.tr("展开后显示审核记录、文件位置与技术信息")
        onClicked: disclosure.expanded = !disclosure.expanded
        Accessible.name: disclosure.summary
        Accessible.description: disclosure.expanded ? I18n.tr("已展开") : I18n.tr("已折叠")
        contentItem: RowLayout {
            spacing: 5
            Text { textFormat: Text.PlainText;
                id: summaryText
                text: summaryButton.text
                color: Theme.ink
                font.family: Theme.fontFamily
                font.pixelSize: Theme.metaSize
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
        }
    }
    ColumnLayout {
        id: detailColumn
        y: summaryButton.height + 12
        width: parent.width
        spacing: 8
        opacity: disclosure.expanded ? 1 : 0
        visible: disclosure.expanded
        Text { textFormat: Text.PlainText;
            visible: disclosure.detailText.length > 0
            text: disclosure.detailText
            color: Theme.secondaryInk
            font.family: Theme.fontFamily
            font.pixelSize: Theme.metaSize
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }
    Behavior on implicitHeight { NumberAnimation { duration: disclosure.reducedMotion ? 0 : 180; easing.type: Easing.OutCubic } }
}
