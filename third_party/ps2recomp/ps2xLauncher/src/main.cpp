// SOCOM Unzipped launcher (Task 8b, packaging outline section 3; redesigned in Sprint 8 Goal 9): one window
// that owns config.json, verifies the disc image, shows what the game will read from the controller, and
// starts socom2.exe with the PS2X_* environment.
// raylib on purpose: the controller page calls the same functions the game's input poll does.
//
//   socom_unzipped_launcher.exe              the window
//   socom_unzipped_launcher.exe --selftest   load config.json, verify the ISO if one is set, print the environment, exit
//   socom_unzipped_launcher.exe --screenshot <dir>   every page at both sizes, on a fixed fake state, as PNGs
//   socom_unzipped_launcher.exe --diagnostics <out.zip> [dir]   write the diagnostics zip for <dir> (default: this folder), no window
//   socom_unzipped_launcher.exe --report-bug <form.json> [dir]   send one bug report for <dir>, print the reply, no window
//                                                                (a PROOF unless the form says "test": false)
//   socom_unzipped_launcher.exe --server-status                  print the hosted server's status line, no window
//
// This file is setup, the loop and the page dispatch. Everything drawn lives in src/ui/.
#include "launcher/bug_report.h"
#include "launcher/diagnostics.h"
#include "launcher/iso9660.h"
#include "launcher/launcher_config.h"
#include "launcher/launcher_layout.h"
#include "launcher/mic_devices.h"
#include "launcher/sha256.h"
#include "ps2x/exe_dir.h"
#include "ps2x/zip_store.h"
#include "win32_glue.h"

#include "ui/chrome.h"
#include "ui/fonts.h"
#include "ui/focus.h"
#include "ui/glyphs.h"
#include "ui/pad_input.h"
#include "ui/pad_render.h"
#include "ui/pages.h"
#include "ui/theme.h"
#include "ui/widgets.h"

#include "raylib.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <functional>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;

namespace
{
    // What the Win32 window procedure needs to answer WM_NCHITTEST between frames. The system asks in real
    // pixels, the UI works in screen units, so the scale it is asked with carries the DPI factor too.
    float g_uiScale = 1.0f;
    float g_uiDpi = 1.0f;
    bool g_uiMaximized = false;
    bool g_nativeChrome = false;

    int chromeHitForSystem(int x, int y, int w, int h)
    {
        return static_cast<int>(ui::chromeHitTest(x, y, w, h, g_uiScale * g_uiDpi, g_uiMaximized));
    }

    std::string readText(const fs::path &p)
    {
        std::ifstream in(p, std::ios::binary);
        if (!in)
            return {};
        std::stringstream ss;
        ss << in.rdbuf();
        return ss.str();
    }

    // The first `maxBytes` of a file: the run log's head, where the boot lines (GL, audio, notices) are.
    std::string readHead(const fs::path &p, size_t maxBytes)
    {
        std::ifstream in(p, std::ios::binary);
        if (!in)
            return {};
        std::string out(maxBytes, '\0');
        in.read(out.data(), static_cast<std::streamsize>(maxBytes));
        out.resize(static_cast<size_t>(in.gcount()));
        return out;
    }

    bool writeText(const fs::path &p, const std::string &text)
    {
        std::ofstream out(p, std::ios::binary | std::ios::trunc);
        if (!out)
            return false;
        out << text;
        return static_cast<bool>(out);
    }

    // The disc check: SCUS_972.75 in the root directory, hashed against the pinned r0001 digest.
    struct DiscStatus
    {
        bool checked = false;
        bool ok = false;
        std::string message;
    };

    DiscStatus checkDisc(const std::string &isoPath)
    {
        DiscStatus st;
        st.checked = true;
        if (isoPath.empty())
        {
            st.message = "choose the SOCOM II ISO";
            return st;
        }
        iso9660::Reader read = iso9660::fileReader(isoPath);
        if (!read)
        {
            st.message = "cannot open the file";
            return st;
        }
        iso9660::FileEntry e;
        if (!iso9660::findRootFile(read, launcher::kSocom2ElfName, e))
        {
            st.message = "not a SOCOM II disc image (no SCUS_972.75)";
            return st;
        }
        std::vector<uint8_t> bytes;
        if (!iso9660::readFile(read, e, bytes))
        {
            st.message = "cannot read SCUS_972.75";
            return st;
        }
        const std::string digest = sha256::hex(bytes.data(), bytes.size());
        if (digest != launcher::kSocom2R0001ElfSha256)
        {
            st.message = "not SOCOM II NTSC r0001 (SCUS_972.75 differs)";
            return st;
        }
        st.ok = true;
        st.message = "SOCOM II U.S. Navy SEALs NTSC r0001";
        return st;
    }

    // The newest logs/run_<stamp>.log by name (the stamp sorts), for a launcher that has not started a
    // game this session -- or a game that was double-clicked (the bare run writes the same names).
    std::string newestRunLog(const fs::path &logs)
    {
        std::string best;
        std::error_code ec;
        for (fs::directory_iterator it(logs, ec), end; !ec && it != end; it.increment(ec))
        {
            const std::string name = it->path().filename().string();
            if (name.rfind("run_", 0) == 0 && it->path().extension() == ".log" && name > best)
                best = name;
        }
        return best.empty() ? std::string() : (logs / best).string();
    }

    std::string homeDirectory();   // USERPROFILE, else HOME (defined with the bug report's helpers below)

    // "Save diagnostics": one zip -- the last log, config.json through the allowlist, the GL lines, the
    // crash record if any, versions (launcher/diagnostics.h). `outZip` empty = diagnostics/ under `home`.
    // The log goes in whole: diagnostics::entries() is what clips it to its head and tail and scrubs the
    // home directory out of every entry, and it must see the real byte count to say how much it dropped.
    bool saveDiagnostics(const fs::path &home, const fs::path &outZip, const std::string &lastLog,
                         bool haveLastExit, long long lastExit, std::string &message)
    {
        namespace diag = launcher::diagnostics;
        const std::string stamp = win32glue::stamp();
        const fs::path out = outZip.empty() ? home / "diagnostics" / ("socom_unzipped_" + stamp + ".zip") : outZip;
        std::error_code ec;
        if (out.has_parent_path())
            fs::create_directories(out.parent_path(), ec);

        diag::Inputs in;
        const std::string log = (!lastLog.empty() && fs::exists(lastLog)) ? lastLog : newestRunLog(home / "logs");
        if (!log.empty())
        {
            in.logName = fs::path(log).filename().string();
            in.logText = readText(log);
        }
        in.configText = readText(home / "config.json");
        in.version = readText(home / "version.txt");
        while (!in.version.empty() && (in.version.back() == '\n' || in.version.back() == '\r'))
            in.version.pop_back();
        in.platform = ExeDir::platformName();
        in.homeDir = homeDirectory();
        in.haveLastExit = haveLastExit;
        in.lastExit = lastExit;

        uint16_t date = 0x0021, time = 0;
        ZipStore::dosDateTime(stamp, date, time);
        const std::string bytes = ZipStore::build(diag::entries(in), date, time);
        std::ofstream file(out, std::ios::binary | std::ios::trunc);
        if (bytes.empty() || !file)
        {
            message = "cannot write " + out.string();
            return false;
        }
        file.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
        file.flush();
        if (!file)
        {
            message = "cannot write " + out.string();
            return false;
        }
        message = "saved " + out.string();
        return true;
    }

    // ---- Sprint 9 Goal 8: the bug report and the server's status line ----------------------------------------
    namespace br = launcher::bugreport;

    std::string homeDirectory()
    {
        const char *homeDir = std::getenv("USERPROFILE");
        if (homeDir == nullptr || *homeDir == '\0')
            homeDir = std::getenv("HOME");
        return homeDir ? homeDir : "";
    }

    // The log as the report needs it: the head (where the GL lines are) and the tail (what went wrong, and
    // what is attached), without reading a gigabyte to get them.
    std::string readLogForReport(const fs::path &p)
    {
        constexpr size_t kHead = 256u * 1024u, kTail = 256u * 1024u;
        std::error_code ec;
        const uintmax_t size = fs::file_size(p, ec);
        if (ec)
            return {};
        if (size <= kHead + kTail)
            return readText(p);
        std::ifstream in(p, std::ios::binary);
        if (!in)
            return {};
        std::string tail(kTail, '\0');
        in.seekg(static_cast<std::streamoff>(size - kTail));
        in.read(tail.data(), static_cast<std::streamsize>(kTail));
        tail.resize(static_cast<size_t>(in.gcount()));
        return launcher::diagnostics::joinClipped(readHead(p, kHead), tail, size - kHead - kTail);
    }

