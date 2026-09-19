#pragma once
// Sprint 8 Goal 9: the drawn controller. The geometry is pure (no raylib) so the tests can assert that every
// hit circle really sits on the body and that a stick's drawn offset is the axis the game will read; the
// drawing itself is pad_render.cpp.
#include "theme.h"

#include <cmath>
#include <string>

namespace ui
{
    // Every element the pad drawing lights up. The order is the drawing's, not raylib's.
    enum class PadElement
    {
        DpadUp = 0,
        DpadDown,
        DpadLeft,
        DpadRight,
        FaceUp,      // triangle / Y
        FaceDown,    // cross / A
        FaceLeft,    // square / X
        FaceRight,   // circle / B
        Select,
        Start,
        LeftStickClick,
        RightStickClick,
        Count
    };

    struct PadCircle
    {
        PadElement element = PadElement::DpadUp;
        Vec2 c;
        float r = 0.0f;
    };

    // Sprint 8 Goal 9, second pass: a DualShock 2 seen from the front. The silhouette is a union -- a central
    // body, the two round wings the d-pad and the face cluster sit in, and two handles below -- and every
    // element's place and hit circle comes from here, so the drawing and the tests cannot drift apart.
    struct PadGeometry
    {
        Rect bounds;          // what was asked for
        Rect header;          // the strip above the pad: the shoulders and the triggers live here
        Rect body;            // the central slab, between the two wings
        Rect hull;            // body + wings: what every drawn input has to sit inside
        Rect plate;           // the lighter centre plate carrying SELECT, START and the ANALOG dot
        float cornerRadius = 0.0f;

        Vec2 wing[2];         // the two round wings' centres (left: d-pad, right: face buttons)
        float wingRadius = 0.0f;

        Vec2 handle[2];       // where each handle's axis starts (at the body) ...
        Vec2 handleTip[2];    // ... and where it ends
        float handleRadius = 0.0f;   // at the body end; the tip is 0.72 of it

        Vec2 dpadWell;        // the recessed disc the four segments sit in
        float dpadWellRadius = 0.0f;
        Vec2 faceWell;
        float faceWellRadius = 0.0f;

        PadCircle dpad[4];    // up, down, left, right
        PadCircle face[4];    // up, down, left, right (triangle, cross, square, circle)
        PadCircle center[2];  // select, start
        PadCircle stickClick[2];
        Vec2 well[2];         // the two stick wells' centres
        float wellRadius = 0.0f;
        Rect shoulder[2];     // L1, R1
        Rect trigger[2];      // L2, R2 (drawn as trapezoids inside these bounds)
    };

    // The dead zone drawn inside a stick's well: the fraction of the well the game reads as nothing at all.
    inline float deadZoneRingRadius(float deadZone, float wellRadius) { return deadZone * wellRadius; }

