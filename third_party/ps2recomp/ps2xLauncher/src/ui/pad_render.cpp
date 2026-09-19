// Sprint 8 Goal 9 (second pass): the drawn pad -- a DualShock 2 from the front, built out of raylib
// primitives. No art ships with the launcher, and padGeometry() is the only place any of it is positioned.
#include "pad_render.h"

#include "glyphs.h"
#include "widgets.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace ui
{
    namespace
    {
        constexpr float kDeg = 57.29578f;

        float angleOf(Vec2 dir) { return std::atan2(dir.y, dir.x) * kDeg; }
    }

    void drawPad(const Ctx &ctx, Rect bounds, const PadSnapshot &pad, float deadZone)
    {
        const PadGeometry g = padGeometry(bounds);
        const bool on = pad.present;
        // Disconnected: the whole drawing at 35%, and a line across it saying so.
        auto A = [on](Rgba c)
        {
            return on ? c : Rgba{c.r, c.g, c.b, static_cast<unsigned char>(static_cast<float>(c.a) * 0.35f)};
        };

        const Rgba shell = theme::panel;
        const Rgba edge = theme::line;
        const Rgba recess = theme::mix(theme::ground, theme::panel, 0.22f);
        const Rgba cap = theme::mix(theme::panelHi, theme::line, 0.35f);

        // ---- the silhouette ------------------------------------------------------------------------------
        // One continuous outline: every piece is drawn 2 units oversized in the line colour first, then at
        // its own size in the shell colour, so the union's contour survives and the seams inside it do not.
        auto silhouette = [&](float grow, Rgba color)
        {
            for (int i = 0; i < 2; ++i)
                fillCircle(ctx, g.wing[i], g.wingRadius + grow, color);
            for (int i = 0; i < 2; ++i)
            {
                const int steps = 16;
                for (int s = 0; s <= steps; ++s)
                {
                    const float t = static_cast<float>(s) / static_cast<float>(steps);
                    const Vec2 c{g.handle[i].x + (g.handleTip[i].x - g.handle[i].x) * t,
                                 g.handle[i].y + (g.handleTip[i].y - g.handle[i].y) * t};
                    fillCircle(ctx, c, g.handleRadius * (1.0f - 0.28f * t) + grow, color);
                }
            }
            fillRound(ctx, Rect{g.body.x - grow, g.body.y - grow, g.body.w + grow * 2.0f, g.body.h + grow * 2.0f},
                      g.cornerRadius + grow, color);
        };
        silhouette(2.0f, A(edge));
        silhouette(0.0f, A(shell));
        // A highlight three units inside the top edge, so the shell has some depth.
        drawLine(ctx, Vec2{g.body.x + g.cornerRadius * 0.6f, g.body.y + 3.0f},
                 Vec2{g.body.right() - g.cornerRadius * 0.6f, g.body.y + 3.0f}, A(theme::panelHi), 2.0f);

        // ---- the centre plate ----------------------------------------------------------------------------
        fillRound(ctx, g.plate, g.plate.h * 0.30f, A(theme::mix(theme::panel, theme::panelHi, 0.55f)));
        strokeRound(ctx, g.plate, g.plate.h * 0.30f, A(edge), 1.0f);
        for (int i = 0; i < 2; ++i)
        {
            const PadCircle &b = g.center[i];
            const bool down = pad.down[static_cast<int>(b.element)];
            const Rect pill{b.c.x - b.r * 2.1f, b.c.y - b.r * 0.85f, b.r * 4.2f, b.r * 1.7f};
            fillRound(ctx, pill, pill.h * 0.5f, A(down && on ? theme::gold : recess));
            strokeRound(ctx, pill, pill.h * 0.5f, A(down && on ? theme::goldHi : edge), 1.5f);
            const char *label = i == 0 ? "SELECT" : "START";
            const float size = g.wingRadius * 0.15f;
            text(ctx, label, Vec2{pill.cx() - textWidth(ctx, label, size, Face::Bold) * 0.5f, g.plate.y - size * 1.5f},
                 size, A(theme::dim), Face::Bold);
        }
        // The ANALOG light, between them.
        fillCircle(ctx, Vec2{g.plate.cx(), g.plate.cy()}, g.wingRadius * 0.055f, A(theme::mix(theme::bad, theme::panel, 0.35f)));
        strokeCircle(ctx, Vec2{g.plate.cx(), g.plate.cy()}, g.wingRadius * 0.08f, A(edge), 1.0f);

        // ---- the d-pad: four segments in a recessed well -------------------------------------------------
        fillCircle(ctx, g.dpadWell, g.dpadWellRadius, A(recess));
        strokeCircle(ctx, g.dpadWell, g.dpadWellRadius, A(edge), 1.0f);
        const Vec2 dirs[4] = {{0.0f, -1.0f}, {0.0f, 1.0f}, {-1.0f, 0.0f}, {1.0f, 0.0f}};
        for (int i = 0; i < 4; ++i)
        {
            const PadCircle &b = g.dpad[i];
            const bool down = on && pad.down[static_cast<int>(b.element)];
            const float segR = b.r * 1.5f;
            const float inward = angleOf(dirs[i]) + 180.0f;   // a vertex pointing back at the well's centre
            fillPoly(ctx, b.c, 5, segR, inward, A(down ? theme::gold : theme::mix(theme::panel, theme::panelHi, 0.5f)));
            strokePoly(ctx, b.c, 5, segR, inward, A(down ? theme::goldHi : edge), 1.5f);
            const Vec2 arrowAt{b.c.x + dirs[i].x * segR * 0.16f, b.c.y + dirs[i].y * segR * 0.16f};
            fillPoly(ctx, arrowAt, 3, segR * 0.34f, angleOf(dirs[i]), A(down ? theme::ground : theme::dim));
        }

        // ---- the face buttons ----------------------------------------------------------------------------
        fillCircle(ctx, g.faceWell, g.faceWellRadius, A(recess));
        strokeCircle(ctx, g.faceWell, g.faceWellRadius, A(edge), 1.0f);
        const GlyphFamily family = glyphFamilyFor(pad.name);
        for (int i = 0; i < 4; ++i)
        {
            const PadCircle &b = g.face[i];
            const bool down = on && pad.down[static_cast<int>(b.element)];
            fillCircle(ctx, b.c, b.r, A(down ? theme::gold : cap));
            strokeCircle(ctx, b.c, b.r, A(down ? theme::goldHi : edge), 1.5f);
            const Rgba ink = A(down ? theme::ground : theme::text);
            if (family == GlyphFamily::PlayStation)
                drawShapeGlyph(ctx, i, b.c, b.r * 1.05f, ink);
            else
                textCenteredIn(ctx, faceLetter(family, i), Rect{b.c.x - b.r, b.c.y - b.r, b.r * 2.0f, b.r * 2.0f},
                               b.r * 1.25f, ink, Face::Bold);
        }

        // ---- the sticks ----------------------------------------------------------------------------------
        for (int i = 0; i < 2; ++i)
        {
            const Vec2 centre = g.well[i];
            fillCircle(ctx, centre, g.wellRadius, A(recess));
            strokeCircle(ctx, centre, g.wellRadius, A(edge), 1.5f);
            // The dead zone, the ring the slider resizes live: inside it the game reads nothing at all.
            const float ring = deadZoneRingRadius(deadZone, g.wellRadius);
            if (ring > 0.5f)
                strokeCircle(ctx, centre, ring, A(theme::alpha(theme::warn, 150)), 1.0f);

            const Vec2 axis = i == 0 ? pad.leftStick : pad.rightStick;
            // Three quarters of the well is the cap's travel: pushed all the way, it rides the well's rim.
            const Vec2 off = on ? stickOffset(axis, deadZone, g.wellRadius * 0.75f) : Vec2{0.0f, 0.0f};
            const Vec2 at{centre.x + off.x, centre.y + off.y};
            if (off.x != 0.0f || off.y != 0.0f)
                drawLine(ctx, centre, at, A(theme::alpha(theme::goldHi, 170)), 2.0f);
            const bool down = on && pad.down[static_cast<int>(i == 0 ? PadElement::LeftStickClick : PadElement::RightStickClick)];
            const float capR = g.stickClick[i].r;
            fillCircle(ctx, at, capR, A(down ? theme::gold : theme::mix(theme::panelHi, theme::text, 0.18f)));
            strokeCircle(ctx, at, capR, A(down ? theme::goldHi : edge), 2.0f);
            strokeCircle(ctx, at, capR * 0.55f, A(theme::alpha(theme::ground, 150)), 1.0f);
        }

        // ---- the shoulders and the triggers --------------------------------------------------------------
        for (int i = 0; i < 2; ++i)
        {
            const Rect s = g.shoulder[i];
            const bool held = on && pad.shoulder[i];
            fillRound(ctx, s, s.h * 0.45f, A(held ? theme::gold : theme::mix(theme::panel, theme::panelHi, 0.5f)));
            strokeRound(ctx, s, s.h * 0.45f, A(held ? theme::goldHi : edge), 2.0f);
            textCenteredIn(ctx, i == 0 ? "L1" : "R1", s, s.h * 0.62f, A(held ? theme::ground : theme::text), Face::Bold);

            // The trigger: a trapezoid whose gold fill rises with the analog value.
            const Rect t = g.trigger[i];
            const float inset = t.w * 0.12f;
            auto left = [&](float y) { return t.x + inset * (1.0f - (y - t.y) / t.h); };
            auto right = [&](float y) { return t.right() - inset * (1.0f - (y - t.y) / t.h); };
            fillQuad(ctx, Vec2{left(t.y), t.y}, Vec2{left(t.bottom()), t.bottom()},
                     Vec2{right(t.bottom()), t.bottom()}, Vec2{right(t.y), t.y}, A(recess));
            const float value = on ? std::min(1.0f, std::max(0.0f, pad.trigger[i])) : 0.0f;
            if (value > 0.01f)
            {
                const float yf = t.bottom() - t.h * value;
                fillQuad(ctx, Vec2{left(yf), yf}, Vec2{left(t.bottom()), t.bottom()},
                         Vec2{right(t.bottom()), t.bottom()}, Vec2{right(yf), yf}, A(theme::gold));
            }
            const Rgba outline = A(value > 0.01f ? theme::goldHi : edge);
            drawLine(ctx, Vec2{left(t.y), t.y}, Vec2{left(t.bottom()), t.bottom()}, outline, 2.0f);
            drawLine(ctx, Vec2{right(t.y), t.y}, Vec2{right(t.bottom()), t.bottom()}, outline, 2.0f);
            drawLine(ctx, Vec2{left(t.y), t.y}, Vec2{right(t.y), t.y}, outline, 2.0f);
            drawLine(ctx, Vec2{left(t.bottom()), t.bottom()}, Vec2{right(t.bottom()), t.bottom()}, outline, 2.0f);
            const float size = t.h * 0.50f;
            const Rgba ink = A(value > 0.55f ? theme::ground : theme::text);
            text(ctx, i == 0 ? "L2" : "R2", Vec2{t.x + inset + 6.0f, t.cy() - size * 0.6f}, size, ink, Face::Bold);
            char number[16];
            std::snprintf(number, sizeof(number), "%.2f", static_cast<double>(value));
            text(ctx, number, Vec2{t.right() - inset - 6.0f - textWidth(ctx, number, size * 0.86f, Face::Bold), t.cy() - size * 0.55f},
                 size * 0.86f, A(value > 0.55f ? theme::ground : theme::dim), Face::Bold);
        }

        if (!on)
        {
            const char *msg = "CONNECT A CONTROLLER";
            const float size = std::min(30.0f, g.hull.w * 0.062f);
            const Rect band{g.hull.x, g.hull.cy() - size * 0.95f, g.hull.w, size * 1.9f};
            fillRect(ctx, band, theme::alpha(theme::ground, 190));
            strokeRect(ctx, band, theme::line, 1.0f);
            textCenteredIn(ctx, msg, band, size, theme::dim, Face::Display);
        }
    }
}
