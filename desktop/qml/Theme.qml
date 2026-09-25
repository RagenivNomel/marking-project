pragma Singleton
import QtQuick 2.15

QtObject {
    readonly property color canvas: "#FFF1C7"
    readonly property color card: "#FFDB58"
    readonly property color sidebar: "#87CEEB"
    readonly property color pink: "#FF69B4"
    readonly property color magenta: "#FF00F5"
    readonly property color cyan: "#7DF9FF"
    readonly property color blue: "#87CEEB"
    readonly property color deepBlue: "#3300FF"
    readonly property color yellow: "#FFD21F"
    readonly property color green: "#2FFF2F"
    readonly property color ink: "#000000"
    readonly property color secondaryInk: "#252525"
    readonly property color neutral: "#FFF1C7"
    readonly property int stroke: 2
    readonly property int heroStroke: 3
    readonly property int radius: 7
    readonly property int heroRadius: 12
    readonly property int shadow: 4
    readonly property int smallShadow: 3
    readonly property int bodySize: 16
    readonly property int metaSize: 14
    readonly property int cardTitleSize: 18
    readonly property int sectionTitleSize: 22
    readonly property int screenTitleSize: 30
    readonly property int motionMs: 160
    readonly property int spaceUnit: 4
    readonly property int sectionGap: 24
    readonly property int cardPadding: 24
    readonly property int controlHeight: 44
    readonly property int fieldHeight: 48
    readonly property int bubbleRadius: 18
    // Task names and student identities can contain Chinese in either UI language.
    // A Latin-only family here makes Qt substitute CJK glyphs inside mixed lines.
    readonly property string fontFamily: typeof uiFontFamily !== "undefined"
        ? uiFontFamily : "Microsoft YaHei"
}