    br::Inputs reportInputs(const fs::path &home, const std::string &lastLog, bool haveLastExit, long long lastExit)
    {
        br::Inputs in;
        in.version = readText(home / "version.txt");
        while (!in.version.empty() && (in.version.back() == '\n' || in.version.back() == '\r'))
            in.version.pop_back();
        in.platform = ExeDir::platformName();
        in.homeDir = homeDirectory();
        const std::string log = (!lastLog.empty() && fs::exists(lastLog)) ? lastLog : newestRunLog(home / "logs");
        if (!log.empty())
            in.logText = readLogForReport(log);
        in.haveLastExit = haveLastExit;
        in.lastExit = lastExit;
        return in;
    }

    std::string apiUrl(const char *path)
    {
        return br::apiBase(std::getenv(br::kApiBaseEnv)) + path;
    }

    struct ReportOutcome
    {
        br::Reply reply;
        std::string savedPath;        // set when the report was written to logs/ instead
        std::string transportError;   // for stderr; never shown as the reason on the page
    };

    // Blocking: the POST, and on anything but a receipt or a field to fix, the file. Runs on the worker
    // thread (the page) or on the main one (--report-bug).
    ReportOutcome sendReport(const fs::path &home, const std::string &json)
    {
        ReportOutcome out;
        const win32glue::HttpResult http = win32glue::httpRequest("POST", apiUrl(br::kBugsPath), json, 15000);
        out.transportError = http.error;
        out.reply = br::parseReply(http.status, http.body, http.retryAfter);
        if (out.reply.kind == br::Reply::Kind::Failed || out.reply.kind == br::Reply::Kind::RateLimited)
        {
            std::error_code ec;
            fs::create_directories(home / "logs", ec);
            const fs::path file = home / "logs" / br::savedFileName(win32glue::stamp());
            if (writeText(file, json))
                out.savedPath = file.string();
        }
        return out;
    }

    // GET /api/stats -> the body, or "" when there was no 200. Blocking; the page runs it on a worker.
    std::string fetchStats()
    {
        const win32glue::HttpResult http = win32glue::httpRequest("GET", apiUrl(br::kStatsPath), std::string(), 4000);
        return http.status == 200 ? http.body : std::string();
    }

    // One request at a time, off the UI thread. The UI thread starts it and polls the slot; nothing else is
    // shared. join() waits for the request's own timeout at most, so closing the launcher mid-send neither
    // crashes (the thread never outlives what it writes to) nor hangs for longer than that.
    template <typename T>
    class Worker
    {
    public:
        ~Worker() { join(); }
        bool busy() const { return m_busy; }
        void start(std::function<T()> fn)
        {
            join();
            m_busy = true;
            m_done = false;
            m_thread = std::thread([this, fn]()
            {
                T result{};
                try
                {
                    result = fn();
                }
                catch (...)
                {
                }
                std::lock_guard<std::mutex> lock(m_mutex);
                m_result = std::move(result);
                m_done = true;
            });
        }
        bool poll(T &out)
        {
            if (!m_busy)
                return false;
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                if (!m_done)
                    return false;
            }
            m_thread.join();
            m_busy = false;
            out = std::move(m_result);
            return true;
        }
        void join()
        {
            if (m_thread.joinable())
                m_thread.join();
            m_busy = false;
        }

