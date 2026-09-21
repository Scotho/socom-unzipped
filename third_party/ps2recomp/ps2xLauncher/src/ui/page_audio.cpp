// Sprint 8 Goal 9, the AUDIO page: how loud the game is. (The microphone has a page of its own.)
#include "pages.h"

#include <cstdio>

namespace ui
{
    void drawAudioPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        const Rect r = rectOf(nodes, "audio.volume");
        rowLabel(ctx, r, "VOLUME");

        double volume = static_cast<double>(app.config.audioVolume);
        if (slider(ctx, r, "audio.volume", volume, 0.0, 100.0, 1.0))
        {
            app.config.audioVolume = static_cast<int>(volume + 0.5);
            app.dirty = true;
        }
        char value[32];
        std::snprintf(value, sizeof(value), "%d%%", app.config.audioVolume);
        text(ctx, value, Vec2{r.right() + 18.0f, r.y - 3.0f}, 24.0f, theme::goldHi, Face::Bold);

        caption(ctx, Vec2{r.x, r.bottom() + 44.0f},
                "100% is unity -- the mix the PS2 produced, untouched. Below that the whole mix is attenuated");
        caption(ctx, Vec2{r.x, r.bottom() + 64.0f},
                "before it reaches your sound card, so voices and effects keep their balance.");

        // A quiet scale under the slider, so the number is not the only cue.
        for (int i = 0; i <= 10; ++i)
        {
            const float x = r.x + r.w * (static_cast<float>(i) / 10.0f);
            const bool major = (i % 5) == 0;
            drawLine(ctx, Vec2{x, r.bottom() + 2.0f}, Vec2{x, r.bottom() + (major ? 10.0f : 6.0f)},
                     theme::mix(theme::line, theme::ground, 0.2f), 1.0f);
        }
        text(ctx, "0", Vec2{r.x - 2.0f, r.bottom() + 12.0f}, 14.0f, theme::dim);
        text(ctx, "100", Vec2{r.right() - 22.0f, r.bottom() + 12.0f}, 14.0f, theme::dim);

        // Sprint 10 Q4: the launcher's own cues (the game's HUD sounds, from the player's disc). The row's
        // second line says where they stand: playing, waiting for a disc, or off.
        const Rect sounds = rectOf(nodes, "audio.sounds");
        rowLabel(ctx, sounds, "LAUNCHER");
        if (toggle(ctx, sounds, "Menu sounds from the game (this window's clicks, not the game's mix)", "audio.sounds", app.config.menuSounds))
        {
            app.dirty = true;
            app.requestMenuSounds = true;
        }
        if (!app.menuSoundsStatus.empty())
            caption(ctx, Vec2{sounds.x, sounds.bottom() + 6.0f}, app.menuSoundsStatus.c_str());
    }
}
