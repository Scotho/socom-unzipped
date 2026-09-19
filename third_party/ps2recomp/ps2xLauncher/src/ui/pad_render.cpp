// Sprint 8 Goal 9 (third pass): the drawn pad -- a DualShock 2 from the front, one authored outline filled
// span by span and stroked once. No art ships with the launcher, and padGeometry() places every part of it.
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

        // The silhouette, filled from its own outline: for each row, every crossing of the polygon, sorted,
        // filled in pairs. One shape, no seams, whatever the curve does.
        void fillOutline(const Ctx &ctx, const PadGeometry &g, Rgba color, float grow)
        {
            const float step = 1.1f;
            const float top = g.hull.y - grow;
            const float bottom = g.hull.bottom() + grow;
            float xs[64];
            for (float y = top; y < bottom; y += step)
            {
                const float sampleY = y + step * 0.5f;
                int n = 0;
                for (int i = 0, j = g.outlineCount - 1; i < g.outlineCount && n < 64; j = i++)
                {
                    const Vec2 a = g.outline[i];
                    const Vec2 b = g.outline[j];
                    if ((a.y > sampleY) != (b.y > sampleY))
                        xs[n++] = (b.x - a.x) * (sampleY - a.y) / (b.y - a.y) + a.x;
                }
                if (n < 2)
                    continue;
                std::sort(xs, xs + n);
                for (int k = 0; k + 1 < n; k += 2)
                {
                    const float x0 = xs[k] - grow;
                    const float x1 = xs[k + 1] + grow;
                    fillRect(ctx, Rect{x0, y, x1 - x0, step + 0.6f}, color);
                }
            }
        }
    }

    void drawPad(const Ctx &ctx, Rect bounds, const PadSnapshot &pad, float deadZone, PadMark mark)
    {
        const PadGeometry g = padGeometry(bounds);
        const bool on = pad.present;
        // Disconnected: the whole drawing at 35%, and a line across it saying so.
        auto A = [on](Rgba c)
        {
            return on ? c : Rgba{c.r, c.g, c.b, static_cast<unsigned char>(static_cast<float>(c.a) * 0.35f)};
        };

        const Rgba shell = theme::mix(theme::panelHi, theme::line, 0.18f);
        const Rgba edge = theme::line;
        const Rgba recess = theme::mix(theme::ground, theme::panel, 0.30f);
        const Rgba cap = theme::mix(theme::panelHi, theme::line, 0.40f);

        // ---- the silhouette ------------------------------------------------------------------------------
        fillOutline(ctx, g, A(shell), 0.0f);
        strokePath(ctx, g.outline, g.outlineCount, A(edge), 2.5f, true);
        // A highlight just inside the top edge, so the shell has some depth.
        for (int i = 1; i < g.outlineCount; ++i)
        {
            const Vec2 a = g.outline[i - 1];
            const Vec2 b = g.outline[i];
            if (a.y < g.hull.y + g.height * 0.10f && b.y < g.hull.y + g.height * 0.10f)
                drawLine(ctx, Vec2{a.x, a.y + 3.5f}, Vec2{b.x, b.y + 3.5f}, A(theme::alpha(theme::panelHi, 200)), 2.0f);
        }

        // ---- the centre plate ----------------------------------------------------------------------------
        fillRound(ctx, g.plate, g.plate.h * 0.34f, A(theme::mix(theme::panel, theme::panelHi, 0.75f)));
        strokeRound(ctx, g.plate, g.plate.h * 0.34f, A(edge), 1.5f);
        for (int i = 0; i < 2; ++i)
        {
            const PadCircle &b = g.center[i];
            const bool down = on && pad.down[static_cast<int>(b.element)];
            const Rect pill{b.c.x - b.r * 2.2f, b.c.y - b.r * 0.9f, b.r * 4.4f, b.r * 1.8f};
            fillRound(ctx, pill, pill.h * 0.5f, A(down ? theme::gold : recess));
            strokeRound(ctx, pill, pill.h * 0.5f, A(down ? theme::goldHi : edge), 1.5f);
            const char *label = i == 0 ? "SELECT" : "START";
            const float size = g.width * 0.026f;
            text(ctx, label, Vec2{pill.cx() - textWidth(ctx, label, size, Face::Bold) * 0.5f, g.plate.y - size * 1.6f},
                 size, A(theme::caption), Face::Bold);
        }
        fillCircle(ctx, Vec2{g.plate.cx(), g.plate.cy()}, g.width * 0.010f, A(theme::mix(theme::bad, theme::panel, 0.25f)));
        strokeCircle(ctx, Vec2{g.plate.cx(), g.plate.cy()}, g.width * 0.016f, A(edge), 1.2f);

        // ---- the d-pad: four segments in a recessed well -------------------------------------------------
        fillCircle(ctx, g.dpadWell, g.dpadWellRadius, A(recess));
        strokeCircle(ctx, g.dpadWell, g.dpadWellRadius, A(edge), 1.5f);
        const Vec2 dirs[4] = {{0.0f, -1.0f}, {0.0f, 1.0f}, {-1.0f, 0.0f}, {1.0f, 0.0f}};
        for (int i = 0; i < 4; ++i)
        {
            const PadCircle &b = g.dpad[i];
            const bool down = on && pad.down[static_cast<int>(b.element)];
            const float segR = b.r * 1.55f;
            const float inward = angleOf(dirs[i]) + 180.0f;   // a vertex pointing back at the well's centre
            fillPoly(ctx, b.c, 5, segR, inward, A(down ? theme::gold : theme::mix(theme::panelHi, theme::line, 0.25f)));
            strokePoly(ctx, b.c, 5, segR, inward, A(down ? theme::goldHi : edge), 1.5f);
            const Vec2 arrowAt{b.c.x + dirs[i].x * segR * 0.16f, b.c.y + dirs[i].y * segR * 0.16f};
            fillPoly(ctx, arrowAt, 3, segR * 0.34f, angleOf(dirs[i]), A(down ? theme::ground : theme::caption));
        }

        // ---- the face buttons ----------------------------------------------------------------------------
        fillCircle(ctx, g.faceWell, g.faceWellRadius, A(recess));
        strokeCircle(ctx, g.faceWell, g.faceWellRadius, A(edge), 1.5f);
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
                               b.r * 1.3f, ink, Face::Bold);
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
                strokeCircle(ctx, centre, ring, A(theme::alpha(theme::warn, 160)), 1.2f);

            const Vec2 axis = i == 0 ? pad.leftStick : pad.rightStick;
            // Three quarters of the well is the cap's travel: pushed all the way, it rides the well's rim.
            const Vec2 off = on ? stickOffset(axis, deadZone, g.wellRadius * 0.75f) : Vec2{0.0f, 0.0f};
            const Vec2 at{centre.x + off.x, centre.y + off.y};
            if (off.x != 0.0f || off.y != 0.0f)
                drawLine(ctx, centre, at, A(theme::alpha(theme::goldHi, 180)), 2.0f);
            const bool down = on && pad.down[static_cast<int>(i == 0 ? PadElement::LeftStickClick : PadElement::RightStickClick)];
            const float capR = g.stickClick[i].r;
            fillCircle(ctx, at, capR, A(down ? theme::gold : theme::mix(theme::panelHi, theme::text, 0.22f)));
            strokeCircle(ctx, at, capR, A(down ? theme::goldHi : edge), 2.0f);
            strokeCircle(ctx, at, capR * 0.55f, A(theme::alpha(theme::ground, 160)), 1.2f);
        }

        // ---- the shoulders and the triggers --------------------------------------------------------------
        for (int i = 0; i < 2; ++i)
        {
            const Rect s = g.shoulder[i];
            const bool held = on && pad.shoulder[i];
            fillRound(ctx, s, s.h * 0.45f, A(held ? theme::gold : shell));
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
            const float size = t.h * 0.52f;
            const Rgba ink = A(value > 0.55f ? theme::ground : theme::text);
            text(ctx, i == 0 ? "L2" : "R2", Vec2{t.x + inset + 6.0f, t.cy() - size * 0.62f}, size, ink, Face::Bold);
            char number[16];
            std::snprintf(number, sizeof(number), "%.2f", static_cast<double>(value));
            const float numberSize = size * 0.9f;
            text(ctx, number, Vec2{t.right() - inset - 6.0f - textWidth(ctx, number, numberSize, Face::Bold), t.cy() - size * 0.6f},
                 numberSize, A(value > 0.55f ? theme::ground : theme::caption), Face::Bold);
        }

        // ---- R139: where the crouch shortcut is ----------------------------------------------------------
        if (on && mark != PadMark::None)
        {
            const char *tag = "CROUCH";
            const float size = 13.0f;
            const float tagW = textWidth(ctx, tag, size, Face::Bold, 0.06f);
            Vec2 at;
            if (mark == PadMark::LeftStick)
            {
                strokeCircle(ctx, g.well[0], g.wellRadius + 5.0f, theme::goldHi, 2.0f);
                at = Vec2{g.well[0].x - tagW * 0.5f, g.well[0].y + g.wellRadius + 9.0f};
            }
            else if (mark == PadMark::L2)
            {
                const Rect t = g.trigger[0];
                strokeRect(ctx, Rect{t.x - 4.0f, t.y - 4.0f, t.w + 8.0f, t.h + 8.0f}, theme::goldHi, 2.0f);
                at = Vec2{t.x - tagW - 12.0f, t.cy() - size * 0.6f};
            }
            else
            {
                const Rect r{g.plate.x - 4.0f, g.plate.y - 4.0f, g.plate.w + 8.0f, g.plate.h + 8.0f};
                strokeRound(ctx, r, 8.0f, theme::goldHi, 2.0f);
                at = Vec2{r.cx() - tagW * 0.5f, r.bottom() + 5.0f};
            }
            text(ctx, tag, at, size, theme::goldHi, Face::Bold, 0.06f);
        }

        if (!on)
        {
            const char *msg = "CONNECT A CONTROLLER";
            const float size = std::min(30.0f, g.width * 0.062f);
            const Rect band{g.hull.x, g.hull.cy() - size * 0.95f, g.hull.w, size * 1.9f};
            fillRect(ctx, band, theme::alpha(theme::ground, 200));
            strokeRect(ctx, band, theme::line, 1.0f);
            textCenteredIn(ctx, msg, band, size, theme::caption, Face::Display);
        }
    }
}
