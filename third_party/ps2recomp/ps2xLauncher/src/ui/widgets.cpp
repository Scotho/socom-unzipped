// Sprint 8 Goal 9: the primitives and the focus-aware controls.
#include "widgets.h"

#include <algorithm>
#include <cmath>
#include <vector>

namespace ui
{
    namespace
    {
        Rectangle px(const Ctx &ctx, Rect r)
        {
            return Rectangle{r.x * ctx.scale, r.y * ctx.scale, r.w * ctx.scale, r.h * ctx.scale};
        }
        Vector2 px(const Ctx &ctx, Vec2 v) { return Vector2{v.x * ctx.scale, v.y * ctx.scale}; }

        // A circle's edge is only as smooth as its segment count, and a centre landing exactly on a pixel
        // boundary makes the top and bottom rows disagree -- so centres sit on pixel centres.
        Vector2 circleCentre(const Ctx &ctx, Vec2 v)
        {
            const float k = ctx.scale * ctx.dpi;
            return Vector2{(std::floor(v.x * k) + 0.5f) / ctx.dpi, (std::floor(v.y * k) + 0.5f) / ctx.dpi};
        }

        int segmentsFor(const Ctx &ctx, float radius) { return circleSegments(radius * ctx.scale * ctx.dpi); }

        // Text: rasterised at the pixel size it is drawn at, never below the floor, on the pixel grid.
        int pixelSize(const Ctx &ctx, float size)
        {
            const int wanted = static_cast<int>(std::lround(size * ctx.scale * ctx.dpi));
            return wanted < metrics::minTextPx ? metrics::minTextPx : wanted;
        }

        float snap(const Ctx &ctx, float screenValue)
        {
            return std::round(screenValue * ctx.dpi) / ctx.dpi;
        }
    }

    void fillRect(const Ctx &ctx, Rect r, Rgba color) { DrawRectangleRec(px(ctx, r), rl(color)); }

    void fillRectGradient(const Ctx &ctx, Rect r, Rgba top, Rgba bottom)
    {
        const Rectangle p = px(ctx, r);
        DrawRectangleGradientV(static_cast<int>(p.x), static_cast<int>(p.y), static_cast<int>(p.width),
                               static_cast<int>(p.height), rl(top), rl(bottom));
    }

    void strokeRect(const Ctx &ctx, Rect r, Rgba color, float thick)
    {
        DrawRectangleLinesEx(px(ctx, r), std::max(1.0f, thick * ctx.scale), rl(color));
    }

    void fillCircle(const Ctx &ctx, Vec2 c, float radius, Rgba color)
    {
        DrawCircleSector(circleCentre(ctx, c), radius * ctx.scale, 0.0f, 360.0f, segmentsFor(ctx, radius), rl(color));
    }

    void strokeCircle(const Ctx &ctx, Vec2 c, float radius, Rgba color, float thick)
    {
        const float r = radius * ctx.scale;
        const float t = std::max(1.2f, thick * ctx.scale);
        DrawRing(circleCentre(ctx, c), r - t, r, 0.0f, 360.0f, segmentsFor(ctx, radius), rl(color));
    }

    void fillRound(const Ctx &ctx, Rect r, float radius, Rgba color)
    {
        const Rectangle p = px(ctx, r);
        const float shortest = std::min(p.width, p.height);
        const float roundness = shortest <= 0.0f ? 0.0f : std::min(1.0f, (radius * ctx.scale * 2.0f) / shortest);
        DrawRectangleRounded(p, roundness, std::max(8, circleSegments(radius * ctx.scale * ctx.dpi) / 4), rl(color));
    }

    void strokeRound(const Ctx &ctx, Rect r, float radius, Rgba color, float thick)
    {
        const Rectangle p = px(ctx, r);
        const float shortest = std::min(p.width, p.height);
        const float roundness = shortest <= 0.0f ? 0.0f : std::min(1.0f, (radius * ctx.scale * 2.0f) / shortest);
        DrawRectangleRoundedLinesEx(p, roundness, std::max(8, circleSegments(radius * ctx.scale * ctx.dpi) / 4),
                                    std::max(1.2f, thick * ctx.scale), rl(color));
    }

