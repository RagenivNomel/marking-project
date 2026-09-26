import QtQuick 2.15
import "."
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs

Dialog {
    id: dialog
    property bool reducedMotion: false
    property bool developerMode: false
    property string defaultRosterPath: ""
    signal inspectRequested(string workbook, string jobs, string receipts, string splitPile, string roster, string continuousScan)

    title: dialog.developerMode ? I18n.tr("检查本地文件引用") : I18n.choose("选择作文", "Choose Submissions")
    header: Item { implicitHeight: 0 }
    modal: true
    width: Math.min(720, parent ? parent.width - 48 : 720)
    standardButtons: Dialog.NoButton
    focus: true

    background: Rectangle {
        color: Theme.canvas
        border.color: Theme.ink
        border.width: 3
        radius: 12
        Rectangle { anchors.fill: parent; anchors.leftMargin: 5; anchors.topMargin: 5; color: Theme.ink; radius: 12; z: -1 }
    }
    contentItem: ColumnLayout {
        spacing: 12
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: dialog.title
            color: Theme.ink
            font.family: Theme.fontFamily
            font.pixelSize: Theme.cardTitleSize
            font.weight: Font.Bold
        }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true
            text: dialog.developerMode ? I18n.tr("只读取显式路径；不会搜索其他文件夹。") : I18n.choose("选择一份连续扫描 PDF 和学生名册。应用会自动整理作文。", "Choose one continuous-scan PDF and the class roster. The app will prepare the essays automatically.")
            color: Theme.secondaryInk
            font.family: Theme.fontFamily
            font.pixelSize: Theme.bodySize
            wrapMode: Text.Wrap
        }
        PathField { id: workbookField; visible: dialog.developerMode; label: I18n.tr("审核工作簿"); placeholder: I18n.tr("选择现有的批改结果 Excel") }
        NeoButton { visible: dialog.developerMode; text: I18n.tr("选择 Excel 文件"); onClicked: workbookPicker.open(); reducedMotion: dialog.reducedMotion }
        PathField { id: jobsField; visible: dialog.developerMode; label: I18n.tr("批改作业目录"); placeholder: I18n.tr("例如：C:/…/jobs/…") }
        PathField { id: receiptsField; visible: dialog.developerMode; label: I18n.tr("输出回执目录"); placeholder: I18n.tr("例如：C:/…/receipts/…") }
        PathField { id: splitPileField; visible: dialog.developerMode; label: I18n.tr("作文分组目录"); placeholder: I18n.tr("例如：C:/…/pile1_test") }
        NeoButton { visible: dialog.developerMode; text: I18n.tr("选择作文分组目录"); onClicked: folderPicker.open(); reducedMotion: dialog.reducedMotion }
        PathField { id: continuousScanField; visible: !dialog.developerMode; label: I18n.choose("连续扫描 PDF", "Continuous Scan PDF"); placeholder: I18n.tr("例如：C:/…/class-essays.pdf") }
        NeoButton { visible: !dialog.developerMode; text: I18n.choose("选择连续扫描", "Choose Continuous Scan"); onClicked: scanPicker.open(); reducedMotion: dialog.reducedMotion }
        PathField {
            id: rosterField
            label: I18n.choose("学生名册", "Class Roster")
            placeholder: I18n.choose("选择包含班级、班号和姓名的 Excel", "Choose the Excel roster")
            Component.onCompleted: if (!value.length && dialog.defaultRosterPath.length) value = dialog.defaultRosterPath
        }
        NeoButton { text: I18n.choose("选择学生名册", "Choose Class Roster"); onClicked: rosterPicker.open(); reducedMotion: dialog.reducedMotion }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true
            text: dialog.developerMode ? I18n.tr("只需填写已有资料的位置。文件夹可留空；多个关联文件夹用分号分隔。检查仅会读取保存的内容。") : I18n.choose("结果工作簿、作文分组资料和体检卡文件夹会由应用自动管理。", "The app manages the split submissions, results workbook and feedback-card folder automatically.")
            color: Theme.secondaryInk
            font.family: Theme.fontFamily
            font.pixelSize: Theme.metaSize
            wrapMode: Text.Wrap
        }
        NeoButton {
            Layout.alignment: Qt.AlignRight
            text: dialog.developerMode ? I18n.tr("读取这些资料") : I18n.choose("读取并继续", "Read and Continue")
            enabled: dialog.developerMode
                     ? workbookField.value.trim().length > 0 || jobsField.value.trim().length > 0 || receiptsField.value.trim().length > 0 || splitPileField.value.trim().length > 0
                     : continuousScanField.value.trim().length > 0 && rosterField.value.trim().length > 0
            primary: true
            reducedMotion: dialog.reducedMotion
            onClicked: {
                dialog.inspectRequested(workbookField.value, jobsField.value, receiptsField.value, splitPileField.value, rosterField.value, continuousScanField.value)
                dialog.close()
            }
        }
        NeoButton { text: I18n.tr("取消"); reducedMotion: dialog.reducedMotion; onClicked: dialog.close() }
    }

    FileDialog {
        id: workbookPicker
            visible: dialog.developerMode
            title: I18n.tr("选择已有审核工作簿")
        nameFilters: [I18n.tr("Excel 工作簿 (*.xlsx)")]
        onAccepted: {
            workbookField.value = selectedFile.toString()
            if (!dialog.developerMode) {
                splitPileField.value = ""
                rosterField.value = ""
            }
        }
    }
    FileDialog {
        id: rosterPicker
        title: I18n.choose("选择学生名册", "Choose Class Roster")
        nameFilters: [I18n.tr("Excel 工作簿 (*.xlsx)")]
        onAccepted: rosterField.value = selectedFile.toString()
    }
    FileDialog {
        id: scanPicker
        title: I18n.choose("选择连续扫描 PDF", "Choose Continuous Scan PDF")
        nameFilters: [I18n.tr("PDF 文件 (*.pdf)")]
        onAccepted: continuousScanField.value = selectedFile.toString()
    }
    FolderDialog {
        id: folderPicker
        title: I18n.choose("选择已有作文资料文件夹", "Choose Existing Submission Folder")
        onAccepted: {
            splitPileField.value = selectedFolder.toString()
            if (!dialog.developerMode) workbookField.value = ""
        }
    }

    component PathField: RowLayout {
        property string label: I18n.tr("路径")
        property string placeholder: ""
        property alias value: input.text
        Layout.fillWidth: true
        spacing: 10
        Text { textFormat: Text.PlainText; Layout.preferredWidth: 120; text: parent.label; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
        TextField {
            id: input
            Layout.fillWidth: true
            implicitHeight: Theme.fieldHeight
            placeholderText: parent.placeholder
            placeholderTextColor: Theme.secondaryInk
            Accessible.name: parent.label
            selectByMouse: true
            font.family: Theme.fontFamily
            font.pixelSize: 15
            background: Rectangle { color: Theme.canvas; border.color: input.activeFocus ? Theme.deepBlue : Theme.ink; border.width: input.activeFocus ? 3 : 2; radius: 7 }
        }
    }
}
