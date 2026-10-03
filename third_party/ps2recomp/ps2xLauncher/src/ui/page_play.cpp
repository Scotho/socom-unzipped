// Sprint 8 Goal 9, the PLAY page: what the game is about to do, and the button that does it. A stranger's
// whole path is this page plus DISC once.
#include "pages.h"

#include <cstdio>

namespace ui
{
    namespace
    {
        // One line of state: what it is, what it says, and a CHANGE that jumps to the page that owns it.
        void infoRow(const Ctx &ctx, App &app, Rect r, const char *label, const std::string &value,
                     Rgba valueInk, const std::string &id, Page target)
        {
            const bool live = hovered(ctx, r) || focused(ctx, id);
            fillRect(ctx, r, live ? theme::panelHi : theme::panel);
            strokeRect(ctx, r, live ? theme::gold : theme::line, 2.0f);
            fillRect(ctx, Rect{r.x, r.y, 4.0f, r.h}, live ? theme::goldHi : theme::mix(theme::gold, theme::panel, 0.45f));

            text(ctx, label, Vec2{r.x + 20.0f, r.y + 7.0f}, 15.0f, theme::dim, Face::Bold);
            const std::string shown = ellipsizeEnd(ctx, value, r.w - 180.0f, 21.0f);
            text(ctx, shown.c_str(), Vec2{r.x + 20.0f, r.y + 26.0f}, 21.0f, valueInk);

            const Rect change{r.right() - 122.0f, r.y + 12.0f, 104.0f, 32.0f};
            strokeRect(ctx, change, live ? theme::gold : theme::line, 2.0f);
            textCenteredIn(ctx, "CHANGE", change, 15.0f, live ? theme::goldHi : theme::dim, Face::Bold);

            // Asked for, not done: the page changes in the next frame's input phase (focus.h, Nav::request).
            if (hit(ctx, r, id))
                app.nav.request(target);
        }
    }

    void drawPlayPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        const launcher::Config &c = app.config;
        const bool pcsx2 = app.mode == launcher::ClientMode::Pcsx2;
        // Sprint 18 T6: every CHANGE goes where playRows says -- the table the layout was built from, so a row can never
        // jump to a page outside its client's rail (the T5 review's item 1; Nav::applyRequest drops one anyway).
        const std::vector<std::pair<std::string, Page>> rows = playRows(app.mode);
        auto targetOf = [&rows](const char *id)
        {
            for (const auto &row : rows)
                if (row.first == id)
                    return row.second;
            return Page::Play;
        };

        const std::string &iso = activeIsoPath(app);   // Sprint 18 T6: the active client's disc (R-A)
        infoRow(ctx, app, rectOf(nodes, "play.disc"), "DISC",
                app.discOk ? app.discMessage : (iso.empty() ? std::string("no disc image chosen") : app.discMessage),
                app.discOk ? theme::text : theme::bad, "play.disc", targetOf("play.disc"));

        if (pcsx2)
        {
            // Sprint 18 T6: the PCSX2 view's rows read config.pcsx2.json and the PCSX2 probe, never config.json (R-A):
            // the server PCSX2's DNS will point at, the game version, and which PCSX2 LAUNCH starts.
            infoRow(ctx, app, rectOf(nodes, "play.server"), "SERVER", launcher::pcsx2EffectiveServer(app.pcsx2), theme::text,
                    "play.server", targetOf("play.server"));
            const launcher::GameRevision *rev = launcher::findGameRevision(launcher::normalizeGameRevision(app.pcsx2.gameRevision));
            infoRow(ctx, app, rectOf(nodes, "play.version"), "GAME VERSION", rev != nullptr ? rev->label : app.pcsx2.gameRevision,
                    theme::text, "play.version", targetOf("play.version"));
            const Pcsx2Status &st = app.pcsx2Status;
            const bool found = st.exeFound && !st.versionLine.empty();
            infoRow(ctx, app, rectOf(nodes, "play.pcsx2"), "PCSX2", found ? st.versionLine : std::string("none"),
                    found ? theme::text : theme::warn, "play.pcsx2", targetOf("play.pcsx2"));
        }
        else
        {
            char video[160];
            std::snprintf(video, sizeof(video), "%s window, detail %dx, %s filtering", c.windowSize.c_str(),
                          c.gsScale < 1 ? 1 : c.gsScale, c.presentFilter.c_str());
            infoRow(ctx, app, rectOf(nodes, "play.video"), "VIDEO", video, theme::text, "play.video", targetOf("play.video"));

            std::string pad = app.pad.present ? app.pad.name : std::string("no controller connected -- keyboard only");
            infoRow(ctx, app, rectOf(nodes, "play.pad"), "CONTROLLER", pad,
                    app.pad.present ? theme::text : theme::warn, "play.pad", targetOf("play.pad"));

            const std::string server = launcher::effectiveServer(c) + "   as " + (c.profile.empty() ? std::string("player") : c.profile);
            infoRow(ctx, app, rectOf(nodes, "play.server"), "ONLINE", server, theme::text, "play.server", targetOf("play.server"));
        }

        // The last run's exit line, between the rows and the button.
        const Rect launch = rectOf(nodes, "play.launch");
        const Rect last = rectOf(nodes, rows.back().first);
        if (!app.exitLine.empty())
        {
            const Rect line{last.x, last.bottom() + 20.0f, launch.w + 386.0f, 26.0f};
            text(ctx, "LAST RUN", Vec2{line.x, line.y}, 14.0f, theme::dim, Face::Bold);
            const std::string shown = ellipsizeEnd(ctx, app.exitLine, line.w - 96.0f, 17.0f);
            text(ctx, shown.c_str(), Vec2{line.x + 92.0f, line.y - 2.0f}, 17.0f, theme::warn);
        }

        // Task 11: which build LAUNCH will start, and -- under it, where there is room for the whole
        // sentence -- the warning when that build is not the revision the chosen server runs.
        // Sprint 18 T6: in the PCSX2 view GAME VERSION is a row above and r0001 the one version on offer (R-E), so the
        // selector's place says what LAUNCH does instead.
        if (pcsx2)
        {
            const Rect cell = revisionCell(app.frame.window, Page::Play, 0);
            if (drawable(cell))
                text(ctx, "LAUNCH starts PCSX2 on your disc", Vec2{cell.x, cell.y + 4.0f}, metrics::labelSize, theme::dim,
                     Face::Bold, 0.06f);
        }
        else
            gameVersionRow(ctx, app, nodes, Page::Play);
        const std::string mismatch = revisionMismatchLine(app);
        if (!mismatch.empty())
        {
            const Rect cell = revisionCell(app.frame.window, Page::Play, 0);
            text(ctx, mismatch.c_str(), Vec2{cell.x, cell.bottom() + 6.0f}, metrics::captionSize, theme::warn);
        }

        const std::string blocked = launchBlockedNow(app);   // Sprint 18 T6: the active client's reason
        if (button(ctx, launch, app.running ? "RUNNING" : "LAUNCH", "play.launch", blocked.empty(), true))
            app.requestLaunch = true;
        if (!blocked.empty())
            text(ctx, blocked.c_str(), Vec2{launch.x, launch.y - 24.0f}, 16.0f, app.running ? theme::warn : theme::bad);

        if (button(ctx, rectOf(nodes, "play.diagnostics"), "SAVE DIAGNOSTICS", "play.diagnostics"))
            app.requestDiagnostics = true;
        if (button(ctx, rectOf(nodes, "play.logs"), "OPEN LOGS", "play.logs"))
            app.requestOpenLogs = true;
    }
}
