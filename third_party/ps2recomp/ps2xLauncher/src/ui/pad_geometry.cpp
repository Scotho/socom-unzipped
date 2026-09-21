// Sprint 8 Goal 9, third pass: where every part of the drawn controller is. Pure -- no raylib.
//
// The silhouette is authored once, as the RIGHT HALF of a DualShock 2 seen from the front: seven cubic
// Beziers in a normalised box (x 0 at the centre line to 1 at the right extreme, y 0 at the top to 1 at the
// handle's tip). The left half is that path mirrored, so the shape is symmetric by construction rather than
// by luck. Flattened here; pad_render.cpp fills and strokes exactly these points.
#include "pad_render.h"

#include <cmath>

namespace ui
{
    namespace
    {
        struct Cubic
        {
            float c1x, c1y, c2x, c2y, ex, ey;   // two controls and the end point; the start is the previous end
        };

        // The right half, clockwise from the centre of the top edge down to the centre of the bottom edge.
        //   1 the top edge, rising slightly from the centre to the shoulder hump
        //   2 the rounded outer shoulder
        //   3 the long outer handle edge, sweeping down and inward
        //   4 the rounded tip
        //   5 the inner handle edge, with the curve back up into the body
        //   6 into the bottom of the body
        //   7 the body's bottom edge, back to the centre line
        constexpr float kStartX = 0.000f;
        constexpr float kStartY = 0.075f;
        constexpr Cubic kRightHalf[] = {
            {0.180f, 0.052f, 0.380f, 0.014f, 0.580f, 0.008f},
            {0.820f, 0.004f, 1.000f, 0.085f, 1.000f, 0.255f},
            {1.000f, 0.500f, 0.950f, 0.720f, 0.855f, 0.885f},
            {0.800f, 0.975f, 0.705f, 1.000f, 0.625f, 0.965f},
            {0.545f, 0.925f, 0.495f, 0.845f, 0.465f, 0.755f},
            {0.440f, 0.700f, 0.360f, 0.685f, 0.265f, 0.700f},
            {0.190f, 0.712f, 0.090f, 0.718f, 0.000f, 0.720f},
        };
        constexpr int kSegments = static_cast<int>(sizeof(kRightHalf) / sizeof(kRightHalf[0]));
        constexpr int kFlatten = 26;   // points per segment: the curve has to read as a curve at 2x scale

        Vec2 bezier(Vec2 p0, Vec2 c1, Vec2 c2, Vec2 p1, float t)
        {
            const float u = 1.0f - t;
            const float a = u * u * u;
            const float b = 3.0f * u * u * t;
            const float c = 3.0f * u * t * t;
            const float d = t * t * t;
            return Vec2{a * p0.x + b * c1.x + c * c2.x + d * p1.x,
                        a * p0.y + b * c1.y + c * c2.y + d * p1.y};
        }
    }

