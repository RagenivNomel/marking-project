import QtQuick 2.15
import "."

Item {
    id: rail
    implicitWidth: 34
    Rectangle { anchors.fill: parent; color: Theme.sidebar }
    Rectangle { anchors.right: parent.right; width: 3; height: parent.height; color: Theme.ink }
    Repeater {
        model: [{fraction:0.24, diameter:42, fill:Theme.cyan},
                {fraction:0.53, diameter:54, fill:Theme.magenta},
                {fraction:0.82, diameter:32, fill:Theme.yellow}]
        delegate: Item {
            x: rail.width - width / 2
            y: rail.height * modelData.fraction
            width: modelData.diameter; height: width
            Rectangle { x: 4; y: 4; width: parent.width; height: parent.height; radius: width / 2; color: Theme.ink }
            Rectangle { width: parent.width; height: parent.height; radius: width / 2; color: modelData.fill; border.width: 3; border.color: Theme.ink }
        }
    }
}
