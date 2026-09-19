// Sprint 8 Goal 9: the primitives and the focus-aware controls.
#include "widgets.h"

#include <algorithm>
#include <cmath>

namespace ui
{
    namespace
    {
        Rectangle px(const Ctx &ctx, Rect r)
        {
            return Rectangle{r.x * ctx.scale, r.y * ctx.scale, r.w * ctx.scale, r.h * ctx.scale};
        }
        Vector2 px(const Ctx &ctx, Vec2 v) { return Vector2{v.x * ctx.scale, v.y * ctx.scale}; }

        const Font &fontOf(const Ctx &ctx, Face face)
        {
            if (face == Face::Display)
                return ctx.fonts->display;
            if (face == Face::Bold)
                return ctx.fonts->bodyBold;
            return ctx.fonts->body;
        }

        float spacingFor(Face face, float sizePx)
        {
            return face == Face::Display ? sizePx * 0.08f : sizePx * 0.02f;
        }
    }

    void fillRect(const Ctx &ctx, Rect r, Rgba color) { DrawRectangleRec(px(ctx, r), rl(color)); }

    void strokeRect(const Ctx &ctx, Rect r, Rgba color, float thick)
    {
        DrawRectangleLinesEx(px(ctx, r), std::max(1.0f, thick * ctx.scale), rl(color));
    }

    void fillCircle(const Ctx &ctx, Vec2 c, float radius, Rgba color)
    {
        DrawCircleV(px(ctx, c), radius * ctx.scale, rl(color));
    }

    void strokeCircle(const Ctx &ctx, Vec2 c, float radius, Rgba color, float thick)
    {
        const float r = radius * ctx.scale;
        const float t = std::max(1.0f, thick * ctx.scale);
        DrawRing(px(ctx, c), r - t, r, 0.0f, 360.0f, 48, rl(color));
    }

    void fillRound(const Ctx &ctx, Rect r, float radius, Rgba color)
    {
        const Rectangle p = px(ctx, r);
        const float shortest = std::min(p.width, p.height);
        const float roundness = shortest <= 0.0f ? 0.0f : std::min(1.0f, (radius * ctx.scale * 2.0f) / shortest);
        DrawRectangleRounded(p, roundness, 12, rl(color));
    }

    void strokeRound(const Ctx &ctx, Rect r, float radius, Rgba color, float thick)
    {
        const Rectangle p = px(ctx, r);
        const float shortest = std::min(p.width, p.height);
        const float roundness = shortest <= 0.0f ? 0.0f : std::min(1.0f, (radius * ctx.scale * 2.0f) / shortest);
        DrawRectangleRoundedLinesEx(p, roundness, 12, std::max(1.0f, thick * ctx.scale), rl(color));
    }

    void drawLine(const Ctx &ctx, Vec2 a, Vec2 b, Rgba color, float thick)
    {
        DrawLineEx(px(ctx, a), px(ctx, b), std::max(1.0f, thick * ctx.scale), rl(color));
    }

    void fillTriangle(const Ctx &ctx, Vec2 a, Vec2 b, Vec2 c, Rgba color)
    {
        DrawTriangle(px(ctx, a), px(ctx, b), px(ctx, c), rl(color));
    }

    void fillPoly(const Ctx &ctx, Vec2 centre, int sides, float radius, float rotation, Rgba color)
    {
        DrawPoly(px(ctx, centre), sides, radius * ctx.scale, rotation, rl(color));
    }

    void strokePoly(const Ctx &ctx, Vec2 centre, int sides, float radius, float rotation, Rgba color, float thick)
    {
        DrawPolyLinesEx(px(ctx, centre), sides, radius * ctx.scale, rotation, std::max(1.0f, thick * ctx.scale), rl(color));
    }

    void fillQuad(const Ctx &ctx, Vec2 tl, Vec2 bl, Vec2 br, Vec2 tr, Rgba color)
    {
        // The same two triangles, in the same order, that DrawRectanglePro emits -- so the winding holds.
        DrawTriangle(px(ctx, tl), px(ctx, bl), px(ctx, tr), rl(color));
        DrawTriangle(px(ctx, tr), px(ctx, bl), px(ctx, br), rl(color));
    }

    float textWidth(const Ctx &ctx, const char *s, float size, Face face)
    {
        const float sizePx = size * ctx.scale;
        const Vector2 m = MeasureTextEx(fontOf(ctx, face), s, sizePx, spacingFor(face, sizePx));
        return m.x / ctx.scale;
    }

