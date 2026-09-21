// Sprint 8 Goal 9, the ONLINE page: which server, whose profile, and the second instance for testing.
#include "pages.h"

namespace ui
{
    void drawOnlinePage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        launcher::Config &c = app.config;

        // The first ROW, not the first node: a preset that cannot be played has a row but no node, and the
        // community one is first -- rectOf() answered an empty rect and this heading was drawn off the window.
        const Rect preset0 = onlinePresetRow(app.frame.window, 0);
        text(ctx, "SERVER", Vec2{preset0.x, preset0.y - 26.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
        // Sprint 9 Goal 8: the hosted server's own word on itself (GET /api/stats, fetched off this thread).
        // Blank when the site cannot be reached: a player who is offline is not told anything is wrong.
        if (!app.serverStatus.empty())
        {
            const bool up = app.serverStatus.find(": online") != std::string::npos;
            const float size = metrics::captionSize;
            const float w = textWidth(ctx, app.serverStatus.c_str(), size);
            const float right = app.frame.body.right();
            fillCircle(ctx, Vec2{right - w - 12.0f, preset0.y - 17.0f}, 4.0f, up ? theme::lampGreen : theme::warn);
            text(ctx, app.serverStatus.c_str(), Vec2{right - w, preset0.y - 26.0f}, size, up ? theme::text : theme::caption);
        }

        // "Custom" -- the one with no address -- unless one of the ids matches.
        int presetSel = static_cast<int>(launcher::kServerPresetCount) - 1;
        for (size_t i = 0; i < launcher::kServerPresetCount; ++i)
            if (c.serverPreset == launcher::kServerPresets[i].id && launcher::presetAvailable(launcher::kServerPresets[i]))
                presetSel = static_cast<int>(i);
        for (int i = 0; i < static_cast<int>(launcher::kServerPresetCount); ++i)
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
                                        : Rect{profile.x, profile.y - kOnlineRowPitch, 420.0f, 40.0f};
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

        // Sprint 10 Goal 9: the persona and its password, capped where the game's own keyboards cap them
        // (research/38), the password masked (R179: plain in config.json, never on screen). Empty = the game
        // asks on its keyboard, as it always did; filled = the keyboard opens already typed (R180).
        const Rect name = rectOf(nodes, "online.name");
        rowLabel(ctx, name, "PLAYER NAME");
        textField(ctx, name, c.loginName, "online.name", changed, true, launcher::kLoginNameCap);
        caption(ctx, Vec2{name.right() + 18.0f, name.y + 12.0f}, "the persona; empty = the game asks");
        const Rect password = rectOf(nodes, "online.password");
        rowLabel(ctx, password, "PASSWORD");
        textField(ctx, password, c.loginPassword, "online.password", changed, true, launcher::kLoginPasswordCap, true);
        caption(ctx, Vec2{password.right() + 18.0f, password.y + 12.0f}, "kept in config.json, plain; masked here");

        // Sprint 9 P4: everything above is a stranger's first run; everything below the rule is not. The
        // second instance is a testing tool -- it starts a whole second copy of the game -- so it lives
        // behind the disclosure rather than under the profile field a new player has just filled in.
        const bool forced = advancedForced(c);
        if (advancedHeader(ctx, rectOf(nodes, "online.advanced"), "online.advanced", app.advancedOpen || forced, forced))
            app.advancedOpen = !app.advancedOpen;

        // Shut, the toggle is not in the node list at all, so there is nothing to look up and nothing to
        // draw -- `hasNode` rather than a rect test, because absence is the point.
        if (hasNode(nodes, "online.second"))
        {
            const Rect second = rectOf(nodes, "online.second");
            if (toggle(ctx, second, "Second instance on this machine (for testing)", "online.second", c.secondInstance))
                changed = true;
            caption(ctx, Vec2{second.x, second.bottom() + 10.0f},
                    "A second instance shifts its UDP ports and uses its own card directory, so two copies can play here.");
        }

        if (changed)
            app.dirty = true;
    }
}