    PadGeometry padGeometry(Rect bounds)
    {
        PadGeometry g;
        g.bounds = bounds;

        // The shoulders and triggers take the top strip; the silhouette fills what is left, at the
        // DualShock's own 1.55:1.
        const float headerH = bounds.h * 0.155f;
        const float room = bounds.h - headerH;
        float w = bounds.w;
        float h = w / 1.55f;
        if (h > room)
        {
            h = room;
            w = h * 1.55f;
        }
        g.width = w;
        g.height = h;
        const float halfW = w * 0.5f;
        const float cx = bounds.cx();
        const float top = bounds.y + headerH;   // the shoulders sit ON the top contour, not above a gap
        g.centre = Vec2{cx, top};
        g.hull = Rect{cx - halfW, top, w, h};
        g.header = Rect{cx - halfW * 0.92f, bounds.y, w * 0.92f, headerH};

        // ---- the outline: the right half, then its mirror ------------------------------------------------
        auto place = [&](float nx, float ny) { return Vec2{cx + halfW * nx, top + h * ny}; };
        Vec2 right[kSegments * kFlatten + 1];
        int count = 0;
        Vec2 cursor = place(kStartX, kStartY);
        right[count++] = cursor;
        for (int s = 0; s < kSegments; ++s)
        {
            const Cubic &c = kRightHalf[s];
            const Vec2 c1 = place(c.c1x, c.c1y);
            const Vec2 c2 = place(c.c2x, c.c2y);
            const Vec2 end = place(c.ex, c.ey);
            for (int i = 1; i <= kFlatten; ++i)
                right[count++] = bezier(cursor, c1, c2, end, static_cast<float>(i) / static_cast<float>(kFlatten));
            cursor = end;
        }
        g.outlineCount = 0;
        for (int i = 0; i < count; ++i)
            g.outline[g.outlineCount++] = right[i];
        // The mirror, walked back up, without repeating either point on the centre line.
        for (int i = count - 2; i >= 1; --i)
            g.outline[g.outlineCount++] = Vec2{2.0f * cx - right[i].x, right[i].y};

        // ---- what sits on it ------------------------------------------------------------------------------
        // The two wells ride the shoulder humps; the sticks sit inboard and lower, as on the pad itself.
        g.dpadWellRadius = w * 0.105f;
        g.faceWellRadius = w * 0.105f;
        g.dpadWell = Vec2{cx - w * 0.23f, top + h * 0.38f};
        g.faceWell = Vec2{cx + w * 0.23f, top + h * 0.38f};

        const Vec2 dirs[4] = {{0.0f, -1.0f}, {0.0f, 1.0f}, {-1.0f, 0.0f}, {1.0f, 0.0f}};   // up, down, left, right
        const PadElement dpadIds[4] = {PadElement::DpadUp, PadElement::DpadDown, PadElement::DpadLeft, PadElement::DpadRight};
        const PadElement faceIds[4] = {PadElement::FaceUp, PadElement::FaceDown, PadElement::FaceLeft, PadElement::FaceRight};
        const float dpadReach = g.dpadWellRadius * 0.52f;
        const float dpadR = g.dpadWellRadius * 0.26f;
        const float faceReach = g.faceWellRadius * 0.55f;
        const float faceR = g.faceWellRadius * 0.30f;
        for (int i = 0; i < 4; ++i)
        {
            g.dpad[i] = PadCircle{dpadIds[i], Vec2{g.dpadWell.x + dirs[i].x * dpadReach, g.dpadWell.y + dirs[i].y * dpadReach}, dpadR};
            g.face[i] = PadCircle{faceIds[i], Vec2{g.faceWell.x + dirs[i].x * faceReach, g.faceWell.y + dirs[i].y * faceReach}, faceR};
        }

        g.wellRadius = w * 0.072f;
        const float stickY = top + h * 0.575f;
        g.well[0] = Vec2{cx - w * 0.12f, stickY};
        g.well[1] = Vec2{cx + w * 0.12f, stickY};
        g.stickClick[0] = PadCircle{PadElement::LeftStickClick, g.well[0], g.wellRadius * 0.48f};
        g.stickClick[1] = PadCircle{PadElement::RightStickClick, g.well[1], g.wellRadius * 0.48f};

        g.plate = Rect{cx - w * 0.115f, top + h * 0.300f, w * 0.230f, h * 0.115f};
        const float centerR = w * 0.016f;
        g.center[0] = PadCircle{PadElement::Select, Vec2{g.plate.x + g.plate.w * 0.20f, g.plate.cy()}, centerR};
        g.center[1] = PadCircle{PadElement::Start, Vec2{g.plate.right() - g.plate.w * 0.20f, g.plate.cy()}, centerR};

        // The shoulders follow the top contour: each bar sits over its own well, the trigger above it.
        const float groupW = w * 0.235f;
        for (int i = 0; i < 2; ++i)
        {
            const float centreX = i == 0 ? g.dpadWell.x : g.faceWell.x;
            g.shoulder[i] = Rect{centreX - groupW * 0.5f, g.header.y + headerH * 0.54f, groupW, headerH * 0.40f};
            g.trigger[i] = Rect{centreX - groupW * 0.44f, g.header.y + headerH * 0.05f, groupW * 0.88f, headerH * 0.43f};
        }
        return g;
    }

    PadAnchor padAnchor(const PadGeometry &g, int host)
    {
        // launcher/mapping.h's numbering, written out so this file stays free of it: 1-4 the d-pad (up, right,
        // down, left), 5-8 the face buttons (up, right, down, left), 9 L1, 10 L2, 11 R1, 12 R2, 13 select, 14 the
        // guide button, 15 start, 16-17 the stick clicks.
        auto circle = [](const PadCircle &c) { return PadAnchor{c.c, c.r, true}; };
        auto rect = [](const Rect &r) { return PadAnchor{Vec2{r.cx(), r.cy()}, r.h * 0.5f, true}; };
        switch (host)
        {
        case 1: return circle(g.dpad[0]);
        case 2: return circle(g.dpad[3]);
        case 3: return circle(g.dpad[1]);
        case 4: return circle(g.dpad[2]);
        case 5: return circle(g.face[0]);
        case 6: return circle(g.face[3]);
        case 7: return circle(g.face[1]);
        case 8: return circle(g.face[2]);
        case 9: return rect(g.shoulder[0]);
        case 10: return rect(g.trigger[0]);
        case 11: return rect(g.shoulder[1]);
        case 12: return rect(g.trigger[1]);
        case 13: return circle(g.center[0]);
        case 14: return PadAnchor{Vec2{g.plate.cx(), g.plate.cy()}, g.width * 0.016f, true};
        case 15: return circle(g.center[1]);
        case 16: return PadAnchor{g.well[0], g.wellRadius, true};
        case 17: return PadAnchor{g.well[1], g.wellRadius, true};
        case kPadAnchorTouchpad: return PadAnchor{Vec2{g.plate.cx(), g.plate.cy()}, g.plate.h * 0.5f, true};
        default: return PadAnchor{};
        }
    }

    bool padContains(const PadGeometry &g, Vec2 p)
    {
        bool inside = false;
        for (int i = 0, j = g.outlineCount - 1; i < g.outlineCount; j = i++)
        {
            const Vec2 a = g.outline[i];
            const Vec2 b = g.outline[j];
            if ((a.y > p.y) != (b.y > p.y))
            {
                const float x = (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x;
                if (p.x < x)
                    inside = !inside;
            }
        }
        return inside;
    }
}