    // The whole pad inside `bounds`: the shoulder strip on top, then the silhouette -- a body between two
    // round wings, with two handles splaying down and out. Every input's place and hit circle comes from here.
    // Inline so the tests need no raylib to assert on it.
    inline PadGeometry padGeometry(Rect bounds)
    {
        PadGeometry g;
        g.bounds = bounds;
        const float w = bounds.w;
        const float h = bounds.h;

        const float R = w * 0.155f;              // a wing, and the unit the whole pad is built from
        const float padTop = bounds.y + h * 0.225f;
        const float wingCy = padTop + R;
        g.wingRadius = R;
        g.wing[0] = Vec2{bounds.x + w * 0.19f, wingCy};
        g.wing[1] = Vec2{bounds.x + w * 0.81f, wingCy};

        const float bodyBottom = wingCy + R * 1.05f;
        g.body = Rect{g.wing[0].x, padTop, g.wing[1].x - g.wing[0].x, bodyBottom - padTop};
        g.hull = Rect{g.wing[0].x - R, padTop, (g.wing[1].x + R) - (g.wing[0].x - R), bodyBottom - padTop};
        g.cornerRadius = R * 0.45f;

        // The handles: an axis from under each wing, 12 degrees outwards, tapering to the tip.
        const float lean = 0.2079f;   // sin(12 degrees)
        const float drop = 0.9781f;   // cos(12 degrees)
        const float length = R * 0.72f;
        g.handleRadius = R * 0.45f;
        for (int i = 0; i < 2; ++i)
        {
            const float sign = i == 0 ? -1.0f : 1.0f;
            g.handle[i] = Vec2{g.wing[i].x + sign * R * 0.15f, wingCy + R * 0.48f};
            g.handleTip[i] = Vec2{g.handle[i].x + sign * length * lean, g.handle[i].y + length * drop};
        }

        // The centre plate: SELECT, START and the ANALOG dot, clear of the sticks below it.
        g.plate = Rect{g.hull.cx() - w * 0.15f, wingCy - R * 0.15f, w * 0.30f, R * 0.40f};
        const float centerR = R * 0.075f;
        g.center[0] = PadCircle{PadElement::Select, Vec2{g.plate.x + g.plate.w * 0.22f, g.plate.cy()}, centerR};
        g.center[1] = PadCircle{PadElement::Start, Vec2{g.plate.x + g.plate.w * 0.78f, g.plate.cy()}, centerR};

        // The two wells, one in each wing.
        g.dpadWell = g.wing[0];
        g.dpadWellRadius = R * 0.60f;
        g.faceWell = g.wing[1];
        g.faceWellRadius = R * 0.60f;

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

        // The sticks: inboard of the wells and below them, a mirrored pair about the pad's centre line.
        g.wellRadius = R * 0.40f;
        const float stickY = wingCy + R * 0.62f;
        g.well[0] = Vec2{g.hull.cx() - w * 0.115f, stickY};
        g.well[1] = Vec2{g.hull.cx() + w * 0.115f, stickY};
        g.stickClick[0] = PadCircle{PadElement::LeftStickClick, g.well[0], g.wellRadius * 0.48f};
        g.stickClick[1] = PadCircle{PadElement::RightStickClick, g.well[1], g.wellRadius * 0.48f};

        // The shoulders hug each wing's top contour; the triggers sit above them.
        const float headerH = h * 0.21f;
        g.header = Rect{g.hull.x + 4.0f, bounds.y, g.hull.w - 8.0f, headerH};
        const float groupW = R * 1.45f;
        for (int i = 0; i < 2; ++i)
        {
            g.shoulder[i] = Rect{g.wing[i].x - groupW * 0.5f, g.header.y + headerH * 0.54f, groupW, headerH * 0.40f};
            g.trigger[i] = Rect{g.wing[i].x - groupW * 0.44f, g.header.y + headerH * 0.06f, groupW * 0.88f, headerH * 0.42f};
        }
        return g;
    }

    // Where a stick's dot is drawn, given the raw axes and the dead zone the player set: nothing at all inside
    // the dead zone, and outside it the axis rescaled over the remaining travel, times the well's radius and
    // never past it. Kept in step with hostPadAxis (ps2xRuntime/include/runtime/host_gamepad_select.h): a dot
    // resting in the middle of the well is exactly the neutral the game will see.
    inline Vec2 stickOffset(Vec2 axis, float deadZone, float wellRadius)
    {
        const float mag = std::sqrt(axis.x * axis.x + axis.y * axis.y);
        if (mag <= 0.0f)
            return Vec2{0.0f, 0.0f};
        float scaled = mag;
        if (deadZone > 0.0f)
        {
            if (mag <= deadZone)
                return Vec2{0.0f, 0.0f};
            scaled = (mag - deadZone) / (1.0f - deadZone);
        }
        if (scaled > 1.0f)
            scaled = 1.0f;
        const float k = scaled * wellRadius / mag;
        return Vec2{axis.x * k, axis.y * k};
    }

    // One frame of a pad, real or faked for the screenshots: what the drawing lights up.
    struct PadSnapshot
    {
        bool present = false;
        std::string name;
        bool down[static_cast<int>(PadElement::Count)] = {};
        bool shoulder[2] = {false, false};   // L1, R1
        float trigger[2] = {0.0f, 0.0f};     // L2, R2 as analog fills
        Vec2 leftStick, rightStick;          // the raw axes, before the dead zone
    };

    struct Ctx;   // widgets.h -- the drawing half only
    void drawPad(const Ctx &ctx, Rect bounds, const PadSnapshot &pad, float deadZone);
}
