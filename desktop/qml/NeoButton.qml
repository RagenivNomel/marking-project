import QtQuick 2.15
import QtQuick.Controls 2.15
import "."

Button {
    id: control
    property bool primary: false
    property bool danger: false
    property bool reviewOnly: false
    property string reason: ""
    property bool loading: false
    property bool reducedMotion: false
    property int pressTravel: 3

    implicitHeight: Theme.controlHeight
    implicitWidth: Math.max(120, contentItem.implicitWidth + 36)
    leftPadding: 18
    rightPadding: 18
    topPadding: 9
    bottomPadding: 9
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    font.family: Theme.fontFamily
    font.pixelSize: Theme.bodySize
    font.weight: Font.DemiBold
    display: AbstractButton.TextOnly

    contentItem: Text { textFormat: Text.PlainText;
        text: control.loading ? I18n.tr("正在检查…") : control.text
        color: control.enabled ? Theme.ink : Theme.secondaryInk
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
        elide: Text.ElideNone
        transform: Translate {
            x: control.pressed ? control.pressTravel : 0
            y: control.pressed ? control.pressTravel : control.hovered ? -1 : 0
            Behavior on x { NumberAnimation { duration: control.reducedMotion ? 0 : Theme.motionMs } }
            Behavior on y { NumberAnimation { duration: control.reducedMotion ? 0 : Theme.motionMs } }
        }
    }

    background: Item {
        implicitHeight: Theme.controlHeight
        Rectangle {
            id: shadow
            visible: !control.pressed
            x: control.enabled && (control.primary || control.reviewOnly) ? 4 : 0
            y: control.enabled && (control.primary || control.reviewOnly) ? 4 : 0
            width: buttonSurface.width
            height: buttonSurface.height
            color: control.enabled && (control.primary || control.reviewOnly) ? Theme.ink : "transparent"
            radius: 7
        }
        Rectangle {
            id: buttonSurface
            anchors.fill: parent
            color: !control.enabled ? Theme.neutral : control.danger ? Theme.magenta : control.primary ? Theme.yellow : Theme.card
            border.color: Theme.ink
            border.width: 2
            radius: 7
            opacity: 1
            transform: Translate {
                x: control.pressed ? control.pressTravel : 0
                y: control.pressed ? control.pressTravel : control.hovered ? -1 : 0
                Behavior on x { NumberAnimation { duration: control.reducedMotion ? 0 : Theme.motionMs } }
                Behavior on y { NumberAnimation { duration: control.reducedMotion ? 0 : Theme.motionMs; easing.type: Easing.OutCubic } }
            }
            Behavior on color { ColorAnimation { duration: control.reducedMotion ? 0 : 120 } }
        }
        Rectangle {
            anchors.fill: buttonSurface
            anchors.margins: -4
            color: "transparent"
            border.color: control.activeFocus ? Theme.deepBlue : "transparent"
            border.width: 3
            radius: 9
        }
    }
    Accessible.name: control.text
    Accessible.description: control.enabled ? control.reason : (control.reason.length ? control.reason : I18n.tr("此操作暂不可用"))
}
