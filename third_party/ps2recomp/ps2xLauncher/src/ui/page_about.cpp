// Sprint 8 Goal 9, the ABOUT page: what this is, what it is built from, where it keeps its two files.
#include "pages.h"

namespace ui
{
    void drawAboutPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        const Rect logs = rectOf(nodes, "about.logs");
        const Rect b = app.frame.body;
        const float x = b.x;
        float y = b.y;

        text(ctx, "SOCOM UNZIPPED", Vec2{x, y}, 34.0f, theme::gold, Face::Display);
        y += 44.0f;
        text(ctx, app.version.empty() ? "development build" : app.version.c_str(), Vec2{x, y}, metrics::bodySize - 1.0f, theme::caption);
        y += 34.0f;
        text(ctx, "SOCOM II: U.S. Navy SEALs, recompiled for the PC. Not affiliated with Sony or Zipper Interactive.",
             Vec2{x, y}, 17.0f, theme::text);
        y += 26.0f;
        text(ctx, "The game's disc image is yours and stays yours: nothing from it ships here.",
             Vec2{x, y}, 17.0f, theme::text);

        y += 40.0f;
        text(ctx, "BUILT FROM", Vec2{x, y}, 15.0f, theme::dim, Face::Bold);
        y += 22.0f;
        // Two columns on the same grid: what it is on the left, the licence it carries on the right.
        static const char *credits[][2] = {
            {"the PS2Recomp fork", "GPL-3.0"},
            {"raylib (window, input, audio)", "zlib"},
            {"ffmpeg (video)", "LGPL-2.1-or-later"},
            {"SDL2", "zlib"},
            {"Saira Stencil One, Rajdhani (type)", "SIL Open Font License 1.1"},
        };
        for (const auto &line : credits)
        {
            text(ctx, line[0], Vec2{x, y}, 16.0f, theme::text);
            text(ctx, line[1], Vec2{x + 300.0f, y}, 16.0f, theme::dim);
            y += 22.0f;
        }
        text(ctx, "Every licence text ships in LICENSES/ next to the game.", Vec2{x, y}, 15.0f, theme::dim);

        y += 36.0f;
        text(ctx, "WHERE THINGS LIVE", Vec2{x, y}, 15.0f, theme::dim, Face::Bold);
        y += 24.0f;
        text(ctx, "config", Vec2{x, y}, 16.0f, theme::dim);
        text(ctx, ellipsizeStart(ctx, app.configPath, logs.w * 2.6f, 16.0f).c_str(), Vec2{x + 80.0f, y}, 16.0f, theme::text);
        y += 22.0f;
        text(ctx, "logs", Vec2{x, y}, 16.0f, theme::dim);
        text(ctx, ellipsizeStart(ctx, app.logsPath, logs.w * 2.6f, 16.0f).c_str(), Vec2{x + 80.0f, y}, 16.0f, theme::text);
        y += 28.0f;
        text(ctx, "Nothing is installed; delete the folder to remove it.", Vec2{x, y}, 17.0f, theme::goldHi, Face::Bold);

        if (button(ctx, logs, "OPEN LOGS", "about.logs"))
            app.requestOpenLogs = true;
    }
}
