#pragma once
// Sprint 8 Goal 9, third pass: the launcher's own title bar (owner request: "implement a custom top bar").
// The window has no OS caption; this 38-unit bar carries the mark, the drag region, the state lamp, the
// unsaved pill and the three window controls.
//
// ONE hit test. The Win32 window procedure answers WM_NCHITTEST from it, and the UI decides what the mouse
// is over from the same function, so what is drawn and what the system believes can never disagree. Pure:
// no raylib, no windows.h.
#include <algorithm>
#include "theme.h"

#include <vector>

namespace ui
{
    enum class ChromeHit
    {
        Client = 0,
        Caption,
        Minimize,
        Maximize,
        Close,
        UnsavedPill,
        Left,
        Right,
        Top,
        Bottom,
        TopLeft,
        TopRight,
        BottomLeft,
        BottomRight
    };

    // Where everything in the bar sits, in design units, for a window `designW` units wide.
    struct ChromeLayout
    {
        Rect bar;        // the whole bar
        Rect mark;       // the SOCOM II / UNZIPPED mark at the left (not draggable)
        Rect caption;    // the drag region
        Rect status;     // the lamp and its one-line state
        Rect pill;       // "UNSAVED", only drawn when there are unsaved changes
        Rect minimize, maximize, close;
    };

    namespace chrome
    {
        constexpr float markW = 210.0f;
        constexpr float buttonW = 46.0f;
        constexpr float pillW = 96.0f;
        constexpr float pillGap = 10.0f;
        constexpr float statusW = 230.0f;
        constexpr float borderPx = 6.0f;      // the resize grab, in real pixels
        constexpr float buttonTopPx = 2.0f;   // the top resize border still wins in the button's top 2 px
        constexpr float pad = 16.0f;          // the one padding the bar's clusters are spaced by
        constexpr float lampGap = 20.0f;      // the lamp's centre to the state word
        constexpr float lampR = 9.0f;         // the lamp's outer ring
        constexpr float tabGap = 18.0f;       // between the tabs of the group
    }

    inline ChromeLayout chromeLayout(float designW)
    {
        ChromeLayout l;
        const float h = metrics::barH;
        l.bar = Rect{0.0f, 0.0f, designW, h};
        l.mark = Rect{0.0f, 0.0f, chrome::markW, h};
        l.close = Rect{designW - chrome::buttonW, 0.0f, chrome::buttonW, h};
        l.maximize = Rect{l.close.x - chrome::buttonW, 0.0f, chrome::buttonW, h};
        l.minimize = Rect{l.maximize.x - chrome::buttonW, 0.0f, chrome::buttonW, h};
        l.pill = Rect{l.minimize.x - chrome::pillGap - chrome::pillW, 4.0f, chrome::pillW, h - 8.0f};
        l.status = Rect{l.pill.x - chrome::statusW, 0.0f, chrome::statusW, h};
        l.caption = Rect{l.mark.right(), 0.0f, l.status.x - l.mark.right(), h};
        if (l.caption.w < 0.0f)
            l.caption.w = 0.0f;
        return l;
    }

    // The half of the bar that only measured text can place: the page tabs, the state lamp and its word.
    // The caller measures with the real font and hands the widths over; everything here is arithmetic, so the
    // test asserts on the very numbers the bar draws.
    struct TopBarText
    {
        float markRight = chrome::markW;   // where the drawn mark ends, its left padding included
        float statusW = 0.0f;              // the state word ("READY") at its drawn size
        bool showPill = false;             // the UNSAVED pill is only drawn when there is something to save
        std::vector<float> tabW;           // the tab labels' drawn widths, in order
        float tabGap = chrome::tabGap;

        // Sprint 9 P4. The ink, not the line box. `text()` is given the top of the LINE box, and a line box
        // is not the letters: the ascent above the capitals and the descender space below them are not
        // equal. So two sizes drawn at one y do not share a baseline ("UNZIPPED ... is lower than the SOCOM
        // II text"), and an all-caps word centred in a bar-height box sits above the lamp it is meant to sit
        // beside ("the running text ... appears higher"). The caller measures each word's capital ink with
        // ui::capInk and hands it over, exactly as it already hands over the widths.
        float markY = 10.0f;               // where SOCOM II's line box is drawn -- the mark's anchor
        float markCapTop = 0.0f;           // SOCOM II: the capitals' top, below the line box's top
        float markCapH = 0.0f;             // and their height
        float markSubCapTop = 0.0f;        // UNZIPPED, at its own smaller size
        float markSubCapH = 0.0f;
        float statusCapTop = 0.0f;         // the state word ("RUNNING")
        float statusCapH = 0.0f;
    };

