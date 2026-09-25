import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."
Item {
    id: list
    property var rows: []
    property bool reducedMotion: false
    property int viewportHeight: 372
    property string selectedId: ""
    implicitHeight: viewportHeight
    ListView {
        id: view
        objectName: "submissionList"
        anchors.fill: parent
        clip: true
        model: list.rows
        currentIndex: -1
        keyNavigationEnabled: true
        activeFocusOnTab: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        delegate: SubmissionRow {
            width: view.width - 14
            rowData: modelData
            selected: ListView.isCurrentItem
            reducedMotion: list.reducedMotion
        }
        onCurrentIndexChanged: {
            if (currentIndex >= 0 && currentIndex < list.rows.length) list.selectedId = list.rows[currentIndex].id
            if (activeFocus && currentItem) currentItem.forceActiveFocus()
        }
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_End) { currentIndex = count - 1; positionViewAtEnd(); event.accepted = true }
            if (event.key === Qt.Key_Home) { currentIndex = 0; positionViewAtBeginning(); event.accepted = true }
        }
    }
    onRowsChanged: {
        var position = rows.findIndex(function(r) { return r.id === list.selectedId })
        var active = rows.findIndex(function(r) { return r.tone === "active" })
        Qt.callLater(function() {
            view.currentIndex = position >= 0 ? position : active
            if (active >= 0) view.positionViewAtIndex(Math.max(0, active - 1), ListView.Beginning)
        })
    }
}
