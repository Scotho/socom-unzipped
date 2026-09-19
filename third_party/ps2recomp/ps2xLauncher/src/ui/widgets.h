#pragma once
// Sprint 8 Goal 9: the drawing primitives and the focus-aware controls every page is built from.
//
// Everything here takes DESIGN units (the 1100x700 grid) and multiplies by ctx.scale on the way to raylib, so
// a page's code never mentions a pixel and the layout the focus model asserts on is the layout drawn.
//
// Third pass: type is rasterised at the exact pixel size it is drawn at (ctx.scale x ctx.dpi), never below
// metrics::minTextPx, and laid on the pixel grid; circles carry enough segments for their radius.
#include "fonts.h"
#include "theme.h"

#include "raylib.h"

#include <string>

namespace ui
{
    inline Color rl(Rgba c) { return Color{c.r, c.g, c.b, c.a}; }

    struct Ctx
    {
        float scale = 1.0f;
        float dpi = 1.0f;       // GetWindowScaleDPI(): screen units -> real pixels
        Fonts *fonts = nullptr;

        Vec2 mouse;             // design units
        bool click = false;     // left button went down this frame
        bool held = false;      // left button is down
        bool mouseMoved = false;   // hover only counts once the mouse has moved (the pad must not fight it)

        std::string focus;      // the focused node's id
        std::string *focusOut = nullptr;   // where a click puts the focus
        bool activate = false;  // enter / space / the pad's bottom face button, this frame
        int adjust = 0;         // -1 / +1 for the focused slider

        std::string *activeField = nullptr;   // the text field that owns the keyboard, by id
        double time = 0.0;
        bool fake = false;      // --screenshot: no hover, no caret blink, no animation
    };

    // ---- primitives ---------------------------------------------------------------------------------------
    void fillRect(const Ctx &ctx, Rect r, Rgba color);
    void fillRectGradient(const Ctx &ctx, Rect r, Rgba top, Rgba bottom);
    void strokeRect(const Ctx &ctx, Rect r, Rgba color, float thick = 2.0f);
    void fillCircle(const Ctx &ctx, Vec2 c, float radius, Rgba color);
    void strokeCircle(const Ctx &ctx, Vec2 c, float radius, Rgba color, float thick = 2.0f);
    void fillRound(const Ctx &ctx, Rect r, float radius, Rgba color);
    void strokeRound(const Ctx &ctx, Rect r, float radius, Rgba color, float thick = 2.0f);
    void drawLine(const Ctx &ctx, Vec2 a, Vec2 b, Rgba color, float thick = 2.0f);
    void fillTriangle(const Ctx &ctx, Vec2 a, Vec2 b, Vec2 c, Rgba color);
    // A regular polygon, `rotation` degrees from +X (screen space, so -90 points up): the d-pad's segments.
    void fillPoly(const Ctx &ctx, Vec2 centre, int sides, float radius, float rotation, Rgba color);
    void strokePoly(const Ctx &ctx, Vec2 centre, int sides, float radius, float rotation, Rgba color, float thick = 2.0f);
    // A quad given in raylib's own winding: top-left, bottom-left, bottom-right, top-right.
    void fillQuad(const Ctx &ctx, Vec2 tl, Vec2 bl, Vec2 br, Vec2 tr, Rgba color);
    // A thick polyline through `count` points: the pad's outline.
    void strokePath(const Ctx &ctx, const Vec2 *points, int count, Rgba color, float thick, bool closed);

    float textWidth(const Ctx &ctx, const char *s, float size, Face face = Face::Body, float tracking = 0.0f);
    void text(const Ctx &ctx, const char *s, Vec2 at, float size, Rgba color, Face face = Face::Body, float tracking = 0.0f);
    void textCenteredIn(const Ctx &ctx, const char *s, Rect r, float size, Rgba color, Face face = Face::Body, float tracking = 0.0f);
    void textRightIn(const Ctx &ctx, const char *s, Rect r, float size, Rgba color, Face face = Face::Body);
    // The head that fits, with "..." (a path's tail) or the tail that fits (a field being typed in).
    std::string ellipsizeEnd(const Ctx &ctx, const std::string &s, float maxWidth, float size, Face face = Face::Body);
    std::string ellipsizeStart(const Ctx &ctx, const std::string &s, float maxWidth, float size, Face face = Face::Body);

    // ---- chrome -------------------------------------------------------------------------------------------
    void panel(const Ctx &ctx, Rect r, bool raised = false);
    void groundGrid(const Ctx &ctx, Rect window);   // the faint 32 px grid and the vignette
    void glow(const Ctx &ctx, Vec2 centre, float radius, Rgba color, unsigned char peak);   // the logo's blue halo
    void focusRing(const Ctx &ctx, Rect r);

    bool hovered(const Ctx &ctx, Rect r);
    bool focused(const Ctx &ctx, const std::string &id);
    // Clicked on, or acted on where the focus is -- the one rule every control and every page row shares.
    // A click also moves the focus, so the keyboard and the pad carry on from wherever the mouse left off.
    bool hit(const Ctx &ctx, Rect r, const std::string &id, bool enabled = true);

    // ---- controls -----------------------------------------------------------------------------------------
    // Every one of these returns true on the frame it was acted on, by mouse or by the focus model, and every
    // one takes the focus when it is clicked.
    bool button(const Ctx &ctx, Rect r, const char *label, const std::string &id, bool enabled = true, bool primary = false);
    bool toggle(const Ctx &ctx, Rect r, const char *label, const std::string &id, bool &value);
    bool radioCell(const Ctx &ctx, Rect r, const char *label, const std::string &id, bool selected);
    bool listRow(const Ctx &ctx, Rect r, const std::string &label, const std::string &id, bool selected);
    bool slider(const Ctx &ctx, Rect r, const std::string &id, double &value, double lo, double hi, double step);
    void textField(const Ctx &ctx, Rect r, std::string &value, const std::string &id, bool &changed, bool editable = true);
    void meterBar(const Ctx &ctx, Rect r, float fraction, Rgba fill);
}