    private:
        std::thread m_thread;
        std::mutex m_mutex;
        bool m_done = false;
        bool m_busy = false;
        T m_result{};
    };

    int exitCodeFor(const br::Reply &reply)
    {
        switch (reply.kind)
        {
        case br::Reply::Kind::Sent: return 0;
        case br::Reply::Kind::FieldError: return 2;
        case br::Reply::Kind::RateLimited: return 3;
        case br::Reply::Kind::Failed: return 4;
        }
        return 4;
    }

    // --report-bug <form.json> [dir]: one report, built exactly as the page builds it, and the reply's line.
    int reportBugHeadless(const fs::path &formFile, const fs::path &home)
    {
        br::Form form;
        if (!br::formFromJson(readText(formFile), form))
        {
            std::printf("cannot read the form file %s\n", formFile.string().c_str());
            return 5;
        }
        const std::string problem = br::checkForm(form);
        if (!problem.empty())
        {
            std::printf("NOT SENT. %s\n", problem.c_str());
            return 2;
        }
        launcher::Config config;
        launcher::fromJson(readText(home / "config.json"), config);
        const br::Payload payload = br::build(config, form, reportInputs(home, std::string(), false, 0));
        std::printf("%s\n", br::previewLine(payload, form).c_str());
        const ReportOutcome outcome = sendReport(home, payload.json);
        if (!outcome.transportError.empty())
            std::fprintf(stderr, "[report] %s\n", outcome.transportError.c_str());
        std::printf("%s\n", outcome.reply.text.c_str());
        if (!outcome.savedPath.empty())
            std::printf("%s\n", br::savedLocallyLine(outcome.savedPath).c_str());
        return exitCodeFor(outcome.reply);
    }

    // ---- the chrome around the pages ----------------------------------------------------------------------

    // ---- the launcher's own title bar (there is no OS caption above it) -----------------------------------

    void drawWindowButton(const ui::Ctx &ctx, ui::Rect r, int kind, bool hover, bool maximized)
    {
        using namespace ui;
        if (hover)
            fillRect(ctx, r, kind == 2 ? theme::bad : theme::panelHi);
        const Rgba ink = hover && kind == 2 ? Rgba{0xFF, 0xFF, 0xFF, 0xFF} : theme::text;
        const float cx = r.cx();
        const float cy = r.cy();
        const float s = 5.0f;
        if (kind == 0)   // minimise
        {
            drawLine(ctx, Vec2{cx - s, cy + 0.5f}, Vec2{cx + s, cy + 0.5f}, ink, 1.5f);
        }
        else if (kind == 1)   // maximise / restore
        {
            if (maximized)
            {
                strokeRect(ctx, Rect{cx - s + 1.5f, cy - s - 1.0f, s * 2.0f - 1.5f, s * 2.0f - 1.5f}, ink, 1.5f);
                strokeRect(ctx, Rect{cx - s - 1.5f, cy - s + 2.0f, s * 2.0f - 1.5f, s * 2.0f - 1.5f}, ink, 1.5f);
            }
            else
            {
                strokeRect(ctx, Rect{cx - s, cy - s, s * 2.0f, s * 2.0f}, ink, 1.5f);
            }
        }
        else   // close
        {
            drawLine(ctx, Vec2{cx - s, cy - s}, Vec2{cx + s, cy + s}, ink, 1.6f);
            drawLine(ctx, Vec2{cx - s, cy + s}, Vec2{cx + s, cy - s}, ink, 1.6f);
        }
    }

    void drawTopBar(const ui::Ctx &ctx, ui::App &app, ui::ChromeHit hover, bool maximized)
    {
        using namespace ui;
        const ChromeLayout l = chromeLayout(app.frame.window.w);
        fillRect(ctx, l.bar, theme::mix(theme::panel, theme::ground, 0.5f));
        fillRect(ctx, Rect{0.0f, l.bar.bottom() - 1.0f, l.bar.w, 1.0f}, theme::line);

        // The mark, small: the big wordmark lives at the head of the rail.
        const float markX = 16.0f;
        text(ctx, "SOCOM II", Vec2{markX, 10.0f}, 15.0f, theme::gold, Face::Bold, 0.08f);
        const float markW = textWidth(ctx, "SOCOM II", 15.0f, Face::Bold, 0.08f);
        text(ctx, "UNZIPPED", Vec2{markX + markW + 10.0f, 12.0f}, 13.0f, theme::dim, Face::Bold, 0.10f);

        // Where the measured halves of the bar go: the tab group and the state cluster, from the widths this
        // font actually draws (ui::topBarPlaces does the arithmetic, and the tests assert on it).
        const char *state = app.running ? "RUNNING" : (app.discOk ? "READY" : "NOT READY");
        const char *name = pageName(app.nav.page);
        TopBarText measured;
        measured.markRight = markX + markW + 10.0f + textWidth(ctx, "UNZIPPED", 13.0f, Face::Bold, 0.10f);
        measured.statusW = textWidth(ctx, state, 14.0f, Face::Bold, 0.06f);
        measured.showPill = app.dirty;
        measured.tabW.push_back(textWidth(ctx, name, 13.0f, Face::Bold, 0.12f));
        const TopBarPlaces places = topBarPlaces(l, measured);

        // The page tab: where you are, without taking a click.
        if (!places.tab.empty())
            textCenteredIn(ctx, name, places.tab[0], 13.0f, theme::alpha(theme::caption, 150), Face::Bold, 0.12f);

        // The state lamp and its word, moved here from the old header band.
        const Rgba lamp = app.running ? theme::goldHi : (app.discOk ? theme::lampGreen : theme::warn);
        fillCircle(ctx, places.lamp, 5.0f, lamp);
        strokeCircle(ctx, places.lamp, chrome::lampR, theme::alpha(lamp, 110), 1.5f);
        textCenteredIn(ctx, state, places.status, 14.0f, theme::text, Face::Bold, 0.06f);

        // UNSAVED: only when there is something to save, and clicking it saves.
        if (app.dirty)
        {
            const bool over = hover == ChromeHit::UnsavedPill;
            fillRound(ctx, l.pill, l.pill.h * 0.5f, over ? theme::mix(theme::panelHi, theme::gold, 0.25f) : theme::panel);
            strokeRound(ctx, l.pill, l.pill.h * 0.5f, theme::gold, 1.5f);
            textCenteredIn(ctx, "UNSAVED", l.pill, 13.0f, theme::goldHi, Face::Bold, 0.06f);
        }

        drawWindowButton(ctx, l.minimize, 0, hover == ChromeHit::Minimize, maximized);
        drawWindowButton(ctx, l.maximize, 1, hover == ChromeHit::Maximize, maximized);
        drawWindowButton(ctx, l.close, 2, hover == ChromeHit::Close, maximized);
    }

    void drawRail(const ui::Ctx &ctx, ui::App &app, const std::vector<ui::Node> &rail)
    {
        using namespace ui;
        fillRect(ctx, app.frame.rail, theme::alpha(theme::panel, 170));
        fillRect(ctx, Rect{app.frame.rail.right() - 2.0f, app.frame.rail.y, 2.0f, app.frame.rail.h}, theme::line);

        // The wordmark, where it finally has room to be read: the stencil face is only used above 28 px.
        // Behind it, the blue halo the game puts behind its trident -- drawn, never traced.
        const Rect head{app.frame.rail.x, app.frame.rail.y, app.frame.rail.w, metrics::railTop};
        glow(ctx, Vec2{head.cx(), head.cy() - 4.0f}, 96.0f, theme::blue, 46);
        const float wordSize = 32.0f;
        const float wordW = textWidth(ctx, "SOCOM II", wordSize, Face::Display, 0.04f);
        text(ctx, "SOCOM II", Vec2{head.cx() - wordW * 0.5f, head.y + 16.0f}, wordSize, theme::gold, Face::Display, 0.04f);
        const float subW = textWidth(ctx, "UNZIPPED", 14.0f, Face::Bold, 0.34f);
        text(ctx, "UNZIPPED", Vec2{head.cx() - subW * 0.5f, head.y + 54.0f}, 14.0f, theme::goldHi, Face::Bold, 0.34f);
        fillRect(ctx, Rect{head.cx() - wordW * 0.5f, head.y + 50.0f, wordW, 1.0f}, theme::alpha(theme::gold, 120));
        for (const Node &n : rail)
        {
            const bool current = n.page == app.nav.page;
            const bool live = hovered(ctx, n.r) || focused(ctx, n.id);
            if (current)
                fillRectGradient(ctx, n.r, theme::panelHi, theme::mix(theme::panelHi, theme::blue, 0.22f));
            else
                fillRect(ctx, n.r, live ? theme::panel : theme::alpha(theme::panel, 190));
            strokeRect(ctx, n.r, current ? theme::gold : (live ? theme::line : theme::alpha(theme::line, 120)), 2.0f);
            fillRect(ctx, Rect{n.r.x, n.r.y, 5.0f, n.r.h}, current ? theme::gold : theme::alpha(theme::line, 160));
            // Rajdhani, not the stencil: at this size the stencil's gaps eat the letters (the owner's
            // "illegible at smaller resolutions").
            const float size = metrics::bodySize - 1.0f;
            const float drawn = size;
            text(ctx, pageName(n.page), Vec2{n.r.x + 20.0f, n.r.y + (n.r.h - drawn * 1.2f) * 0.5f}, size,
                 current ? theme::goldHi : (live ? theme::text : theme::caption), Face::Bold, 0.06f);
            if (hit(ctx, n.r, n.id) && app.graph != nullptr)
                app.nav.goTo(*app.graph, n.page);
        }
    }

    // The prompts: what the keys or the pad buttons do to whatever holds the focus.
    void drawPrompts(const ui::Ctx &ctx, ui::App &app, float x, float y, float height)
    {
        using namespace ui;
        const ui::GlyphFamily family = glyphFamilyFor(app.pad.name);
        const bool typing = !app.activeField.empty();
        const bool onRail = app.nav.onRail();
        const bool adjusts = adjustsHorizontally(app.nav.focus);

        struct Prompt
        {
            const char *key;
            const char *verb;
            int padFace;   // -1: not a face button
        };
        Prompt prompts[3];
        int count = 0;
        if (typing)
        {
            prompts[count++] = Prompt{"TYPE", "EDIT", -1};
            prompts[count++] = Prompt{"ENTER", "DONE", -1};
        }
        else if (onRail)
        {
            prompts[count++] = Prompt{"UP/DN", "MOVE", -1};
            prompts[count++] = Prompt{"ENTER", "OPEN", 1};
        }
        else
        {
            prompts[count++] = Prompt{adjusts ? "LT/RT" : "ARROWS", adjusts ? "ADJUST" : "MOVE", -1};
            prompts[count++] = Prompt{"ENTER", "SELECT", 1};
            prompts[count++] = Prompt{"ESC", "BACK", 3};
        }
        for (int i = 0; i < count; ++i)
        {
            float w = 0.0f;
            if (app.padPrompts && prompts[i].padFace >= 0)
                w = drawPadPrompt(ctx, Vec2{x, y}, family, prompts[i].padFace, height, theme::text);
            else
                w = drawKeyCap(ctx, Vec2{x, y}, prompts[i].key, height, theme::text);
            x += w + 8.0f;
            text(ctx, prompts[i].verb, Vec2{x, y + (height - 15.0f * 1.12f) * 0.5f}, 15.0f, theme::dim, Face::Bold);
            x += textWidth(ctx, prompts[i].verb, 15.0f, Face::Bold) + 22.0f;
        }
    }

    void drawBar(const ui::Ctx &ctx, ui::App &app, const std::vector<ui::Node> &nodes)
    {
        using namespace ui;
        const Rect bar = app.frame.bar;
        fillRect(ctx, bar, theme::panel);
        fillRect(ctx, Rect{0.0f, bar.y, bar.w, 2.0f}, theme::line);

        const std::string profile = app.config.profile.empty() ? std::string("player") : app.config.profile;
        text(ctx, "PROFILE", Vec2{metrics::margin, bar.y + 10.0f}, 13.0f, theme::dim, Face::Bold);
        text(ctx, profile.c_str(), Vec2{metrics::margin, bar.y + 26.0f}, 19.0f, theme::text, Face::Bold);

        const bool onPlay = app.nav.page == Page::Play;
        const Rect launch = onPlay ? Rect{bar.right() - metrics::margin - 220.0f, bar.y + 10.0f, 220.0f, 36.0f}
                                   : rectOf(nodes, barLaunchId(app.nav.page));
        const float statusX = metrics::margin + 130.0f;
        const float promptsX = launch.x - 330.0f;
        if (!app.status.empty())
        {
            const std::string shown = ellipsizeEnd(ctx, app.status, promptsX - statusX - 24.0f, 16.0f);
            text(ctx, shown.c_str(), Vec2{statusX, bar.y + 20.0f}, 16.0f, theme::dim);
        }
        drawPrompts(ctx, app, promptsX, bar.y + 12.0f, 26.0f);

        const std::string blocked = launchBlockedReason(app.discOk, app.running, app.config.isoPath.empty());
        if (onPlay)
        {
            // PLAY has its own large LAUNCH; a second one here would be the same button twice. The state of
            // the last run goes in its place.
            const std::string state = app.running
                                          ? std::string("the game is running")
                                          : (!blocked.empty() ? blocked
                                                              : (app.exitLine.empty() ? std::string("ready to launch") : app.exitLine));
            const Rgba ink = app.running ? theme::goldHi : (blocked.empty() ? theme::dim : theme::warn);
            const std::string shown = ellipsizeEnd(ctx, state, launch.w + 40.0f, 17.0f);
            text(ctx, shown.c_str(), Vec2{launch.right() - textWidth(ctx, shown.c_str(), 17.0f), launch.y + 9.0f}, 17.0f, ink);
        }
        else if (button(ctx, launch, app.running ? "RUNNING" : "LAUNCH", barLaunchId(app.nav.page), blocked.empty(), true))
            app.requestLaunch = true;
    }

    void drawContentFrame(const ui::Ctx &ctx, ui::App &app)
    {
        using namespace ui;
        const Rect c = app.frame.content;
        panel(ctx, c);
        const Rect band{c.x + 2.0f, c.y + 2.0f, c.w - 4.0f, 42.0f};
        fillRect(ctx, band, theme::panelHi);
        fillRect(ctx, Rect{band.x, band.bottom(), band.w, 2.0f}, theme::line);
        text(ctx, pageName(app.nav.page), Vec2{band.x + 18.0f, band.y + 9.0f}, 22.0f, theme::goldHi, Face::Bold, 0.08f);
        const float nameW = textWidth(ctx, pageName(app.nav.page), 22.0f, Face::Bold, 0.08f);
        const char *title = pageTitle(app.nav.page);
        const char *dash = std::strstr(title, "-- ");
        const std::string sub = dash != nullptr ? std::string(dash + 3) : std::string(title);
        const float room = band.w - nameW - 60.0f;
        text(ctx, ellipsizeEnd(ctx, sub, room, metrics::captionSize).c_str(),
             Vec2{band.x + 30.0f + nameW, band.y + 13.0f}, metrics::captionSize, theme::caption);
    }

    void drawPage(const ui::Ctx &ctx, ui::App &app, const std::vector<ui::Node> &nodes)
    {
        switch (app.nav.page)
        {
        case ui::Page::Play: ui::drawPlayPage(ctx, app, nodes); break;
        case ui::Page::Disc: ui::drawDiscPage(ctx, app, nodes); break;
        case ui::Page::Video: ui::drawVideoPage(ctx, app, nodes); break;
        case ui::Page::Audio: ui::drawAudioPage(ctx, app, nodes); break;
        case ui::Page::Controller: ui::drawControllerPage(ctx, app, nodes); break;
        case ui::Page::Microphone: ui::drawMicrophonePage(ctx, app, nodes); break;
        case ui::Page::Online: ui::drawOnlinePage(ctx, app, nodes); break;
        case ui::Page::Report: ui::drawReportPage(ctx, app, nodes); break;
        case ui::Page::About: ui::drawAboutPage(ctx, app, nodes); break;
        }
    }

    // ---- the pad, as the drawing and the navigation both see it ---------------------------------------------

    int shownSlot(const launcher::Config &config)
    {
        if (config.gamepadIndex >= 0)
            return config.gamepadIndex;
        for (int i = 0; i < 4; ++i)
            if (IsGamepadAvailable(i))
                return i;
        return -1;
    }

    float triggerValue(int slot, int axis, int button)
    {
        if (GetGamepadAxisCount(slot) > axis)
        {
            const float v = (GetGamepadAxisMovement(slot, axis) + 1.0f) * 0.5f;
            if (v > 0.001f)
                return v > 1.0f ? 1.0f : v;
        }
        return IsGamepadButtonDown(slot, button) ? 1.0f : 0.0f;
    }

    ui::PadSnapshot pollPad(int slot)
    {
        ui::PadSnapshot pad;
        if (slot < 0 || !IsGamepadAvailable(slot))
            return pad;
        pad.present = true;
        const char *name = GetGamepadName(slot);
        pad.name = name != nullptr ? name : "";
        auto set = [&](ui::PadElement e, int button) { pad.down[static_cast<int>(e)] = IsGamepadButtonDown(slot, button); };
        set(ui::PadElement::DpadUp, GAMEPAD_BUTTON_LEFT_FACE_UP);
        set(ui::PadElement::DpadDown, GAMEPAD_BUTTON_LEFT_FACE_DOWN);
        set(ui::PadElement::DpadLeft, GAMEPAD_BUTTON_LEFT_FACE_LEFT);
        set(ui::PadElement::DpadRight, GAMEPAD_BUTTON_LEFT_FACE_RIGHT);
        set(ui::PadElement::FaceUp, GAMEPAD_BUTTON_RIGHT_FACE_UP);
        set(ui::PadElement::FaceDown, GAMEPAD_BUTTON_RIGHT_FACE_DOWN);
        set(ui::PadElement::FaceLeft, GAMEPAD_BUTTON_RIGHT_FACE_LEFT);
        set(ui::PadElement::FaceRight, GAMEPAD_BUTTON_RIGHT_FACE_RIGHT);
        set(ui::PadElement::Select, GAMEPAD_BUTTON_MIDDLE_LEFT);
        set(ui::PadElement::Start, GAMEPAD_BUTTON_MIDDLE_RIGHT);
        set(ui::PadElement::LeftStickClick, GAMEPAD_BUTTON_LEFT_THUMB);
        set(ui::PadElement::RightStickClick, GAMEPAD_BUTTON_RIGHT_THUMB);
        pad.shoulder[0] = IsGamepadButtonDown(slot, GAMEPAD_BUTTON_LEFT_TRIGGER_1);
        pad.shoulder[1] = IsGamepadButtonDown(slot, GAMEPAD_BUTTON_RIGHT_TRIGGER_1);
        pad.trigger[0] = triggerValue(slot, GAMEPAD_AXIS_LEFT_TRIGGER, GAMEPAD_BUTTON_LEFT_TRIGGER_2);
        pad.trigger[1] = triggerValue(slot, GAMEPAD_AXIS_RIGHT_TRIGGER, GAMEPAD_BUTTON_RIGHT_TRIGGER_2);
        pad.leftStick = ui::Vec2{GetGamepadAxisMovement(slot, GAMEPAD_AXIS_LEFT_X), GetGamepadAxisMovement(slot, GAMEPAD_AXIS_LEFT_Y)};
        pad.rightStick = ui::Vec2{GetGamepadAxisMovement(slot, GAMEPAD_AXIS_RIGHT_X), GetGamepadAxisMovement(slot, GAMEPAD_AXIS_RIGHT_Y)};
        return pad;
    }

    // ---- the fake state the screenshots are taken on (it never touches config.json) --------------------------

    ui::PadSnapshot fakeXboxPad()
    {
        ui::PadSnapshot pad;
        pad.present = true;
        pad.name = "Xbox Wireless Controller";
        pad.down[static_cast<int>(ui::PadElement::FaceDown)] = true;   // A
        pad.down[static_cast<int>(ui::PadElement::DpadUp)] = true;
        pad.shoulder[0] = true;   // LB
        pad.trigger[1] = 0.7f;
        pad.leftStick = ui::Vec2{0.6f, -0.4f};
        return pad;
    }

    ui::PadSnapshot fakePlayStationPad()
    {
        ui::PadSnapshot pad = fakeXboxPad();
        pad.name = "Wireless Controller";
        return pad;
    }

    void fillFakeState(ui::App &app)
    {
        app.fake = true;
        app.config = launcher::Config{};
        app.config.isoPath = "D:\\games\\SOCOM II - U.S. Navy SEALs (USA).iso";
        // the default preset (the project's hosted server), so the ONLINE page's screenshot shows what a stranger sees
        app.config.profile = "player";
        app.config.micDevice = "Headset (USB)";
        app.discChecked = true;
        app.discOk = true;
        app.discMessage = "SOCOM II U.S. Navy SEALs NTSC r0001";
        app.status = "ready";
        app.exitLine = launcher::exitMessage(0);
        app.padLabels = {"first available", "[0] Xbox Wireless Controller"};
        app.padSlots = {-1, 0};
        app.pad = fakeXboxPad();
        app.micLabels = {"None", "Headset (USB)", "Microphone (Realtek High Definition Audio)"};
        app.meterOn = true;
        app.micDb = -18.0f;
        app.micDbValid = true;
        app.micStatus = "listening";
        app.configPath = "C:\\games\\socom2\\config.json";
        app.logsPath = "C:\\games\\socom2\\logs";
        app.version = "SOCOM Unzipped -- sprint 8 build";
        app.monitorSize = "2560x1440";
        app.layout.padChoices = static_cast<int>(app.padLabels.size());
        app.layout.micChoices = static_cast<int>(app.micLabels.size());
        app.layout.customServer = false;   // the default preset owns the address
    }
}

