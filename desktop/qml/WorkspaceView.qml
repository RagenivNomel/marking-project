import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

Item {
    id: workspace
    property var appState: ({})
    property string demoKey: "workspace"
    property bool reducedMotion: false
    property bool developerMode: false
    property int currentSection: developerMode
        ? Number(appState.section === undefined ? 2 : appState.section)
        : (appState.progress && appState.progress.operation === "render" && appState.progress.running === true
           ? 3 : Number(appState.teacherFlow && appState.teacherFlow.stageIndex !== undefined ? appState.teacherFlow.stageIndex : 0))
    signal sectionRequested(int section)
    signal inspectRequested()
    signal refreshRequested()
    signal confirmIdentitiesRequested(var selections)
    signal markingRequested()
    signal cancelMarkingRequested()
    signal feedbackRequested()
    signal backRequested()

    implicitHeight: page.implicitHeight
    ColumnLayout {
        id: page
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 20
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            BackNavigation {
                objectName: "workspaceBackNavigation"
                visible: !workspace.developerMode && !Boolean(workspace.appState.demo) && Boolean(workspace.appState.hasSource)
                destinationLabel: I18n.choose("我的批改任务", "My Marking Tasks")
                enabled: !bridge.busy
                reducedMotion: workspace.reducedMotion
                onActivated: workspace.backRequested()
            }
            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: (workspace.developerMode || !Boolean(workspace.appState.hasSource))
                      ? I18n.tr("我的批改任务　/　") + String(workspace.appState.title || I18n.tr("作文任务"))
                      : I18n.tr("/　") + String(workspace.appState.title || I18n.tr("作文任务"))
                color: Theme.secondaryInk
                font.family: Theme.fontFamily
                font.pixelSize: Theme.metaSize
                wrapMode: Text.Wrap
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(workspace.appState.title || I18n.tr("那一次，我学会了坚持")); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize; font.weight: Font.Bold; wrapMode: Text.Wrap }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(workspace.appState.subtitle || I18n.tr("中二高华作文批改 · 31份作文")); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
            }
            NeoBadge { visible: workspace.developerMode && Boolean(workspace.appState.demo); label: I18n.tr("演示数据"); tone: "yellow" }
        }
        Flow {
            visible: workspace.developerMode
            Layout.fillWidth: true
            spacing: 4
            Repeater {
                model: workspace.appState.sections || [I18n.tr("作文准备"), I18n.tr("AI批改"), I18n.tr("教师审核"), I18n.tr("反馈输出")]
                delegate: NeoTab {
                    objectName: "sectionTab" + index
                    text: String(modelData)
                    selected: workspace.currentSection === index
                    reducedMotion: workspace.reducedMotion
                    onTabSelected: workspace.sectionRequested(index)
                    Keys.onLeftPressed: {
                        if (index > 0) workspace.sectionRequested(index - 1)
                    }
                    Keys.onRightPressed: {
                        if (index < 3) workspace.sectionRequested(index + 1)
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Home) { workspace.sectionRequested(0); event.accepted = true }
                        if (event.key === Qt.Key_End) { workspace.sectionRequested(3); event.accepted = true }
                    }
                }
            }
        }
        WorkflowProgress {
            objectName: "workflowProgress"
            visible: !workspace.developerMode
            Layout.fillWidth: true
            currentStage: workspace.currentSection
            finished: workspace.appState.teacherFlow && workspace.appState.teacherFlow.step === "complete"
                      && !(workspace.appState.progress && workspace.appState.progress.running === true)
            labels: [I18n.choose("作文准备", "Preparation"), I18n.choose("批改", "Marking"), I18n.choose("教师审核", "Teacher Review"), I18n.choose("生成反馈", "Generate Feedback")]
        }
        WorkspaceSection {
            visible: workspace.developerMode
            Layout.fillWidth: true
            section: workspace.currentSection
            appState: workspace.appState
            demoKey: workspace.demoKey
            reducedMotion: workspace.reducedMotion
            onInspectRequested: workspace.inspectRequested()
            onRefreshRequested: workspace.refreshRequested()
        }
        TeacherFlowSection {
            objectName: "teacherFlowSection"
            visible: !workspace.developerMode
            Layout.fillWidth: true
            appState: workspace.appState
            reducedMotion: workspace.reducedMotion
            onInspectRequested: workspace.inspectRequested()
            onRefreshRequested: workspace.refreshRequested()
            onConfirmIdentitiesRequested: workspace.confirmIdentitiesRequested(selections)
            onMarkingRequested: workspace.markingRequested()
            onCancelMarkingRequested: workspace.cancelMarkingRequested()
            onFeedbackRequested: workspace.feedbackRequested()
        }
        DetailsDisclosure {
            visible: workspace.developerMode
            Layout.fillWidth: true
            summary: I18n.tr("查看文件来源详情")
            detailText: (workspace.appState.fileReferences || []).join("\n")
            reducedMotion: workspace.reducedMotion
        }
    }
}
