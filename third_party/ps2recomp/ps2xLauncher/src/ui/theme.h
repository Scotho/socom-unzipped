#pragma once
// Sprint 8 Goal 9: the launcher's palette, its metrics and the one scale factor everything is drawn through.
//
// PURE ON PURPOSE: no raylib here. The tests compile this header (ui::scaleFor, ui::Rect), and the drawing
// code turns ui::Rgba into raylib's Color at the call site (widgets.h's `rl()`).
#include <cstdint>

namespace ui
{
    struct Rgba
    {
        unsigned char r, g, b, a;
    };

    struct Vec2
    {
        float x = 0.0f, y = 0.0f;
    };

    struct Rect
    {
        float x = 0.0f, y = 0.0f, w = 0.0f, h = 0.0f;
        float cx() const { return x + w * 0.5f; }
        float cy() const { return y + h * 0.5f; }
        float right() const { return x + w; }
        float bottom() const { return y + h; }
        bool contains(Vec2 p) const { return p.x >= x && p.x <= x + w && p.y >= y && p.y <= y + h; }
        bool inside(const Rect &o) const
        {
            return x >= o.x - 0.001f && y >= o.y - 0.001f && x + w <= o.x + o.w + 0.001f && y + h <= o.y + o.h + 0.001f;
        }
    };

    // The design's palette, the spec's hex values, in one place (Goal 9, "Theme").
    namespace theme
    {
        constexpr Rgba ground = {0x0B, 0x14, 0x16, 0xFF};
        constexpr Rgba panel = {0x12, 0x26, 0x2A, 0xFF};
        constexpr Rgba panelHi = {0x1B, 0x3A, 0x40, 0xFF};
        constexpr Rgba line = {0x2C, 0x51, 0x58, 0xFF};
        constexpr Rgba text = {0xC9, 0xD6, 0xD2, 0xFF};
        constexpr Rgba dim = {0x7D, 0x91, 0x8D, 0xFF};
        constexpr Rgba gold = {0xC9, 0xA2, 0x4A, 0xFF};
        constexpr Rgba goldHi = {0xE8, 0xC7, 0x6A, 0xFF};
        constexpr Rgba lampGreen = {0x3B, 0xE0, 0x6A, 0xFF};
        constexpr Rgba warn = {0xE0, 0xA0, 0x30, 0xFF};
        constexpr Rgba bad = {0xD0, 0x50, 0x3A, 0xFF};

        inline constexpr Rgba alpha(Rgba c, unsigned char a) { return {c.r, c.g, c.b, a}; }
        inline constexpr Rgba mix(Rgba a, Rgba b, float t)
        {
            return {static_cast<unsigned char>(a.r + (b.r - a.r) * t),
                    static_cast<unsigned char>(a.g + (b.g - a.g) * t),
                    static_cast<unsigned char>(a.b + (b.b - a.b) * t),
                    static_cast<unsigned char>(a.a + (b.a - a.a) * t)};
        }
    }

    // The design is laid out in these units and multiplied by scaleFor(); 1100x700 is 1:1.
    namespace metrics
    {
        constexpr float designW = 1100.0f;
        constexpr float designH = 700.0f;
        constexpr float minW = 800.0f;
        constexpr float minH = 520.0f;

        constexpr float headerH = 76.0f;
        constexpr float barH = 56.0f;
        constexpr float railW = 220.0f;
        constexpr float railRowH = 42.0f;
        constexpr float railGap = 6.0f;
        constexpr float margin = 28.0f;
        constexpr float gap = 20.0f;
        constexpr float rowH = 52.0f;
        constexpr float rowGap = 12.0f;
        constexpr float labelW = 156.0f;
        constexpr float gridStep = 32.0f;   // the faint ground grid
    }

    // One factor for the whole window: the smaller of the two axes' ratios against the 1100x700 design, never
    // below the factor the 800x520 minimum window itself gets (so a window clamped at the minimum and a window
    // asked to be smaller than the minimum draw the same thing, not a squashed one).
    inline float scaleFor(int w, int h)
    {
        const float sx = static_cast<float>(w) / metrics::designW;
        const float sy = static_cast<float>(h) / metrics::designH;
        float s = sx < sy ? sx : sy;
        const float fx = metrics::minW / metrics::designW;
        const float fy = metrics::minH / metrics::designH;
        const float floorFactor = fx < fy ? fx : fy;
        return s < floorFactor ? floorFactor : s;
    }
}
