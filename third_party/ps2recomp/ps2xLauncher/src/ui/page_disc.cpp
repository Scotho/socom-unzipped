// Sprint 8 Goal 9, the DISC page: the image, the check, the verdict.
#include "pages.h"

namespace ui
{
    void drawDiscPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        const Rect field = rectOf(nodes, "disc.path");
        const Rect browse = rectOf(nodes, "disc.browse");
        const Rect verify = rectOf(nodes, "disc.verify");
        rowLabel(ctx, field, "DISC IMAGE");
        bool changed = false;
        textField(ctx, field, app.config.isoPath, "disc.path", changed);
        if (changed)
        {
            app.dirty = true;
            app.requestVerify = true;
        }
        if (button(ctx, browse, "BROWSE...", "disc.browse"))
            app.requestBrowse = true;

        // The verdict, as a lamp and a sentence.
        const Rect verdict{field.x - metrics::labelW, field.bottom() + 24.0f,
                           browse.right() - (field.x - metrics::labelW), 74.0f};
        panel(ctx, verdict);
        const Rgba lamp = app.discOk ? theme::lampGreen : (app.config.isoPath.empty() ? theme::warn : theme::bad);
        fillCircle(ctx, Vec2{verdict.x + 30.0f, verdict.cy()}, 9.0f, lamp);
        strokeCircle(ctx, Vec2{verdict.x + 30.0f, verdict.cy()}, 15.0f, theme::alpha(lamp, 110), 2.0f);
        const std::string message = app.discMessage.empty() ? std::string("not checked yet") : app.discMessage;
        text(ctx, ellipsizeEnd(ctx, message, verdict.w - 90.0f, 22.0f, Face::Bold).c_str(),
             Vec2{verdict.x + 60.0f, verdict.y + 16.0f}, 22.0f, app.discOk ? theme::text : lamp, Face::Bold);
        caption(ctx, Vec2{verdict.x + 60.0f, verdict.y + 44.0f},
                "SCUS_972.75 is read out of the image and hashed against the pinned NTSC r0001 digest");

        if (button(ctx, verify, "RE-VERIFY  F5", "disc.verify"))
            app.requestVerify = true;

        caption(ctx, Vec2{verdict.x, verify.bottom() + 22.0f},
                "Nothing is copied and nothing is installed: the game reads your image where it sits.");
        caption(ctx, Vec2{verdict.x, verify.bottom() + 44.0f},
                "The disc image is yours; none of it ships with SOCOM Unzipped.");
    }
}
