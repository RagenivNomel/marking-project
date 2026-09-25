import QtQuick 2.15
import "."
import QtQuick.Layouts 1.15

NeoCard {
    id: attentionCard
    property var item: ({})
    property bool reducedMotion: false
    fill: Theme.card
    padding: Theme.cardPadding
    content: ColumnLayout {
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String((attentionCard.item || {}).title || I18n.tr("需要处理")); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.cardTitleSize; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
            NeoBadge { label: I18n.tr("△ 需要处理"); tone: "pink" }
        }
        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: String((attentionCard.item || {}).message || ""); color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: Theme.bodySize; wrapMode: Text.Wrap }
        DetailsDisclosure { Layout.fillWidth: true; detailText: String((attentionCard.item || {}).details || ""); reducedMotion: attentionCard.reducedMotion }
    }
}