    void text(const Ctx &ctx, const char *s, Vec2 at, float size, Rgba color, Face face)
    {
        const float sizePx = size * ctx.scale;
        DrawTextEx(fontOf(ctx, face), s, px(ctx, at), sizePx, spacingFor(face, sizePx), rl(color));
    }

    void textCenteredIn(const Ctx &ctx, const char *s, Rect r, float size, Rgba color, Face face)
    {
        const float w = textWidth(ctx, s, size, face);
        text(ctx, s, Vec2{r.x + (r.w - w) * 0.5f, r.y + (r.h - size * 1.12f) * 0.5f}, size, color, face);
    }

    void textRightIn(const Ctx &ctx, const char *s, Rect r, float size, Rgba color, Face face)
    {
        const float w = textWidth(ctx, s, size, face);
        text(ctx, s, Vec2{r.right() - w, r.y + (r.h - size * 1.12f) * 0.5f}, size, color, face);
    }

    std::string ellipsizeEnd(const Ctx &ctx, const std::string &s, float maxWidth, float size, Face face)
    {
        if (textWidth(ctx, s.c_str(), size, face) <= maxWidth)
            return s;
        std::string out = s;
        while (!out.empty() && textWidth(ctx, (out + "...").c_str(), size, face) > maxWidth)
            out.pop_back();
        return out + "...";
    }

    std::string ellipsizeStart(const Ctx &ctx, const std::string &s, float maxWidth, float size, Face face)
    {
        std::string out = s;
        while (!out.empty() && textWidth(ctx, out.c_str(), size, face) > maxWidth)
            out.erase(0, 1);
        return out;
    }

    void panel(const Ctx &ctx, Rect r, bool raised)
    {
        fillRect(ctx, r, raised ? theme::panelHi : theme::panel);
        strokeRect(ctx, r, theme::line, 2.0f);
    }

    void groundGrid(const Ctx &ctx, Rect window)
    {
        const Rgba faint = theme::alpha(theme::line, 42);
        for (float x = 0.0f; x <= window.w; x += metrics::gridStep)
            drawLine(ctx, Vec2{x, 0.0f}, Vec2{x, window.h}, faint, 1.0f);
        for (float y = 0.0f; y <= window.h; y += metrics::gridStep)
            drawLine(ctx, Vec2{0.0f, y}, Vec2{window.w, y}, faint, 1.0f);
        // A vignette: four bands of the ground colour fading in from the edges.
        const int bands = 10;
        for (int i = 0; i < bands; ++i)
        {
            const float t = static_cast<float>(i) / static_cast<float>(bands);
            const unsigned char a = static_cast<unsigned char>(10.0f + 12.0f * (1.0f - t));
            const float inset = t * 46.0f;
            const Rgba c = theme::alpha(theme::ground, a);
            fillRect(ctx, Rect{0.0f, inset, window.w, 4.6f}, c);
            fillRect(ctx, Rect{0.0f, window.h - inset - 4.6f, window.w, 4.6f}, c);
            fillRect(ctx, Rect{inset, 0.0f, 4.6f, window.h}, c);
            fillRect(ctx, Rect{window.w - inset - 4.6f, 0.0f, 4.6f, window.h}, c);
        }
    }

    void focusRing(const Ctx &ctx, Rect r)
    {
        strokeRect(ctx, Rect{r.x - 3.0f, r.y - 3.0f, r.w + 6.0f, r.h + 6.0f}, theme::gold, 2.0f);
        strokeRect(ctx, Rect{r.x - 1.0f, r.y - 1.0f, r.w + 2.0f, r.h + 2.0f}, theme::alpha(theme::goldHi, 90), 1.0f);
    }

    bool hovered(const Ctx &ctx, Rect r)
    {
        return !ctx.fake && ctx.mouseMoved && r.contains(ctx.mouse);
    }

    bool focused(const Ctx &ctx, const std::string &id) { return ctx.focus == id; }

    bool hit(const Ctx &ctx, Rect r, const std::string &id, bool enabled)
    {
        if (!enabled)
            return false;
        const bool byMouse = !ctx.fake && ctx.click && r.contains(ctx.mouse);
        if (byMouse && ctx.focusOut != nullptr)
            *ctx.focusOut = id;
        const bool byFocus = focused(ctx, id) && ctx.activate;
        return byMouse || byFocus;
    }