    void drawLine(const Ctx &ctx, Vec2 a, Vec2 b, Rgba color, float thick)
    {
        DrawLineEx(px(ctx, a), px(ctx, b), std::max(1.5f, thick * ctx.scale), rl(color));
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
        DrawPolyLinesEx(px(ctx, centre), sides, radius * ctx.scale, rotation, std::max(1.2f, thick * ctx.scale), rl(color));
    }

    void fillQuad(const Ctx &ctx, Vec2 tl, Vec2 bl, Vec2 br, Vec2 tr, Rgba color)
    {
        // The same two triangles, in the same order, that DrawRectanglePro emits -- so the winding holds.
        DrawTriangle(px(ctx, tl), px(ctx, bl), px(ctx, tr), rl(color));
        DrawTriangle(px(ctx, tr), px(ctx, bl), px(ctx, br), rl(color));
    }

    void strokePath(const Ctx &ctx, const Vec2 *points, int count, Rgba color, float thick, bool closed)
    {
        if (count < 2)
            return;
        std::vector<Vector2> pts;
        pts.reserve(static_cast<size_t>(count) + 1);
        for (int i = 0; i < count; ++i)
            pts.push_back(px(ctx, points[i]));
        if (closed)
            pts.push_back(pts.front());
        DrawSplineLinear(pts.data(), static_cast<int>(pts.size()), std::max(1.5f, thick * ctx.scale), rl(color));
    }

    float textWidth(const Ctx &ctx, const char *s, float size, Face face, float tracking)
    {
        const int pixels = pixelSize(ctx, size);
        const float screenSize = static_cast<float>(pixels) / ctx.dpi;
        const Font &font = ctx.fonts->at(face, pixels);
        const Vector2 m = MeasureTextEx(font, s, screenSize, screenSize * tracking);
        return m.x / ctx.scale;
    }

    void text(const Ctx &ctx, const char *s, Vec2 at, float size, Rgba color, Face face, float tracking)
    {
        const int pixels = pixelSize(ctx, size);
        const float screenSize = static_cast<float>(pixels) / ctx.dpi;
        const Font &font = ctx.fonts->at(face, pixels);
        const Vector2 where{snap(ctx, at.x * ctx.scale), snap(ctx, at.y * ctx.scale)};
        DrawTextEx(font, s, where, screenSize, screenSize * tracking, rl(color));
    }

    void textCenteredIn(const Ctx &ctx, const char *s, Rect r, float size, Rgba color, Face face, float tracking)
    {
        const float w = textWidth(ctx, s, size, face, tracking);
        const float drawn = static_cast<float>(pixelSize(ctx, size)) / (ctx.dpi * ctx.scale);   // design units
        text(ctx, s, Vec2{r.x + (r.w - w) * 0.5f, r.y + (r.h - drawn * 1.12f) * 0.5f}, size, color, face, tracking);
    }

