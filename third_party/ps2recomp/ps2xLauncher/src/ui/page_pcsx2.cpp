// Sprint 18 T5, the PCSX2 page (R341 = R-C, R344 = R-F): which PCSX2 the launcher drives -- one the player SELECTs, or
// the official release INSTALL downloads -- its version, where it reads the BIOS from, and the one sentence that says
// everything else (video, audio, the pad, the BIOS itself) is PCSX2's own. The page reads App and raises requests;
// main.cpp does the browsing, the download and the folder.
#include "pages.h"

#include <string>

namespace ui
{
    namespace
    {
        // A read-only field: the path INSTALL or SELECT left, or what to do when there is none. Not a control (there
        // is nothing to type), so it is drawn, not focused.
        void pathField(const Ctx &ctx, Rect r, const std::string &path)
        {
            if (!drawable(r))
                return;
            fillRect(ctx, r, theme::alpha(theme::panel, 200));
            strokeRect(ctx, r, theme::alpha(theme::line, 160), 1.5f);
            const Rect inner{r.x + 12.0f, r.y, r.w - 24.0f, r.h};
            const float size = metrics::bodySize - 2.0f;
            const float y = r.y + (r.h - size * 1.2f) * 0.5f;
            if (path.empty())
                text(ctx, ellipsizeEnd(ctx, "none -- SELECT one, or INSTALL the official release", inner.w, size).c_str(),
                     Vec2{inner.x, y}, size, theme::dim);
            else
                text(ctx, ellipsizeStart(ctx, path, inner.w, size).c_str(), Vec2{inner.x, y}, size, theme::text);
        }

        // Wrapped caption lines from `y`; answers the y under the last line.
        float paragraph(const Ctx &ctx, Rect box, float y, const char *s)
        {
            for (const std::string &line : wrapText(ctx, s, box.w, metrics::captionSize))
            {
                if (y + metrics::captionSize * 1.2f > box.bottom())
                    break;
                text(ctx, line.c_str(), Vec2{box.x, y}, metrics::captionSize, theme::caption);
                y += metrics::captionSize * 1.3f;
            }
            return y;
        }
    }

