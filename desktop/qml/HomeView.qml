import QtQuick 2.15
import QtQuick.Layouts 1.15
import "."

Item {
    id: home
    property var appState: ({})
    property string demoKey: "home"
    property bool reducedMotion: false
    property bool developerMode: false
    property var workflows: []
    property var selectedWorkflow: ({})
    readonly property bool workflowChosen: Boolean(home.selectedWorkflow && home.selectedWorkflow.id)
    signal navigateRequested(string view)
    signal inspectRequested()
    signal workflowSelected(string workflowId)
    signal workflowListRequested()
    implicitHeight: home.developerMode ? developerPage.implicitHeight
        : home.workflowChosen ? teacherPage.implicitHeight : workflowPage.implicitHeight

    ColumnLayout {
        id: workflowPage
        visible: !home.developerMode && !home.workflowChosen
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 28

        Text {
            textFormat: Text.PlainText; Layout.fillWidth: true
            text: I18n.choose("选择工作流程", "Choose a Workflow")
            color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize
            font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        }
        Text {
            textFormat: Text.PlainText; Layout.fillWidth: true
            text: I18n.choose("选择这次要使用的工作流程。", "Choose the workflow to use for this task.")
            color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        }
        Repeater {
            model: home.workflows
            delegate: NeoCard {
                required property var modelData
                Layout.fillWidth: true
                Layout.maximumWidth: 760
                Layout.alignment: Qt.AlignHCenter
                fill: Theme.card
                padding: 28
                content: RowLayout {
                    spacing: 20
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            textFormat: Text.PlainText; Layout.fillWidth: true
                            text: I18n.choose(modelData.nameZh, modelData.nameEn)
                            color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize
                            font.weight: Font.Bold; wrapMode: Text.Wrap
                        }
                        Text {
                            textFormat: Text.PlainText; Layout.fillWidth: true
                            text: I18n.choose(modelData.descriptionZh, modelData.descriptionEn)
                            color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize
                            wrapMode: Text.Wrap
                        }
                    }
                    NeoButton {
                        objectName: "selectWorkflow_" + modelData.id
                        text: I18n.choose("选择", "Select")
                        primary: true
                        reducedMotion: home.reducedMotion
                        onClicked: home.workflowSelected(modelData.id)
                    }
                }
            }
        }
        // Placeholder only: shows that more prebuilt workflows can be added here.
        NeoCard {
            objectName: "workflowPlaceholder"
            Layout.fillWidth: true
            Layout.maximumWidth: 760
            Layout.alignment: Qt.AlignHCenter
            fill: Theme.canvas
            padding: 28
            content: RowLayout {
                spacing: 20
                Rectangle {
                    width: 56; height: 64; radius: 9
                    color: Theme.cyan; border.color: Theme.ink; border.width: 3
                    Text { anchors.centerIn: parent; text: "+"; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 40; font.weight: Font.Bold }
                }
                Text {
                    textFormat: Text.PlainText; Layout.fillWidth: true
                    text: I18n.choose("添加新工作流程", "Add New Workflows")
                    color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize
                    font.weight: Font.Bold; wrapMode: Text.Wrap
                }
            }
        }
    }

    ColumnLayout {
        id: teacherPage
        visible: !home.developerMode && home.workflowChosen
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 28

        NeoButton {
            objectName: "allWorkflowsButton"
            text: I18n.choose("← 全部工作流程", "← All Workflows")
            reducedMotion: home.reducedMotion
            onClicked: home.workflowListRequested()
        }
        Text {
            textFormat: Text.PlainText; Layout.fillWidth: true
            text: home.workflowChosen ? I18n.choose(home.selectedWorkflow.nameZh, home.selectedWorkflow.nameEn) : ""
            color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize
            font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        }
        Text {
            textFormat: Text.PlainText; Layout.fillWidth: true
            text: I18n.choose("选择连续扫描 PDF 和学生名册，然后跟随页面上的下一步。", "Choose the continuous-scan PDF and class roster, then follow the next step shown here.")
            color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        }
        NeoCard {
            Layout.fillWidth: true
            Layout.maximumWidth: 760
            Layout.alignment: Qt.AlignHCenter
            fill: Theme.card
            padding: 34
            content: ColumnLayout {
                spacing: 18
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 68; height: 78; radius: 9
                    color: Theme.pink; border.color: Theme.ink; border.width: 3
                    Text { anchors.centerIn: parent; text: I18n.tr("文"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 38; font.weight: Font.Bold }
                }
                Text {
                    textFormat: Text.PlainText; Layout.fillWidth: true
                    text: I18n.choose("准备开始新的批改任务", "Ready to Begin a New Marking Task")
                    color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize
                    font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                }
                Text {
                    textFormat: Text.PlainText; Layout.fillWidth: true
                    text: I18n.choose("选择作文和学生名册。读取资料不会开始批改。", "Choose the essays and class roster. Reading them will not start marking.")
                    color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize
                    horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                }
                NeoButton {
                    objectName: "homePrimaryAction"
                    Layout.alignment: Qt.AlignHCenter
                    text: I18n.choose("选择作文", "Choose Submissions")
                    primary: true
                    reducedMotion: home.reducedMotion
                    onClicked: home.inspectRequested()
                }
            }
        }
    }

    ColumnLayout {
        id: developerPage
        visible: home.developerMode
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.sectionGap
        Text { textFormat: Text.PlainText; text: I18n.tr("作文工作台"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
        RowLayout {
            Layout.fillWidth: true; spacing: 20
            ColumnLayout {
                Layout.fillWidth: true; spacing: 8
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("老师，今天从这里开始。"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize; font.weight: Font.Bold; wrapMode: Text.Wrap }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("准备作文、查看批改进度，或回到上次的审核。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
            }
            NeoButton { text: I18n.tr("＋ 新建批改任务"); primary: true; reducedMotion: home.reducedMotion; onClicked: home.navigateRequested("create") }
        }
        NextActionPanel {
            Layout.fillWidth: true
            kicker: I18n.tr("接着上次的工作")
            title: String(home.appState.title || I18n.tr("作文任务"))
            subtitle: String(home.appState.subtitle || "")
            actionText: I18n.tr("查看这次任务")
            reason: home.appState.demo ? I18n.tr("演示任务 · 查看示例状态") : I18n.tr("查看本次已读取的文件状态")
            actionEnabled: true
            onActionRequested: home.navigateRequested("workspace")
            reducedMotion: home.reducedMotion
            tone: "pending"
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            Text { textFormat: Text.PlainText; text: I18n.tr("最近的批改任务"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold }
            Text { textFormat: Text.PlainText; text: I18n.tr("按最近打开排序"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
            Item { Layout.fillWidth: true }
        }
        NeoCard {
            Layout.fillWidth: true; fill: Theme.card; padding: Theme.cardPadding
            content: ColumnLayout {
                spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        Text { textFormat: Text.PlainText; text: I18n.tr("作文二 · 一次勇敢的尝试"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
                        Text { textFormat: Text.PlainText; text: I18n.tr("207 班 · 32份作文"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize }
                    }
                    NeoBadge { label: I18n.tr("✓ 32张已生成"); tone: "green" }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.ink }
                RowLayout {
                    Layout.fillWidth: true
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("已核对当前审核版本的体检卡"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                    NeoButton { text: I18n.choose("输出示例", "Output Example"); reducedMotion: home.reducedMotion; enabled: false; reason: I18n.tr("演示数据没有实际输出目录") }
                }
            }
        }
    }
}
