// Sprint 7 review finding: the launcher's window is taller than a 1366x768 or 1920x1080 laptop screen once
// Windows DPI scaling is at 125-150%, which puts the Launch row off the bottom with no way to resize.
// These two pure functions decide the window's height and clamp the body's scroll; main.cpp owns the drawing.
#pragma once

namespace launcher
{
    // The height to open the window at: `wanted` when it fits inside the monitor with `margin` left for the
    // taskbar and the title bar, otherwise as much of the monitor as that margin allows -- never below 400,
    // which still shows a panel and the scroll that reaches the rest.
    inline int fitWindowHeight(int wanted, int monitorHeight, int margin)
    {
        const int usable = monitorHeight - margin;
        if (wanted <= usable)
            return wanted;
        return usable < 400 ? 400 : usable;
    }

    // The scroll offset, clamped to the part of the content that does not fit: 0 when the body is shorter than
    // the window (nothing to scroll), so a tall display never drifts off the top.
    inline int scrollClamp(int scroll, int contentHeight, int viewHeight)
    {
        const int span = contentHeight - viewHeight;
        const int maximum = span > 0 ? span : 0;
        if (scroll < 0)
            return 0;
        return scroll > maximum ? maximum : scroll;
    }
}
