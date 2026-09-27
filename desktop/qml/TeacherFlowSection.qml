pragma ComponentBehavior: Bound
import QtQuick 2.15
import QtQuick.Layouts 1.15
import "."

Item {
    id: teacherFlow
    property var appState: ({})
    property var flow: appState.teacherFlow || ({})
    property bool reducedMotion: false
    property bool showRows: false
    signal inspectRequested()
    signal refreshRequested()
    signal confirmIdentitiesRequested(var selections)
    signal markingRequested()
    signal cancelMarkingRequested()
    signal feedbackRequested()
    property var identityReview: teacherFlow.appState.identityReview || ({})
    function identityForAttention() {
        var rows = teacherFlow.appState.rows || []
        for (var i = 0; i < rows.length; i++) {
            var status = String(rows[i].status || "").toLowerCase()
            if (status.indexOf("身份") >= 0 || status.indexOf("identity") >= 0)
                return String(rows[i].identity || "")
        }
        return rows.length ? String(rows[0].identity || "") : ""
    }
    function operationalAttention() {
        var result = []
        var items = teacherFlow.appState.attention || []
        for (var i = 0; i < items.length; i++) {
            var code = String(items[i].details || "").split("\n")[0]
            if (code !== "IDENTITY_UNRESOLVED" && code !== "SUBMISSION_LINK_REQUIRED") result.push(items[i])
        }
        return result
    }
    implicitHeight: content.implicitHeight

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 20

        ProgressPanel {
            Layout.fillWidth: true
            visible: (Object.keys(teacherFlow.appState.progress || {}).length > 0
                         && teacherFlow.appState.progress.operation !== "render")
                     || (teacherFlow.appState.progress && teacherFlow.appState.progress.operation === "render"
                         && teacherFlow.appState.progress.running === true)
            progressState: teacherFlow.appState.progress || ({})
            reducedMotion: teacherFlow.reducedMotion
            canCancel: !Boolean(teacherFlow.appState.demo) && bridge.busy
            onCancelRequested: teacherFlow.cancelMarkingRequested()
        }

        NextActionPanel {
            Layout.fillWidth: true
            visible: !teacherFlow.identityReview.visible
                     && teacherFlow.flow.step !== "review"
                     && !(teacherFlow.flow.step === "marking" && Object.keys(teacherFlow.appState.progress || {}).length > 0)
                     && !(teacherFlow.appState.progress && teacherFlow.appState.progress.operation === "render"
                          && teacherFlow.appState.progress.running === true)
            completed: teacherFlow.flow.step === "complete"
            kicker: String(teacherFlow.flow.stageLabel || I18n.choose("下一步", "Next Step"))
            title: String(teacherFlow.flow.headline || I18n.choose("选择作文", "Choose Submissions"))
            subtitle: String(teacherFlow.flow.detail || "")
            tone: String(teacherFlow.flow.tone || "pending")
            actionText: String(teacherFlow.flow.primaryActionLabel || I18n.choose("选择作文", "Choose Submissions"))
            actionEnabled: Boolean(teacherFlow.flow.primaryActionEnabled) && !bridge.busy
            reason: String(teacherFlow.flow.actionReason || (actionEnabled
                    ? ""
                    : String(teacherFlow.appState.disabledReason || I18n.choose("当前界面尚未开放此操作。", "This action is not available from this screen yet."))))
            reducedMotion: teacherFlow.reducedMotion
            onActionRequested: {
                if (teacherFlow.flow.primaryAction === "REFRESH_REVIEW_STATUS") teacherFlow.refreshRequested()
                else if (teacherFlow.flow.primaryAction === "RUN_MARKING") teacherFlow.markingRequested()
                else if (teacherFlow.flow.primaryAction === "RENDER_APPROVED") teacherFlow.feedbackRequested()
                else if (teacherFlow.flow.primaryAction === "REVIEW_EXCEL") bridge.openResults()
                else if (teacherFlow.flow.primaryAction === "VIEW_OUTPUTS") bridge.openFeedbackCards()
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: ((teacherFlow.appState.renderResult || {}).failed || []).length > 0
            spacing: 10
            Text { textFormat: Text.PlainText; text: I18n.choose("部分体检卡尚未生成", "Some feedback cards were not generated"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
            Repeater {
                model: (teacherFlow.appState.renderResult || {}).failed || []
                delegate: AttentionCard {
                    required property var modelData
                    Layout.fillWidth: true
                    property var failureIdentity: modelData.identity || ({})
                    item: ({title: String(failureIdentity.class_name || "") + " · " + String(failureIdentity.student_id || "") + " · " + String(failureIdentity.student_name || ""), message: teacherFlow.appState.language === "en" ? String(modelData.message || "This card could not be generated; the approved Excel result is unchanged.") : "体检卡未能生成，已审核的 Excel 内容保持不变。请查看详情后重试。", details: String(modelData.error || "")})
                    reducedMotion: teacherFlow.reducedMotion
                }
            }
        }

        IdentityConfirmationPanel {
            objectName: "identityConfirmationPanel"
            Layout.fillWidth: true
            visible: Boolean(teacherFlow.identityReview.visible) && !Boolean(teacherFlow.identityReview.requiresRoster)
            review: teacherFlow.identityReview
            reducedMotion: teacherFlow.reducedMotion
            onConfirmRequested: teacherFlow.confirmIdentitiesRequested(selections)
        }

        NeoCard {
            Layout.fillWidth: true
            visible: Boolean(teacherFlow.identityReview.visible) && Boolean(teacherFlow.identityReview.requiresRoster)
            fill: Theme.card
            content: ColumnLayout {
                spacing: 10
                Text { textFormat: Text.PlainText; text: I18n.choose("需要学生名册", "Class roster required"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(teacherFlow.identityReview.message || I18n.choose("请选择学生名册后重新读取。", "Choose the class roster and read again.")); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
            }
        }

        NeoCard {
            Layout.fillWidth: true
            visible: teacherFlow.flow.step === "preparation"
            fill: Theme.card
            content: ColumnLayout {
                spacing: 10
                Text { textFormat: Text.PlainText; text: I18n.choose("作文资料", "Submission Materials"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(teacherFlow.flow.detail || I18n.choose("选择作文后，这里会显示资料完整情况。", "After choosing submissions, their readiness appears here.")); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
            }
        }

        NeoCard {
            Layout.fillWidth: true
            visible: teacherFlow.flow.step === "review"
            fill: Theme.card
            content: ColumnLayout {
                spacing: 12
                Text { textFormat: Text.PlainText; text: I18n.choose("审核进度", "Review Progress"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.choose(String((teacherFlow.appState.summary && teacherFlow.appState.summary.approved) || 0) + "份已确认 · " + String((teacherFlow.appState.summary && teacherFlow.appState.summary.awaiting_review) || 0) + "份尚未确认", String((teacherFlow.appState.summary && teacherFlow.appState.summary.approved) || 0) + " confirmed · " + String((teacherFlow.appState.summary && teacherFlow.appState.summary.awaiting_review) || 0) + " awaiting review"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.choose("在 Excel 中修改并保存后，回到这里重新读取。应用会检查保存的内容。", "Edit and save in Excel, then return here and read again. The app verifies the saved content."); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
                FileReferenceCard {
                    Layout.fillWidth: true
                    title: I18n.tr("批改结果 Excel")
                    path: Boolean(teacherFlow.appState.resultsWorkbookAvailable)
                          ? String(teacherFlow.appState.workbook || "results.xlsx")
                          : I18n.choose("批改结果工作簿不可用", "Results workbook unavailable")
                    subtitle: I18n.tr("教师审核工作簿")
                    actionText: I18n.choose("打开 results.xlsx", "Open results.xlsx")
                    actionEnabled: Boolean(teacherFlow.appState.resultsWorkbookAvailable)
                    actionOpensFile: true
                    reducedMotion: teacherFlow.reducedMotion
                    onOpenRequested: bridge.openResults()
                }
                NeoButton { text: I18n.tr("重新读取并检查 Excel"); enabled: !bridge.busy && !Boolean(teacherFlow.appState.demo) && Boolean(teacherFlow.appState.hasSource); reason: I18n.tr("读取只读文件引用"); reducedMotion: teacherFlow.reducedMotion; onClicked: teacherFlow.refreshRequested() }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: teacherFlow.operationalAttention().length > 0
            spacing: 12
            Text { textFormat: Text.PlainText; text: I18n.choose("需要您处理", "Needs Your Attention"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold }
            Repeater {
                model: teacherFlow.operationalAttention()
                delegate: AttentionCard {
                    required property var modelData
                    Layout.fillWidth: true
                    item: modelData || ({})
                    reducedMotion: teacherFlow.reducedMotion
                }
            }
        }

        NeoCard {
            Layout.fillWidth: true
            visible: teacherFlow.flow.step === "resolve_attention" && teacherFlow.operationalAttention().length === 0 && !teacherFlow.identityReview.visible
            fill: Theme.card
            content: ColumnLayout {
                spacing: 12
                Text { textFormat: Text.PlainText; text: I18n.choose("这份作文需要确认学生资料", "This Submission Needs a Student Check"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: teacherFlow.identityForAttention(); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.choose("每份作文都会保留独立来源；姓名相同也不会自动合并。", "Each submission keeps its own source; matching names are never merged automatically."); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                NeoButton { text: I18n.choose("确认并继续", "Confirm and Continue"); primary: true; enabled: false; reason: String(teacherFlow.appState.disabledReason || ""); reducedMotion: teacherFlow.reducedMotion }
            }
        }

        NeoCard {
            Layout.fillWidth: true
            visible: teacherFlow.flow.step === "generate"
            fill: Theme.card
            content: ColumnLayout {
                spacing: 10
                Text { textFormat: Text.PlainText; text: I18n.choose("生成范围", "Generation Scope"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(teacherFlow.flow.detail || ""); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: (teacherFlow.appState.rows || []).length > 0
            spacing: 12
            NeoButton {
                text: teacherFlow.showRows
                      ? I18n.choose("收起作文列表", "Hide Submission List")
                      : I18n.choose("查看全部 " + (teacherFlow.appState.rows || []).length + " 份作文", "View All " + (teacherFlow.appState.rows || []).length + " Submissions")
                reducedMotion: teacherFlow.reducedMotion
                onClicked: teacherFlow.showRows = !teacherFlow.showRows
            }
            SubmissionList {
                Layout.fillWidth: true
                visible: teacherFlow.showRows
                rows: teacherFlow.appState.rows || []
                viewportHeight: Math.min(560, Math.max(240, rows.length * 73))
                reducedMotion: teacherFlow.reducedMotion
            }
        }

        DetailsDisclosure {
            Layout.fillWidth: true
            visible: (teacherFlow.appState.fileReferences || []).length > 0
            summary: I18n.tr("查看文件来源详情")
            detailText: (teacherFlow.appState.fileReferences || []).join("\n")
            reducedMotion: teacherFlow.reducedMotion
        }
    }
}
