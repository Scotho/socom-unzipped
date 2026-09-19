// Sprint 8 Goal 9, the VIDEO page: detail, filtering, the window the game opens, the overlay.
#include "pages.h"

namespace ui
{
    namespace
    {
        int indexOf(const std::vector<const char *> &labels, const std::string &value, int fallback)
        {
            for (size_t i = 0; i < labels.size(); ++i)
                if (value == labels[i])
                    return static_cast<int>(i);
            return fallback;
        }
    }

    void drawVideoPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        launcher::Config &c = app.config;

        // ---- Detail -------------------------------------------------------------------------------------
        const std::vector<const char *> detail = {"NATIVE", "SHARP 2x", "SHARPER 3x", "SHARPEST 4x"};
        const int detailSel = c.gsScale >= 4 ? 3 : (c.gsScale == 3 ? 2 : (c.gsScale == 2 ? 1 : 0));
        Rect first = rectOf(nodes, "video.detail.0");
        rowLabel(ctx, first, "DETAIL");
        for (int i = 0; i < 4; ++i)
        {
            const Rect r = rectOf(nodes, "video.detail." + std::to_string(i));
            if (radioCell(ctx, r, detail[i], "video.detail." + std::to_string(i), i == detailSel) && i != detailSel)
            {
                c.gsScale = i + 1;
                app.dirty = true;
            }
        }
        caption(ctx, Vec2{first.x, first.bottom() + 6.0f},
                "How many pixels the game renders per PS2 pixel. 3x is experimental; 4x wants a strong GPU.");

        // ---- Filter -------------------------------------------------------------------------------------
        const std::vector<const char *> filters = {"linear", "integer", "point"};
        const int filterSel = indexOf(filters, c.presentFilter, 0);
        const Rect filter0 = rectOf(nodes, "video.filter.0");
        rowLabel(ctx, filter0, "FILTER");
        for (int i = 0; i < 3; ++i)
        {
            const Rect r = rectOf(nodes, "video.filter." + std::to_string(i));
            const std::string label = i == 0 ? "LINEAR" : (i == 1 ? "INTEGER" : "POINT");
            if (radioCell(ctx, r, label.c_str(), "video.filter." + std::to_string(i), i == filterSel) && i != filterSel)
            {
                c.presentFilter = filters[i];
                app.dirty = true;
            }
        }
        caption(ctx, Vec2{filter0.x, filter0.bottom() + 6.0f},
                "How the finished frame is scaled to your window. Integer keeps every pixel square.");

        // ---- Window -------------------------------------------------------------------------------------
        const std::vector<const char *> sizes = {"640x448", "1280x896", "fullscreen", "Match display"};
        int sizeSel = indexOf(sizes, c.windowSize, -1);
        if (sizeSel < 0)
            sizeSel = (c.windowSize == app.monitorSize && !app.monitorSize.empty()) ? 3 : 0;
        const Rect window0 = rectOf(nodes, "video.window.0");
        rowLabel(ctx, window0, "WINDOW");
        for (int i = 0; i < 4; ++i)
        {
            const Rect r = rectOf(nodes, "video.window." + std::to_string(i));
            const std::string label = i == 3 ? (app.monitorSize.empty() ? std::string("MATCH DISPLAY")
                                                                       : "MATCH " + app.monitorSize)
                                             : std::string(sizes[i]);
            std::string shown = label;
            for (char &ch : shown)
                ch = static_cast<char>(ch >= 'a' && ch <= 'z' ? ch - 32 : ch);
            if (radioCell(ctx, r, shown.c_str(), "video.window." + std::to_string(i), i == sizeSel) && i != sizeSel)
            {
                // "Match display" is a button, not a stored value: what lands in config.json is the monitor's
                // own <w>x<h>, so a config carried to another machine is a size, not a surprise.
                if (i == 3)
                {
                    if (!app.monitorSize.empty())
                    {
                        c.windowSize = app.monitorSize;
                        app.dirty = true;
                    }
                }
                else
                {
                    c.windowSize = sizes[i];
                    app.dirty = true;
                }
            }
        }
        caption(ctx, Vec2{window0.x, window0.bottom() + 6.0f},
                "The size the game's own window opens at. This launcher's window is separate.");

        // ---- FPS overlay --------------------------------------------------------------------------------
        const Rect fps = rectOf(nodes, "video.fps");
        rowLabel(ctx, fps, "OVERLAY");
        if (toggle(ctx, fps, "FPS overlay -- host fps, the game's vsync rate, frame time", "video.fps", c.fpsOverlay))
            app.dirty = true;
    }
}
