import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

Item {
    id: systemView
    property bool reducedMotion: false
    implicitHeight: page.implicitHeight

    ColumnLayout {
        id: page
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.sectionGap
        Text { textFormat: Text.PlainText; text: I18n.tr("设计系统 / 组件状态"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize; font.weight: Font.Bold; wrapMode: Text.Wrap }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("温暖的纸面，清楚的结构。颜色承载状态，边框强调操作，留白让老师专注。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
        Flow {
            Layout.fillWidth: true
            spacing: 12
            Repeater {
                model: [
                    { label: I18n.tr("进行中"), tone: "blue" },
                    { label: I18n.tr("已完成"), tone: "green" },
                    { label: I18n.tr("待审核"), tone: "yellow" },
                    { label: I18n.tr("需处理"), tone: "pink" },
                    { label: I18n.tr("等待中"), tone: "neutral" }
                ]
                delegate: NeoBadge { label: modelData.label; tone: modelData.tone }
            }
        }
        NeoCard {
            Layout.fillWidth: true
            fill: Theme.card
            content: ColumnLayout {
                spacing: 16
                Text { textFormat: Text.PlainText; text: I18n.tr("按钮与反馈"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold }
                Flow {
                    Layout.fillWidth: true
                    spacing: 12
                    NeoButton { text: I18n.tr("主要操作"); primary: true; reducedMotion: systemView.reducedMotion }
                    NeoButton { text: I18n.tr("次要操作"); reducedMotion: systemView.reducedMotion }
                    NeoButton { text: I18n.tr("键盘焦点"); primary: true; reducedMotion: systemView.reducedMotion; activeFocusOnTab: true }
                    NeoButton { text: I18n.tr("暂不可用"); primary: false; enabled: false; reason: I18n.tr("生产连接尚未接入"); reducedMotion: systemView.reducedMotion }
                    NeoButton { text: I18n.tr("正在检查…"); loading: true; enabled: false; reason: I18n.tr("检查期间禁止重复操作"); reducedMotion: systemView.reducedMotion }
                }
                Text { textFormat: Text.PlainText; text: I18n.tr("44px最小高度 · 7px圆角 · 2px边框 · 3–4px硬阴影 · 焦点环独立显示"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sectionGap
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.canvas
                content: ColumnLayout {
                    spacing: 10
                    Text { textFormat: Text.PlainText; text: I18n.tr("主标题 30 / 42"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize; font.weight: Font.Bold }
                    Text { textFormat: Text.PlainText; text: I18n.tr("区域标题 22 / 33"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold }
                    Text { textFormat: Text.PlainText; text: I18n.tr("正文16 / 26：原有评语没有被修改。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                    Text { textFormat: Text.PlainText; text: I18n.tr("辅助信息14 / 21：已读取保存的内容。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
                }
            }
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.canvas
                content: ColumnLayout {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: I18n.tr("清楚表达每一种状态"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        NeoBadge { label: I18n.tr("● 批改中"); tone: "blue" }
                        NeoBadge { label: I18n.tr("✓ 已生成"); tone: "green" }
                        NeoBadge { label: I18n.tr("○ 待审核"); tone: "yellow" }
                        NeoBadge { label: I18n.tr("△ 需要处理"); tone: "pink" }
                        NeoBadge { label: I18n.tr("○ 等待中"); tone: "neutral" }
                    }
                    DetailsDisclosure { Layout.fillWidth: true; detailText: I18n.tr("完整文件路径、审核标识与诊断信息在展开后显示。"); reducedMotion: systemView.reducedMotion }
                }
            }
        }
    }
}