    bool button(const Ctx &ctx, Rect r, const char *label, const std::string &id, bool enabled, bool primary)
    {
        const bool isFocused = focused(ctx, id);
        const bool isHover = enabled && hovered(ctx, r);
        Rgba fill = theme::panelHi;
        Rgba edge = theme::line;
        Rgba ink = theme::text;
        if (primary)
        {
            fill = enabled ? (isHover || isFocused ? theme::gold : theme::mix(theme::gold, theme::panel, 0.25f)) : theme::panel;
            edge = enabled ? theme::goldHi : theme::line;
            ink = enabled ? theme::ground : theme::dim;
        }
        else
        {
            if (!enabled)
            {
                fill = theme::mix(theme::panel, theme::ground, 0.4f);
                ink = theme::mix(theme::dim, theme::ground, 0.35f);
            }
            else if (isHover || isFocused)
            {
                fill = theme::mix(theme::panelHi, theme::gold, 0.16f);
                edge = theme::gold;
                ink = theme::goldHi;
            }
        }
        fillRect(ctx, r, fill);
        strokeRect(ctx, r, edge, 2.0f);
        textCenteredIn(ctx, label, r, primary ? 24.0f : 18.0f, ink, Face::Bold);
        return hit(ctx, r, id, enabled);
    }

    bool toggle(const Ctx &ctx, Rect r, const char *label, const std::string &id, bool &value)
    {
        const float boxSide = std::min(24.0f, r.h - 6.0f);
        const Rect box{r.x, r.y + (r.h - boxSide) * 0.5f, boxSide, boxSide};
        const bool live = hovered(ctx, r) || focused(ctx, id);
        fillRect(ctx, box, theme::ground);
        strokeRect(ctx, box, live ? theme::gold : theme::line, 2.0f);
        if (value)
            fillRect(ctx, Rect{box.x + 5.0f, box.y + 5.0f, box.w - 10.0f, box.h - 10.0f}, theme::goldHi);
        text(ctx, label, Vec2{box.right() + 12.0f, r.y + (r.h - 18.0f * 1.12f) * 0.5f}, 18.0f,
             live ? theme::text : theme::dim);
        if (hit(ctx, r, id))
        {
            value = !value;
            return true;
        }
        return false;
    }

    bool radioCell(const Ctx &ctx, Rect r, const char *label, const std::string &id, bool selected)
    {
        const bool live = hovered(ctx, r) || focused(ctx, id);
        fillRect(ctx, r, selected ? theme::mix(theme::panelHi, theme::gold, 0.22f) : theme::mix(theme::panel, theme::ground, 0.3f));
        strokeRect(ctx, r, selected ? theme::gold : (live ? theme::mix(theme::line, theme::gold, 0.5f) : theme::line), 2.0f);
        const Rgba ink = selected ? theme::goldHi : (live ? theme::text : theme::dim);
        const float size = 18.0f;
        const std::string shown = ellipsizeEnd(ctx, label, r.w - 16.0f, size, Face::Bold);
        textCenteredIn(ctx, shown.c_str(), r, size, ink, Face::Bold);
        if (selected)
            fillRect(ctx, Rect{r.x, r.bottom() - 3.0f, r.w, 3.0f}, theme::gold);
        return hit(ctx, r, id);
    }

    bool listRow(const Ctx &ctx, Rect r, const std::string &label, const std::string &id, bool selected)
    {
        const bool live = hovered(ctx, r) || focused(ctx, id);
        if (selected || live)
            fillRect(ctx, r, selected ? theme::mix(theme::panelHi, theme::gold, 0.14f) : theme::panelHi);
        const Rect mark{r.x + 6.0f, r.y + r.h * 0.5f - 5.0f, 10.0f, 10.0f};
        strokeRect(ctx, mark, selected ? theme::gold : theme::line, 2.0f);
        if (selected)
            fillRect(ctx, Rect{mark.x + 3.0f, mark.y + 3.0f, 4.0f, 4.0f}, theme::goldHi);
        const std::string shown = ellipsizeEnd(ctx, label, r.w - 36.0f, 18.0f);
        text(ctx, shown.c_str(), Vec2{mark.right() + 12.0f, r.y + (r.h - 18.0f * 1.12f) * 0.5f}, 18.0f,
             selected ? theme::goldHi : (live ? theme::text : theme::dim));
        return hit(ctx, r, id);
    }

