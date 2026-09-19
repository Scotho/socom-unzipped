// Sprint 8 Goal 9, the MICROPHONE page: the capture device, and a meter that proves it hears you.
#include "pages.h"

#include <cmath>
#include <cstdio>

namespace ui
{
    void drawMicrophonePage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        const Rect first = rectOf(nodes, "mic.pick.0");
        const Rect rescan = rectOf(nodes, "mic.rescan");

        text(ctx, "CAPTURE DEVICE", Vec2{first.x, first.y - 26.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
        int micSel = 0;
        for (size_t i = 1; i < app.micLabels.size(); ++i)
            if (app.micLabels[i] == app.config.micDevice)
                micSel = static_cast<int>(i);
        for (size_t i = 0; i < app.micLabels.size(); ++i)
        {
            const std::string id = "mic.pick." + std::to_string(i);
            const Rect r = rectOf(nodes, id);
            if (r.w <= 0.0f)
                continue;
            if (listRow(ctx, r, app.micLabels[i], id, static_cast<int>(i) == micSel) && static_cast<int>(i) != micSel)
            {
                app.config.micDevice = (i == 0) ? std::string() : app.micLabels[i];
                app.requestMicChanged = true;
                app.dirty = true;
            }
        }

        if (button(ctx, rescan, "RESCAN", "mic.rescan"))
            app.requestMicRescan = true;

        // The meter: -60 dB (silence) to 0 dB (full scale), redrawn every frame from the capture callback.
        const Rect column{rescan.x - 200.0f, rescan.bottom() + 28.0f, rescan.right() - (rescan.x - 200.0f), 140.0f};
        text(ctx, "LEVEL", Vec2{column.x, column.y}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
        const Rect meter{column.x, column.y + 22.0f, column.w, 26.0f};
        float filled = 0.0f;
        if (app.meterOn && app.micDbValid)
            filled = (app.micDb + 60.0f) / 60.0f;
        filled = filled < 0.0f ? 0.0f : (filled > 1.0f ? 1.0f : filled);
        meterBar(ctx, meter, filled, filled > 0.9f ? theme::bad : theme::mix(theme::lampGreen, theme::panel, 0.22f));
        char db[32];
        if (app.meterOn && app.micDbValid)
            std::snprintf(db, sizeof(db), "%.0f dB", static_cast<double>(app.micDb));
        else
            std::snprintf(db, sizeof(db), "--");
        // The reading goes above the bar, beside its label; the scale's two ends go under it.
        text(ctx, db, Vec2{column.right() - textWidth(ctx, db, 18.0f, Face::Bold), column.y - 3.0f}, 18.0f,
             theme::text, Face::Bold);
        text(ctx, "-60 dB", Vec2{meter.x, meter.bottom() + 8.0f}, 15.0f, theme::dim);
        text(ctx, "0 dBFS", Vec2{meter.right() - textWidth(ctx, "0 dBFS", 15.0f), meter.bottom() + 8.0f}, 15.0f, theme::dim);

        if (!app.micStatus.empty())
            text(ctx, app.micStatus.c_str(), Vec2{meter.x, meter.bottom() + 32.0f}, 17.0f,
                 app.meterOn ? theme::lampGreen : theme::warn);

        caption(ctx, Vec2{first.x, column.bottom() + 6.0f},
                "The game does not send your voice yet (that is a later sprint); this meter proves the device works");
        caption(ctx, Vec2{first.x, column.bottom() + 26.0f},
                "and is the one the game will open. While the game runs, it holds the device instead of the launcher.");
    }
}
