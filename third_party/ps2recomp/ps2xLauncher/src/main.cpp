// SOCOM Unzipped launcher (Task 8b, packaging outline section 3; redesigned in Sprint 8 Goal 9): one window
// that owns config.json, verifies the disc image, shows what the game will read from the controller, and
// starts socom2.exe with the PS2X_* environment.
// raylib on purpose: the controller page calls the same functions the game's input poll does.
//
//   socom_unzipped_launcher.exe              the window
//   socom_unzipped_launcher.exe --selftest   load config.json, verify the ISO if one is set, print the environment, exit
//   socom_unzipped_launcher.exe --screenshot <dir>   every page at both sizes, on a fixed fake state, as PNGs
//
// This file is setup, the loop and the page dispatch. Everything drawn lives in src/ui/.
#include "launcher/iso9660.h"
#include "launcher/launcher_config.h"
#include "launcher/launcher_layout.h"
#include "launcher/mic_devices.h"
#include "launcher/sha256.h"
#include "win32_glue.h"

#include "ui/fonts.h"
#include "ui/focus.h"
#include "ui/glyphs.h"
#include "ui/pad_render.h"
#include "ui/pages.h"
#include "ui/theme.h"
#include "ui/widgets.h"

#include "raylib.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;

namespace
{
    std::string readText(const fs::path &p)
    {
        std::ifstream in(p, std::ios::binary);
        if (!in)
            return {};
        std::stringstream ss;
        ss << in.rdbuf();
        return ss.str();
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

    // "Copy diagnostics": the last run log and config.json into diagnostics/<stamp>/ (no archiver dependency).
    std::string copyDiagnostics(const fs::path &dir, const std::string &lastLog)
    {
        const fs::path out = dir / "diagnostics" / win32glue::stamp();
        std::error_code ec;
        fs::create_directories(out, ec);
        if (ec)
            return "cannot create " + out.string();
        if (!lastLog.empty() && fs::exists(lastLog))
            fs::copy_file(lastLog, out / fs::path(lastLog).filename(), fs::copy_options::overwrite_existing, ec);
        if (fs::exists(dir / "config.json"))
            fs::copy_file(dir / "config.json", out / "config.json", fs::copy_options::overwrite_existing, ec);
        return "copied to " + out.string();
    }

    // ---- the chrome around the pages ----------------------------------------------------------------------

    void drawHeader(const ui::Ctx &ctx, ui::App &app)
    {
        using namespace ui;
        const Rect h = app.frame.header;
        fillRect(ctx, h, theme::panel);
        fillRect(ctx, Rect{0.0f, h.bottom() - 2.0f, h.w, 2.0f}, theme::line);

        text(ctx, "SOCOM II", Vec2{metrics::margin, 8.0f}, 38.0f, theme::gold, Face::Display);
        const float wordmarkW = textWidth(ctx, "SOCOM II", 38.0f, Face::Display);
        text(ctx, "UNZIPPED", Vec2{metrics::margin + 3.0f, 50.0f}, 16.0f, theme::goldHi, Face::Bold);
        fillRect(ctx, Rect{metrics::margin, 46.0f, wordmarkW, 2.0f}, theme::alpha(theme::gold, 120));

        // The state, with its lamp, at the right.
        const char *state = app.running ? "RUNNING" : (app.discOk ? "READY" : "NOT READY");
        const Rgba lamp = app.running ? theme::goldHi : (app.discOk ? theme::lampGreen : theme::warn);
        const float sw = textWidth(ctx, state, 20.0f, Face::Bold);
        const float sx = h.w - metrics::margin - sw;
        text(ctx, state, Vec2{sx, 40.0f}, 20.0f, theme::text, Face::Bold);
        const Vec2 lampAt{h.w - metrics::margin - 9.0f, 24.0f};
        fillCircle(ctx, lampAt, 7.0f, lamp);
        strokeCircle(ctx, lampAt, 13.0f, theme::alpha(lamp, 110), 2.0f);
        const char *what = app.running ? "the game has the screen" : (app.discOk ? "disc verified" : "disc not verified");
        text(ctx, what, Vec2{h.w - metrics::margin - 30.0f - textWidth(ctx, what, 15.0f), 17.0f}, 15.0f, theme::dim);
    }

    void drawRail(const ui::Ctx &ctx, ui::App &app, const std::vector<ui::Node> &rail)
    {
        using namespace ui;
        fillRect(ctx, app.frame.rail, theme::alpha(theme::panel, 150));
        fillRect(ctx, Rect{app.frame.rail.right() - 2.0f, app.frame.rail.y, 2.0f, app.frame.rail.h}, theme::line);
        for (const Node &n : rail)
        {
            const bool current = n.page == app.nav.page;
            const bool live = hovered(ctx, n.r) || focused(ctx, n.id);
            fillRect(ctx, n.r, current ? theme::panelHi : (live ? theme::panel : theme::alpha(theme::panel, 190)));
            strokeRect(ctx, n.r, current || live ? theme::line : theme::alpha(theme::line, 120), 2.0f);
            fillRect(ctx, Rect{n.r.x, n.r.y, 5.0f, n.r.h}, current ? theme::gold : theme::alpha(theme::line, 160));
            const float size = 19.0f;
            text(ctx, pageName(n.page), Vec2{n.r.x + 20.0f, n.r.y + (n.r.h - size * 1.2f) * 0.5f}, size,
                 current ? theme::goldHi : (live ? theme::text : theme::dim), Face::Display);
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
        text(ctx, pageName(app.nav.page), Vec2{band.x + 18.0f, band.y + 8.0f}, 24.0f, theme::goldHi, Face::Display);
        const float nameW = textWidth(ctx, pageName(app.nav.page), 24.0f, Face::Display);
        const char *title = pageTitle(app.nav.page);
        const char *dash = std::strstr(title, "-- ");
        const std::string sub = dash != nullptr ? std::string(dash + 3) : std::string(title);
        const float room = band.w - nameW - 60.0f - (app.dirty ? 190.0f : 0.0f);
        text(ctx, ellipsizeEnd(ctx, sub, room, 16.0f).c_str(), Vec2{band.x + 30.0f + nameW, band.y + 13.0f}, 16.0f, theme::dim);
        if (app.dirty)
        {
            const char *hint = "UNSAVED CHANGES";
            const float w = textWidth(ctx, hint, 14.0f, Face::Bold);
            text(ctx, hint, Vec2{band.right() - 16.0f - w, band.y + 14.0f}, 14.0f, theme::warn, Face::Bold);
        }
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
        app.config.serverPreset = "custom";
        app.config.server = "127.0.0.1";
        app.config.profile = "player";
        app.config.micDevice = "Headset (USB)";
        app.discChecked = true;
        app.discOk = true;
        app.discMessage = "SOCOM II U.S. Navy SEALs NTSC r0001";
        app.status = "ready";
        app.exitLine = "the last run exited normally";
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
        app.layout.customServer = true;
    }
}

int main(int argc, char **argv)
{
    const fs::path dir = win32glue::exeDirectory();
    const fs::path configPath = dir / "config.json";
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
    SetConfigFlags(screenshotDir != nullptr ? FLAG_WINDOW_RESIZABLE : (FLAG_WINDOW_HIGHDPI | FLAG_WINDOW_RESIZABLE));
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

    ui::Fonts fonts = ui::loadFonts();

    ui::App app;
    app.config = config;
    app.configPath = configPath.string();
    app.logsPath = (dir / "logs").string();
    app.version = readText(dir / "version.txt");
    while (!app.version.empty() && (app.version.back() == '\n' || app.version.back() == '\r'))
        app.version.pop_back();

    win32glue::GameProcess game;
    std::string lastLog;
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

    ui::Nav &nav = app.nav;
    nav.page = ui::Page::Play;
    nav.focus = ui::railId(ui::Page::Play);

    ui::Rect shownFocus{};
    bool focusShownValid = false;
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
    }
    size_t shotIndex = 0;
    int shotFrame = 0;
    int resizeWaits = 0;

    while (!WindowShouldClose())
    {
        const float scale = ui::scaleFor(GetScreenWidth(), GetScreenHeight());
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
                // Task 1a: 65 means the run happened but on the CPU rasterizer -- say so rather than
                // leaving the player with a slideshow and no reason.
                const std::string why = launcher::exitMessage(game.exitCode());
                game.close();
                app.exitLine = why.empty() ? "the game exited" : why;
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

        if (!app.fake)
        {
            const bool typing = !app.activeField.empty();
            const int padSlot = shownSlot(app.config);
            const bool padPresent = padSlot >= 0 && IsGamepadAvailable(padSlot);
            auto padPressed = [&](int button) { return padPresent && IsGamepadButtonPressed(padSlot, button); };

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
                if (padPressed(GAMEPAD_BUTTON_LEFT_FACE_LEFT))
                    dx -= 1;
                if (padPressed(GAMEPAD_BUTTON_LEFT_FACE_RIGHT))
                    dx += 1;
                if (padPressed(GAMEPAD_BUTTON_LEFT_FACE_UP))
                    dy -= 1;
                if (padPressed(GAMEPAD_BUTTON_LEFT_FACE_DOWN))
                    dy += 1;
                // The left stick, with a repeat so a held stick walks rather than sprints.
                if (padPresent)
                {
                    const float ax = GetGamepadAxisMovement(padSlot, GAMEPAD_AXIS_LEFT_X);
                    const float ay = GetGamepadAxisMovement(padSlot, GAMEPAD_AXIS_LEFT_Y);
                    const bool pushed = std::fabs(ax) > 0.55f || std::fabs(ay) > 0.55f;
                    if (!pushed)
                        padRepeatAt = 0.0;
                    else if (ctx.time >= padRepeatAt)
                    {
                        padRepeatAt = ctx.time + (padRepeatAt == 0.0 ? 0.32 : 0.13);
                        if (std::fabs(ax) > std::fabs(ay))
                            dx += ax < 0.0f ? -1 : 1;
                        else
                            dy += ay < 0.0f ? -1 : 1;
                    }
                }
                if (dx != 0 || dy != 0)
                    app.padPrompts = padPresent && !(IsKeyDown(KEY_LEFT) || IsKeyDown(KEY_RIGHT) || IsKeyDown(KEY_UP) || IsKeyDown(KEY_DOWN));

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
                ctx.activate = IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_SPACE) ||
                               padPressed(GAMEPAD_BUTTON_RIGHT_FACE_DOWN);
                if (IsKeyPressed(KEY_ESCAPE) || padPressed(GAMEPAD_BUTTON_RIGHT_FACE_RIGHT))
                    nav.back(graph);
                if (padPressed(GAMEPAD_BUTTON_LEFT_TRIGGER_1))
                    nav.goTo(graph, ui::pageAt(ui::pageIndex(nav.page) - 1));
                if (padPressed(GAMEPAD_BUTTON_RIGHT_TRIGGER_1))
                    nav.goTo(graph, ui::pageAt(ui::pageIndex(nav.page) + 1));
                if (padPressed(GAMEPAD_BUTTON_MIDDLE_RIGHT))
                    app.requestLaunch = true;
                if (IsKeyPressed(KEY_F5))
                    app.requestVerify = true;
                if (padPressed(GAMEPAD_BUTTON_RIGHT_FACE_DOWN) || padPressed(GAMEPAD_BUTTON_RIGHT_FACE_RIGHT))
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
        drawHeader(ctx, app);
        drawRail(ctx, app, rail);
        drawContentFrame(ctx, app);
        drawPage(ctx, app, nodes);
        drawBar(ctx, app, nodes);

        // The focus ring, eased into place over 120 ms (nothing else on the page moves).
        const ui::Node *focusNode = graph.find(nav.focus);
        if (focusNode != nullptr)
        {
            const ui::Rect target = focusNode->r;
            if (!focusShownValid || app.fake)
                shownFocus = target;
            else
            {
                const float k = std::min(1.0f, GetFrameTime() / 0.12f);
                shownFocus.x += (target.x - shownFocus.x) * k;
                shownFocus.y += (target.y - shownFocus.y) * k;
                shownFocus.w += (target.w - shownFocus.w) * k;
                shownFocus.h += (target.h - shownFocus.h) * k;
            }
            focusShownValid = true;
            ui::focusRing(ctx, shownFocus);
        }

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
            if (app.requestDiagnostics)
                app.status = copyDiagnostics(dir, lastLog);
            if (app.requestOpenLogs)
                win32glue::openFolder((dir / "logs").string());
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
        app.requestBrowse = app.requestVerify = app.requestLaunch = false;
        app.requestDiagnostics = app.requestOpenLogs = false;
        app.requestMicChanged = app.requestMicRescan = false;

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
                app.pad = std::strlen(shot.suffix) > 0 ? fakePlayStationPad() : fakeXboxPad();
            }
            if (++shotFrame >= 3)
            {
                char path[512];
                std::snprintf(path, sizeof(path), "%s/%s%s_%dx%d.png", screenshotDir, ui::pageName(shot.page),
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
    ui::unloadFonts(fonts);
    CloseWindow();
    return 0;
}
