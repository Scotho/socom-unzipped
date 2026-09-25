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

        infoRow(ctx, app, rectOf(nodes, "play.disc"), "DISC",
                app.discOk ? app.discMessage : (c.isoPath.empty() ? std::string("no disc image chosen") : app.discMessage),
                app.discOk ? theme::text : theme::bad, "play.disc", Page::Disc);

        char video[160];
        std::snprintf(video, sizeof(video), "%s window, detail %dx, %s filtering", c.windowSize.c_str(),
                      c.gsScale < 1 ? 1 : c.gsScale, c.presentFilter.c_str());
        infoRow(ctx, app, rectOf(nodes, "play.video"), "VIDEO", video, theme::text, "play.video", Page::Video);

        std::string pad = app.pad.present ? app.pad.name : std::string("no controller connected -- keyboard only");
        infoRow(ctx, app, rectOf(nodes, "play.pad"), "CONTROLLER", pad,
                app.pad.present ? theme::text : theme::warn, "play.pad", Page::Controller);

        const std::string server = launcher::effectiveServer(c) + "   as " + (c.profile.empty() ? std::string("player") : c.profile);
        infoRow(ctx, app, rectOf(nodes, "play.server"), "ONLINE", server, theme::text, "play.server", Page::Online);

        // The last run's exit line, between the rows and the button.
        const Rect launch = rectOf(nodes, "play.launch");
        const Rect last = rectOf(nodes, "play.server");
        if (!app.exitLine.empty())
        {
            const Rect line{last.x, last.bottom() + 20.0f, launch.w + 386.0f, 26.0f};
            text(ctx, "LAST RUN", Vec2{line.x, line.y}, 14.0f, theme::dim, Face::Bold);
            const std::string shown = ellipsizeEnd(ctx, app.exitLine, line.w - 96.0f, 17.0f);
            text(ctx, shown.c_str(), Vec2{line.x + 92.0f, line.y - 2.0f}, 17.0f, theme::warn);
        }

        // Task 11: which build LAUNCH will start, and -- under it, where there is room for the whole
        // sentence -- the warning when that build is not the revision the chosen server runs.
        gameVersionRow(ctx, app, nodes, Page::Play);
        const std::string mismatch = revisionMismatchLine(app);
        if (!mismatch.empty())
        {
            const Rect cell = revisionCell(app.frame.window, Page::Play, 0);
            text(ctx, mismatch.c_str(), Vec2{cell.x, cell.bottom() + 6.0f}, metrics::captionSize, theme::warn);
        }

        const std::string blocked = launchBlockedReason(app.discOk, app.running, app.config.isoPath.empty());
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