    void drawPcsx2Page(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        const Pcsx2Rows r = pcsx2Rows(app.frame.window);
        const Pcsx2Status &st = app.pcsx2Status;
        const Pcsx2InstallUi &install = app.install;

        // INSTANCE: the exe, SELECT, INSTALL. INSTALL is not a node while a download runs; it is drawn greyed there.
        rowLabel(ctx, r.path, "INSTANCE");
        pathField(ctx, r.path, app.pcsx2.pcsx2Exe);
        if (button(ctx, rectOf(nodes, "pcsx2.select"), "SELECT...", "pcsx2.select", !install.running()))
            app.requestBrowsePcsx2 = true;
        if (hasNode(nodes, "pcsx2.install"))
        {
            if (button(ctx, rectOf(nodes, "pcsx2.install"), "INSTALL", "pcsx2.install", !install.running()))
                app.requestInstallPcsx2 = true;
        }
        else
            button(ctx, r.install, "INSTALL", "pcsx2.install", false);

        // INSTALL's progress and its sentence, under the row it belongs to.
        if (install.state != Pcsx2InstallUi::State::Idle && drawable(r.progress))
        {
            float y = r.progress.y;
            if (install.state == Pcsx2InstallUi::State::Downloading && install.total > 0)
            {
                const float fraction = static_cast<float>(static_cast<double>(install.bytes) / static_cast<double>(install.total));
                meterBar(ctx, Rect{r.progress.x, y, r.progress.w, 8.0f}, fraction > 1.0f ? 1.0f : fraction,
                         theme::mix(theme::lampGreen, theme::panel, 0.22f));
            }
            y += 14.0f;
            const bool failed = install.state == Pcsx2InstallUi::State::Failed;
            const Rgba ink = failed ? theme::warn : (install.state == Pcsx2InstallUi::State::Done ? theme::lampGreen : theme::caption);
            text(ctx, ellipsizeEnd(ctx, install.message, r.progress.w, metrics::captionSize).c_str(), Vec2{r.progress.x, y},
                 metrics::captionSize, ink);
        }

        // VERSION: the marker INSTALL wrote, or "your own copy".
        rowLabel(ctx, r.version, "VERSION");
        {
            const float size = metrics::bodySize - 2.0f;
            const float y = r.version.y + (r.version.h - size * 1.2f) * 0.5f;
            if (st.exeFound && !st.versionLine.empty())
                text(ctx, ellipsizeEnd(ctx, st.versionLine, r.version.w, size).c_str(), Vec2{r.version.x, y}, size, theme::text);
            else
                text(ctx, app.pcsx2.pcsx2Exe.empty() ? "none yet" : "that pcsx2-qt.exe is not there any more",
                     Vec2{r.version.x, y}, size, app.pcsx2.pcsx2Exe.empty() ? theme::dim : theme::warn);
        }

        // BIOS: where PCSX2 reads it, and whether anything is there yet. The dump is the player's (R-F).
        rowLabel(ctx, r.bios, "BIOS");
        {
            const float size = metrics::bodySize - 2.0f;
            std::string line;
            Rgba ink = theme::text;
            if (st.biosDir.empty())
            {
                line = "SELECT or INSTALL PCSX2 first";
                ink = theme::dim;
            }
            else if (st.biosFiles > 0)
                line = std::to_string(st.biosFiles) + (st.biosFiles == 1 ? " file in " : " files in ") + st.biosDir;
            else
            {
                line = "none yet: put your PS2 BIOS dump in this folder";
                ink = theme::warn;
            }
            const bool twoLines = !st.biosDir.empty() && st.biosFiles == 0;
            text(ctx, (st.biosFiles > 0 ? ellipsizeStart(ctx, line, r.bios.w, size) : ellipsizeEnd(ctx, line, r.bios.w, size)).c_str(),
                 Vec2{r.bios.x, twoLines ? r.bios.y : r.bios.y + (r.bios.h - size * 1.2f) * 0.5f}, size, ink);
            if (twoLines)
                text(ctx, ellipsizeStart(ctx, st.biosDir, r.bios.w, metrics::captionSize - 1.0f).c_str(),
                     Vec2{r.bios.x, r.bios.y + size * 1.2f}, metrics::captionSize - 1.0f, theme::caption);
        }
        if (button(ctx, rectOf(nodes, "pcsx2.bios.open"), "OPEN FOLDER", "pcsx2.bios.open", !st.biosDir.empty()))
            app.requestOpenBios = true;

        // What PCSX2 owns, and whose PCSX2 it is.
        {
            float y = r.captions.y;
            y = paragraph(ctx, r.captions, y,
                          "PCSX2 keeps its own video, audio, controller and BIOS settings: open PCSX2 and use its Settings menu. "
                          "The launcher writes only its network section and the SOCOM II patch.");
            paragraph(ctx, r.captions, y + 8.0f,
                      "PCSX2 is free software (GPL v3) by the PCSX2 team, github.com/PCSX2/pcsx2. INSTALL downloads their "
                      "official release; nothing of it ships with SOCOM Unzipped.");
        }

        // ADVANCED: the network adapter PCSX2 binds (EthDevice). The launcher picks one; the player may cycle it.
        const bool open = hasNode(nodes, "pcsx2.adapter");
        if (advancedHeader(ctx, rectOf(nodes, "pcsx2.advanced"), "pcsx2.advanced", open, false))
            app.advancedOpen = !app.advancedOpen;
        if (open)
        {
            const Rect adapter = rectOf(nodes, "pcsx2.adapter");
            rowLabel(ctx, adapter, "NETWORK ADAPTER");
            const std::string label = st.adapterName.empty() ? std::string("none found") : st.adapterName;
            if (button(ctx, adapter, ellipsizeEnd(ctx, label, adapter.w - 24.0f, metrics::labelSize + 1.0f, Face::Bold).c_str(),
                       "pcsx2.adapter", !st.adapters.empty()) &&
                !st.adapters.empty())
            {
                // The next adapter after the one shown, round the list.
                const std::string current = launcher::pcsx2install::pickAdapter(st.adapters, app.pcsx2.ethDevice);
                size_t at = 0;
                for (size_t i = 0; i < st.adapters.size(); ++i)
                    if (st.adapters[i].guid == current)
                        at = i;
                const launcher::pcsx2install::Adapter &next = st.adapters[(at + 1) % st.adapters.size()];
                app.pcsx2.ethDevice = next.guid;
                app.pcsx2Status.adapterName = next.name;
                app.pcsx2Dirty = true;
            }
            caption(ctx, Vec2{adapter.x, adapter.bottom() + 10.0f},
                    "PCSX2's network uses this adapter. Press to bind the next one; the one with a gateway is picked by default.");
        }
    }
}