int main(int argc, char **argv)
{
    const fs::path dir = win32glue::exeDirectory();
    const fs::path configPath = dir / "config.json";
    if (argc > 2 && std::strcmp(argv[1], "--diagnostics") == 0)
    {
        // Sprint 9 Goal 1: the zip without the window -- for a report from a machine where the launcher
        // itself will not open, and for tools_py/tests/test_diagnostics_zip.py. Answered before this
        // launcher's own config.json is read, so <dir> is the only folder it looks at.
        std::string message;
        const bool ok = saveDiagnostics(argc > 3 ? fs::path(argv[3]) : dir, fs::path(argv[2]), std::string(), false, 0, message);
        std::printf("%s\n", message.c_str());
        return ok ? 0 : 1;
    }

    if (argc > 2 && std::strcmp(argv[1], "--report-bug") == 0)
        return reportBugHeadless(fs::path(argv[2]), argc > 3 ? fs::path(argv[3]) : dir);
    if (argc > 1 && std::strcmp(argv[1], "--server-status") == 0)
    {
        const std::string line = br::statusLine(fetchStats());
        if (!line.empty())
            std::printf("%s\n", line.c_str());
        return line.empty() ? 1 : 0;   // silent when unreachable, as the ONLINE page is
    }

    launcher::Config config;
    {
        const std::string text = readText(configPath);
        if (!text.empty() && !launcher::fromJson(text, config))
            std::fprintf(stderr, "config.json is malformed; using the defaults\n");
    }

    if (argc > 1 && std::strcmp(argv[1], "--selftest") == 0)
    {
        std::printf("config: %s\n", configPath.string().c_str());
        const DiscStatus st = checkDisc(config.isoPath);
        std::printf("disc: %s -> %s\n", config.isoPath.c_str(), st.message.c_str());
        for (const std::string &kv : launcher::environmentFor(config))
            std::printf("env: %s\n", kv.c_str());
        for (const std::string &line : launcher::selftestExitLines())
            std::printf("%s\n", line.c_str());
        return writeText(configPath, launcher::toJson(config)) ? 0 : 1;
    }

    if (argc > 1 && std::strcmp(argv[1], "--launch-test") == 0)
    {
        // Starts the game the way the Launch button does, waits, and reports whether it ran: the environment
        // plumbing end to end, without a hand on the button.
        const int seconds = argc > 2 ? std::atoi(argv[2]) : 12;
        win32glue::GameProcess game;
        if (!win32glue::startGame(dir.string(), config, game))
        {
            std::printf("launch failed: %s\n", game.error.c_str());
            return 2;
        }
        std::printf("started; log %s\n", game.logPath.c_str());
        const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
        while (game.running() && std::chrono::steady_clock::now() < until)
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        const bool stillRunning = game.running();
        std::printf("after %d s: %s\n", seconds, stillRunning ? "running" : "exited");
        win32glue::terminate(game);
        game.close();
        return stillRunning ? 0 : 3;
    }

    const char *screenshotDir = (argc > 2 && std::strcmp(argv[1], "--screenshot") == 0) ? argv[2] : nullptr;

    // HIGHDPI is what a player wants and what a screenshot must not have: the PNGs are asked for at exact
    // pixel sizes.
    // MSAA for every curved edge (the owner: "the circle at the top right ... jagged at odd resolutions");
    // HIGHDPI so the type is rasterised at real pixels, except under --screenshot where the PNGs must come
    // out at exactly the asked-for size.
    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_WINDOW_RESIZABLE | (screenshotDir != nullptr ? 0u : FLAG_WINDOW_HIGHDPI));
    InitWindow(static_cast<int>(ui::metrics::designW), static_cast<int>(ui::metrics::designH), "SOCOM Unzipped");
    SetWindowMinSize(static_cast<int>(ui::metrics::minW), static_cast<int>(ui::metrics::minH));
    if (screenshotDir == nullptr)
    {
        // Sprint 7 review finding, kept: a 700 px window plus DPI scaling can still be taller than a laptop
        // panel, so the window opens at whatever the monitor allows.
        const int monitorHeight = GetMonitorHeight(GetCurrentMonitor());
        if (monitorHeight > 0)
            SetWindowSize(static_cast<int>(ui::metrics::designW),
                          launcher::fitWindowHeight(static_cast<int>(ui::metrics::designH), monitorHeight, 80));
    }
    SetTargetFPS(60);
    SetExitKey(KEY_NULL);

    // The custom title bar. On Windows the window keeps its frame (resize, snap, shadow) and only loses the
    // caption; everywhere else raylib gives us an undecorated window and we drag it ourselves.
    // --screenshot asks for exact client sizes; the Windows frame trick makes the client cover the whole
    // window, and the two disagree by the frame's thickness for a frame or two -- which lands in the PNG as
    // a shifted capture. The screenshots use an undecorated window instead: the bar below is ours either way.
    if (screenshotDir == nullptr)
    {
        g_nativeChrome = win32glue::installCustomChrome(GetWindowHandle(), chromeHitForSystem);
        if (!g_nativeChrome)
            SetWindowState(FLAG_WINDOW_UNDECORATED);
    }
    else
    {
        SetWindowState(FLAG_WINDOW_UNDECORATED);
    }

    {
        // The owner's report was "illegible at the default resolution", so the default resolution says so.
        const Vector2 dpi = GetWindowScaleDPI();
        std::fprintf(stderr, "[launcher] window %dx%d screen, %dx%d render, dpi %.2f, scale %.3f, monitor %dx%d\n",
                     GetScreenWidth(), GetScreenHeight(), GetRenderWidth(), GetRenderHeight(), dpi.x,
                     static_cast<double>(ui::scaleFor(GetScreenWidth(), GetScreenHeight())),
                     GetMonitorWidth(GetCurrentMonitor()), GetMonitorHeight(GetCurrentMonitor()));
    }

    ui::Fonts fonts;   // rasterised per pixel size, rebuilt when the scale changes

    ui::App app;
    app.config = config;
    app.configPath = configPath.string();
    app.logsPath = (dir / "logs").string();
    app.version = readText(dir / "version.txt");
    while (!app.version.empty() && (app.version.back() == '\n' || app.version.back() == '\r'))
        app.version.pop_back();

    win32glue::GameProcess game;
    std::string lastLog;
    long long lastExitRaw = 0;
    bool haveLastExit = false;
    std::unique_ptr<launcher::MicDevices> mic;
    bool meterOn = false;

    if (screenshotDir != nullptr)
    {
        fillFakeState(app);
    }
    else
    {
        const DiscStatus st = checkDisc(app.config.isoPath);
        app.discChecked = st.checked;
        app.discOk = st.ok;
        app.discMessage = st.message;
        app.status = st.ok ? "ready" : "";
        mic = launcher::makeMicDevices();
        app.micLabels = launcher::micLabels(*mic);
        meterOn = !app.config.micDevice.empty() && mic->startMeter(app.config.micDevice);
        app.meterOn = meterOn;
    }

    // Sprint 9 Goal 8: the two requests this window ever makes, each on its own worker.
    Worker<ReportOutcome> reportJob;
    Worker<std::string> statsJob;
    br::Inputs reportIn;
    double statsAskedAt = -1000.0;
    ui::Page previousPage = ui::Page::Play;

    ui::Nav &nav = app.nav;
    nav.page = ui::Page::Play;
    nav.focus = ui::railId(ui::Page::Play);

    ui::FocusRing ring;
    float lastScale = -1.0f;
    bool quitRequested = false;
    bool dragging = false;
    Vector2 dragGrab{};
    double pageChangedAt = -1.0;
    ui::Page lastPage = nav.page;
    Vector2 lastMouse = GetMousePosition();
    double padRepeatAt = 0.0;

    // --screenshot walks the pages itself; the interactive loop runs until the window closes.
    struct Shot
    {
        ui::Page page;
        int w, h;
        const char *suffix;
    };
    std::vector<Shot> shots;
    if (screenshotDir != nullptr)
    {
        const int sizes[2][2] = {{1100, 700}, {800, 520}};
        for (const auto &size : sizes)
            for (int i = 0; i < ui::kPageCount; ++i)
                shots.push_back(Shot{ui::pageAt(i), size[0], size[1], ""});
        shots.push_back(Shot{ui::Page::Controller, 1100, 700, "_playstation"});
        // R139: the crouch shortcut on each control -- the row, the trade's line, and the mark on the drawing.
        shots.push_back(Shot{ui::Page::Controller, 1100, 700, "_crouch_l3"});
        shots.push_back(Shot{ui::Page::Controller, 800, 520, "_crouch_l3"});
        shots.push_back(Shot{ui::Page::Controller, 1100, 700, "_crouch_touchpad"});
        shots.push_back(Shot{ui::Page::Controller, 1100, 700, "_crouch_l2"});
        // The owner's own config named the community server; this is what the page does with it.
        shots.push_back(Shot{ui::Page::Online, 1100, 700, "_community_healed"});
        // Sprint 9 Goal 8: the hosted server's status line, and the REPORT A BUG page in each of its states
        // (the plain report_<size>.png above is the empty form).
        shots.push_back(Shot{ui::Page::Online, 1100, 700, "_status"});
        shots.push_back(Shot{ui::Page::Online, 800, 520, "_status"});
        for (const char *state : {"_filled", "_sent", "_saved", "_fielderror", "_ratelimited", "_sending"})
        {
            shots.push_back(Shot{ui::Page::Report, 1100, 700, state});
            shots.push_back(Shot{ui::Page::Report, 800, 520, state});
        }
    }
    const char *selfShot = std::getenv("PS2X_LAUNCHER_SHOT");
    unsigned selfShotFrames = 0;
    size_t shotIndex = 0;
    int shotFrame = 0;
    int resizeWaits = 0;

    while (!WindowShouldClose() && !quitRequested)
    {
        const float scale = ui::scaleFor(GetScreenWidth(), GetScreenHeight());
        if (scale != lastScale)
        {
            fonts.clear();   // every raster in the cache is the wrong size now
            lastScale = scale;
        }
        const float dpiScale = GetWindowScaleDPI().x > 0.1f ? GetWindowScaleDPI().x : 1.0f;
        g_uiScale = scale;
        g_uiDpi = dpiScale;
        g_uiMaximized = win32glue::isWindowMaximized() || IsWindowMaximized();
        const ui::Rect window{0.0f, 0.0f, static_cast<float>(GetScreenWidth()) / scale,
                              static_cast<float>(GetScreenHeight()) / scale};
        app.frame = ui::frameFor(window);

        // ---- what the world says this frame ---------------------------------------------------------------
        if (screenshotDir == nullptr)
        {
            const int slot = shownSlot(app.config);
            app.pad = pollPad(slot);
            app.padLabels.assign(1, "first available");
            app.padSlots.assign(1, -1);
            for (int i = 0; i < 4; ++i)
                if (IsGamepadAvailable(i))
                {
                    app.padLabels.push_back(std::string("[") + std::to_string(i) + "] " + GetGamepadName(i));
                    app.padSlots.push_back(i);
                }
            app.running = game.running();
            if (!app.running && game.process)
            {
                // Sprint 9 Goal 1: every ending has a sentence (ps2x/exit_codes.h), and a non-fatal notice
                // in the log -- no audio device -- rides along with it.
                lastExitRaw = game.exitCode();
                haveLastExit = true;
                game.close();
                app.exitLine = launcher::lastRunLine(lastExitRaw, readHead(lastLog, 256u * 1024u));
                app.status = app.exitLine;
                // Review F8: the meter gives the capture device back to the game while it runs; take it now.
                meterOn = !app.config.micDevice.empty() && mic->startMeter(app.config.micDevice);
            }
            app.meterOn = meterOn;
            const float db = meterOn ? mic->levelDb() : -INFINITY;
            app.micDbValid = std::isfinite(db);
            app.micDb = app.micDbValid ? db : -60.0f;
            app.monitorSize = launcher::monitorSizeOrEmpty(GetMonitorWidth(GetCurrentMonitor()),
                                                           GetMonitorHeight(GetCurrentMonitor()));
            app.layout.padChoices = static_cast<int>(app.padLabels.size());
            app.layout.micChoices = static_cast<int>(app.micLabels.size());
            const launcher::ServerPreset *preset = launcher::findServerPreset(app.config.serverPreset);
            app.layout.customServer = preset == nullptr || preset->address[0] == '\0';
        }

        const ui::FocusGraph graph = ui::FocusGraph::build(window, app.layout);
        app.graph = &graph;
        const std::vector<ui::Node> rail = ui::railLayout(window);
        const std::vector<ui::Node> nodes = ui::layoutFor(nav.page, window, app.layout);
        if (graph.find(nav.focus) == nullptr)
            nav.focus = ui::railId(nav.page);   // the list under the focus changed (a pad was unplugged)

        // ---- input ----------------------------------------------------------------------------------------
        ui::Ctx ctx;
        ctx.scale = scale;
        ctx.dpi = dpiScale;
        ctx.fonts = &fonts;
        const Vector2 mouse = GetMousePosition();
        ctx.mouse = ui::Vec2{mouse.x / scale, mouse.y / scale};
        ctx.mouseMoved = (mouse.x != lastMouse.x || mouse.y != lastMouse.y);
        if (ctx.mouseMoved)
            lastMouse = mouse;
        static bool mouseEverMoved = false;
        mouseEverMoved = mouseEverMoved || ctx.mouseMoved;
        ctx.mouseMoved = mouseEverMoved;
        ctx.click = IsMouseButtonPressed(MOUSE_BUTTON_LEFT);
        ctx.held = IsMouseButtonDown(MOUSE_BUTTON_LEFT);
        ctx.focus = nav.focus;
        ctx.focusOut = &nav.focus;
        ctx.activeField = &app.activeField;
        ctx.time = GetTime();
        ctx.fake = app.fake;

        // The bar's own mouse handling: the same hit test the system asks, in screen units.
        const ui::ChromeHit chromeHover =
            app.fake ? ui::ChromeHit::Client
                     : ui::chromeHitTest(static_cast<int>(mouse.x), static_cast<int>(mouse.y), GetScreenWidth(),
                                         GetScreenHeight(), scale, g_uiMaximized);
        if (!app.fake && ctx.click)
        {
            switch (chromeHover)
            {
            case ui::ChromeHit::Minimize:
                if (g_nativeChrome)
                    win32glue::minimizeWindow();
                else
                    MinimizeWindow();
                ctx.click = false;
                break;
            case ui::ChromeHit::Maximize:
                if (g_nativeChrome)
                    win32glue::maximizeToggleWindow();
                else if (IsWindowMaximized())
                    RestoreWindow();
                else
                    MaximizeWindow();
                ctx.click = false;
                break;
            case ui::ChromeHit::Close:
                quitRequested = true;
                ctx.click = false;
                break;
            case ui::ChromeHit::UnsavedPill:
                if (app.dirty)
                    app.requestSave = true;
                ctx.click = false;
                break;
            case ui::ChromeHit::Caption:
                // Without native chrome the launcher drags its own window.
                if (!g_nativeChrome)
                {
                    dragging = true;
                    dragGrab = Vector2{mouse.x, mouse.y};
                }
                ctx.click = false;
                break;
            default:
                break;
            }
        }
        if (dragging)
        {
            if (!IsMouseButtonDown(MOUSE_BUTTON_LEFT))
                dragging = false;
            else
            {
                const Vector2 at = GetWindowPosition();
                SetWindowPosition(static_cast<int>(at.x + mouse.x - dragGrab.x),
                                  static_cast<int>(at.y + mouse.y - dragGrab.y));
            }
        }

        if (!app.fake)
        {
            const bool typing = !app.activeField.empty();
            const int padSlot = shownSlot(app.config);
            const bool padPresent = padSlot >= 0 && IsGamepadAvailable(padSlot);

            // Sprint 9 Goal 9 (P3): every pad reading goes through ONE gate, which knows the game may own
            // the pad. raylib reads the pad whether or not this window has focus, so before this the
            // player's stick walked the launcher's focus ring while they were aiming with it.
            ui::PadFrame padFrame;
            padFrame.present = padPresent;
            if (padPresent)
            {
                auto edge = [&](ui::PadNav nav_, int button)
                { padFrame.pressed[static_cast<int>(nav_)] = IsGamepadButtonPressed(padSlot, button); };
                edge(ui::PadNav::Left, GAMEPAD_BUTTON_LEFT_FACE_LEFT);
                edge(ui::PadNav::Right, GAMEPAD_BUTTON_LEFT_FACE_RIGHT);
                edge(ui::PadNav::Up, GAMEPAD_BUTTON_LEFT_FACE_UP);
                edge(ui::PadNav::Down, GAMEPAD_BUTTON_LEFT_FACE_DOWN);
                edge(ui::PadNav::Activate, GAMEPAD_BUTTON_RIGHT_FACE_DOWN);
                edge(ui::PadNav::Back, GAMEPAD_BUTTON_RIGHT_FACE_RIGHT);
                edge(ui::PadNav::PagePrev, GAMEPAD_BUTTON_LEFT_TRIGGER_1);
                edge(ui::PadNav::PageNext, GAMEPAD_BUTTON_RIGHT_TRIGGER_1);
                edge(ui::PadNav::Launch, GAMEPAD_BUTTON_MIDDLE_RIGHT);
                padFrame.leftX = GetGamepadAxisMovement(padSlot, GAMEPAD_AXIS_LEFT_X);
                padFrame.leftY = GetGamepadAxisMovement(padSlot, GAMEPAD_AXIS_LEFT_Y);
            }
            const ui::PadIntent padWants = ui::padIntent(padFrame, app.running, ctx.time, padRepeatAt);

            if (typing)
            {
                if (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_TAB))
                    app.activeField.clear();
            }
            else
            {
                const bool adjusts = ui::adjustsHorizontally(nav.focus);
                int dx = 0, dy = 0;
                if (IsKeyPressed(KEY_LEFT) || IsKeyPressedRepeat(KEY_LEFT))
                    dx -= 1;
                if (IsKeyPressed(KEY_RIGHT) || IsKeyPressedRepeat(KEY_RIGHT))
                    dx += 1;
                if (IsKeyPressed(KEY_UP) || IsKeyPressedRepeat(KEY_UP))
                    dy -= 1;
                if (IsKeyPressed(KEY_DOWN) || IsKeyPressedRepeat(KEY_DOWN))
                    dy += 1;
                // The d-pad and the left stick (with its repeat) arrive already gated.
                dx += padWants.dx;
                dy += padWants.dy;
                if (dx != 0 || dy != 0)
                    app.padPrompts = padWants.prompts && !(IsKeyDown(KEY_LEFT) || IsKeyDown(KEY_RIGHT) || IsKeyDown(KEY_UP) || IsKeyDown(KEY_DOWN));

                if (adjusts && dx != 0)
                    ctx.adjust = dx;
                else if (dx < 0)
                    nav.move(graph, ui::Dir::Left);
                else if (dx > 0)
                    nav.move(graph, ui::Dir::Right);
                if (dy < 0)
                    nav.move(graph, ui::Dir::Up);
                else if (dy > 0)
                    nav.move(graph, ui::Dir::Down);

                if (IsKeyPressed(KEY_TAB))
                {
                    const std::vector<std::string> ids = graph.idsOn(nav.page);
                    size_t at = 0;
                    for (size_t i = 0; i < ids.size(); ++i)
                        if (ids[i] == nav.focus)
                            at = i + 1;
                    if (!ids.empty())
                        nav.focus = ids[at % ids.size()];
                }
                ctx.activate = IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_SPACE) || padWants.activate;
                if (IsKeyPressed(KEY_ESCAPE) || padWants.back)
                    nav.back(graph);
                if (padWants.pagePrev)
                    nav.goTo(graph, ui::pageAt(ui::pageIndex(nav.page) - 1));
                if (padWants.pageNext)
                    nav.goTo(graph, ui::pageAt(ui::pageIndex(nav.page) + 1));
                if (padWants.launch)
                    app.requestLaunch = true;
                if (IsKeyPressed(KEY_F5))
                    app.requestVerify = true;
                if (padWants.activate || padWants.back)
                    app.padPrompts = true;
            }
            if (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_ESCAPE) || IsKeyPressed(KEY_TAB) ||
                IsKeyPressed(KEY_LEFT) || IsKeyPressed(KEY_RIGHT) || IsKeyPressed(KEY_UP) || IsKeyPressed(KEY_DOWN))
                app.padPrompts = false;
        }
        ctx.focus = nav.focus;

        // ---- draw -----------------------------------------------------------------------------------------
        BeginDrawing();
        ClearBackground(ui::rl(ui::theme::ground));
        ui::groundGrid(ctx, window);
        drawTopBar(ctx, app, chromeHover, g_uiMaximized);
        drawRail(ctx, app, rail);
        drawContentFrame(ctx, app);
        drawPage(ctx, app, nodes);
        drawBar(ctx, app, nodes);

        // A 120 ms wipe on a page change, so the pane arrives rather than snapping.
        if (nav.page != lastPage)
        {
            lastPage = nav.page;
            pageChangedAt = ctx.time;
        }
        if (!app.fake && pageChangedAt > 0.0)
        {
            const float t = static_cast<float>((ctx.time - pageChangedAt) / 0.12);
            if (t < 1.0f)
                ui::fillRect(ctx, app.frame.content, ui::theme::alpha(ui::theme::ground,
                                                                     static_cast<unsigned char>(200.0f * (1.0f - t))));
            else
                pageChangedAt = -1.0;
        }

        // The focus ring: on the focused control's rect, this frame, whole -- and drawn last, after the
        // pane's wipe, so nothing fades it in on the frame it lands (Sprint 8 owner feedback).
        ring.update(graph, nav.focus, GetFrameTime());
        if (ring.visible)
            ui::focusRing(ctx, ring.shown);
        EndDrawing();

        // ---- what the pages asked for ---------------------------------------------------------------------
        if (!app.fake)
        {
            if (app.requestBrowse)
            {
                const std::string chosen = win32glue::browseForIso();
                if (!chosen.empty())
                {
                    app.config.isoPath = chosen;
                    app.dirty = true;
                    app.requestVerify = true;
                }
            }
            if (app.requestVerify)
            {
                const DiscStatus st = checkDisc(app.config.isoPath);
                app.discChecked = st.checked;
                app.discOk = st.ok;
                app.discMessage = st.message;
                app.status = st.ok ? "disc verified" : st.message;
            }
            if (app.requestMicRescan)
            {
                app.micLabels = launcher::micLabels(*mic);
                app.micStatus = TextFormat("%d capture device(s)", static_cast<int>(app.micLabels.size()) - 1);
            }
            if (app.requestMicChanged)
            {
                mic->stopMeter();
                meterOn = !app.config.micDevice.empty() && mic->startMeter(app.config.micDevice);
                app.micStatus = app.config.micDevice.empty() ? "" : (meterOn ? "listening" : "that device will not open");
            }
            if (app.requestSave)
            {
                writeText(configPath, launcher::toJson(app.config));
                app.dirty = false;
                app.status = "settings saved";
            }
            if (app.requestDiagnostics)
            {
                std::string message;
                if (saveDiagnostics(dir, fs::path(), lastLog, haveLastExit, lastExitRaw, message))
                    win32glue::openFolder((dir / "diagnostics").string());
                app.status = message;
            }
            if (app.requestOpenLogs)
                win32glue::openFolder((dir / "logs").string());

            // ---- Sprint 9 Goal 8: the status line. Asked for when ONLINE opens (never within 5 s of the
            // last ask) and every 10 s while it stays open; the answer lands in a slot this thread polls.
            const bool pageEntered = nav.page != previousPage;
            previousPage = nav.page;
            if (nav.page == ui::Page::Online && !statsJob.busy() &&
                ctx.time - statsAskedAt >= (pageEntered ? 5.0 : static_cast<double>(br::kStatsPollSeconds)))
            {
                statsAskedAt = ctx.time;
                statsJob.start(fetchStats);
            }
            std::string statsBody;
            if (statsJob.poll(statsBody))
                app.serverStatus = br::statusLine(statsBody);   // "" when unreachable: the line is not drawn

            // ---- the report: what would be sent, the send, the reply ------------------------------------
            ui::ReportUi &report = app.report;
            if (nav.page == ui::Page::Report && pageEntered)
            {
                reportIn = reportInputs(dir, lastLog, haveLastExit, lastExitRaw);
                report.changed = true;
            }
            if (nav.page == ui::Page::Report && report.changed)
            {
                report.preview = br::previewLine(br::build(app.config, report.form, reportIn), report.form);
                report.changed = false;
            }
            if (report.requestSend && report.state != ui::ReportUi::State::Sending)
            {
                const std::string problem = br::checkForm(report.form);
                if (!problem.empty())
                {
                    report.state = ui::ReportUi::State::FieldError;
                    report.message = problem;
                    const std::string field = br::fieldOf(problem);
                    if (field == "title" || field == "description" || field == "contact")
                        nav.focus = app.activeField = "report." + field;
                }
                else
                {
                    reportIn = reportInputs(dir, lastLog, haveLastExit, lastExitRaw);
                    const std::string json = br::buildPayload(app.config, report.form, reportIn);
                    report.state = ui::ReportUi::State::Sending;
                    report.message.clear();
                    report.savedPath.clear();
                    app.activeField.clear();
                    reportJob.start([dir, json]() { return sendReport(dir, json); });
                }
            }
            report.requestSend = false;
            ReportOutcome outcome;
            if (reportJob.poll(outcome))
            {
                if (!outcome.transportError.empty())
                    std::fprintf(stderr, "[report] %s\n", outcome.transportError.c_str());
                report.message = outcome.reply.text;
                report.savedPath = outcome.savedPath;
                switch (outcome.reply.kind)
                {
                case br::Reply::Kind::Sent:
                    report.state = ui::ReportUi::State::Sent;
                    report.id = outcome.reply.id;
                    report.copied = !report.id.empty();
                    if (report.copied)
                        SetClipboardText(report.id.c_str());
                    // The report is in: the form empties so a second press cannot send it twice.
                    report.form.title.clear();
                    report.form.description.clear();
                    report.changed = true;
                    app.status = outcome.reply.text;
                    break;
                case br::Reply::Kind::FieldError:
                {
                    report.state = ui::ReportUi::State::FieldError;
                    const std::string field = outcome.reply.field;
                    if (nav.page == ui::Page::Report && (field == "title" || field == "description" || field == "contact"))
                        nav.focus = app.activeField = "report." + field;
                    break;
                }
                case br::Reply::Kind::RateLimited:
                    report.state = ui::ReportUi::State::RateLimited;
                    break;
                case br::Reply::Kind::Failed:
                    report.state = ui::ReportUi::State::SavedLocally;
                    break;
                }
            }
            if (app.requestLaunch && !app.running && app.discOk)
            {
                writeText(configPath, launcher::toJson(app.config));
                app.dirty = false;
                mic->stopMeter();   // Review F8: two processes must not hold the same microphone
                meterOn = false;
                if (win32glue::startGame(dir.string(), app.config, game))
                {
                    lastLog = game.logPath;
                    app.status = "started; log " + fs::path(game.logPath).filename().string();
                    app.exitLine.clear();
                }
                else
                    app.status = game.error;
            }
        }
        app.requestBrowse = app.requestVerify = app.requestLaunch = app.requestSave = false;
        app.requestDiagnostics = app.requestOpenLogs = false;
        app.requestMicChanged = app.requestMicRescan = false;

        // PS2X_LAUNCHER_SHOT=<file>: the REAL window, with its own chrome, at whatever size it opened at --
        // a GDI or BitBlt grab of a GL window comes back white on this machine, so the launcher takes it.
        if (selfShot != nullptr && ++selfShotFrames == 120u)
        {
            Image shot = LoadImageFromScreen();
            if (!ExportImage(shot, selfShot))
                std::fprintf(stderr, "[launcher] could not write %s\n", selfShot);
            UnloadImage(shot);
            quitRequested = true;
        }

        // ---- --screenshot: three frames a page, then the PNG ------------------------------------------------
        if (screenshotDir != nullptr)
        {
            if (shotIndex >= shots.size())
                break;
            const Shot &shot = shots[shotIndex];
            if (shotFrame == 0)
            {
                if ((GetScreenWidth() != shot.w || GetScreenHeight() != shot.h) && resizeWaits < 90)
                {
                    SetWindowSize(shot.w, shot.h);
                    ++resizeWaits;
                    continue;   // let the resize land before the state is set
                }
                resizeWaits = 0;
                app.nav.goTo(graph, shot.page);
                {
                    // Sprint 9 Goal 8: canned states, no request made.
                    const std::string suffix = shot.suffix;
                    app.activeField.clear();
                    app.serverStatus = suffix == "_status" ? "SOCOM Unzipped: online, 3 players, 1 game" : "";
                    ui::ReportUi &report = app.report;
                    report = ui::ReportUi{};
                    br::Inputs fakeIn;
                    fakeIn.version = app.version;
                    fakeIn.platform = "windows";
                    fakeIn.logText = "INFO:     > Renderer: NVIDIA GeForce RTX 4070 SUPER/PCIe/SSE2\nthe last run\n";
                    fakeIn.haveLastExit = true;
                    if (shot.page == ui::Page::Report && !suffix.empty())
                    {
                        report.form.title = "The game closes when I join a second round";
                        report.form.description =
                            "I hosted a Suppression room on Frostfire, played one round to the end, and when the second round "
                            "started loading the game window closed without a message. It happened twice in a row. The first "
                            "round was fine both times and voice chat worked.";
                        report.form.contact = "viper#1234 on Discord";
                        report.form.attachLog = true;
                    }
                    if (suffix == "_filled")
                        app.nav.focus = app.activeField = "report.description";
                    else if (shot.page == ui::Page::Report)
                        app.nav.focus = "report.send";
                    if (suffix == "_sending")
                        report.state = ui::ReportUi::State::Sending;
                    if (suffix == "_sent")
                    {
                        report.state = ui::ReportUi::State::Sent;
                        report.id = "BR-20260919-A1B2C3";
                        report.copied = true;
                        report.form.title.clear();
                        report.form.description.clear();
                    }
                    if (suffix == "_saved")
                    {
                        report.state = ui::ReportUi::State::SavedLocally;
                        report.message = br::parseReply(0, "").text;
                        report.savedPath = "C:\\games\\socom2\\logs\\bugreport_20260919_101500.json";
                    }
                    if (suffix == "_fielderror")
                    {
                        report.form.title = "abc";
                        report.state = ui::ReportUi::State::FieldError;
                        report.message = br::checkForm(report.form);
                        app.nav.focus = app.activeField = "report.title";
                    }
                    if (suffix == "_ratelimited")
                    {
                        report.state = ui::ReportUi::State::RateLimited;
                        report.message = br::parseReply(429, "", 1500).text;
                        report.savedPath = "C:\\games\\socom2\\logs\\bugreport_20260919_101500.json";
                    }
                    report.preview = br::previewLine(br::build(app.config, report.form, fakeIn), report.form);
                    report.changed = false;
                }
                const bool touchpadShot = std::strcmp(shot.suffix, "_crouch_touchpad") == 0;
                app.pad = (std::strcmp(shot.suffix, "_playstation") == 0 || touchpadShot) ? fakePlayStationPad() : fakeXboxPad();
                app.config.crouchShortcut = std::strncmp(shot.suffix, "_crouch_", 8) == 0 ? shot.suffix + 8 : "off";
                if (std::strcmp(shot.suffix, "_community_healed") == 0)
                {
                    // A saved config naming the unplayable preset: fromJson moves it to the one that exists.
                    launcher::Config saved;
                    launcher::fromJson("{\"serverPreset\": \"community\", \"server\": \"192.168.2.10\"}", saved);
                    app.config.serverPreset = saved.serverPreset;
                    app.config.server = saved.server;
                }
            }
            if (++shotFrame >= 3)
            {
                char path[512];
                // The page's slug ("play", "report"): every page's name but REPORT A BUG's was already that.
                std::snprintf(path, sizeof(path), "%s/%s%s_%dx%d.png", screenshotDir, ui::pageSlug(shot.page).c_str(),
                              shot.suffix, shot.w, shot.h);
                for (char *p = path; *p != '\0'; ++p)
                    *p = static_cast<char>(*p >= 'A' && *p <= 'Z' ? *p + 32 : *p);
                Image frame = LoadImageFromScreen();
                if (!ExportImage(frame, path))
                    std::fprintf(stderr, "[launcher] could not write %s\n", path);
                UnloadImage(frame);
                ++shotIndex;
                shotFrame = 0;
            }
        }
    }

    if (!app.fake)
        writeText(configPath, launcher::toJson(app.config));
    if (mic)
        mic->stopMeter();
    game.close();
    fonts.clear();
    CloseWindow();
    // A request still in flight: the window is gone already, and each join is bounded by its request's timeout.
    reportJob.join();
    statsJob.join();
    return 0;
}
