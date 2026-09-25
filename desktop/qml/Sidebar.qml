import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: sidebar
    objectName: "developerSidebar"
    property string activeView: "home"
    property bool compact: false
    property bool reducedMotion: false
    property var appState: ({})
    signal navigate(string view)
    implicitWidth: compact ? 184 : 216
    Rectangle { anchors.fill: parent; color: Theme.sidebar }
    Rectangle { anchors.right: parent.right; width: 3; height: parent.height; color: Theme.ink }
    Flickable {
        id: scroll
        anchors.fill: parent
        anchors.rightMargin: 5
        contentWidth: width
        contentHeight: Math.max(height, groups.implicitHeight + 56)
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { }
        ColumnLayout {
            id: groups
            x: sidebar.compact ? 14 : 20
            y: 28
            width: scroll.width - x * 2
            height: scroll.contentHeight - 56
            spacing: 28
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.yellow; raised: true; padding: 10; cornerRadius: Theme.bubbleRadius
                content: RowLayout {
                    spacing: 6
                    Rectangle {
                        Layout.preferredWidth: 28; Layout.preferredHeight: 38
                        color: Theme.pink; border.color: Theme.ink; border.width: 2; radius: 5
                        Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: I18n.tr("文"); font.family: Theme.fontFamily; font.pixelSize: 22; font.bold: true }
                    }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("作文工作台"); wrapMode: Text.Wrap; font.family: Theme.fontFamily; font.pixelSize: I18n.english ? (sidebar.compact ? 12 : 14) : (sidebar.compact ? 15 : 17); font.bold: true; color: Theme.ink }
                }
            }
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.canvas; raised: true; padding: 8; cornerRadius: Theme.bubbleRadius
                content: ColumnLayout {
                    spacing: 4
                    NeoNavItem { Layout.fillWidth: true; text: I18n.tr("我的批改任务"); selected: sidebar.activeView !== "create"; reducedMotion: sidebar.reducedMotion; onNavigated: sidebar.navigate("home") }
                    NeoNavItem { Layout.fillWidth: true; text: I18n.tr("查看本地材料"); selected: sidebar.activeView === "create"; reducedMotion: sidebar.reducedMotion; onNavigated: sidebar.navigate("create") }
                }
            }
            NeoCard {
                Layout.fillWidth: true
                visible: sidebar.appState.scenario !== "empty"
                fill: Theme.card; raised: true; padding: 14; cornerRadius: Theme.bubbleRadius
                content: ColumnLayout {
                    spacing: 16
                    Text { textFormat: Text.PlainText; text: sidebar.appState.demo ? I18n.tr("最近的任务 · 演示") : I18n.tr("当前本地任务"); font.family: Theme.fontFamily; font.pixelSize: 14; color: Theme.secondaryInk }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(sidebar.appState.title || I18n.tr("作文三 · 那一次，我学会了坚持")); wrapMode: Text.Wrap; font.family: Theme.fontFamily; font.pixelSize: 16; font.weight: Font.DemiBold; color: Theme.ink }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: sidebar.appState.demo ? I18n.tr("207 / 211 班 · 演示数据") : I18n.tr("已读取保存的资料"); wrapMode: Text.Wrap; font.family: Theme.fontFamily; font.pixelSize: 14; color: Theme.secondaryInk }
                    Text { textFormat: Text.PlainText; visible: Boolean(sidebar.appState.demo); Layout.fillWidth: true; text: I18n.tr("作文二 · 一次尝试\n207 班 · 已生成（演示）"); wrapMode: Text.Wrap; font.family: Theme.fontFamily; font.pixelSize: 14; color: Theme.secondaryInk }
                }
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: 20 }
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.yellow; raised: true; padding: 12; cornerRadius: Theme.bubbleRadius
                content: Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("中二高华作文批改\n本地文件工作区"); wrapMode: Text.Wrap; font.family: Theme.fontFamily; font.pixelSize: 14; color: Theme.ink }
            }
        }
    }
    Repeater {
        model: [{fraction:0.26, diameter:46, fill:Theme.cyan}, {fraction:0.56, diameter:58, fill:Theme.magenta}, {fraction:0.80, diameter:34, fill:Theme.yellow}]
        delegate: Item {
            x: sidebar.width - width / 2
            y: sidebar.height * modelData.fraction
            width: modelData.diameter; height: width
            Rectangle { x: 4; y: 4; width: parent.width; height: parent.height; radius: width/2; color: Theme.ink }
            Rectangle { width: parent.width; height: parent.height; radius: width/2; color: modelData.fill; border.width: 3; border.color: Theme.ink }
        }
    }
}
