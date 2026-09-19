// Sprint 8 Goal 9, the CONTROLLER page: the pad as the game will read it, and the four knobs that change it.
#include "glyphs.h"
#include "pages.h"

#include <cstdio>

namespace ui
{
    void drawControllerPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        launcher::Config &c = app.config;
        const Rect firstPick = rectOf(nodes, "pad.pick.0");
        const Rect deadZone = rectOf(nodes, "pad.deadzone");
        const Rect mouseLook = rectOf(nodes, "pad.mouselook");
        const Rect sensitivity = rectOf(nodes, "pad.sensitivity");

        // ---- the drawn pad ------------------------------------------------------------------------------
        // The pad fills the band above the controls: 520 units wide, centred on the body, with the glyph
        // legend in its own strip underneath so nothing ever sits on top of the drawing.
        const Rect padArea{firstPick.x + (sensitivity.right() - firstPick.x) * 0.5f - 250.0f,
                           firstPick.y - 310.0f, 500.0f, 252.0f};
        drawPad(ctx, padArea, app.pad, static_cast<float>(c.padDeadZone));

        // The legend: the owner plays on an Xbox pad and the game prompts with PlayStation shapes.
        const GlyphFamily family = glyphFamilyFor(app.pad.name);
        if (app.pad.present && family != GlyphFamily::PlayStation)
        {
            const float y = padArea.bottom() + 6.0f;
            text(ctx, "YOUR PAD / THE GAME", Vec2{padArea.x + 14.0f, y}, 15.0f, theme::dim, Face::Bold);
            float x = padArea.x + 200.0f;
            static const int order[4] = {1, 3, 2, 0};   // cross, circle, square, triangle
            for (int k = 0; k < 4; ++k)
            {
                const int i = order[k];
                text(ctx, faceLetter(family, i), Vec2{x, y - 2.0f}, 18.0f, theme::text, Face::Bold);
                text(ctx, "=", Vec2{x + 17.0f, y - 2.0f}, 18.0f, theme::dim);
                drawShapeGlyph(ctx, i, Vec2{x + 44.0f, y + 9.0f}, 17.0f, theme::goldHi);
                x += 74.0f;
            }
        }

        // ---- the pad picker -----------------------------------------------------------------------------
        text(ctx, "CONTROLLER", Vec2{firstPick.x, firstPick.y - 24.0f}, 15.0f, theme::dim, Face::Bold);
        int padSel = 0;
        for (size_t i = 0; i < app.padSlots.size(); ++i)
            if (app.padSlots[i] == c.gamepadIndex)
                padSel = static_cast<int>(i);
        for (size_t i = 0; i < app.padLabels.size(); ++i)
        {
            const std::string id = "pad.pick." + std::to_string(i);
            const Rect r = rectOf(nodes, id);
            if (r.w <= 0.0f)
                continue;
            if (listRow(ctx, r, app.padLabels[i], id, static_cast<int>(i) == padSel) && static_cast<int>(i) != padSel)
            {
                c.gamepadIndex = app.padSlots[i];
                app.dirty = true;
            }
        }

        // ---- the knobs ----------------------------------------------------------------------------------
        char label[64];
        std::snprintf(label, sizeof(label), "DEAD ZONE  %.2f", c.padDeadZone);
        text(ctx, label, Vec2{deadZone.x, deadZone.y - 22.0f}, 15.0f, theme::dim, Face::Bold);
        if (slider(ctx, deadZone, "pad.deadzone", c.padDeadZone, 0.0, 0.40, 0.01))
            app.dirty = true;

        if (toggle(ctx, mouseLook, "Mouse look", "pad.mouselook", c.mouseLook))
            app.dirty = true;

        std::snprintf(label, sizeof(label), "MOUSE SENSITIVITY  %.2f", c.mouseSensitivity);
        text(ctx, label, Vec2{sensitivity.x, sensitivity.y - 22.0f}, 15.0f,
             c.mouseLook ? theme::dim : theme::mix(theme::dim, theme::ground, 0.45f), Face::Bold);
        if (slider(ctx, sensitivity, "pad.sensitivity", c.mouseSensitivity, 0.25, 3.0, 0.05))
            app.dirty = true;

        caption(ctx, Vec2{firstPick.x, firstPick.y + 142.0f},
                app.pad.present
                    ? "Press a button: what lights up above is what the game reads. The ring is the dead zone."
                    : "No pad: WASD move, IJKL look, Z/X/C/V = square/cross/circle/triangle, Q/E = L1/R1, Enter = start.");
    }
}
