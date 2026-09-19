// Sprint 8 Goal 9, the ONLINE page: which server, whose profile, and the second instance for testing.
#include "pages.h"

namespace ui
{
    void drawOnlinePage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        launcher::Config &c = app.config;

        const Rect preset0 = rectOf(nodes, "online.preset.0");
        text(ctx, "SERVER", Vec2{preset0.x, preset0.y - 26.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);

        int presetSel = 2;   // "Custom" unless one of the ids matches
        for (int i = 0; i < 3; ++i)
            if (c.serverPreset == launcher::kServerPresets[i].id && launcher::presetAvailable(launcher::kServerPresets[i]))
                presetSel = i;
        for (int i = 0; i < 3; ++i)
        {
            const std::string id = "online.preset." + std::to_string(i);
            const bool available = launcher::presetAvailable(launcher::kServerPresets[i]);
            const Rect r = available ? rectOf(nodes, id) : onlinePresetRow(app.frame.window, i);
            if (!available)
            {
                // Drawn, but not on offer: the community server runs a game revision this client cannot
                // play, and a preset the player cannot use must say so rather than fail at launch.
                const Rgba off = theme::mix(theme::dim, theme::ground, 0.45f);
                strokeRect(ctx, Rect{r.x + 6.0f, r.cy() - 5.0f, 10.0f, 10.0f}, off, 2.0f);
                text(ctx, launcher::kServerPresets[i].label, Vec2{r.x + 34.0f, r.cy() - metrics::bodySize * 0.58f},
                     metrics::bodySize - 1.0f, off);
                textRightIn(ctx, "needs the r0004 game update -- planned", Rect{r.x, r.y, r.w - 12.0f, r.h},
                            metrics::captionSize - 1.0f, off);
                continue;
            }
            if (listRow(ctx, r, launcher::kServerPresets[i].label, id, i == presetSel) && i != presetSel)
            {
                c.serverPreset = launcher::kServerPresets[i].id;
                app.dirty = true;
                if (app.activeField == "online.server")
                    app.activeField.clear();   // the preset took the field away mid-edit
            }
            textRightIn(ctx, launcher::kServerPresets[i].note, Rect{r.x, r.y, r.w - 12.0f, r.h},
                        metrics::captionSize - 1.0f,
                        i == presetSel ? theme::caption : theme::mix(theme::caption, theme::ground, 0.3f));
        }

        const launcher::ServerPreset *preset = launcher::findServerPreset(c.serverPreset);
        const bool ownAddress = preset == nullptr || preset->address[0] == '\0';

        const Rect profile = rectOf(nodes, "online.profile");
        const Rect address = ownAddress ? rectOf(nodes, "online.server")
                                        : Rect{profile.x, profile.y - 56.0f, 420.0f, 40.0f};
        rowLabel(ctx, address, "ADDRESS");
        bool changed = false;
        if (ownAddress)
        {
            textField(ctx, address, c.server, "online.server", changed);
        }
        else
        {
            std::string shown = preset->address;
            textField(ctx, address, shown, "online.server", changed, false);
        }

        rowLabel(ctx, profile, "PROFILE");
        textField(ctx, profile, c.profile, "online.profile", changed);
        caption(ctx, Vec2{profile.right() + 18.0f, profile.y + 12.0f}, "picks cards/<profile> for the memory card");

        const Rect second = rectOf(nodes, "online.second");
        if (toggle(ctx, second, "Second instance on this machine (for testing)", "online.second", c.secondInstance))
            changed = true;
        caption(ctx, Vec2{second.x, second.bottom() + 10.0f},
                "A second instance shifts its UDP ports and uses its own card directory, so two copies can play here.");

        if (changed)
            app.dirty = true;
    }
}