    bool slider(const Ctx &ctx, Rect r, const std::string &id, double &value, double lo, double hi, double step)
    {
        const bool isFocused = focused(ctx, id);
        const bool live = isFocused || hovered(ctx, r);
        const double before = value;
        // The control is the whole row: a recessed well with the track down its middle, so the focus ring
        // encloses something rather than hanging in space.
        fillRect(ctx, r, theme::mix(theme::panel, theme::ground, 0.45f));
        strokeRect(ctx, r, live ? theme::line : theme::alpha(theme::line, 150), 2.0f);
        const Rect track{r.x + 14.0f, r.y + r.h * 0.5f - 3.0f, r.w - 28.0f, 6.0f};
        fillRect(ctx, track, theme::ground);
        strokeRect(ctx, track, theme::line, 1.0f);
        const float t = hi > lo ? static_cast<float>((value - lo) / (hi - lo)) : 0.0f;
        fillRect(ctx, Rect{track.x, track.y, track.w * t, track.h}, live ? theme::gold : theme::mix(theme::gold, theme::panel, 0.35f));
        const Vec2 knob{track.x + track.w * t, track.cy()};
        fillCircle(ctx, knob, 9.0f, live ? theme::goldHi : theme::gold);
        strokeCircle(ctx, knob, 9.0f, theme::ground, 2.0f);

        if (!ctx.fake && ctx.held && Rect{r.x, r.y, r.w, r.h}.contains(ctx.mouse))
        {
            if (ctx.click && ctx.focusOut != nullptr)
                *ctx.focusOut = id;
            double nt = static_cast<double>((ctx.mouse.x - track.x) / track.w);
            nt = nt < 0.0 ? 0.0 : (nt > 1.0 ? 1.0 : nt);
            value = lo + (hi - lo) * nt;
        }
        else if (isFocused && ctx.adjust != 0)
        {
            value += step * ctx.adjust;
        }
        if (step > 0.0)
            value = std::round(value / step) * step;
        value = value < lo ? lo : (value > hi ? hi : value);
        return value != before;
    }

    void textField(const Ctx &ctx, Rect r, std::string &value, const std::string &id, bool &changed, bool editable)
    {
        const bool isFocused = focused(ctx, id);
        const bool isActive = editable && ctx.activeField != nullptr && *ctx.activeField == id;
        fillRect(ctx, r, theme::ground);
        strokeRect(ctx, r, isActive ? theme::goldHi : (isFocused ? theme::gold : theme::line), 2.0f);

        if (!ctx.fake && ctx.click && r.contains(ctx.mouse))
        {
            if (ctx.focusOut != nullptr)
                *ctx.focusOut = id;
            if (editable && ctx.activeField != nullptr)
                *ctx.activeField = id;
        }
        if (editable && isFocused && ctx.activate && ctx.activeField != nullptr)
            *ctx.activeField = id;

        if (isActive)
        {
            for (int c = GetCharPressed(); c > 0; c = GetCharPressed())
                if (c >= 32 && c < 127)
                {
                    value.push_back(static_cast<char>(c));
                    changed = true;
                }
            if ((IsKeyPressed(KEY_BACKSPACE) || IsKeyPressedRepeat(KEY_BACKSPACE)) && !value.empty())
            {
                value.pop_back();
                changed = true;
            }
        }

        const float inset = 10.0f;
        const float size = 19.0f;
        // A path is read from its end while it is typed, and from its front when it is not.
        const std::string shown = isActive ? ellipsizeStart(ctx, value, r.w - inset * 2.0f, size)
                                           : ellipsizeEnd(ctx, value, r.w - inset * 2.0f, size);
        text(ctx, shown.c_str(), Vec2{r.x + inset, r.y + (r.h - size * 1.12f) * 0.5f}, size,
             editable ? theme::text : theme::dim);
        if (isActive && (ctx.fake || (static_cast<int>(ctx.time * 2.0) & 1)))
        {
            const float w = textWidth(ctx, shown.c_str(), size);
            fillRect(ctx, Rect{r.x + inset + w + 2.0f, r.y + 8.0f, 2.0f, r.h - 16.0f}, theme::goldHi);
        }
    }

    void meterBar(const Ctx &ctx, Rect r, float fraction, Rgba fill)
    {
        fraction = fraction < 0.0f ? 0.0f : (fraction > 1.0f ? 1.0f : fraction);
        fillRect(ctx, r, theme::ground);
        fillRect(ctx, Rect{r.x + 2.0f, r.y + 2.0f, (r.w - 4.0f) * fraction, r.h - 4.0f}, fill);
        strokeRect(ctx, r, theme::line, 2.0f);
        // Tick marks every tenth: a level meter reads as a scale, not as a bar.
        for (int i = 1; i < 10; ++i)
        {
            const float x = r.x + r.w * (static_cast<float>(i) / 10.0f);
            drawLine(ctx, Vec2{x, r.bottom() - 5.0f}, Vec2{x, r.bottom() - 2.0f}, theme::alpha(theme::ground, 160), 1.0f);
        }
    }
}
