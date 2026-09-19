#pragma once
// Sprint 8 Goal 9: the prompt glyphs. Which family a pad's name belongs to is pure (the tests assert it);
// drawing the shapes is glyphs.cpp.
//
// Why it matters: the owner plays on an Xbox pad and SOCOM II prompts with PlayStation shapes, so the
// CONTROLLER page labels the buttons the way the pad in his hands is labelled and puts the game's shape
// beside it in a legend.
#include "theme.h"

#include <cctype>
#include <string>

namespace ui
{
    enum class GlyphFamily
    {
        Xbox,
        PlayStation,
        Generic
    };

    inline GlyphFamily glyphFamilyFor(const std::string &padName)
    {
        std::string n;
        n.reserve(padName.size());
        for (char c : padName)
            n.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        auto has = [&n](const char *needle) { return n.find(needle) != std::string::npos; };

        // Xbox first: "Xbox Wireless Controller" is an Xbox pad, not the bare "Wireless Controller" that
        // SDL reports for a DualShock 4.
        if (has("xbox") || has("xinput") || has("x-box") || has("microsoft"))
            return GlyphFamily::Xbox;
        if (has("dualshock") || has("dualsense") || has("playstation") || has("sony") || has("ps4") || has("ps5"))
            return GlyphFamily::PlayStation;
        if (n == "wireless controller")
            return GlyphFamily::PlayStation;
        return GlyphFamily::Generic;
    }

    // The letter a family puts on a face button: index 0 up, 1 down, 2 left, 3 right.
    inline const char *faceLetter(GlyphFamily family, int index)
    {
        static const char *xbox[4] = {"Y", "A", "X", "B"};
        static const char *generic[4] = {"1", "2", "3", "4"};
        if (family == GlyphFamily::Xbox)
            return xbox[index & 3];
        if (family == GlyphFamily::Generic)
            return generic[index & 3];
        return "";   // PlayStation: the shape is drawn, not lettered
    }

    struct Ctx;   // widgets.h
    // The PlayStation shape for that index (triangle, cross, square, circle) at `size` across.
    void drawShapeGlyph(const Ctx &ctx, int index, Vec2 centre, float size, Rgba color);
    // A key cap: the letter or word inside a bordered box. Returns the width it took.
    float drawKeyCap(const Ctx &ctx, Vec2 topLeft, const char *label, float height, Rgba color);
    // A pad button glyph for the bottom bar's prompts (the family's face button, index as above).
    float drawPadPrompt(const Ctx &ctx, Vec2 topLeft, GlyphFamily family, int index, float height, Rgba color);
}
