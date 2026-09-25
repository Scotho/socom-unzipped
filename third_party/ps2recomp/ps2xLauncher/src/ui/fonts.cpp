// Sprint 8 Goal 9: loading the embedded faces, one raster per pixel size in use.
#include "fonts.h"

#include "fonts_embedded/rajdhani_medium.h"
#include "fonts_embedded/rajdhani_semibold.h"
#include "fonts_embedded/saira_stencil_one.h"

#include <cstdio>

namespace ui
{
    namespace
    {
        struct Source
        {
            const unsigned char *data;
            int len;
        };

        Source sourceFor(Face face)
        {
            switch (face)
            {
            case Face::Display:
                return Source{kFont_SairaStencilOne, kFont_SairaStencilOne_len};
            case Face::Bold:
                return Source{kFont_RajdhaniSemiBold, kFont_RajdhaniSemiBold_len};
            default:
                return Source{kFont_RajdhaniMedium, kFont_RajdhaniMedium_len};
            }
        }
    }

    const Font &Fonts::at(Face face, int pixels)
    {
        if (pixels < 6)
            pixels = 6;
        if (pixels > 400)
            pixels = 400;
        const int key = (static_cast<int>(face) << 12) | pixels;
        auto found = m_cache.find(key);
        if (found != m_cache.end())
            return found->second;

        const Source src = sourceFor(face);
        Font font = LoadFontFromMemory(".ttf", src.data, src.len, pixels, nullptr, 0);
        if (font.texture.id == 0 || font.glyphCount == 0)
        {
            // The spec's stop rule: ship the redesign on the default face rather than block it.
            if (!m_warned)
            {
                std::fprintf(stderr, "[launcher] embedded fonts would not load; falling back to the default face\n");
                m_warned = true;
            }
            m_embedded = false;
            font = GetFontDefault();
        }
        else
        {
            // Each raster is drawn at its own size, so bilinear is a 1:1 sample and only softens the
            // sub-pixel remainder; point sampling would alias the glyph stems instead.
            SetTextureFilter(font.texture, TEXTURE_FILTER_BILINEAR);
        }
        return m_cache.emplace(key, font).first->second;
    }

    void Fonts::clear()
    {
        // The destructor can run after CloseWindow() has taken the GL context down; with nothing cached
        // there is nothing to unload, and asking raylib anything at that point is a crash.
        if (m_cache.empty())
            return;
        const Font def = GetFontDefault();
        for (auto &entry : m_cache)
            if (entry.second.texture.id != 0 && entry.second.texture.id != def.texture.id)
                UnloadFont(entry.second);
        m_cache.clear();
    }
}
