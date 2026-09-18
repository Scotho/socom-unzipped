#include "socom2_host_input.h"

#include "raylib.h"
#include "runtime/host_gamepad.h"
#include "runtime/host_gamepad_select.h"
#include "runtime/injected_pad_latch.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace ps2_stubs
{
    namespace
    {
        struct ScriptEvent
        {
            double at = 0.0;
            double hold = 0.25;
            uint16_t buttons = 0;          // bit n = button id n
            uint8_t axisValue[4] = {0x80u, 0x80u, 0x80u, 0x80u};
            bool axisSet[4] = {false, false, false, false};
            std::string text;
        };

        struct HostInputConfig
        {
            bool initialised = false;
            bool mouse = false;
            float mouseSensitivity = 4.0f;
            std::vector<ScriptEvent> script;
            std::vector<bool> fired;
            std::chrono::steady_clock::time_point start;
        };

        HostInputConfig g_config;

        // PS2X_SOCOM2_INPUT_FILE sampler. The harness holds a press for ~0.09 s of wall clock, but
        // the poll below runs once per rendered frame, so under ~11 fps a whole press fell between
        // two polls and was never seen (ten driven launches, 2026-09-18). A thread samples the file
        // every 2 ms into a latch and the poll takes every button seen since the previous poll, so a
        // press is delivered late rather than dropped. No thread exists unless the variable is set.
        struct InjectedPadSampler
        {
            ps2x::InjectedPadLatch latch;
            std::thread worker;
            std::atomic<bool> stop{false};

            void start(const char *path)
            {
                if (worker.joinable())
                    return;
                stop.store(false, std::memory_order_relaxed);
                const std::string file(path);
                worker = std::thread([this, file]()
                {
                    while (!stop.load(std::memory_order_relaxed))
                    {
                        if (FILE *f = std::fopen(file.c_str(), "rb"))
                        {
                            char line[128] = {0};
                            const size_t n = std::fread(line, 1, sizeof(line) - 1, f);
                            std::fclose(f);
                            line[n] = '\0';
                            ps2x::InjectedPadSample sample;
                            if (ps2x::parseInjectedPadLine(line, sample))
                                latch.observe(sample);
                        }
                        std::this_thread::sleep_for(std::chrono::milliseconds(2));
                    }
                });
            }

            void shutdown()
            {
                stop.store(true, std::memory_order_relaxed);
                if (worker.joinable())
                    worker.join();
            }

            ~InjectedPadSampler() { shutdown(); }
        };

        InjectedPadSampler g_injectedPadSampler;

        int buttonIdFromName(const std::string &name)
        {
            static const char *const names[16] = {
                "SELECT", "L3", "R3", "START", "UP", "RIGHT", "DOWN", "LEFT",
                "L2", "R2", "L1", "R1", "TRIANGLE", "CIRCLE", "CROSS", "SQUARE"};
            for (int index = 0; index < 16; ++index)
            {
                if (name == names[index])
                {
                    return index;
                }
            }
            if (name == "X")
                return kPadCross;
            if (name == "O")
                return kPadCircle;
            return -1;
        }

        int axisIdFromName(const std::string &name)
        {
            if (name == "RX")
                return 0;
            if (name == "RY")
                return 1;
            if (name == "LX")
                return 2;
            if (name == "LY")
                return 3;
            return -1;
        }

        std::vector<std::string> split(const std::string &text, char separator)
        {
            std::vector<std::string> parts;
            std::string current;
            for (char c : text)
            {
                if (c == separator)
                {
                    parts.push_back(current);
                    current.clear();
                }
                else if (c != ' ')
                {
                    current.push_back(c);
                }
            }
            parts.push_back(current);
            return parts;
        }

        // "t:NAME[+NAME|AXIS=v...][:hold]" entries separated by ',' or ';'.
        void parseScript(const char *text)
        {
            std::string all(text);
            std::replace(all.begin(), all.end(), ';', ',');
            for (const std::string &entry : split(all, ','))
            {
                if (entry.empty())
                    continue;
                const std::vector<std::string> fields = split(entry, ':');
                if (fields.size() < 2)
                {
                    std::cout << "[socom2-input] script: ignoring '" << entry << "'" << std::endl;
                    continue;
                }
                ScriptEvent event;
                event.at = std::atof(fields[0].c_str());
                if (fields.size() >= 3)
                    event.hold = std::atof(fields[2].c_str());
                event.text = fields[1];
                for (const std::string &name : split(fields[1], '+'))
                {
                    const size_t eq = name.find('=');
                    if (eq != std::string::npos)
                    {
                        const int axis = axisIdFromName(name.substr(0, eq));
                        if (axis >= 0)
                        {
                            event.axisSet[axis] = true;
                            event.axisValue[axis] = static_cast<uint8_t>(std::clamp(std::atoi(name.substr(eq + 1).c_str()), 0, 255));
                        }
                        continue;
                    }
                    std::string upper = name;
                    std::transform(upper.begin(), upper.end(), upper.begin(), [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
                    const int id = buttonIdFromName(upper);
                    if (id >= 0)
                        event.buttons |= static_cast<uint16_t>(1u << id);
                    else
                        std::cout << "[socom2-input] script: unknown button '" << name << "'" << std::endl;
                }
                g_config.script.push_back(event);
            }
            g_config.fired.assign(g_config.script.size(), false);
        }

        void initialise()
        {
            g_config.initialised = true;
            g_config.start = std::chrono::steady_clock::now();
            if (const char *mouse = std::getenv("PS2X_SOCOM2_MOUSE"))
                g_config.mouse = (mouse[0] != '0');
            if (const char *sens = std::getenv("PS2X_SOCOM2_MOUSE_SENS"))
                g_config.mouseSensitivity = static_cast<float>(std::atof(sens));
            if (const char *script = std::getenv("PS2X_SOCOM2_INPUT_SCRIPT"))
                parseScript(script);
            // Task 8: name the pad that is actually read (PS2X_HOST_GAMEPAD_INDEX), not slot 0.
            const int pad = hostGamepadEnabled()
                                ? hostGamepadSelect(std::getenv("PS2X_HOST_GAMEPAD_INDEX"), kHostGamepadSlots, IsGamepadAvailable)
                                : -1;
            std::cout << "[socom2-input] keyboard on (arrows/WASD/IJKL, Enter=START, Backspace=SELECT, ZXCV=Square/Cross/Circle/Triangle, QE=L1/R1, 13=L2/R2, 24=L3/R3)"
                      << "; gamepad " << (!hostGamepadEnabled() ? "off (PS2X_HOST_GAMEPAD=0)" : pad >= 0 ? GetGamepadName(pad) : "none")
                      << "; mouse " << (g_config.mouse ? "on" : "off (PS2X_SOCOM2_MOUSE=1)")
                      << "; script events " << g_config.script.size() << std::endl;
        }

        uint8_t axisFromKeys(int negativeKey, int positiveKey)
        {
            const bool negative = IsKeyDown(negativeKey);
            const bool positive = IsKeyDown(positiveKey);
            if (negative == positive)
                return 0x80u;
            return negative ? 0x00u : 0xFFu;
        }

        uint8_t clampAxis(float value)
        {
            return static_cast<uint8_t>(std::clamp(std::lround(value), 0L, 255L));
        }
    }

    void socom2HostInputStartSampler(const char *path)
    {
        if (path != nullptr && path[0] != 0)
            g_injectedPadSampler.start(path);
    }

    void socom2HostInputShutdown()
    {
        g_injectedPadSampler.shutdown();
    }

    bool socom2HostInputSamplerRunning()
    {
        return g_injectedPadSampler.worker.joinable();
    }

    void socom2HostInputPoll(Socom2PadState &pad)
    {
        if (!IsWindowReady())
        {
            return;
        }
        if (!g_config.initialised)
        {
            initialise();
        }

        Socom2PadState next;

        // Keyboard.
        static const struct { int key; uint8_t button; } kKeys[] = {
            {KEY_ENTER, kPadStart}, {KEY_BACKSPACE, kPadSelect},
            {KEY_UP, kPadUp}, {KEY_RIGHT, kPadRight}, {KEY_DOWN, kPadDown}, {KEY_LEFT, kPadLeft},
            {KEY_Z, kPadSquare}, {KEY_X, kPadCross}, {KEY_SPACE, kPadCross}, {KEY_C, kPadCircle}, {KEY_V, kPadTriangle},
            {KEY_Q, kPadL1}, {KEY_E, kPadR1}, {KEY_ONE, kPadL2}, {KEY_THREE, kPadR2}, {KEY_TWO, kPadL3}, {KEY_FOUR, kPadR3},
        };
        for (const auto &entry : kKeys)
        {
            if (IsKeyDown(entry.key))
                next.button[entry.button] = 1u;
        }
        next.axis[2] = axisFromKeys(KEY_A, KEY_D);   // LX
        next.axis[3] = axisFromKeys(KEY_W, KEY_S);   // LY (up = 0)
        next.axis[0] = axisFromKeys(KEY_J, KEY_L);   // RX
        next.axis[1] = axisFromKeys(KEY_I, KEY_K);   // RY

        // Gamepad 0 (raylib: XInput / DirectInput), OR-ed with the keyboard like the pad file is. The
        // generic pad path (ps2_pad.cpp) read it already, but SOCOM's pad is served by this poll once
        // PS2X_SOCOM2_PAD is set, so an Xbox controller did nothing here until 2026-09-16 (owner's free
        // play: Windows saw the controller, the game did not). A stick overrides the keyboard axis only
        // when deflected past the dead zone, so WASD/IJKL/mouse keep working with a pad plugged in.
        // Task 8: the pad the launcher picked (PS2X_HOST_GAMEPAD_INDEX), or the first available one.
        // Re-selected every poll rather than latched: pads are hot-pluggable, and a player who plugs one in
        // mid-session should not have to restart.
        // `padSlot`, not `pad`: the poll's own out-parameter is named `pad` (Socom2PadState &).
        const int padSlot = hostGamepadEnabled()
                                ? hostGamepadSelect(std::getenv("PS2X_HOST_GAMEPAD_INDEX"), kHostGamepadSlots, IsGamepadAvailable)
                                : -1;
        if (padSlot >= 0)
        {
            static const struct { int button; uint8_t pad; } kPadButtons[] = {
                {GAMEPAD_BUTTON_LEFT_FACE_UP, kPadUp}, {GAMEPAD_BUTTON_LEFT_FACE_RIGHT, kPadRight},
                {GAMEPAD_BUTTON_LEFT_FACE_DOWN, kPadDown}, {GAMEPAD_BUTTON_LEFT_FACE_LEFT, kPadLeft},
                {GAMEPAD_BUTTON_RIGHT_FACE_UP, kPadTriangle}, {GAMEPAD_BUTTON_RIGHT_FACE_RIGHT, kPadCircle},
                {GAMEPAD_BUTTON_RIGHT_FACE_DOWN, kPadCross}, {GAMEPAD_BUTTON_RIGHT_FACE_LEFT, kPadSquare},
                {GAMEPAD_BUTTON_LEFT_TRIGGER_1, kPadL1}, {GAMEPAD_BUTTON_RIGHT_TRIGGER_1, kPadR1},
                {GAMEPAD_BUTTON_LEFT_TRIGGER_2, kPadL2}, {GAMEPAD_BUTTON_RIGHT_TRIGGER_2, kPadR2},
                {GAMEPAD_BUTTON_MIDDLE_LEFT, kPadSelect}, {GAMEPAD_BUTTON_MIDDLE_RIGHT, kPadStart},
                {GAMEPAD_BUTTON_LEFT_THUMB, kPadL3}, {GAMEPAD_BUTTON_RIGHT_THUMB, kPadR3},
            };
            for (const auto &entry : kPadButtons)
            {
                if (IsGamepadButtonDown(padSlot, entry.button))
                    next.button[entry.pad] = 1u;
            }
            // Triggers: raylib maps the trigger axes (rest -1.0) past 0.1 to GAMEPAD_BUTTON_*_TRIGGER_2 itself
            // (rcore_desktop_glfw.c), so the button table above covers L2/R2; no axis read here.
            static const struct { int axis; int slot; } kSticks[] = {
                {GAMEPAD_AXIS_RIGHT_X, 0}, {GAMEPAD_AXIS_RIGHT_Y, 1}, {GAMEPAD_AXIS_LEFT_X, 2}, {GAMEPAD_AXIS_LEFT_Y, 3},
            };
            const float deadZone = hostPadDeadZone();
            for (const auto &stick : kSticks)
            {
                const float v = hostPadAxis(GetGamepadAxisMovement(padSlot, stick.axis), deadZone);
                if (v != 0.0f)
                    next.axis[stick.slot] = clampAxis(128.0f + v * 127.0f);
            }
        }

        // Mouse -> right stick + triggers.
        if (g_config.mouse)
        {
            const Vector2 delta = GetMouseDelta();
            if (delta.x != 0.0f || delta.y != 0.0f)
            {
                next.axis[0] = clampAxis(128.0f + delta.x * g_config.mouseSensitivity);
                next.axis[1] = clampAxis(128.0f + delta.y * g_config.mouseSensitivity);
            }
            if (IsMouseButtonDown(MOUSE_BUTTON_LEFT))
                next.button[kPadR1] = 1u;
            if (IsMouseButtonDown(MOUSE_BUTTON_RIGHT))
                next.button[kPadL1] = 1u;
        }

        // Scripted presses.
        if (!g_config.script.empty())
        {
            const double now = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_config.start).count();
            for (size_t index = 0; index < g_config.script.size(); ++index)
            {
                const ScriptEvent &event = g_config.script[index];
                if (now < event.at || now > event.at + event.hold)
                    continue;
                if (!g_config.fired[index])
                {
                    g_config.fired[index] = true;
                    std::cout << "[socom2-input] t=" << event.at << " press " << event.text << " for " << event.hold << "s" << std::endl;
                }
                for (int id = 0; id < 16; ++id)
                {
                    if (event.buttons & (1u << id))
                        next.button[id] = 1u;
                }
                for (int axis = 0; axis < 4; ++axis)
                {
                    if (event.axisSet[axis])
                        next.axis[axis] = event.axisValue[axis];
                }
            }
        }

        // PS2X_SOCOM2_INPUT_FILE=<path>: a driver-written pad state, sampled by a background
        // thread and latched, so every press written to the file is seen by at least one poll. One
        // line: "b=<hex 16-bit button mask> rx=<0-255> ry=<n> lx=<n> ly=<n>". Buttons are OR-ed
        // with the keyboard, an axis overrides the keyboard when it is not neutral (0x80).
        // Posted keyboard messages reach raylib only when the window thread pumps, so scripted
        // holds were dropped or their release was seen only at the next press (probe6, 2026-09-10);
        // the file path is deterministic and works for two instances on one host. Reading the file
        // here only, once per rendered frame, dropped a whole 0.09 s press under ~11 fps: the press
        // lived entirely between two polls (ten driven launches, 2026-09-18).
        {
            static const char *s_file = std::getenv("PS2X_SOCOM2_INPUT_FILE");
            if (s_file != nullptr)
            {
                socom2HostInputStartSampler(s_file);
                const ps2x::InjectedPadSample sample = g_injectedPadSampler.latch.take();
                for (int id = 0; id < 16; ++id)
                    if (sample.buttons & (1u << id))
                        next.button[id] = 1u;
                const unsigned values[4] = {sample.rx, sample.ry, sample.lx, sample.ly};
                for (int axis = 0; axis < 4; ++axis)
                    if (values[axis] != 0x80u)
                        next.axis[axis] = static_cast<uint8_t>(std::min(values[axis], 255u));
            }
        }

        // PS2X_SOCOM2_INPUT_TRACE=1: log every change of the pad state the game will read
        // (buttons as a 16-bit mask, the four axes), so a scripted probe's presses are provable.
        {
            static const bool s_trace = std::getenv("PS2X_SOCOM2_INPUT_TRACE") != nullptr;
            if (s_trace)
            {
                static Socom2PadState s_last;
                if (std::memcmp(&s_last, &next, sizeof(next)) != 0)
                {
                    unsigned mask = 0;
                    for (int id = 0; id < 16; ++id)
                        if (next.button[id])
                            mask |= 1u << id;
                    std::fprintf(stderr, "[socom2-input] state buttons=%04x rx=%02x ry=%02x lx=%02x ly=%02x\n",
                                 mask, next.axis[0], next.axis[1], next.axis[2], next.axis[3]);
                    s_last = next;
                }
            }
        }
        pad = next;
    }
}