    void textRightIn(const Ctx &ctx, const char *s, Rect r, float size, Rgba color, Face face)
    {
        const float w = textWidth(ctx, s, size, face);
        const float drawn = static_cast<float>(pixelSize(ctx, size)) / (ctx.dpi * ctx.scale);
        text(ctx, s, Vec2{r.right() - w, r.y + (r.h - drawn * 1.12f) * 0.5f}, size, color, face);
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
        const Rgba faint = theme::alpha(theme::line, 40);
        for (float x = 0.0f; x <= window.w; x += metrics::gridStep)
            drawLine(ctx, Vec2{x, 0.0f}, Vec2{x, window.h}, faint, 1.0f);
        for (float y = 0.0f; y <= window.h; y += metrics::gridStep)
            drawLine(ctx, Vec2{0.0f, y}, Vec2{window.w, y}, faint, 1.0f);
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

    void glow(const Ctx &ctx, Vec2 centre, float radius, Rgba color, unsigned char peak)
    {
        // The halo behind the game's trident, as rings of falling alpha: procedural, no artwork.
        const int rings = 16;
        for (int i = rings; i >= 1; --i)
        {
            const float t = static_cast<float>(i) / static_cast<float>(rings);
            const float a = static_cast<float>(peak) * (1.0f - t) * (1.0f - t);
            fillCircle(ctx, centre, radius * t, theme::alpha(color, static_cast<unsigned char>(a)));
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
        const bool live = isHover || isFocused;
        if (primary)
        {
            // The logo's signature: the letters' blue-to-navy gradient inside a gold outline.
            if (enabled)
            {
                fillRectGradient(ctx, r, theme::blueFill, theme::blueDeep);
                strokeRect(ctx, r, live ? theme::goldHi : theme::gold, 2.0f);
                textCenteredIn(ctx, label, r, metrics::bodySize + 5.0f, theme::text, Face::Bold, 0.06f);
            }
            else
            {
                fillRect(ctx, r, theme::mix(theme::panel, theme::ground, 0.35f));
                strokeRect(ctx, r, theme::line, 2.0f);
                textCenteredIn(ctx, label, r, metrics::bodySize + 5.0f, theme::dim, Face::Bold, 0.06f);
            }
            return hit(ctx, r, id, enabled);
        }
        Rgba fill = theme::panelHi;
        Rgba edge = theme::line;
        Rgba ink = theme::text;
        if (!enabled)
        {
            fill = theme::mix(theme::panel, theme::ground, 0.4f);
            ink = theme::dim;
        }
        else if (live)
        {
            fill = theme::mix(theme::panelHi, theme::gold, 0.18f);
            edge = theme::gold;
            ink = theme::goldHi;
        }
        fillRect(ctx, r, fill);
        strokeRect(ctx, r, edge, 2.0f);
        textCenteredIn(ctx, label, r, metrics::labelSize + 1.0f, ink, Face::Bold, 0.04f);
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
        const float size = metrics::bodySize - 1.0f;
        const float drawn = static_cast<float>(pixelSize(ctx, size)) / (ctx.dpi * ctx.scale);
        text(ctx, label, Vec2{box.right() + 12.0f, r.y + (r.h - drawn * 1.12f) * 0.5f}, size,
             live ? theme::text : theme::caption);
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
        if (selected)
            fillRectGradient(ctx, r, theme::blueFill, theme::blueDeep);
        else
            fillRect(ctx, r, live ? theme::panelHi : theme::mix(theme::panel, theme::ground, 0.25f));
        strokeRect(ctx, r, selected ? theme::gold : (live ? theme::mix(theme::line, theme::gold, 0.5f) : theme::line), 2.0f);
        const Rgba ink = selected ? theme::text : (live ? theme::text : theme::caption);
        const float size = metrics::labelSize + 1.0f;
        const std::string shown = ellipsizeEnd(ctx, label, r.w - 16.0f, size, Face::Bold);
        textCenteredIn(ctx, shown.c_str(), r, size, ink, Face::Bold, 0.04f);
        return hit(ctx, r, id);
    }

    bool listRow(const Ctx &ctx, Rect r, const std::string &label, const std::string &id, bool selected)
    {
        const bool live = hovered(ctx, r) || focused(ctx, id);
        if (selected)
            fillRect(ctx, r, theme::mix(theme::panelHi, theme::blue, 0.30f));
        else if (live)
            fillRect(ctx, r, theme::panelHi);
        const Rect mark{r.x + 6.0f, r.y + r.h * 0.5f - 5.0f, 10.0f, 10.0f};
        strokeRect(ctx, mark, selected ? theme::gold : theme::line, 2.0f);
        if (selected)
            fillRect(ctx, Rect{mark.x + 3.0f, mark.y + 3.0f, 4.0f, 4.0f}, theme::goldHi);
        const float size = metrics::bodySize - 1.0f;
        const float drawn = static_cast<float>(pixelSize(ctx, size)) / (ctx.dpi * ctx.scale);
        const std::string shown = ellipsizeEnd(ctx, label, r.w - 36.0f, size);
        text(ctx, shown.c_str(), Vec2{mark.right() + 12.0f, r.y + (r.h - drawn * 1.12f) * 0.5f}, size,
             selected ? theme::text : (live ? theme::text : theme::caption));
        return hit(ctx, r, id);
    }

    bool slider(const Ctx &ctx, Rect r, const std::string &id, double &value, double lo, double hi, double step)
    {
        const bool isFocused = focused(ctx, id);
        const bool live = isFocused || hovered(ctx, r);
        const double before = value;
        fillRect(ctx, r, theme::mix(theme::panel, theme::ground, 0.45f));
        strokeRect(ctx, r, live ? theme::line : theme::alpha(theme::line, 150), 2.0f);
        const Rect track{r.x + 14.0f, r.y + r.h * 0.5f - 3.0f, r.w - 28.0f, 6.0f};
        fillRect(ctx, track, theme::ground);
        const float t = hi > lo ? static_cast<float>((value - lo) / (hi - lo)) : 0.0f;
        fillRect(ctx, Rect{track.x, track.y, track.w * t, track.h}, live ? theme::gold : theme::mix(theme::gold, theme::panel, 0.3f));
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

    namespace
    {
        // What a focused field takes from the keyboard this frame: typed characters, Ctrl+V, backspace.
        // Printable ASCII only, as the launcher's fonts are; a pasted line break becomes a space.
        bool typeInto(std::string &value, size_t maxLen, bool paste)
        {
            bool changed = false;
            auto room = [&]() { return maxLen == 0 || value.size() < maxLen; };
            for (int c = GetCharPressed(); c > 0; c = GetCharPressed())
                if (c >= 32 && c < 127 && room())
                {
                    value.push_back(static_cast<char>(c));
                    changed = true;
                }
            if (paste && (IsKeyDown(KEY_LEFT_CONTROL) || IsKeyDown(KEY_RIGHT_CONTROL)) && IsKeyPressed(KEY_V))
            {
                const char *clip = GetClipboardText();
                for (const char *p = clip; p != nullptr && *p != '\0' && room(); ++p)
                {
                    unsigned char c = static_cast<unsigned char>(*p);
                    if (c == '\n' || c == '\t')
                        c = ' ';
                    if (c >= 32 && c < 127)
                    {
                        value.push_back(static_cast<char>(c));
                        changed = true;
                    }
                }
            }
            if ((IsKeyPressed(KEY_BACKSPACE) || IsKeyPressedRepeat(KEY_BACKSPACE)) && !value.empty())
            {
                value.pop_back();
                changed = true;
            }
            return changed;
        }
    }

    std::vector<std::string> wrapText(const Ctx &ctx, const std::string &s, float maxWidth, float size, Face face)
    {
        std::vector<std::string> lines;
        std::string line;
        size_t at = 0;
        while (at < s.size())
        {
            if (s[at] == '\n')
            {
                lines.push_back(line);
                line.clear();
                ++at;
                continue;
            }
            size_t end = at;
            while (end < s.size() && s[end] != ' ' && s[end] != '\n')
                ++end;
            while (end < s.size() && s[end] == ' ')
                ++end;   // a word carries its trailing spaces, so the caret sits where the next letter goes
            std::string word = s.substr(at, end - at);
            at = end;
            if (!line.empty() && textWidth(ctx, (line + word).c_str(), size, face) > maxWidth)
            {
                lines.push_back(line);
                line.clear();
            }
            // A word wider than the field is broken where it stops fitting.
            while (word.size() > 1 && textWidth(ctx, word.c_str(), size, face) > maxWidth)
            {
                size_t fit = word.size() - 1;
                while (fit > 1 && textWidth(ctx, word.substr(0, fit).c_str(), size, face) > maxWidth)
                    --fit;
                lines.push_back(word.substr(0, fit));
                word.erase(0, fit);
            }
            line += word;
        }
        lines.push_back(line);
        return lines;
    }

    void textArea(const Ctx &ctx, Rect r, std::string &value, const std::string &id, bool &changed, size_t maxLen)
    {
        const bool isFocused = focused(ctx, id);
        const bool isActive = ctx.activeField != nullptr && *ctx.activeField == id;
        fillRect(ctx, r, theme::ground);
        strokeRect(ctx, r, isActive ? theme::goldHi : (isFocused ? theme::gold : theme::line), 2.0f);

        if (!ctx.fake && ctx.click && r.contains(ctx.mouse))
        {
            if (ctx.focusOut != nullptr)
                *ctx.focusOut = id;
            if (ctx.activeField != nullptr)
                *ctx.activeField = id;
        }
        if (isFocused && ctx.activate && ctx.activeField != nullptr)
            *ctx.activeField = id;
        if (isActive && typeInto(value, maxLen, true))
            changed = true;

        const float inset = 10.0f;
        const float size = metrics::bodySize - 2.0f;
        const float lineH = size * 1.22f;
        const int room = static_cast<int>((r.h - inset * 2.0f + 2.0f) / lineH);
        const std::vector<std::string> lines = wrapText(ctx, value, r.w - inset * 2.0f - 4.0f, size, Face::Body);
        const int total = static_cast<int>(lines.size());
        // While typing, the END is what matters (there is no caret to move); at rest, the beginning.
        const int first = (isActive && total > room) ? total - room : 0;
        for (int i = 0; i < room && first + i < total; ++i)
        {
            std::string shown = lines[static_cast<size_t>(first + i)];
            if (!isActive && i == room - 1 && first + i + 1 < total)
                shown = ellipsizeEnd(ctx, shown, r.w - inset * 2.0f - 60.0f, size) + " ...";
            text(ctx, shown.c_str(), Vec2{r.x + inset, r.y + inset + lineH * static_cast<float>(i)}, size, theme::text);
        }
        if (isActive && (ctx.fake || (static_cast<int>(ctx.time * 2.0) & 1)))
        {
            const int row = total - 1 - first;
            const float w = textWidth(ctx, lines.back().c_str(), size);
            fillRect(ctx, Rect{r.x + inset + w + 2.0f, r.y + inset + lineH * static_cast<float>(row < 0 ? 0 : row), 2.0f, lineH - 2.0f},
                     theme::goldHi);
        }
    }

    void textField(const Ctx &ctx, Rect r, std::string &value, const std::string &id, bool &changed, bool editable, size_t maxLen)
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

        // maxLen > 0 marks the REPORT A BUG fields: capped at the contract's length, and they take Ctrl+V.
        if (isActive && typeInto(value, maxLen, maxLen > 0))
            changed = true;

        const float inset = 10.0f;
        const float size = metrics::bodySize;
        const float drawn = static_cast<float>(pixelSize(ctx, size)) / (ctx.dpi * ctx.scale);
        const std::string shown = isActive ? ellipsizeStart(ctx, value, r.w - inset * 2.0f, size)
                                           : ellipsizeEnd(ctx, value, r.w - inset * 2.0f, size);
        text(ctx, shown.c_str(), Vec2{r.x + inset, r.y + (r.h - drawn * 1.12f) * 0.5f}, size,
             editable ? theme::text : theme::caption);
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
        for (int i = 1; i < 10; ++i)
        {
            const float x = r.x + r.w * (static_cast<float>(i) / 10.0f);
            drawLine(ctx, Vec2{x, r.bottom() - 5.0f}, Vec2{x, r.bottom() - 2.0f}, theme::alpha(theme::ground, 160), 1.0f);
        }
    }
}
