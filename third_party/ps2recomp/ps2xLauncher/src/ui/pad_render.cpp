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

        float clamp01(float v) { return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v); }

        Rect grown(Rect r, float by) { return Rect{r.x - by, r.y - by, r.w + by * 2.0f, r.h + by * 2.0f}; }

        // The silhouette, filled from its own outline: for each row, every crossing of the polygon, sorted,
        // filled in pairs. One shape, no seams, whatever the curve does.
        //
        // W9 (2026-09-22, "improve the graphic just a bit"): the fill is a vertical gradient rather than one
        // flat colour, and the whole shape can be offset -- which is all a drop shadow is. Both fall out of
        // the scanline loop that was already here, so the pad gained depth without gaining a pipeline.
        void fillOutline(const Ctx &ctx, const PadGeometry &g, Rgba top, Rgba bottom, float grow, Vec2 offset)
        {
            const float step = 1.1f;
            const float y0 = g.hull.y - grow;
            const float y1 = g.hull.bottom() + grow;
            const float span = y1 - y0 > 0.001f ? y1 - y0 : 1.0f;
            float xs[64];
            for (float y = y0; y < y1; y += step)
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
                const Rgba row = theme::mix(top, bottom, clamp01((y - y0) / span));
                for (int k = 0; k + 1 < n; k += 2)
                {
                    const float x0 = xs[k] - grow + offset.x;
                    const float x1 = xs[k + 1] + grow + offset.x;
                    fillRect(ctx, Rect{x0, y + offset.y, x1 - x0, step + 0.6f}, row);
                }
            }
        }
    }

    void drawPad(const Ctx &ctx, Rect bounds, const PadSnapshot &pad, float deadZone, int markHost,
                 const std::vector<PadCallout> *callouts, int holdHost, float holdProgress)
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
        // W9: the shell is lit from above -- brighter than `shell` at the top edge, darker than it at the
        // handles' tips. The old flat fill is the average of these two, so nothing on the pad moved; the
        // plastic simply stopped being a paper cut-out.
        const Rgba shellTop = theme::mix(shell, theme::text, 0.13f);
        const Rgba shellBottom = theme::mix(shell, theme::ground, 0.30f);

        // ---- the silhouette ------------------------------------------------------------------------------
        // A shadow first: the same shape, offset down and out, so the pad sits ON the panel instead of in it.
        fillOutline(ctx, g, theme::alpha(theme::ground, on ? 130 : 60), theme::alpha(theme::ground, on ? 130 : 60),
                    1.5f, Vec2{0.0f, 5.0f});
        fillOutline(ctx, g, A(shellTop), A(shellBottom), 0.0f, Vec2{0.0f, 0.0f});
        strokePath(ctx, g.outline, g.outlineCount, A(edge), 2.5f, true);
        // A highlight just inside the top edge, so the shell has some depth.
        for (int i = 1; i < g.outlineCount; ++i)
        {
            const Vec2 a = g.outline[i - 1];
            const Vec2 b = g.outline[i];
            if (a.y < g.hull.y + g.height * 0.10f && b.y < g.hull.y + g.height * 0.10f)
                drawLine(ctx, Vec2{a.x, a.y + 3.5f}, Vec2{b.x, b.y + 3.5f}, A(theme::alpha(theme::panelHi, 200)), 2.0f);
        }
        // ... and a soft darkening along the bottom contour, the other half of the same lighting.
        for (int i = 1; i < g.outlineCount; ++i)
        {
            const Vec2 a = g.outline[i - 1];
            const Vec2 b = g.outline[i];
            if (a.y > g.hull.y + g.height * 0.62f && b.y > g.hull.y + g.height * 0.62f)
                drawLine(ctx, Vec2{a.x, a.y - 3.0f}, Vec2{b.x, b.y - 3.0f}, A(theme::alpha(theme::ground, 90)), 3.0f);
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

        // ---- the d-pad: ONE cross in a recessed well ------------------------------------------------------
        // W9: it was four pentagons that read as four separate buttons. A DualShock's d-pad is a single
        // rocker, so it is drawn as one -- an outlined cross plate, with the pressed arm lit inside it. The
        // hit geometry (g.dpad[i], and padAnchor's places for hosts 1-4) is untouched: this is the drawing
        // catching up with the shape the geometry already described.
        fillCircle(ctx, g.dpadWell, g.dpadWellRadius, A(recess));
        fillCircle(ctx, g.dpadWell, g.dpadWellRadius * 0.93f, A(theme::mix(recess, theme::ground, 0.40f)));
        strokeCircle(ctx, g.dpadWell, g.dpadWellRadius, A(edge), 1.5f);
        const Vec2 dirs[4] = {{0.0f, -1.0f}, {0.0f, 1.0f}, {-1.0f, 0.0f}, {1.0f, 0.0f}};
        {
            const float arm = g.dpadWellRadius * 0.90f;     // the tip: just inside the well's rim
            const float half = g.dpadWellRadius * 0.31f;    // half the rocker's width
            const float corner = half * 0.40f;   // not "round": <cmath> has one
            const Vec2 c = g.dpadWell;
            const Rect horiz{c.x - arm, c.y - half, arm * 2.0f, half * 2.0f};
            const Rect vert{c.x - half, c.y - arm, half * 2.0f, arm * 2.0f};
            // The outline is the same cross grown by the stroke, drawn underneath: two strokeRounds would
            // leave the seam of each bar showing where it crosses the other.
            fillRound(ctx, grown(horiz, 1.6f), corner + 1.6f, A(edge));
            fillRound(ctx, grown(vert, 1.6f), corner + 1.6f, A(edge));
            fillRound(ctx, horiz, corner, A(theme::mix(cap, theme::ground, 0.10f)));
            fillRound(ctx, vert, corner, A(theme::mix(cap, theme::ground, 0.10f)));
            // A lit top face on each bar, so the rocker is not a flat plus sign.
            fillRound(ctx, Rect{horiz.x, horiz.y, horiz.w, horiz.h * 0.46f}, corner, A(theme::alpha(theme::panelHi, 150)));
            fillRound(ctx, Rect{vert.x, vert.y, vert.w, vert.h * 0.26f}, corner, A(theme::alpha(theme::panelHi, 150)));
            for (int i = 0; i < 4; ++i)
            {
                const PadCircle &b = g.dpad[i];
                const bool down = on && pad.down[static_cast<int>(b.element)];
                if (down)
                {
                    // Only the arm that is pressed, from the rocker's centre out to its tip.
                    const Rect lit = dirs[i].y < 0.0f   ? Rect{c.x - half, c.y - arm, half * 2.0f, arm}
                                     : dirs[i].y > 0.0f ? Rect{c.x - half, c.y, half * 2.0f, arm}
                                     : dirs[i].x < 0.0f ? Rect{c.x - arm, c.y - half, arm, half * 2.0f}
                                                        : Rect{c.x, c.y - half, arm, half * 2.0f};
                    fillRound(ctx, lit, corner, A(theme::gold));
                }
                const Vec2 arrowAt{c.x + dirs[i].x * arm * 0.62f, c.y + dirs[i].y * arm * 0.62f};
                fillPoly(ctx, arrowAt, 3, half * 0.62f, angleOf(dirs[i]), A(down ? theme::ground : theme::text));
            }
        }

        // ---- the face buttons ----------------------------------------------------------------------------
        fillCircle(ctx, g.faceWell, g.faceWellRadius, A(recess));
        fillCircle(ctx, g.faceWell, g.faceWellRadius * 0.93f, A(theme::mix(recess, theme::ground, 0.40f)));
        strokeCircle(ctx, g.faceWell, g.faceWellRadius, A(edge), 1.5f);
        const GlyphFamily family = glyphFamilyFor(pad.name);
        for (int i = 0; i < 4; ++i)
        {
            const PadCircle &b = g.face[i];
            const bool down = on && pad.down[static_cast<int>(b.element)];
            // W9: a rim, a cap and a lit top -- a disc with a stroke around it read as a sticker.
            fillCircle(ctx, b.c, b.r + 1.2f, A(theme::mix(edge, theme::ground, 0.35f)));
            fillCircle(ctx, b.c, b.r, A(down ? theme::gold : cap));
            fillCircle(ctx, Vec2{b.c.x, b.c.y - b.r * 0.24f}, b.r * 0.55f,
                       A(theme::alpha(theme::panelHi, down ? 60 : 120)));
            strokeCircle(ctx, b.c, b.r, A(down ? theme::goldHi : edge), 1.2f);
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
            fillCircle(ctx, centre, g.wellRadius + 1.0f, A(theme::mix(edge, theme::ground, 0.45f)));
            fillCircle(ctx, centre, g.wellRadius, A(recess));
            // W9: a dish rather than a flat disc -- the well darkens towards its own centre.
            fillCircle(ctx, centre, g.wellRadius * 0.78f, A(theme::mix(recess, theme::ground, 0.35f)));
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
            fillCircle(ctx, at, capR + 1.4f, A(theme::mix(edge, theme::ground, 0.35f)));
            fillCircle(ctx, at, capR, A(down ? theme::gold : theme::mix(theme::panelHi, theme::text, 0.22f)));
            fillCircle(ctx, Vec2{at.x, at.y - capR * 0.22f}, capR * 0.58f, A(theme::alpha(theme::text, down ? 40 : 70)));
            strokeCircle(ctx, at, capR, A(down ? theme::goldHi : edge), 2.0f);
            strokeCircle(ctx, at, capR * 0.55f, A(theme::alpha(theme::ground, 160)), 1.2f);
        }

        // ---- the shoulders and the triggers --------------------------------------------------------------
        for (int i = 0; i < 2; ++i)
        {
            const Rect s = g.shoulder[i];
            const bool held = on && pad.shoulder[i];
            // W9: the bar is lit along its top like the shell above it, so it reads as a bumper sitting on
            // the pad's shoulder rather than a flat pill floating over it.
            fillRound(ctx, s, s.h * 0.45f, A(held ? theme::gold : shellBottom));
            if (!held)
                fillRound(ctx, Rect{s.x + 1.5f, s.y + 1.5f, s.w - 3.0f, s.h * 0.48f}, s.h * 0.30f,
                          A(theme::alpha(shellTop, 210)));
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

        // ---- Sprint 10 Goal 8: the callouts -- the game's button on the control that drives it now ---------
        if (on && callouts != nullptr)
        {
            for (const PadCallout &call : *callouts)
            {
                const PadAnchor a = padAnchor(g, call.host);
                if (!a.valid)
                    continue;
                if (call.highlight)
                    strokeCircle(ctx, a.c, a.r + 6.0f, theme::goldHi, 2.5f);
                if (call.focus)
                    strokeCircle(ctx, a.c, a.r + 4.0f, theme::blueHi, 2.5f);
                if (call.face < 0 && (call.text == nullptr || call.text[0] == '\0'))
                    continue;
                // A pill carrying the shape or the word: what the game reads from that control. Gold over
                // the control for a binding the player moved; teal BELOW it for the cell they are standing
                // on, so the control they are about to change stays visible under its own label (W9).
                const float size = 11.0f;
                const float w = call.face >= 0 ? 22.0f : textWidth(ctx, call.text, size, Face::Bold) + 12.0f;
                const Rect pill = call.focus ? Rect{a.c.x - w * 0.5f, a.c.y + a.r + 3.0f, w, 18.0f}
                                             : Rect{a.c.x - w * 0.5f, a.c.y - 9.0f, w, 18.0f};
                // blueFill, not blue: theme::text on theme::blue is 3.4:1 and this pill carries 11-unit
                // type. On blueFill it is 6.1:1, past the 4.5 the palette holds every text pair to.
                const Rgba back = call.focus ? theme::blueFill : theme::gold;
                fillRound(ctx, pill, 9.0f, back);
                strokeRound(ctx, pill, 9.0f, theme::ground, 1.0f);
                const Rgba ink = call.focus ? theme::text : theme::ground;
                if (call.face >= 0)
                    drawShapeGlyph(ctx, call.face, Vec2{pill.cx(), pill.cy()}, 12.0f, ink);
                else
                    textCenteredIn(ctx, call.text, pill, size, ink, Face::Bold);
            }
        }

        // ---- R139: where the crouch shortcut is ----------------------------------------------------------
        // Ringed and tagged on whichever host control the mapping binds to the shortcut's PS2 button (the plate
        // for the touchpad, which the DualShock 2 drawn here does not have).
        if (on && markHost != 0)
        {
            const PadAnchor a = padAnchor(g, markHost);
            if (a.valid)
            {
                const char *tag = "CROUCH";
                const float size = 13.0f;
                const float tagW = textWidth(ctx, tag, size, Face::Bold, 0.06f);
                Vec2 at;
                if (markHost == kPadAnchorTouchpad)
                {
                    const Rect r{g.plate.x - 4.0f, g.plate.y - 4.0f, g.plate.w + 8.0f, g.plate.h + 8.0f};
                    strokeRound(ctx, r, 8.0f, theme::goldHi, 2.0f);
                    at = Vec2{r.cx() - tagW * 0.5f, r.bottom() + 5.0f};
                }
                else if (markHost == 10 || markHost == 12 || markHost == 9 || markHost == 11)
                {
                    // A shoulder or a trigger: a box around it, the tag beside it, away from the centre line.
                    const Rect t = markHost == 10 ? g.trigger[0] : (markHost == 12 ? g.trigger[1] : (markHost == 9 ? g.shoulder[0] : g.shoulder[1]));
                    strokeRect(ctx, Rect{t.x - 4.0f, t.y - 4.0f, t.w + 8.0f, t.h + 8.0f}, theme::goldHi, 2.0f);
                    at = a.c.x < g.centre.x ? Vec2{t.x - tagW - 12.0f, t.cy() - size * 0.6f} : Vec2{t.right() + 12.0f, t.cy() - size * 0.6f};
                }
                else
                {
                    strokeCircle(ctx, a.c, a.r + 5.0f, theme::goldHi, 2.0f);
                    at = Vec2{a.c.x - tagW * 0.5f, a.c.y + a.r + 9.0f};
                }
                text(ctx, tag, at, size, theme::goldHi, Face::Bold, 0.06f);
            }
        }

        // ---- W9: the hold gesture, on the control it is building on --------------------------------------
        // A ring that CLOSES on the button as the hold fills, drawn last so nothing sits on top of it. The
        // words and the bar are the page's (page_controller.cpp); this is the half that answers "which
        // button?" without the player having to read anything.
        if (on && holdHost != 0)
        {
            const PadAnchor a = padAnchor(g, holdHost);
            if (a.valid)
            {
                const float t = clamp01(holdProgress);
                strokeCircle(ctx, a.c, a.r + 3.0f, theme::alpha(theme::gold, 130), 1.5f);
                strokeCircle(ctx, a.c, a.r + 16.0f - 12.0f * t, theme::goldHi, 2.0f + 2.5f * t);
            }
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
