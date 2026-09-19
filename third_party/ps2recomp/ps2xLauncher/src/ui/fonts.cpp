// Sprint 8 Goal 9: loading the embedded faces.
#include "fonts.h"

#include "fonts_embedded/rajdhani_medium.h"
#include "fonts_embedded/rajdhani_semibold.h"
#include "fonts_embedded/saira_stencil_one.h"

#include <cstdio>

namespace ui
{
    namespace
    {
        // Twice the largest size the design asks for at scale 1.0: the wordmark is 40 units, body text tops
        // out at 26. Anything the scale factor asks for above that is a downscale of a bigger glyph, which is
        // what the bilinear filter is for.
        constexpr int kDisplayPx = 80;
        constexpr int kBodyPx = 52;

        Font loadOne(const unsigned char *data, int len, int px)
        {
            Font f = LoadFontFromMemory(".ttf", data, len, px, nullptr, 0);
            if (f.texture.id == 0 || f.glyphCount == 0)
                return Font{};
            SetTextureFilter(f.texture, TEXTURE_FILTER_BILINEAR);
            return f;
        }
    }

    Fonts loadFonts()
    {
        Fonts fonts;
        fonts.display = loadOne(kFont_SairaStencilOne, kFont_SairaStencilOne_len, kDisplayPx);
        fonts.body = loadOne(kFont_RajdhaniMedium, kFont_RajdhaniMedium_len, kBodyPx);
        fonts.bodyBold = loadOne(kFont_RajdhaniSemiBold, kFont_RajdhaniSemiBold_len, kBodyPx);
        fonts.embedded = fonts.display.texture.id != 0 && fonts.body.texture.id != 0 && fonts.bodyBold.texture.id != 0;
        if (!fonts.embedded)
        {
            // The spec's stop rule: ship the redesign on the default face rather than block it.
            std::fprintf(stderr, "[launcher] embedded fonts would not load; falling back to the default face\n");
            unloadFonts(fonts);
            fonts.display = GetFontDefault();
            fonts.body = GetFontDefault();
            fonts.bodyBold = GetFontDefault();
            fonts.embedded = false;
        }
        return fonts;
    }

    void unloadFonts(Fonts &fonts)
    {
        const Font def = GetFontDefault();
        if (fonts.display.texture.id != 0 && fonts.display.texture.id != def.texture.id)
            UnloadFont(fonts.display);
        if (fonts.body.texture.id != 0 && fonts.body.texture.id != def.texture.id)
            UnloadFont(fonts.body);
        if (fonts.bodyBold.texture.id != 0 && fonts.bodyBold.texture.id != def.texture.id)
            UnloadFont(fonts.bodyBold);
        fonts.display = Font{};
        fonts.body = Font{};
        fonts.bodyBold = Font{};
    }
}
