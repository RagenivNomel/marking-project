import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

Item {
    id: workspaceBody
    property int section: 2
    property var appState: ({})
    property string demoKey: "workspace"
    property bool reducedMotion: false
    signal inspectRequested()
    signal refreshRequested()
    signal navigateRequested(string view)

    implicitHeight: body.implicitHeight

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 20

        NextActionPanel {
            Layout.fillWidth: true
            completed: workspaceBody.section === 3 && workspaceBody.demoKey === "complete"
            visible: !(workspaceBody.section === 1 && workspaceBody.appState.progress && Object.keys(workspaceBody.appState.progress).length > 0)
            kicker: String(workspaceBody.appState.hero && workspaceBody.appState.hero.kicker || workspaceBody.appState.sections && workspaceBody.appState.sections[workspaceBody.section] || I18n.tr("下一步"))
            title: String(!workspaceBody.appState.demo && workspaceBody.appState.teacherFlow
                          ? workspaceBody.appState.teacherFlow.headline
                          : workspaceBody.appState.hero && workspaceBody.appState.hero.title || I18n.tr("查看任务状态"))
            subtitle: String(!workspaceBody.appState.demo && workspaceBody.appState.teacherFlow
                             ? workspaceBody.appState.teacherFlow.detail
                             : workspaceBody.appState.hero && workspaceBody.appState.hero.subtitle || "")
            tone: String(workspaceBody.appState.hero && workspaceBody.appState.hero.tone || "pending")
            actionText: String(!workspaceBody.appState.demo && workspaceBody.appState.teacherFlow
                               ? workspaceBody.appState.teacherFlow.primaryActionLabel
                               : workspaceBody.appState.hero && workspaceBody.appState.hero.action || I18n.tr("查看详情"))
            reason: String((workspaceBody.appState.teacherFlow || {}).actionReason
                           || workspaceBody.appState.disabledReason || I18n.tr("当前仅供查看；生产操作尚未接入。"))
            reducedMotion: workspaceBody.reducedMotion
            actionEnabled: workspaceBody.appState.teacherFlow
                           ? Boolean(workspaceBody.appState.teacherFlow.primaryActionEnabled)
                           : false
            onActionRequested: {
                var action = String((workspaceBody.appState.teacherFlow || {}).primaryAction || "")
                if (action === "REVIEW_EXCEL") bridge.openResults()
                else if (action === "VIEW_OUTPUTS") bridge.openFeedbackCards()
                else if (action === "RUN_MARKING") bridge.startMarking()
                else if (action === "RENDER_APPROVED") bridge.generateFeedback()
                else if (action === "REFRESH_REVIEW_STATUS") workspaceBody.refreshRequested()
            }
        }

        ProgressPanel {
            Layout.fillWidth: true
            visible: workspaceBody.section === 1 && workspaceBody.appState.progress && Object.keys(workspaceBody.appState.progress).length > 0
            progressState: workspaceBody.appState.progress || ({})
            reducedMotion: workspaceBody.reducedMotion
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: (workspaceBody.appState.attention || []).length > 0
            spacing: 12
            Repeater {
                model: workspaceBody.appState.attention || []
                delegate: AttentionCard { Layout.fillWidth: true; item: modelData; reducedMotion: workspaceBody.reducedMotion }
            }
        }

        GridLayout {
            columns: workspaceBody.width < 1000 ? 1 : 2
            Layout.fillWidth: true
            columnSpacing: 24
            rowSpacing: 24
            visible: workspaceBody.section === 0 && workspaceBody.demoKey === "identity"
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.canvas
                content: ColumnLayout {
                    spacing: 12
                    RowLayout {
                        Layout.fillWidth: true
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("作文 018"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                        NeoBadge { label: I18n.tr("△ 待确认"); tone: "pink" }
                    }
                    Text { textFormat: Text.PlainText; text: I18n.tr("原稿姓名区域 · 示意占位"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 190
                        color: Theme.canvas
                        border.color: Theme.ink
                        border.width: 2
                        radius: 4
                        Column {
                            anchors.centerIn: parent
                            spacing: 14
                            Text { textFormat: Text.PlainText; text: I18n.tr("姓名栏预览"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
                            Text { textFormat: Text.PlainText; text: I18n.tr("张瑞颖"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.DemiBold }
                            Repeater { model: 3; delegate: Rectangle { width: 220; height: 1; color: Theme.ink } }
                        }
                    }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("原稿预览按比例缩放，不裁掉姓名证据。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
                }
            }
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.card
                content: ColumnLayout {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: I18n.tr("与学生名单核对"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("207 · 20 · 张瑞颖"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("此学生另有作文 017。请核对是否为同一份作文，不能仅凭姓名合并。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                    NeoButton { text: I18n.tr("记录身份确认"); primary: true; enabled: false; reason: String(workspaceBody.appState.disabledReason || I18n.tr("身份记录写入尚未接入")); reducedMotion: workspaceBody.reducedMotion }
                    DetailsDisclosure { Layout.fillWidth: true; detailText: I18n.tr("身份确认需要明确的持久化写入授权；当前只读取并展示证据。"); reducedMotion: workspaceBody.reducedMotion }
                }
            }
        }

        GridLayout {
            columns: workspaceBody.width < 1000 ? 1 : 2
            Layout.fillWidth: true
            columnSpacing: 24
            rowSpacing: 24
            visible: workspaceBody.section === 2
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 14
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(workspaceBody.appState.notice || I18n.tr("请在 Excel 中完成审核，再重新读取保存内容。")); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                FileReferenceCard { Layout.fillWidth: true; title: I18n.tr("批改结果 Excel"); path: String(workspaceBody.appState.workbook || I18n.tr("尚未选择审核工作簿")); subtitle: I18n.tr("审核工作簿 · 保留原文件位置"); reducedMotion: workspaceBody.reducedMotion; actionText: I18n.tr("检查路径"); onInspectRequested: workspaceBody.inspectRequested() }
                RowLayout {
                    NeoButton { text: I18n.choose("打开批改结果 Excel", "Open Results in Excel"); primary: true; enabled: Boolean(workspaceBody.appState.resultsWorkbookAvailable); reason: I18n.choose("批改结果工作簿不可用", "Results workbook unavailable"); reducedMotion: workspaceBody.reducedMotion; onClicked: bridge.openResults() }
                    NeoButton { text: I18n.tr("重新读取并检查 Excel"); enabled: !bridge.busy && !Boolean(workspaceBody.appState.demo) && Boolean(workspaceBody.appState.hasSource); reason: I18n.tr("读取只读文件引用"); reducedMotion: workspaceBody.reducedMotion; onClicked: workspaceBody.refreshRequested() }
                }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("保存后再读取；应用不会自动批准作文。生成前请关闭 Excel，避免同时写入。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
            }
            NeoCard {
                Layout.preferredWidth: workspaceBody.width < 1000 ? workspaceBody.width : 304
                Layout.fillWidth: workspaceBody.width < 1000
                fill: Theme.card
                content: ColumnLayout {
                    spacing: 10
                    Text { textFormat: Text.PlainText; text: I18n.tr("审核摘要"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(workspaceBody.appState.summary && workspaceBody.appState.summary.approved || 0) + I18n.tr("份已审核"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String(workspaceBody.appState.summary && workspaceBody.appState.summary.awaiting_review || 0) + I18n.tr("份待审核"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("1　阅读并修改批改意见\n2　确认后，在 Excel 标为已批准\n3　保存工作簿，再返回这里"); wrapMode: Text.Wrap; color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; lineHeight: 1.6 }
                    DetailsDisclosure { Layout.fillWidth: true; detailText: I18n.tr("“已审核”指保存的 Excel 中为 APPROVED；这里不会猜测老师身份或替代 Excel。"); reducedMotion: workspaceBody.reducedMotion }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: (workspaceBody.appState.rows || []).length > 0
            spacing: 16
            RowLayout {
                Layout.fillWidth: true
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: (workspaceBody.section === 1 && Object.keys(workspaceBody.appState.progress || {}).length > 0) ? I18n.tr("作文队列") : workspaceBody.section === 3 ? I18n.tr("输出状态") : I18n.tr("作文状态"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold }
                Text { textFormat: Text.PlainText; text: String((workspaceBody.appState.rows || []).length) + I18n.tr("份 · 按作文分别保留"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
            }
            SubmissionList {
                Layout.fillWidth: true
                rows: workspaceBody.appState.rows || []
                viewportHeight: workspaceBody.demoKey === "stress" ? 560 : 366
                reducedMotion: workspaceBody.reducedMotion
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: workspaceBody.section === 3
            spacing: 16
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sectionGap
                visible: workspaceBody.demoKey === "complete" || workspaceBody.demoKey === "generate"
                NeoCard {
                    Layout.fillWidth: true
                    fill: Theme.green
                    content: ColumnLayout {
                        spacing: 10
                        Text { textFormat: Text.PlainText; text: workspaceBody.demoKey === "complete" ? I18n.tr("✓ 当前版本已核对") : I18n.tr("生成范围"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: workspaceBody.demoKey === "complete" ? I18n.tr("31份作文 · 31份已审核 · 31张体检卡") : I18n.tr("28份已审核，其中24张已有当前版本。本次可生成4张；3份待审核作文不会包含在内。"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                        NeoButton { visible: workspaceBody.demoKey === "complete"; text: I18n.choose("输出位置示例", "Output Location Example"); primary: true; enabled: false; reason: I18n.tr("演示数据没有实际输出目录"); reducedMotion: workspaceBody.reducedMotion }
                        NeoButton { visible: workspaceBody.demoKey === "generate"; text: I18n.tr("生成4张作文体检卡"); primary: true; enabled: false; reason: String(workspaceBody.appState.disabledReason || I18n.tr("生成操作尚未接入")); reducedMotion: workspaceBody.reducedMotion }
                    }
                }
                NeoCard {
                    Layout.fillWidth: true
                    fill: Theme.canvas
                    content: ColumnLayout {
                        spacing: 10
                        Text { textFormat: Text.PlainText; text: I18n.tr("文件留在您的电脑上"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("输出可能分布在多个作文文件夹；按作文显示对应位置。已生成不代表已打印、已发给学生或已打包交付。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                        DetailsDisclosure { Layout.fillWidth: true; detailText: I18n.tr("Stage 1 的 rendered 是当前来源及文件核对结果；没有统一发布清单或整批 COMPLETE 交付命令。"); reducedMotion: workspaceBody.reducedMotion }
                    }
                }
            }
        }
    }
}
