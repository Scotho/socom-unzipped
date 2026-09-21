// Sprint 8 Goal 9, the CONTROLLER page: the pad as the game will read it, and the four knobs that change it.
#include "glyphs.h"
#include "pages.h"

#include <cstdio>
#include <string>

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
        const Rect padArea{firstPick.x + (sensitivity.right() - firstPick.x) * 0.5f - 280.0f,
                           firstPick.y - 330.0f, 560.0f, 282.0f};
        const std::string crouch = launcher::normalizeCrouchShortcut(c.crouchShortcut);
        const PadMark mark = crouch == "l3" ? PadMark::LeftStick
                                            : (crouch == "touchpad" ? PadMark::Plate : (crouch == "l2" ? PadMark::L2 : PadMark::None));
        drawPad(ctx, padArea, app.pad, static_cast<float>(c.padDeadZone), mark);

        // The legend: the owner plays on an Xbox pad and the game prompts with PlayStation shapes.
        const GlyphFamily family = glyphFamilyFor(app.pad.name);
        if (app.pad.present && family != GlyphFamily::PlayStation)
        {
            const float y = padArea.bottom() + 4.0f;
            text(ctx, "YOUR PAD / THE GAME", Vec2{padArea.x + 14.0f, y}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
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
        text(ctx, "CONTROLLER", Vec2{firstPick.x, firstPick.y - 24.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
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
        text(ctx, label, Vec2{deadZone.x, deadZone.y - 22.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
        if (slider(ctx, deadZone, "pad.deadzone", c.padDeadZone, 0.0, 0.40, 0.01))
            app.dirty = true;

        if (toggle(ctx, mouseLook, "Mouse look", "pad.mouselook", c.mouseLook))
            app.dirty = true;

        std::snprintf(label, sizeof(label), "MOUSE SENSITIVITY  %.2f", c.mouseSensitivity);
        text(ctx, label, Vec2{sensitivity.x, sensitivity.y - 22.0f}, metrics::labelSize,
             c.mouseLook ? theme::dim : theme::mix(theme::dim, theme::ground, 0.35f), Face::Bold, 0.06f);
        if (slider(ctx, sensitivity, "pad.sensitivity", c.mouseSensitivity, 0.25, 3.0, 0.05))
            app.dirty = true;

        // ---- the crouch shortcut (owner request 2026-09-19, R139) ------------------------------------------
        // One line of help serves the page. It states the shortcut's trade while a crouch cell is under the focus
        // or the mouse (so the cost is read BEFORE it is chosen) and for as long as a shortcut is on; otherwise it
        // is the page's own line.
        const Rect crouch0 = rectOf(nodes, "pad.crouch.0");
        const char *hint = crouch == "off" ? nullptr : launcher::crouchShortcutHint(crouch);
        if (crouch0.w > 0.0f)
        {
            text(ctx, "CROUCH SHORTCUT", Vec2{firstPick.x, crouch0.y + 6.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
            for (int i = 0; i < launcher::kCrouchShortcutCount; ++i)
            {
                const std::string id = "pad.crouch." + std::to_string(i);
                const Rect r = rectOf(nodes, id);
                const char *value = launcher::kCrouchShortcuts[i];
                const bool selected = crouch == value;
                if (hovered(ctx, r) || focused(ctx, id))
                    hint = launcher::crouchShortcutHint(value);
                if (radioCell(ctx, r, launcher::crouchShortcutLabel(value), id, selected) && !selected)
                {
                    c.crouchShortcut = value;
                    app.dirty = true;
                }
            }
        }

        // +123, not +112: a line longer than the pad list is wide has to clear the sensitivity slider (ends at +120).
        caption(ctx, Vec2{firstPick.x, firstPick.y + 123.0f},
                hint != nullptr
                    ? hint
                    : (app.pad.present
                           ? "Press a button: what lights up above is what the game reads. The ring is the dead zone."
                           : "No pad: WASD move, IJKL look, Z/X/C/V = square/cross/circle/triangle, Q/E = L1/R1, Enter = start."));
    }
}
