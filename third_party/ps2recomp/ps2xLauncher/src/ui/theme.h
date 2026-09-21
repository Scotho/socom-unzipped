#pragma once
// Sprint 8 Goal 9: the launcher's palette, its metrics and the one scale factor everything is drawn through.
//
// The palette is sampled from the project's own logo (owner request, Sprint 10: "something along the lines of
// #0E8697 or a bit darker ... the gold is good"): the letters' teal gradient, the orange-gold outline around
// them, the trident's gold, and the black it all sits on. Nothing from the disc ships here -- these are
// measured colours, not artwork. The logo itself is drawn at the head of the rail (logo_embedded/).
//
//   sampled      #FA9600 / #E8AB2D  the logo's orange outline      -> gold / goldHi
//                #FFC010 / #F6C656  the trident's gold highlight
//                #088090 / #088898  the letters' teal (measured on the s2u logo; the owner's #0E8697)
//                                                                  -> blue / blueHi, and the panels' cast
//                #085060 / #084858  the letters' deep teal bottom  -> blueFill / blueDeep
//                #3D4241 / #656C6E  the U.S. NAVY SEALS banner     -> the steel of the lines
//                #010101 / #120300  the two grounds
//
// Sprint 8 Goal 9's palette was the retail logo's electric blue (#008DCD / #012334); Sprint 10 moved the
// whole blue family to the teal above and gave the greys a matching cast, gold untouched. The names stayed
// ("blue") because forty call sites carry them and a rename is not a colour change.
//
// PURE ON PURPOSE: no raylib here. The tests compile this header (ui::scaleFor, ui::contrastRatio, ui::Rect),
// and the drawing code turns ui::Rgba into raylib's Color at the call site (widgets.h's `rl()`).
#include <cmath>
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

    // A rect anything may place ink in. `rectOf` answers a default Rect -- the origin, zero by zero -- for an
    // id the node list does not hold, and a label centred in exactly that is the one-frame flash at the top
    // left the owner reported on 2026-09-20 (Sprint 9 P4). Every primitive and control in widgets.cpp refuses
    // a rect this returns false for, so an unknown id cannot mark the window whatever the caller does.
    inline bool drawable(Rect r) { return r.w > 0.0f && r.h > 0.0f; }

    // The design's palette (Goal 9, third pass: "a slightly bolder theme, from the logo's own colours").
    namespace theme
    {
        constexpr Rgba ground = {0x06, 0x0E, 0x11, 0xFF};    // near-black with a teal cast
        constexpr Rgba panel = {0x0A, 0x1E, 0x24, 0xFF};     // deep teal-navy
        constexpr Rgba panelHi = {0x11, 0x37, 0x40, 0xFF};   // raised / hovered
        constexpr Rgba line = {0x1B, 0x5A, 0x64, 0xFF};      // mid teal

        constexpr Rgba text = {0xDD, 0xE8, 0xEA, 0xFF};      // cool off-white
        constexpr Rgba caption = {0xA8, 0xC5, 0xCA, 0xFF};   // help text: legible on every panel
        constexpr Rgba dim = {0x8D, 0xAE, 0xB3, 0xFF};       // secondary text (never on panelHi)

        constexpr Rgba gold = {0xF2, 0xA2, 0x1E, 0xFF};      // THE accent: selection, focus, the wordmark
        constexpr Rgba goldHi = {0xFF, 0xB9, 0x38, 0xFF};
        constexpr Rgba blue = {0x0E, 0x86, 0x97, 0xFF};      // the logo's letter teal (the owner's own number): markers
        constexpr Rgba blueFill = {0x0A, 0x5C, 0x68, 0xFF};  // the same teal, dark enough to carry text
        constexpr Rgba blueHi = {0x2F, 0xB3, 0xC4, 0xFF};
        constexpr Rgba blueDeep = {0x05, 0x30, 0x38, 0xFF};  // the bottom of the letters' gradient

        constexpr Rgba lampGreen = {0x3B, 0xE0, 0x6A, 0xFF};
        constexpr Rgba warn = gold;
        constexpr Rgba bad = {0xD8, 0x4A, 0x32, 0xFF};
        constexpr Rgba badInk = {0xFF, 0x8A, 0x70, 0xFF};    // the same error, as text on a panel

        inline constexpr Rgba alpha(Rgba c, unsigned char a) { return {c.r, c.g, c.b, a}; }
        inline constexpr Rgba mix(Rgba a, Rgba b, float t)
        {
            return {static_cast<unsigned char>(a.r + (b.r - a.r) * t),
                    static_cast<unsigned char>(a.g + (b.g - a.g) * t),
                    static_cast<unsigned char>(a.b + (b.b - a.b) * t),
                    static_cast<unsigned char>(a.a + (b.a - a.a) * t)};
        }
    }

    // WCAG relative luminance and the contrast ratio between two opaque colours. Pure; the tests hold every
    // text-on-background pair in the theme to 4.5:1, because the owner reads this window on a bright desk.
    inline float relativeLuminance(Rgba c)
    {
        auto channel = [](unsigned char v)
        {
            const float s = static_cast<float>(v) / 255.0f;
            return s <= 0.03928f ? s / 12.92f : std::pow((s + 0.055f) / 1.055f, 2.4f);
        };
        return 0.2126f * channel(c.r) + 0.7152f * channel(c.g) + 0.0722f * channel(c.b);
    }

    inline float contrastRatio(Rgba a, Rgba b)
    {
        const float la = relativeLuminance(a);
        const float lb = relativeLuminance(b);
        const float hi = la > lb ? la : lb;
        const float lo = la > lb ? lb : la;
        return (hi + 0.05f) / (lo + 0.05f);
    }

    // The design is laid out in these units and multiplied by scaleFor(); 1100x700 is 1:1.
    namespace metrics
    {
        constexpr float designW = 1100.0f;
        constexpr float designH = 700.0f;
        constexpr float minW = 800.0f;
        constexpr float minH = 520.0f;

        constexpr float barH = 38.0f;        // the custom top bar (there is no OS title bar above it)
        // The content panel's title strip. Two lines of caption-size help must fit in it beside the page's
        // name (Sprint 10: the help lives here, never over the page), under the 54 the body starts at.
        constexpr float bandH = 48.0f;
        constexpr float bodyTop = 66.0f;     // where a page's body starts under the panel's top: bandH + the rule + 16
        constexpr float bottomH = 56.0f;
        constexpr float railW = 220.0f;
        constexpr float railTop = 124.0f;    // the logo's block at the top of the rail (204 x 108 inside it)
        constexpr float railRowH = 42.0f;
        constexpr float railGap = 6.0f;
        constexpr float margin = 28.0f;
        constexpr float gap = 20.0f;
        constexpr float rowH = 52.0f;
        constexpr float rowGap = 12.0f;
        constexpr float labelW = 156.0f;
        constexpr float gridStep = 32.0f;    // the faint ground grid

        // Type: nothing is ever rasterised or drawn below this many real pixels. When the window is too small
        // for the design size to clear it, the type stops shrinking and the layout gives.
        constexpr int minTextPx = 13;
        constexpr float bodySize = 19.0f;    // >= 15 px at scale 1
        constexpr float captionSize = 16.0f;
        constexpr float labelSize = 16.0f;
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

    // How many segments a circle of this many real pixels needs before its edge stops looking faceted.
    // (The owner: "the circle at the top right is jagged at odd resolutions".)
    inline int circleSegments(float radiusPx)
    {
        const int wanted = static_cast<int>(radiusPx * 2.0f);
        if (wanted < 24)
            return 24;
        return wanted > 180 ? 180 : wanted;
    }
}
