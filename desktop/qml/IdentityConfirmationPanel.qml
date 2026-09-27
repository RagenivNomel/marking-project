import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "."

Item {
    id: panel
    property var review: ({})
    property bool reducedMotion: false
    property var selections: ({})
    property int selectionVersion: 0
    signal confirmRequested(var selections)
    implicitHeight: content.implicitHeight

    function resetSelections() {
        var next = {}
        var rows = review.rows || []
        for (var i = 0; i < rows.length; i++)
            if (String(rows[i].selectedKey || "").length) next[String(rows[i].sourcePdf)] = String(rows[i].selectedKey)
        selections = next
        selectionVersion++
    }
    function setSelection(sourcePdf, key) {
        var next = {}
        for (var oldKey in selections) next[oldKey] = selections[oldKey]
        if (String(key).length) next[String(sourcePdf)] = String(key)
        else delete next[String(sourcePdf)]
        selections = next
        selectionVersion++
    }
    function rosterItem(key) {
        var roster = review.roster || []
        for (var i = 0; i < roster.length; i++) if (String(roster[i].key) === String(key)) return roster[i]
        return null
    }
    function selectedCount() {
        var ignored = selectionVersion
        var count = 0
        var rows = review.rows || []
        for (var i = 0; i < rows.length; i++) if (String(selections[String(rows[i].sourcePdf)] || "").length) count++
        return count
    }
    function hasDuplicate() {
        var ignored = selectionVersion
        var seen = {}
        var used = review.usedKeys || []
        for (var i = 0; i < used.length; i++) seen[String(used[i])] = true
        var rows = review.rows || []
        for (var j = 0; j < rows.length; j++) {
            var key = String(selections[String(rows[j].sourcePdf)] || "")
            if (!key.length) continue
            if (seen[key]) return true
            seen[key] = true
        }
        return false
    }
    function selectionPayload() {
        var ignored = selectionVersion
        var result = []
        var rows = review.rows || []
        for (var i = 0; i < rows.length; i++) {
            var key = String(selections[String(rows[i].sourcePdf)] || "")
            var student = rosterItem(key)
            if (student) result.push({sourcePdf: String(rows[i].sourcePdf), className: String(student.className), studentId: String(student.studentId)})
        }
        return result
    }
    onReviewChanged: resetSelections()
    Component.onCompleted: resetSelections()

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 16

        NeoCard {
            Layout.fillWidth: true
            fill: Theme.card
            content: ColumnLayout {
                spacing: 8
                Text { textFormat: Text.PlainText; text: I18n.choose("学生资料确认", "Confirm Student Information"); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.Bold }
                Text {
                    textFormat: Text.PlainText; Layout.fillWidth: true
                    text: I18n.choose("系统找到" + String(panel.review.totalCount || 0) + "份作文。请确认每份作文对应的学生。", "The system found " + String(panel.review.totalCount || 0) + " submissions. Confirm the student for each one.")
                    color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap
                }
                Text {
                    textFormat: Text.PlainText
                    text: I18n.choose("已确认 " + String(panel.review.confirmedCount || 0) + " / " + String(panel.review.totalCount || 0), "Confirmed " + String(panel.review.confirmedCount || 0) + " / " + String(panel.review.totalCount || 0))
                    color: Theme.deepBlue; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.Bold
                }
            }
        }

        Text {
            visible: panel.hasDuplicate()
            textFormat: Text.PlainText; Layout.fillWidth: true
            text: I18n.choose("同一名册学生不能同时分配给两份作文。请检查选择。", "The same roster student cannot be assigned to two submissions. Check the selections.")
            color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.DemiBold; wrapMode: Text.Wrap
        }

        Repeater {
            model: panel.review.rows || []
            delegate: NeoCard {
                required property var modelData
                required property int index
                Layout.fillWidth: true
                fill: index % 2 ? Theme.canvas : Theme.card
                content: RowLayout {
                    spacing: 14
                    Image {
                        Layout.preferredWidth: 320; Layout.preferredHeight: 80
                        visible: String(modelData.previewUrl || "").length > 0
                        source: String(modelData.previewUrl || "")
                        fillMode: Image.PreserveAspectFit
                        asynchronous: false
                        Accessible.name: I18n.choose(modelData.label + " 姓名、班级、班号预览", modelData.label + " name, class and seat-number preview")
                    }
                    ColumnLayout {
                        Layout.preferredWidth: 140; Layout.fillWidth: false; spacing: 4
                        Text { textFormat: Text.PlainText; text: String(modelData.label); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; font.weight: Font.Bold }
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: I18n.choose("文件显示：", "File label: ") + String(modelData.sourceHint || I18n.choose("未命名", "Unnamed")); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize; wrapMode: Text.Wrap }
                        Text { textFormat: Text.PlainText; text: String(modelData.pages || 0) + I18n.choose("页", " pages"); color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize }
                    }
                    ComboBox {
                        id: studentSelector
                        objectName: "identitySelector" + String(index)
                        Layout.fillWidth: true
                        Layout.minimumWidth: 280
                        implicitHeight: Theme.controlHeight
                        model: panel.review.roster || []
                        textRole: "label"
                        valueRole: "key"
                        font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize
                        currentIndex: {
                            var chosen = String(panel.selections[String(modelData.sourcePdf)] || modelData.selectedKey || "")
                            for (var i = 0; i < count; i++) if (String(valueAt(i)) === chosen) return i
                            return -1
                        }
                        displayText: currentIndex >= 0 ? currentText : I18n.choose("选择学生…", "Choose student…")
                        Accessible.name: I18n.choose(modelData.label + " 对应学生", "Student for " + modelData.label)
                        onActivated: panel.setSelection(String(modelData.sourcePdf), String(currentValue))
                        background: Rectangle { color: Theme.canvas; border.color: studentSelector.activeFocus ? Theme.deepBlue : Theme.ink; border.width: studentSelector.activeFocus ? 3 : 2; radius: 7 }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Text {
                textFormat: Text.PlainText; Layout.fillWidth: true
                text: I18n.choose("已选择 " + String(panel.selectedCount()) + " / " + String((panel.review.rows || []).length), "Selected " + String(panel.selectedCount()) + " / " + String((panel.review.rows || []).length))
                color: Theme.secondaryInk; font.family: Theme.fontFamily; font.pixelSize: Theme.metaSize
            }
            NeoButton {
                visible: panel.selectedCount() > 0 && panel.selectedCount() < (panel.review.rows || []).length
                text: I18n.choose("保存已确认", "Save Confirmed")
                enabled: !panel.hasDuplicate() && !bridge.busy
                reducedMotion: panel.reducedMotion
                onClicked: panel.confirmRequested(panel.selectionPayload())
            }
            NeoButton {
                objectName: "confirmIdentitiesAction"
                text: bridge.busy ? I18n.choose("正在重新检查…", "Checking Again…") : I18n.choose("确认并继续", "Confirm and Continue")
                primary: true
                enabled: panel.selectedCount() === (panel.review.rows || []).length && panel.selectedCount() > 0 && !panel.hasDuplicate() && !bridge.busy
                reason: I18n.choose("保存名册选择并重新检查作文", "Save roster selections and inspect the submissions again")
                reducedMotion: panel.reducedMotion
                onClicked: panel.confirmRequested(panel.selectionPayload())
            }
        }
    }
}