    struct TopBarPlaces
    {
        Rect status;             // the state word's own box, the full height of the bar
        Vec2 lamp;               // the lamp's centre
        Rect tabs;               // the tab group as a whole
        std::vector<Rect> tab;   // each label's box, in order
        bool tabsCentred = false;
        float markSubY = 0.0f;   // the y to draw UNZIPPED at, so its baseline is SOCOM II's
        float statusY = 0.0f;    // the y to draw the state word at, so its capitals centre on the lamp
    };

    inline TopBarPlaces topBarPlaces(const ChromeLayout &l, const TopBarText &m)
    {
        TopBarPlaces o;
        const float h = l.bar.h;

        // Right to left: the three window buttons, the UNSAVED pill when there is one, then the state word
        // exactly one padding clear of whichever of them it follows, and its lamp one gap left of that. The
        // word's box is the width the font measured and the full height of the bar, so it sits on the centre
        // line (owner, Sprint 8: "the READY status label sits too far right").
        const float clusterRight = (m.showPill ? l.pill.x : l.minimize.x) - chrome::pad;
        o.status = Rect{clusterRight - m.statusW, 0.0f, m.statusW, h};
        o.lamp = Vec2{o.status.x - chrome::lampGap, l.bar.cy()};

        // The word beside the lamp is centred on the LAMP, by its capitals: the lamp is a circle on the
        // bar's centre line, and the eye lines the letters up with it, not the invisible box they sit in.
        o.statusY = o.lamp.y - m.statusCapH * 0.5f - m.statusCapTop;

        // The mark's second word sits on the first word's baseline, which is where the capitals END.
        o.markSubY = (m.markY + m.markCapTop + m.markCapH) - m.markSubCapH - m.markSubCapTop;

        // The tab group, centred in what is free between the wordmark and that cluster -- at every window
        // width, and never over either of them. Too wide to fit there, it sits after the wordmark instead.
        float groupW = 0.0f;
        for (size_t i = 0; i < m.tabW.size(); ++i)
            groupW += m.tabW[i] + (i + 1 < m.tabW.size() ? m.tabGap : 0.0f);
        const float freeL = m.markRight + chrome::pad;
        const float freeR = o.lamp.x - chrome::lampR - chrome::pad;
        o.tabsCentred = groupW <= freeR - freeL;
        // On the bar's own middle -- the window's, which is where the eye expects it -- and pushed aside only as
        // far as the mark or the cluster requires (the cluster is the wider of the two, so the free width's
        // middle sits left of the window's and read as misplaced: owner, Sprint 8).
        const float x = o.tabsCentred ? std::clamp(l.bar.cx() - groupW * 0.5f, freeL, freeR - groupW) : freeL;
        o.tabs = Rect{x, 0.0f, groupW, h};
        float cursor = x;
        for (float w : m.tabW)
        {
            o.tab.push_back(Rect{cursor, 0.0f, w, h});
            cursor += w + m.tabGap;
        }
        return o;
    }

    // `x`, `y`, `w`, `h` in real pixels; `scale` the window's factor. Resize borders disappear when the
    // window is maximised, and the bar's buttons win over the top border below its top two pixels.
    inline ChromeHit chromeHitTest(int x, int y, int w, int h, float scale, bool maximized)
    {
        const float fx = static_cast<float>(x);
        const float fy = static_cast<float>(y);
        const ChromeLayout l = chromeLayout(static_cast<float>(w) / scale);
        auto in = [&](Rect r)
        {
            return fx >= r.x * scale && fx < r.right() * scale && fy >= r.y * scale && fy < r.bottom() * scale;
        };

        const bool belowButtonTop = fy >= chrome::buttonTopPx;
        if (belowButtonTop)
        {
            if (in(l.close))
                return ChromeHit::Close;
            if (in(l.maximize))
                return ChromeHit::Maximize;
            if (in(l.minimize))
                return ChromeHit::Minimize;
            if (in(l.pill))
                return ChromeHit::UnsavedPill;
        }

        if (!maximized)
        {
            const float b = chrome::borderPx;
            const bool left = fx < b;
            const bool right = fx >= static_cast<float>(w) - b;
            const bool top = fy < b;
            const bool bottom = fy >= static_cast<float>(h) - b;
            if (top && left)
                return ChromeHit::TopLeft;
            if (top && right)
                return ChromeHit::TopRight;
            if (bottom && left)
                return ChromeHit::BottomLeft;
            if (bottom && right)
                return ChromeHit::BottomRight;
            if (top)
                return ChromeHit::Top;
            if (bottom)
                return ChromeHit::Bottom;
            if (left)
                return ChromeHit::Left;
            if (right)
                return ChromeHit::Right;
        }

        if (in(l.caption))
            return ChromeHit::Caption;
        return ChromeHit::Client;
    }
}
