import QtQuick 2.15
import "."

Item {
    id: backNavigation
    property string destinationLabel: I18n.choose("我的批改任务", "My Marking Tasks")
    property bool reducedMotion: false
    signal activated()

    implicitWidth: backButton.implicitWidth
    implicitHeight: backButton.implicitHeight

    NeoButton {
        id: backButton
        objectName: "backNavigationButton"
        text: I18n.choose("← " + backNavigation.destinationLabel,
                          "← " + backNavigation.destinationLabel)
        enabled: backNavigation.enabled
        reason: I18n.choose("返回任务选择", "Return to task selection")
        reducedMotion: backNavigation.reducedMotion
        onClicked: backNavigation.activated()
    }
}
