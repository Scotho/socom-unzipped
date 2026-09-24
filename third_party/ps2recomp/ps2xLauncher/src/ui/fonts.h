#pragma once
// Sprint 8 Goal 9: the two embedded OFL faces. They are byte arrays in the exe so the portable folder stays
// self-contained -- no font files to lose, nothing to install. Sprint 11 Task 17 (R247): the arrays are no
// longer tracked; the build generates fonts_embedded/*.h from assets/fonts/*.ttf with scripts/embed_font.py
// (see ps2xLauncher/CMakeLists.txt) into the build tree, and fonts.cpp includes them from there.
//
// Third pass, the owner's "the header font becomes quite illegible at smaller resolutions": the launcher no
// longer keeps one 2x atlas and scales it. Every face is rasterised at the EXACT pixel size it will be drawn
// at, cached by (face, pixels), and thrown away when the window's scale changes. Saira Stencil One is a
// display face and is only used above 28 px; everything else is Rajdhani.
#include "raylib.h"

#include <map>

namespace ui
{
    enum class Face
    {
        Body,      // Rajdhani Medium
        Bold,      // Rajdhani SemiBold: headings, values, buttons, the rail
        Display    // Saira Stencil One: the wordmark alone
    };

    class Fonts
    {
    public:
        ~Fonts() { clear(); }

        // The face at exactly this many pixels, rasterised on first ask and kept. Never fails: if the
        // embedded bytes will not load (the spec's stop rule) every face is raylib's default.
        const Font &at(Face face, int pixels);
        bool embedded() const { return m_embedded; }
        void clear();   // the scale changed: every size in the cache is the wrong size now

    private:
        std::map<int, Font> m_cache;   // key: face << 12 | pixels
        bool m_embedded = true;
        bool m_warned = false;
    };
}
