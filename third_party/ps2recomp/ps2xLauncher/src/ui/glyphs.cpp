// Sprint 8 Goal 9: the prompt glyphs, drawn rather than typed -- the embedded faces carry ASCII only, and a
// square-box "missing glyph" in the bottom bar would be worse than no prompt at all.
#include "glyphs.h"

#include "widgets.h"

#include <algorithm>

namespace ui
{
    void drawShapeGlyph(const Ctx &ctx, int index, Vec2 centre, float size, Rgba color)
    {
        const float r = size * 0.5f;
        switch (index & 3)
        {
        case 0:   // triangle
        {
            const Vec2 a{centre.x, centre.y - r};
            const Vec2 b{centre.x - r * 0.92f, centre.y + r * 0.72f};
            const Vec2 c{centre.x + r * 0.92f, centre.y + r * 0.72f};
            drawLine(ctx, a, b, color, 2.0f);
            drawLine(ctx, b, c, color, 2.0f);
            drawLine(ctx, c, a, color, 2.0f);
            break;
        }
        case 1:   // cross
        {
            const float d = r * 0.72f;
            drawLine(ctx, Vec2{centre.x - d, centre.y - d}, Vec2{centre.x + d, centre.y + d}, color, 2.0f);
            drawLine(ctx, Vec2{centre.x - d, centre.y + d}, Vec2{centre.x + d, centre.y - d}, color, 2.0f);
            break;
        }
        case 2:   // square
        {
            const float d = r * 0.74f;
            strokeRect(ctx, Rect{centre.x - d, centre.y - d, d * 2.0f, d * 2.0f}, color, 2.0f);
            break;
        }
        default:   // circle
            strokeCircle(ctx, centre, r * 0.82f, color, 2.0f);
            break;
        }
    }

    float drawKeyCap(const Ctx &ctx, Vec2 topLeft, const char *label, float height, Rgba color)
    {
        const float size = height * 0.62f;
        const float w = std::max(height, textWidth(ctx, label, size, Face::Bold) + height * 0.6f);
        const Rect r{topLeft.x, topLeft.y, w, height};
        fillRect(ctx, r, theme::mix(theme::panel, theme::ground, 0.25f));
        strokeRect(ctx, r, theme::line, 2.0f);
        textCenteredIn(ctx, label, r, size, color, Face::Bold);
        return w;
    }

    float drawPadPrompt(const Ctx &ctx, Vec2 topLeft, GlyphFamily family, int index, float height, Rgba color)
    {
        const Vec2 centre{topLeft.x + height * 0.5f, topLeft.y + height * 0.5f};
        strokeCircle(ctx, centre, height * 0.5f, theme::line, 2.0f);
        if (family == GlyphFamily::PlayStation)
            drawShapeGlyph(ctx, index, centre, height * 0.62f, color);
        else
            textCenteredIn(ctx, faceLetter(family, index), Rect{topLeft.x, topLeft.y, height, height}, height * 0.62f, color, Face::Bold);
        return height;
    }
}
