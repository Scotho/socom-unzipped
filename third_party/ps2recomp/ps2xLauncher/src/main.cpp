// SOCOM Unzipped launcher (Task 8b, packaging outline section 3): one window that owns config.json, verifies the
// disc image, shows what the game will read from the controller, and starts socom2.exe with the PS2X_* environment.
// raylib on purpose: the controller panel calls the same functions the game's input poll does.
//
//   socom_unzipped_launcher.exe            the window
//   socom_unzipped_launcher.exe --selftest load config.json, verify the ISO if one is set, print the environment, exit
#include "launcher/iso9660.h"
#include "launcher/launcher_config.h"
#include "launcher/mic_devices.h"
#include "launcher/sha256.h"
#include "win32_glue.h"

#include "raylib.h"

#include <chrono>
#include <cmath>
#include <memory>
#include <thread>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace
{
    constexpr int kWidth = 820;
    constexpr int kHeight = 932;   // Task 8: +26 for the Controller panel's pad list and dead-zone slider  // Task 10: +28 for the Video panel's FPS-overlay row  // Task 11: +34 for the Video panel's Volume row  // Task 9: +184 for the Microphone panel

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

    // ---- tiny immediate-mode widgets --------------------------------------------------------------------------

    const Color kBg = {28, 30, 34, 255};
    const Color kPanel = {40, 43, 48, 255};
    const Color kText = {225, 228, 232, 255};
    const Color kDim = {140, 145, 152, 255};
    const Color kAccent = {88, 160, 96, 255};
    const Color kBad = {220, 80, 70, 255};
    const Color kField = {22, 24, 27, 255};

    bool button(Rectangle r, const char *label, bool enabled = true)
    {
        const bool hover = enabled && CheckCollisionPointRec(GetMousePosition(), r);
        DrawRectangleRec(r, enabled ? (hover ? Color{70, 74, 82, 255} : Color{58, 62, 70, 255}) : Color{45, 47, 52, 255});
        DrawRectangleLinesEx(r, 1, enabled ? kDim : Color{60, 62, 66, 255});
        const int w = MeasureText(label, 16);
        DrawText(label, static_cast<int>(r.x + (r.width - w) / 2), static_cast<int>(r.y + (r.height - 16) / 2), 16, enabled ? kText : kDim);
        return hover && IsMouseButtonPressed(MOUSE_BUTTON_LEFT);
    }

    bool checkbox(float x, float y, const char *label, bool &value)
    {
        const Rectangle box = {x, y, 18, 18};
        const Rectangle hit = {x, y, 18 + 8 + static_cast<float>(MeasureText(label, 16)), 18};
        DrawRectangleRec(box, kField);
        DrawRectangleLinesEx(box, 1, kDim);
        if (value)
            DrawRectangle(static_cast<int>(x) + 4, static_cast<int>(y) + 4, 10, 10, kAccent);
        DrawText(label, static_cast<int>(x) + 26, static_cast<int>(y) + 1, 16, kText);
        if (CheckCollisionPointRec(GetMousePosition(), hit) && IsMouseButtonPressed(MOUSE_BUTTON_LEFT))
        {
            value = !value;
            return true;
        }
        return false;
    }

    // A row of radio choices; returns the selected index (changed or not).
    int radios(float x, float y, const std::vector<const char *> &labels, int selected)
    {
        float cx = x;
        for (size_t i = 0; i < labels.size(); ++i)
        {
            const Rectangle hit = {cx, y, 18 + 8 + static_cast<float>(MeasureText(labels[i], 16)), 18};
            DrawCircle(static_cast<int>(cx) + 9, static_cast<int>(y) + 9, 9, kField);
            DrawCircleLines(static_cast<int>(cx) + 9, static_cast<int>(y) + 9, 9, kDim);
            if (static_cast<int>(i) == selected)
                DrawCircle(static_cast<int>(cx) + 9, static_cast<int>(y) + 9, 5, kAccent);
            DrawText(labels[i], static_cast<int>(cx) + 26, static_cast<int>(y) + 1, 16, kText);
            if (CheckCollisionPointRec(GetMousePosition(), hit) && IsMouseButtonPressed(MOUSE_BUTTON_LEFT))
                selected = static_cast<int>(i);
            cx += hit.width + 24;
        }
        return selected;
    }

    // A text field that cannot be typed in: the address a preset decides. Same box, dimmed text, no cursor, and it
    // never takes the keyboard (clicks fall through).
    void readOnlyField(Rectangle r, const char *value)
    {
        DrawRectangleRec(r, kField);
        DrawRectangleLinesEx(r, 1, Color{60, 62, 66, 255});
        // trimmed from the end, not the start: the front of an address is the part that identifies it
        std::string shown = value;
        if (MeasureText(shown.c_str(), 16) > r.width - 12)
        {
            while (!shown.empty() && MeasureText((shown + "...").c_str(), 16) > r.width - 12)
                shown.pop_back();
            shown += "...";
        }
        DrawText(shown.c_str(), static_cast<int>(r.x) + 6, static_cast<int>(r.y) + 6, 16, kDim);
    }

    // A single-line text field; `active` is the field that takes the keyboard.
    void textField(Rectangle r, std::string &value, int id, int &active, bool &changed)
    {
        const bool isActive = active == id;
        DrawRectangleRec(r, kField);
        DrawRectangleLinesEx(r, 1, isActive ? kAccent : kDim);
        if (CheckCollisionPointRec(GetMousePosition(), r) && IsMouseButtonPressed(MOUSE_BUTTON_LEFT))
            active = id;
        if (isActive)
        {
            for (int c = GetCharPressed(); c > 0; c = GetCharPressed())
                if (c >= 32 && c < 127)
                {
                    value.push_back(static_cast<char>(c));
                    changed = true;
                }
            if ((IsKeyPressed(KEY_BACKSPACE) || IsKeyPressedRepeat(KEY_BACKSPACE)) && !value.empty())
            {
                value.pop_back();
                changed = true;
            }
            if (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_TAB))
                active = -1;
        }
        // draw the tail that fits
        std::string shown = value;
        while (!shown.empty() && MeasureText(shown.c_str(), 16) > r.width - 12)
            shown.erase(0, 1);
        DrawText(shown.c_str(), static_cast<int>(r.x) + 6, static_cast<int>(r.y) + 6, 16, kText);
        if (isActive && (static_cast<int>(GetTime() * 2) & 1))
            DrawText("_", static_cast<int>(r.x) + 6 + MeasureText(shown.c_str(), 16), static_cast<int>(r.y) + 6, 16, kAccent);
    }

    // Sprint 7 Task 11: an integer slider -- the double `slider` below quantises to steps of 0.05, which is
    // meaningless on a 0-100 range.
    void sliderInt(Rectangle r, int &value, int lo, int hi)
    {
        DrawRectangle(static_cast<int>(r.x), static_cast<int>(r.y + r.height / 2 - 2), static_cast<int>(r.width), 4, kField);
        const float t = static_cast<float>(value - lo) / static_cast<float>(hi - lo);
        DrawCircle(static_cast<int>(r.x + t * r.width), static_cast<int>(r.y + r.height / 2), 7, kAccent);
        if (CheckCollisionPointRec(GetMousePosition(), {r.x - 8, r.y, r.width + 16, r.height}) && IsMouseButtonDown(MOUSE_BUTTON_LEFT))
        {
            float nt = (GetMousePosition().x - r.x) / r.width;
            nt = nt < 0 ? 0 : (nt > 1 ? 1 : nt);
            value = lo + static_cast<int>(static_cast<float>(hi - lo) * nt + 0.5f);
        }
    }

    void slider(Rectangle r, double &value, double lo, double hi)
    {
        DrawRectangle(static_cast<int>(r.x), static_cast<int>(r.y + r.height / 2 - 2), static_cast<int>(r.width), 4, kField);
        const float t = static_cast<float>((value - lo) / (hi - lo));
        const float kx = r.x + t * r.width;
        DrawCircle(static_cast<int>(kx), static_cast<int>(r.y + r.height / 2), 7, kAccent);
        if (CheckCollisionPointRec(GetMousePosition(), {r.x - 8, r.y, r.width + 16, r.height}) && IsMouseButtonDown(MOUSE_BUTTON_LEFT))
        {
            float nt = (GetMousePosition().x - r.x) / r.width;
            nt = nt < 0 ? 0 : (nt > 1 ? 1 : nt);
            value = lo + (hi - lo) * nt;
            value = static_cast<double>(static_cast<int>(value * 20 + 0.5)) / 20.0;   // steps of 0.05
        }
    }

    void panelTitle(float x, float y, const char *title)
    {
        DrawText(title, static_cast<int>(x), static_cast<int>(y), 18, kAccent);
    }

    // Kept in step with hostPadAxis (ps2xRuntime/include/runtime/host_gamepad_select.h). The launcher does not
    // include the runtime's headers -- the same rule exitMessage follows (launcher_config.cpp).
    float launcherPadAxis(float v, float deadZone)
    {
        if (deadZone <= 0.0f)
            return v;
        const float mag = v < 0.0f ? -v : v;
        if (mag <= deadZone)
            return 0.0f;
        const float scaled = (mag - deadZone) / (1.0f - deadZone);
        return v < 0.0f ? -scaled : scaled;
    }

    // A column of radio choices; returns the selected index (changed or not). Pad names do not fit one 820 px row.
    int radiosColumn(float x, float y, const std::vector<std::string> &labels, int selected, float rowHeight = 22.0f)
    {
        for (size_t i = 0; i < labels.size(); ++i)
        {
            const float ry = y + static_cast<float>(i) * rowHeight;
            const Rectangle hit = {x, ry, 18 + 8 + static_cast<float>(MeasureText(labels[i].c_str(), 14)), 18};
            DrawCircle(static_cast<int>(x) + 9, static_cast<int>(ry) + 9, 9, kField);
            DrawCircleLines(static_cast<int>(x) + 9, static_cast<int>(ry) + 9, 9, kDim);
            if (static_cast<int>(i) == selected)
                DrawCircle(static_cast<int>(x) + 9, static_cast<int>(ry) + 9, 5, kAccent);
            DrawText(labels[i].c_str(), static_cast<int>(x) + 26, static_cast<int>(ry) + 2, 14, kText);
            if (CheckCollisionPointRec(GetMousePosition(), hit) && IsMouseButtonPressed(MOUSE_BUTTON_LEFT))
                selected = static_cast<int>(i);
        }
        return selected;
    }

    // The controller diagram for ONE slot: the same raylib calls the game's input poll makes
    // (socom2_host_input.cpp), on the pad the player picked, with the dead zone they set applied to the drawn
    // sticks -- so a dot resting in the middle of the ring is exactly the neutral the game will see.
    void drawController(float x, float y, int slot, float deadZone)
    {
        const bool pad = slot >= 0 && IsGamepadAvailable(slot);
        const char *name = pad ? GetGamepadName(slot) : "none";
        DrawText(pad ? name : "no gamepad (keyboard: WASD move, IJKL look, Z/X/C/V = square/cross/circle/triangle, Q/E = L1/R1, Enter = start)",
                 static_cast<int>(x), static_cast<int>(y), 14, pad ? kText : kDim);
        auto stick = [&](float cx, float cy, int axisX, int axisY, const char *label)
        {
            DrawCircleLines(static_cast<int>(cx), static_cast<int>(cy), 28, kDim);
            float ax = 0, ay = 0;
            if (pad)
            {
                ax = launcherPadAxis(GetGamepadAxisMovement(slot, axisX), deadZone);
                ay = launcherPadAxis(GetGamepadAxisMovement(slot, axisY), deadZone);
            }
            DrawCircle(static_cast<int>(cx + ax * 24), static_cast<int>(cy + ay * 24), 6, kAccent);
            DrawText(label, static_cast<int>(cx) - 8, static_cast<int>(cy) + 34, 12, kDim);
        };
        y += 18;   // below the hint line
        stick(x + 60, y + 70, GAMEPAD_AXIS_LEFT_X, GAMEPAD_AXIS_LEFT_Y, "L");
        stick(x + 150, y + 70, GAMEPAD_AXIS_RIGHT_X, GAMEPAD_AXIS_RIGHT_Y, "R");
        struct Btn { int id; float dx, dy; const char *label; };
        const Btn btns[] = {
            {GAMEPAD_BUTTON_LEFT_FACE_UP, 240, 40, "^"}, {GAMEPAD_BUTTON_LEFT_FACE_DOWN, 240, 100, "v"},
            {GAMEPAD_BUTTON_LEFT_FACE_LEFT, 210, 70, "<"}, {GAMEPAD_BUTTON_LEFT_FACE_RIGHT, 270, 70, ">"},
            {GAMEPAD_BUTTON_RIGHT_FACE_UP, 360, 40, "T"}, {GAMEPAD_BUTTON_RIGHT_FACE_DOWN, 360, 100, "X"},
            {GAMEPAD_BUTTON_RIGHT_FACE_LEFT, 330, 70, "S"}, {GAMEPAD_BUTTON_RIGHT_FACE_RIGHT, 390, 70, "O"},
            {GAMEPAD_BUTTON_LEFT_TRIGGER_1, 210, 10, "L1"}, {GAMEPAD_BUTTON_LEFT_TRIGGER_2, 250, 10, "L2"},
            {GAMEPAD_BUTTON_RIGHT_TRIGGER_1, 350, 10, "R1"}, {GAMEPAD_BUTTON_RIGHT_TRIGGER_2, 390, 10, "R2"},
            {GAMEPAD_BUTTON_MIDDLE_LEFT, 280, 130, "Bk"}, {GAMEPAD_BUTTON_MIDDLE_RIGHT, 320, 130, "St"},
            {GAMEPAD_BUTTON_LEFT_THUMB, 60, 130, "L3"}, {GAMEPAD_BUTTON_RIGHT_THUMB, 150, 130, "R3"},
        };
        for (const Btn &b : btns)
        {
            const bool down = pad && IsGamepadButtonDown(slot, b.id);
            DrawCircle(static_cast<int>(x + b.dx), static_cast<int>(y + b.dy), 11, down ? kAccent : kField);
            DrawCircleLines(static_cast<int>(x + b.dx), static_cast<int>(y + b.dy), 11, kDim);
            DrawText(b.label, static_cast<int>(x + b.dx) - MeasureText(b.label, 10) / 2, static_cast<int>(y + b.dy) - 5, 10, down ? kBg : kText);
        }
    }

    int indexOf(const std::vector<const char *> &labels, const std::string &value, int fallback)
    {
        for (size_t i = 0; i < labels.size(); ++i)
            if (value == labels[i])
                return static_cast<int>(i);
        return fallback;
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

    SetConfigFlags(FLAG_WINDOW_HIGHDPI);
    InitWindow(kWidth, kHeight, "SOCOM Unzipped");
    SetTargetFPS(60);
    SetExitKey(KEY_NULL);

    DiscStatus disc = checkDisc(config.isoPath);
    int activeField = -1;
    win32glue::GameProcess game;
    std::string status = disc.ok ? "ready" : "";
    std::string lastLog;
    // Sprint 7 Task 9a: the capture devices, enumerated once here and again only on Rescan --
    // ma_context_get_devices starts the host audio backend, and doing that sixty times a second stalls the
    // window on some WASAPI setups.
    std::unique_ptr<launcher::MicDevices> mic = launcher::makeMicDevices();
    std::vector<std::string> micLabels = launcher::micLabels(*mic);
    std::string micStatus;
    bool meterOn = !config.micDevice.empty() && mic->startMeter(config.micDevice);
    bool dirty = false;

    const std::vector<const char *> scaleLabels = {"Native", "Sharp (2x)", "Sharper (3x, experimental)", "Sharpest (4x)"};
    const std::vector<const char *> filterLabels = {"linear", "integer", "point"};
    const std::vector<const char *> sizeLabels = {"640x448", "1280x896", "fullscreen", "Match display"};
    std::vector<const char *> presetLabels;
    for (const launcher::ServerPreset &p : launcher::kServerPresets)
        presetLabels.push_back(p.label);

    // --screenshot <file.png>: draw thirty frames, save the window with raylib's own reader, exit (a GDI grab of a GL
    // window comes back white on this machine).
    const char *screenshotPath = (argc > 2 && std::strcmp(argv[1], "--screenshot") == 0) ? argv[2] : nullptr;
    unsigned frames = 0;
    while (!WindowShouldClose())
    {
        if (screenshotPath && frames == 30u)
        {
            TakeScreenshot(screenshotPath);
            break;
        }
        if ((frames++ % 600u) == 0u)   // a heartbeat every ten seconds when stdout is captured
            std::fprintf(stderr, "[launcher] frame %u screen %dx%d render %dx%d ready %d\n", frames, GetScreenWidth(), GetScreenHeight(), GetRenderWidth(), GetRenderHeight(), IsWindowReady() ? 1 : 0);
        BeginDrawing();
        ClearBackground(kBg);
        float y = 16;

        // ---- Disc ----
        DrawRectangle(12, static_cast<int>(y) - 6, kWidth - 24, 84, kPanel);
        panelTitle(24, y, "Disc");
        bool pathChanged = false;
        textField({24, y + 28, kWidth - 24 - 24 - 110, 30}, config.isoPath, 1, activeField, pathChanged);
        if (button({kWidth - 24 - 96, y + 28, 96, 30}, "Browse..."))
        {
            const std::string chosen = win32glue::browseForIso();
            if (!chosen.empty())
            {
                config.isoPath = chosen;
                pathChanged = true;
            }
        }
        if (pathChanged)
        {
            disc = checkDisc(config.isoPath);
            dirty = true;
        }
        else if (activeField != 1 && !disc.checked)
            disc = checkDisc(config.isoPath);
        DrawText(disc.message.c_str(), 24, static_cast<int>(y) + 62, 14, disc.ok ? kAccent : kBad);
        y += 96;

        // ---- Video ----
        DrawRectangle(12, static_cast<int>(y) - 6, kWidth - 24, 180, kPanel);
        panelTitle(24, y, "Video");
        DrawText("Detail", 24, static_cast<int>(y) + 30, 14, kDim);
        int scaleSel = config.gsScale >= 4 ? 3 : (config.gsScale == 3 ? 2 : (config.gsScale == 2 ? 1 : 0));
        const int newScale = radios(100, y + 28, scaleLabels, scaleSel);
        if (newScale != scaleSel)
        {
            config.gsScale = newScale + 1;
            dirty = true;
        }
        DrawText("Filter", 24, static_cast<int>(y) + 58, 14, kDim);
        int filterSel = indexOf(filterLabels, config.presentFilter, 0);
        const int newFilter = radios(100, y + 56, filterLabels, filterSel);
        if (newFilter != filterSel)
        {
            config.presentFilter = filterLabels[newFilter];
            dirty = true;
        }
        DrawText("Window", 24, static_cast<int>(y) + 86, 14, kDim);
        const std::string monitorSize = TextFormat("%dx%d", GetMonitorWidth(GetCurrentMonitor()), GetMonitorHeight(GetCurrentMonitor()));
        int sizeSel = indexOf(sizeLabels, config.windowSize, -1);
        if (sizeSel < 0)
            sizeSel = (config.windowSize == monitorSize) ? 3 : 0;
        const int newSize = radios(100, y + 84, sizeLabels, sizeSel);
        if (newSize != sizeSel)
        {
            // "Match display" is a button, not a stored value: what lands in config.json is the monitor's own
            // <w>x<h>, so a config carried to a machine with a different screen is a size, not a surprise.
            config.windowSize = (newSize == 3) ? monitorSize : std::string(sizeLabels[newSize]);
            dirty = true;
        }
        if (checkbox(100, y + 110, "FPS overlay (host fps, the game's vsync rate, frame time)", config.fpsOverlay))
            dirty = true;
        DrawText(TextFormat("Volume %d%%", config.audioVolume), 24, static_cast<int>(y) + 140, 14, kDim);
        {
            const int before = config.audioVolume;
            sliderInt({140, y + 138, 280, 20}, config.audioVolume, 0, 100);
            if (config.audioVolume != before)
                dirty = true;
        }
        y += 192;

        // ---- Controller ----
        DrawRectangle(12, static_cast<int>(y) - 6, kWidth - 24, 232, kPanel);
        panelTitle(24, y, "Controller");
        // The pads raylib sees, polled every frame: one plugged in while the launcher is open appears in the
        // list without a restart, and one unplugged disappears (the pick then falls back to "first available",
        // which is exactly what an unset PS2X_HOST_GAMEPAD_INDEX means to the runtime).
        std::vector<std::string> padLabels = {"first available"};
        std::vector<int> padSlots = {-1};
        for (int i = 0; i < 4; ++i)
        {
            if (IsGamepadAvailable(i))
            {
                padLabels.push_back(std::string("[") + std::to_string(i) + "] " + GetGamepadName(i));
                padSlots.push_back(i);
            }
        }
        int padSel = 0;
        for (size_t i = 0; i < padSlots.size(); ++i)
            if (padSlots[i] == config.gamepadIndex)
                padSel = static_cast<int>(i);
        const int newPad = radiosColumn(480, y + 28, padLabels, padSel);
        if (newPad != padSel)
        {
            config.gamepadIndex = padSlots[newPad];
            dirty = true;
        }
        // The slot the test area draws: the pick, or the first available pad when there is no pick.
        int shownSlot = config.gamepadIndex;
        if (shownSlot < 0)
        {
            for (int i = 0; i < 4 && shownSlot < 0; ++i)
                if (IsGamepadAvailable(i))
                    shownSlot = i;
        }
        drawController(24, y + 28, shownSlot, static_cast<float>(config.padDeadZone));
        DrawText(TextFormat("dead zone %.2f", config.padDeadZone), 480, static_cast<int>(y) + 128, 14, kDim);
        {
            const double before = config.padDeadZone;
            slider({480, y + 148, 280, 20}, config.padDeadZone, 0.0, 0.40);
            if (config.padDeadZone != before)
                dirty = true;
        }
        if (checkbox(480, y + 176, "mouse look", config.mouseLook))
            dirty = true;
        DrawText(TextFormat("sensitivity %.2f", config.mouseSensitivity), 480, static_cast<int>(y) + 200, 14, kDim);
        {
            const double before = config.mouseSensitivity;
            slider({480, y + 218, 280, 20}, config.mouseSensitivity, 0.25, 3.0);
            if (config.mouseSensitivity != before)
                dirty = true;
        }
        y += 244;

        // ---- Microphone ----
        DrawRectangle(12, static_cast<int>(y) - 6, kWidth - 24, 172, kPanel);
        panelTitle(24, y, "Microphone");
        int micSel = 0;
        for (size_t i = 1; i < micLabels.size(); ++i)
            if (micLabels[i] == config.micDevice)
                micSel = static_cast<int>(i);
        const int newMic = radiosColumn(24, y + 28, micLabels, micSel);
        if (newMic != micSel)
        {
            config.micDevice = (newMic == 0) ? std::string() : micLabels[newMic];
            mic->stopMeter();
            meterOn = !config.micDevice.empty() && mic->startMeter(config.micDevice);
            micStatus = config.micDevice.empty() ? "" : (meterOn ? "listening" : "that device will not open");
            dirty = true;
        }
        if (button({kWidth - 24 - 96, y + 28, 96, 26}, "Rescan"))
        {
            micLabels = launcher::micLabels(*mic);
            micStatus = TextFormat("%d capture device(s)", static_cast<int>(micLabels.size()) - 1);
        }
        // The meter: -60 dB (silence) to 0 dB (full scale) across 280 px, redrawn every frame from the capture
        // callback's atomic. A bar that moves when the player speaks is the whole point of the panel.
        const float db = meterOn ? mic->levelDb() : -INFINITY;
        float filled = 0.0f;
        if (meterOn && std::isfinite(db))
            filled = (db + 60.0f) / 60.0f;
        filled = filled < 0.0f ? 0.0f : (filled > 1.0f ? 1.0f : filled);
        DrawRectangle(480, static_cast<int>(y) + 32, 280, 18, kField);
        DrawRectangle(480, static_cast<int>(y) + 32, static_cast<int>(280.0f * filled), 18, filled > 0.9f ? kBad : kAccent);
        DrawRectangleLines(480, static_cast<int>(y) + 32, 280, 18, kDim);
        DrawText(meterOn && std::isfinite(db) ? TextFormat("%.0f dB", db) : "--", 768, static_cast<int>(y) + 34, 14, kDim);
        DrawText(micStatus.c_str(), 480, static_cast<int>(y) + 58, 14, kDim);
        DrawText("the game does not send your voice yet (Sprint 8); this meter proves the device works",
                 480, static_cast<int>(y) + 80, 12, kDim);
        y += 184;

        // ---- Online ----
        DrawRectangle(12, static_cast<int>(y) - 6, kWidth - 24, 128, kPanel);
        panelTitle(24, y, "Online");
        bool changed = false;
        int presetSel = static_cast<int>(presetLabels.size()) - 1;   // "Custom" unless one of the ids matches
        for (size_t i = 0; i < presetLabels.size(); ++i)
            if (config.serverPreset == launcher::kServerPresets[i].id)
                presetSel = static_cast<int>(i);
        const int newPreset = radios(24, y + 26, presetLabels, presetSel);
        if (newPreset != presetSel)
        {
            config.serverPreset = launcher::kServerPresets[newPreset].id;
            changed = true;
        }
        const launcher::ServerPreset *preset = launcher::findServerPreset(config.serverPreset);
        const bool ownAddress = preset == nullptr || preset->address[0] == '\0';
        DrawText("Server", 24, static_cast<int>(y) + 56, 14, kDim);
        if (ownAddress)
            textField({100, y + 50, 310, 30}, config.server, 2, activeField, changed);
        else
        {
            if (activeField == 2)
                activeField = -1;   // the preset took the field away mid-edit
            readOnlyField({100, y + 50, 310, 30}, preset->address);
        }
        DrawText("Profile", 430, static_cast<int>(y) + 56, 14, kDim);
        textField({490, y + 50, 200, 30}, config.profile, 3, activeField, changed);
        DrawText(preset ? preset->note : "", 100, static_cast<int>(y) + 84, 14, kDim);
        if (checkbox(24, y + 100, "second instance on this machine (for testing)", config.secondInstance))
            changed = true;
        if (changed)
            dirty = true;
        y += 130;

        // ---- Launch ----
        const bool running = game.running();
        if (!running && game.process)
        {
            // Task 1a: 65 means the run happened but on the CPU rasterizer -- say so rather than
            // leaving the player with a slideshow and no reason.
            const std::string why = launcher::exitMessage(game.exitCode());
            game.close();
            status = why.empty() ? "the game exited" : why;
        }
        const bool canLaunch = disc.ok && !running;
        if (button({24, y, 160, 40}, running ? "running..." : "Launch", canLaunch))
        {
            writeText(configPath, launcher::toJson(config));
            dirty = false;
            if (win32glue::startGame(dir.string(), config, game))
            {
                lastLog = game.logPath;
                status = "started; log " + fs::path(game.logPath).filename().string();
            }
            else
                status = game.error;
        }
        if (button({200, y, 170, 40}, "Copy diagnostics"))
            status = copyDiagnostics(dir, lastLog);
        if (button({386, y, 120, 40}, "Open logs"))
            win32glue::openFolder((dir / "logs").string());
        DrawText(status.c_str(), 24, static_cast<int>(y) + 50, 14, kDim);
        if (dirty)
            DrawText("unsaved changes (saved on Launch or exit)", kWidth - 24 - MeasureText("unsaved changes (saved on Launch or exit)", 12), static_cast<int>(y) + 52, 12, kDim);
        EndDrawing();
    }
    writeText(configPath, launcher::toJson(config));
    mic->stopMeter();
    game.close();
    CloseWindow();
    return 0;
}
