import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: root
    visible: true
    width: 1440; height: 820
    minimumWidth: 1024; minimumHeight: 720
    title: I18n.choose("作文工作台", "Composition Workspace")
    color: Theme.canvas
    property var bridgeState: bridge.state
    property string currentScenario: String(bridgeState.scenario)
    property bool reducedMotion: Boolean(bridgeState.reducedMotion)
    property bool compactShell: width < 1100
    property bool developerMode: typeof devUi !== "undefined" && Boolean(devUi)
    property var demoKeys: ["home","workspace","marking","handoff","review","attention","complete","create","identity","generate","empty","unknown","system","stress","real"]
    property var demoLabels: [I18n.tr("首页 / 最近任务"),I18n.tr("混合状态"),I18n.tr("批改进度演示"),I18n.tr("Excel 交接"),I18n.tr("部分审核"),I18n.tr("部分输出失败"),I18n.tr("当前输出完成"),I18n.tr("本地材料"),I18n.tr("身份核对"),I18n.tr("生成范围"),I18n.tr("空状态"),I18n.tr("状态不确定"),I18n.tr("组件与键盘焦点"),I18n.tr("长内容 / 40份作文"),I18n.tr("本地只读任务")]
    Binding { target: I18n; property: "language"; value: String(root.bridgeState.language || "zh") }
    header: Rectangle {
        visible: root.developerMode
        height: root.developerMode ? implicitHeight : 0
        implicitHeight: toolbar.height + (notice.visible ? notice.implicitHeight + 20 : 0)
        color: Theme.canvas
        border.width: 1; border.color: Theme.ink
        Column {
            width: parent.width
            RowLayout {
                id: toolbar
                width: parent.width
                height: 56
                spacing: 12
                Item { Layout.preferredWidth: 12 }
                Text { textFormat: Text.PlainText; visible: !root.compactShell; text: root.developerMode ? I18n.choose("开发 / QA 界面", "Developer / QA UI") : I18n.choose("中二高华作文批改", "Secondary 2 Higher Chinese"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; font.weight: root.developerMode ? Font.Bold : Font.Normal }
                NeoBadge { visible: root.developerMode; label: I18n.choose("开发模式", "Developer Mode"); tone: "pink" }
                Item { Layout.fillWidth: true }
                ComboBox {
                    id: selector
                    objectName: "scenarioSelector"
                    visible: root.developerMode
                    Layout.preferredWidth: root.compactShell ? 220 : 270
                    implicitHeight: Theme.controlHeight
                    model: bridge.hasInspection ? root.demoLabels : root.demoLabels.slice(0,14)
                    currentIndex: Math.max(0,root.demoKeys.indexOf(root.currentScenario))
                    font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
                    enabled: !bridge.busy
                    Accessible.name: I18n.tr("选择演示状态或本地任务")
                    onActivated: bridge.selectDemo(root.demoKeys[currentIndex])
                    background: Rectangle { color: Theme.card; border.width: selector.activeFocus ? 3 : 2; border.color: selector.activeFocus ? Theme.deepBlue : Theme.ink; radius: 7 }
                }
                ComboBox {
                    id: languageSelector
                    objectName: "languageSelector"
                    Layout.preferredWidth: 106
                    implicitHeight: Theme.controlHeight
                    model: ["中文", "English"]
                    currentIndex: bridge.language === "en" ? 1 : 0
                    font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
                    enabled: !bridge.busy
                    Accessible.name: I18n.choose("界面语言", "Interface language")
                    onActivated: bridge.setLanguage(currentIndex === 1 ? "en" : "zh")
                    background: Rectangle { color: Theme.cyan; border.width: languageSelector.activeFocus ? 3 : 2; border.color: languageSelector.activeFocus ? Theme.deepBlue : Theme.ink; radius: 7 }
                }
                CheckBox {
                    id: motionToggle
                    visible: root.developerMode
                    text: I18n.tr("减少动画")
                    checked: root.reducedMotion
                    font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
                    implicitHeight: Theme.controlHeight
                    Accessible.name: text
                    onToggled: bridge.setReducedMotion(checked)
                    indicator: Rectangle {
                        x: 4; y: (motionToggle.height - height) / 2
                        width: 24; height: 24; radius: 4
                        color: motionToggle.checked ? Theme.cyan : Theme.canvas
                        border.color: motionToggle.activeFocus ? Theme.deepBlue : Theme.ink
                        border.width: motionToggle.activeFocus ? 3 : 2
                        Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: motionToggle.checked ? "✓" : ""; color: Theme.ink; font.pixelSize: 20 }
                    }
                }
                NeoButton {
                    objectName: "refreshButton"
                    visible: root.developerMode
                    text: bridge.busy ? I18n.tr("正在检查…") : I18n.tr("重新读取")
                    enabled: !bridge.busy && !root.bridgeState.demo && Boolean(root.bridgeState.hasSource)
                    reducedMotion: root.reducedMotion
                    onClicked: bridge.refresh()
                }
                NeoButton {
                    objectName: "inspectButton"
                    visible: root.developerMode
                    text: I18n.tr("选择本地资料")
                    primary: true
                    enabled: !bridge.busy
                    reducedMotion: root.reducedMotion
                    onClicked: inspectDialog.open()
                }
                Item { Layout.preferredWidth: 16 }
            }
            Text { textFormat: Text.PlainText;
                id: notice
                visible: root.developerMode
                x: 24; width: parent.width - 48
                text: String(root.bridgeState.notice)
                font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
                color: Theme.secondaryInk
                wrapMode: Text.Wrap
            }
        }
    }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Sidebar {
            z: 2
            visible: root.developerMode
            Layout.fillHeight: true
            Layout.preferredWidth: root.developerMode ? (root.compactShell ? 184 : 216) : 0
            compact: root.compactShell
            appState: root.bridgeState
            activeView: String(root.bridgeState.view)
            reducedMotion: root.reducedMotion
            onNavigate: function(view) { bridge.navigate(view) }
        }
        AccentRail {
            z: 2
            visible: !root.developerMode
            Layout.fillHeight: true
            Layout.preferredWidth: root.developerMode ? 0 : 34
        }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true
            ComboBox {
                id: teacherLanguageSelector
                visible: !root.developerMode
                z: 3
                anchors.top: parent.top; anchors.right: parent.right
                anchors.topMargin: 12; anchors.rightMargin: root.compactShell ? 28 : 70
                width: 106; implicitHeight: Theme.controlHeight
                model: ["中文", "English"]
                currentIndex: bridge.language === "en" ? 1 : 0
                font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
                enabled: !bridge.busy
                Accessible.name: I18n.choose("界面语言", "Interface language")
                onActivated: bridge.setLanguage(currentIndex === 1 ? "en" : "zh")
                background: Rectangle { color: Theme.cyan; border.width: teacherLanguageSelector.activeFocus ? 3 : 2; border.color: teacherLanguageSelector.activeFocus ? Theme.deepBlue : Theme.ink; radius: 7 }
            }
            ScrollView {
                id: mainScroll
                objectName: "mainScroll"
                anchors.fill: parent
                anchors.leftMargin: root.compactShell ? 34 : (root.developerMode ? 36 : 70)
                anchors.rightMargin: root.compactShell ? 28 : (root.developerMode ? 36 : 70)
                anchors.topMargin: root.developerMode ? 28
                    : (root.bridgeState.teacherFlow && root.bridgeState.teacherFlow.step === "complete"
                       ? Math.max(68, (parent.height - pageLoader.implicitHeight) / 2) : 68)
                anchors.bottomMargin: 20
                clip: true
                contentWidth: availableWidth
                Loader {
                    id: pageLoader
                    width: mainScroll.availableWidth - 8
                    sourceComponent: root.developerMode
                        ? (root.bridgeState.view === "home" ? homeComponent : root.bridgeState.view === "empty" ? emptyComponent : root.bridgeState.view === "create" ? createComponent : root.bridgeState.view === "system" ? systemComponent : workspaceComponent)
                        : (root.bridgeState.view === "workspace" ? workspaceComponent : homeComponent)
                }
            }
        }
    }
    Connections {
        target: bridge
        function onChanged() {
            if (mainScroll.contentItem && mainScroll.contentItem.contentY !== undefined) mainScroll.contentItem.contentY = 0
        }
    }
    InspectPathsDialog {
        id: inspectDialog
        objectName: "inspectDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        reducedMotion: root.reducedMotion
        developerMode: root.developerMode
        defaultRosterPath: bridge.defaultRosterPath
        onInspectRequested: function(workbook,jobs,receipts,splitPile,roster,continuousScan,rosterClass) { bridge.inspectPaths(workbook,jobs,receipts,splitPile,roster,continuousScan,rosterClass) }
    }
    Component { id: homeComponent; HomeView { appState: root.bridgeState; demoKey: root.currentScenario; reducedMotion: root.reducedMotion; developerMode: root.developerMode; workflows: bridge.workflows; selectedWorkflow: bridge.selectedWorkflow; onNavigateRequested: function(view) { bridge.navigate(view) }; onInspectRequested: inspectDialog.open(); onWorkflowSelected: function(workflowId) { bridge.selectWorkflow(workflowId) }; onWorkflowListRequested: bridge.showWorkflowList() } }
    Component { id: emptyComponent; EmptyView { reducedMotion: root.reducedMotion; onCreateRequested: bridge.navigate("create") } }
    Component { id: createComponent; CreateView { appState: root.bridgeState; reducedMotion: root.reducedMotion; onInspectRequested: inspectDialog.open() } }
    Component { id: systemComponent; SystemView { reducedMotion: root.reducedMotion } }
    Component {
        id: workspaceComponent
        WorkspaceView {
            appState: root.bridgeState; demoKey: root.currentScenario; reducedMotion: root.reducedMotion; developerMode: root.developerMode
            onSectionRequested: function(section) { bridge.selectSection(section) }
            onInspectRequested: inspectDialog.open()
            onRefreshRequested: bridge.refresh()
            onConfirmIdentitiesRequested: bridge.confirmIdentitySelections(selections)
            onMarkingRequested: bridge.startMarking()
            onCancelMarkingRequested: bridge.cancelMarking()
            onFeedbackRequested: bridge.generateFeedback()
            onBackRequested: bridge.navigate("home")
        }
    }
}
