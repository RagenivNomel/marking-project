import QtQuick 2.15
import "."
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: create
    property var appState: ({})
    property bool reducedMotion: false
    signal inspectRequested()
    signal navigateRequested(string view)

    implicitHeight: page.implicitHeight
    ColumnLayout {
        id: page
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.sectionGap
        Text { textFormat: Text.PlainText; text: I18n.tr("我的批改任务　/　新建"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.tr("新建批改任务"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.screenTitleSize; font.weight: Font.Bold; wrapMode: Text.Wrap }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.choose("选择连续扫描 PDF 和学生名册。应用会自动整理作文，批改结果和体检卡文件夹会自动创建。", "Choose the continuous-scan PDF and class roster. The app prepares the essays and creates the results workbook and feedback-card folder automatically."); wrapMode: Text.Wrap; color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize }

        GridLayout {
            columns: create.width < 1000 ? 1 : 2
            Layout.fillWidth: true
            columnSpacing: Theme.sectionGap
            rowSpacing: Theme.sectionGap
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.card
                hero: true
                content: ColumnLayout {
                    spacing: 14
                    Text { textFormat: Text.PlainText; text: I18n.tr("作文材料"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold }
                    Text { textFormat: Text.PlainText; text: I18n.tr("任务名称"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold }
                    TextField {
                        readOnly: true
                        Accessible.name: I18n.tr("演示任务名称，不保存")
                        Layout.fillWidth: true
                        text: I18n.tr("作文三 · 那一次，我学会了坚持")
                        implicitHeight: Theme.fieldHeight
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.bodySize
                        background: Rectangle { color: Theme.canvas; border.color: Theme.ink; border.width: 2; radius: 7 }
                    }
                    Text { textFormat: Text.PlainText; text: I18n.tr("作文材料"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold }
                    ComboBox {
                        id: materialType
                        enabled: false
                        Accessible.name: I18n.tr("材料类型示例，尚未接入")
                        Layout.fillWidth: true
                        implicitHeight: Theme.fieldHeight
                        model: [I18n.tr("已经按作文分好的文件夹"), I18n.tr("正面 / 背面扫描 PDF（后续接入）")]
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.bodySize
                        contentItem: Text { textFormat: Text.PlainText; text: materialType.currentText; color: Theme.secondaryInk; font: materialType.font; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                        background: Rectangle { color: Theme.canvas; border.color: Theme.ink; border.width: 2; radius: 7 }
                    }
                    FileReferenceCard { Layout.fillWidth: true; title: I18n.choose("连续扫描 PDF", "Continuous Scan PDF"); path: I18n.tr("尚未选择 PDF"); subtitle: I18n.choose("选择包含全班连续扫描内容的一份 PDF。", "Choose the single PDF containing the continuous class scan."); reducedMotion: create.reducedMotion; actionText: I18n.choose("选择连续扫描", "Choose Continuous Scan"); onInspectRequested: create.inspectRequested() }
                    FileReferenceCard { Layout.fillWidth: true; title: I18n.choose("学生名册", "Class Roster"); path: I18n.tr("尚未选择名单工作簿"); subtitle: I18n.choose("名册用于匹配学生身份。", "The roster is used to match student identities."); reducedMotion: create.reducedMotion; actionText: I18n.choose("选择学生名册", "Choose Class Roster"); onInspectRequested: create.inspectRequested() }
                    NeoButton { text: I18n.choose("选择作文和名册", "Choose Essays and Roster"); primary: true; enabled: true; reducedMotion: create.reducedMotion; onClicked: create.inspectRequested() }
                    Text { textFormat: Text.PlainText; text: I18n.tr("选择文件不会发起 AI批改。下一步会核对每份作文与学生身份。"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
                }
            }
            NeoCard {
                Layout.fillWidth: true
                fill: Theme.yellow
                content: ColumnLayout {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: I18n.tr("先核对，再批改"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.choose("选择作文和名册后，应用会根据保存记录恢复任务进度，并自动管理结果文件。", "After you choose the essays and roster, the app restores saved progress and manages the task outputs automatically."); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
                    DetailsDisclosure { Layout.fillWidth: true; detailText: I18n.tr("原始扫描 PDF 的正反面配对、页数验证和排序属于后续接入；不会通过目录存在来推断准备成功。"); reducedMotion: create.reducedMotion }
                }
            }
        }
    }
}
