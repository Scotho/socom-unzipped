#pragma once
// Sprint 8 Goal 9, third pass: the launcher's own title bar (owner request: "implement a custom top bar").
// The window has no OS caption; this 38-unit bar carries the mark, the drag region, the state lamp, the
// unsaved pill and the three window controls.
//
// ONE hit test. The Win32 window procedure answers WM_NCHITTEST from it, and the UI decides what the mouse
// is over from the same function, so what is drawn and what the system believes can never disagree. Pure:
// no raylib, no windows.h.
#include "theme.h"

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
