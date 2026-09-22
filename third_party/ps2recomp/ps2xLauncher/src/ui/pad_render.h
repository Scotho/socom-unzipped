#pragma once
// Sprint 8 Goal 9: the drawn controller. The geometry is pure (no raylib) so the tests can assert that every
// hit circle really sits on the pad's outline and that a stick's drawn offset is the axis the game will read;
// the drawing itself is pad_render.cpp.
//
// Third pass (the owner: "the controller shape is also a bit janky"): the silhouette is no longer assembled
// from circles and capsules. It is ONE authored closed path -- the right half of a DualShock 2 front view as
// seven cubic Beziers, mirrored about the centre line -- flattened here into `outline`.
#include "theme.h"

#include <cmath>
#include <string>
#include <vector>

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

    struct PadGeometry
    {
        Rect bounds;          // what was asked for
        Rect header;          // the strip above the pad: the shoulders and the triggers live here
        Rect hull;            // the outline's bounding box
        Rect plate;           // the lighter centre plate carrying SELECT, START and the ANALOG light
        float width = 0.0f;   // the silhouette's width; its height is width / 1.55
        float height = 0.0f;
        Vec2 centre;          // the centre line's x, the body's y

        // The flattened silhouette, closed, symmetric about the centre line, counted in `outlineCount`.
        static constexpr int kOutlineMax = 420;
        Vec2 outline[kOutlineMax];
        int outlineCount = 0;

        Vec2 dpadWell;
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

    // The whole pad inside `bounds`. Pure: pad_geometry.cpp.
    PadGeometry padGeometry(Rect bounds);
    // Is that point inside the silhouette? (Even-odd, on the flattened outline.) The tests hold every
    // interactive element to it; the drawing fills the shape with the same spans.
    bool padContains(const PadGeometry &g, Vec2 point);

    // The dead zone drawn inside a stick's well: the fraction of the well the game reads as nothing at all.
    inline float deadZoneRingRadius(float deadZone, float wellRadius) { return deadZone * wellRadius; }

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

    // Sprint 10 Goal 8: where a host button sits on the drawing -- a centre and a radius -- so the callouts (the
    // game's button drawn on the control that now drives it) and R139's CROUCH mark hang off one table. `host`
    // is launcher/mapping.h's HostButton (raylib's GamepadButton numbering); kPadAnchorTouchpad is the centre
    // plate, where a DualShock 4's touchpad is (the DualShock 2 drawn here has none). Pure: pad_geometry.cpp.
    struct PadAnchor
    {
        Vec2 c;
        float r = 0.0f;
        bool valid = false;
    };
    constexpr int kPadAnchorTouchpad = -1;
    PadAnchor padAnchor(const PadGeometry &g, int host);

    // One callout: the game's button (a shape index as drawShapeGlyph's, or a word) on host button `host`;
    // `highlight` rings it -- the binding just made.
    //
    // W9 (2026-09-22), the owner's "clearer indication of which button is bound to what": `focus` is the
    // cell the player is standing on in the BUTTONS list. It is drawn as a teal ring with its label pill
    // BELOW the control rather than over it, so walking the sixteen cells lights each control up on the
    // drawing and the control itself stays visible under the label.
    struct PadCallout
    {
        int host;
        int face;
        const char *text;
        bool highlight;
        bool focus = false;
    };

    struct Ctx;   // widgets.h -- the drawing half only
    // `markHost`: R139's crouch shortcut, ringed and tagged CROUCH on its control whether or not it is held (0 for
    // none; kPadAnchorTouchpad for the plate). `callouts`: the mapping's differences from the default, drawn on
    // the pad (null or empty for none).
    // W9: `holdHost` / `holdProgress` are ui::padHold's answer -- the host button the player is holding down to
    // remap and how far along it is (0..1). Drawn as a ring closing in on that control, so "which button is it
    // building on" is answered on the pad itself and not only in words. 0 / 0.0f: no hold.
    void drawPad(const Ctx &ctx, Rect bounds, const PadSnapshot &pad, float deadZone, int markHost = 0,
                 const std::vector<PadCallout> *callouts = nullptr, int holdHost = 0, float holdProgress = 0.0f);
}
