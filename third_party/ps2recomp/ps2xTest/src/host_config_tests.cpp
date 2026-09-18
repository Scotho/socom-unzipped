// Task 8b: the knobs the launcher sets for the game, parsed on the runtime side.
#include "MiniTest.h"
#include "runtime/fps_overlay.h"
#include "runtime/ps2_window_size.h"
#include "launcher/launcher_config.h"

#include <algorithm>
#include <limits>
#include <string>
#include <vector>

void register_host_config_tests()
{
    MiniTest::Case("HostConfig", [](TestCase &tc)
    {
        // Sprint 7 review finding F5: "Match display" is a button whose stored value is the monitor's own size,
        // read from raylib. Before a monitor is known raylib answers 0, and "0x0" went straight into
        // config.json -- where nothing rejected it and the game was told to open a window of no size.
        tc.Run("Match display: a monitor with no size stores nothing, and a stored 0x0 is not a window size", [](TestCase &t)
        {
            t.Equals(launcher::monitorSizeOrEmpty(2560, 1440), std::string("2560x1440"), "a real monitor resolves to <w>x<h>");
            t.Equals(launcher::monitorSizeOrEmpty(0, 768), std::string(""), "no width: nothing to store, so the caller keeps what it had");
            t.Equals(launcher::monitorSizeOrEmpty(1366, 0), std::string(""), "no height either");
            t.Equals(launcher::monitorSizeOrEmpty(-1, -1), std::string(""), "and a negative answer is not a size");

            launcher::Config c;
            t.IsTrue(launcher::fromJson("{\"windowSize\": \"0x0\"}", c), "config.json with a 0x0 windowSize parses");
            t.Equals(c.windowSize, launcher::Config{}.windowSize, "a 0x0 window size loads as the default, not as 0x0");

            launcher::Config zeroHeight;
            t.IsTrue(launcher::fromJson("{\"windowSize\": \"1280x0\"}", zeroHeight), "so does one with a zero dimension");
            t.Equals(zeroHeight.windowSize, launcher::Config{}.windowSize, "any zero dimension falls back to the default");

            launcher::Config kept;
            t.IsTrue(launcher::fromJson("{\"windowSize\": \"fullscreen\"}", kept), "fullscreen still parses");
            t.Equals(kept.windowSize, std::string("fullscreen"), "and is left alone");

            launcher::Config bad;
            bad.windowSize = "0x0";
            const std::vector<std::string> env = launcher::environmentFor(bad);
            t.IsTrue(std::find(env.begin(), env.end(), std::string("PS2X_WINDOW_SIZE=1280x896")) != env.end(),
                     "and a 0x0 that reached a Config anyway never becomes PS2X_WINDOW_SIZE=0x0");
        });

        tc.Run("PS2X_WINDOW_SIZE: <w>x<h> sets the window, fullscreen is borderless, anything else keeps the default", [](TestCase &t)
        {
            ps2_window::Size s = ps2_window::parseWindowSize("1280x896", 640, 448);
            t.IsTrue(s.set && s.width == 1280 && s.height == 896 && !s.borderless, "1280x896");
            s = ps2_window::parseWindowSize("640X448", 640, 448);
            t.IsTrue(s.set && s.width == 640 && s.height == 448, "a capital X is accepted");
            s = ps2_window::parseWindowSize("fullscreen", 640, 448);
            t.IsTrue(s.set && s.borderless && s.width == 640 && s.height == 448, "fullscreen: borderless, the default size as the placeholder");
            s = ps2_window::parseWindowSize("FULLSCREEN", 640, 448);
            t.IsTrue(s.set && s.borderless, "case does not matter");
            for (const char *bad : {"", "abc", "1280", "1280x", "x896", "0x0", "-1x10", "99999x99999", "1280x896x2"})
            {
                s = ps2_window::parseWindowSize(bad, 640, 448);
                t.IsTrue(!s.set && s.width == 640 && s.height == 448 && !s.borderless, std::string("malformed keeps the default: '") + bad + "'");
            }
            s = ps2_window::parseWindowSize(nullptr, 640, 448);
            t.IsTrue(!s.set && s.width == 640 && s.height == 448, "unset keeps the default");
            s = ps2_window::parseWindowSize("320x224", 640, 448);
            t.IsTrue(s.set && s.width == 320 && s.height == 224, "a smaller window is allowed");
        });

        tc.Run("PS2X_FPS_OVERLAY: one line, three fields, and never a printed infinity", [](TestCase &t)
        {
            t.Equals(fpsOverlayLine(60, 59.94, 16.67), std::string("60 fps  guest 59.9 Hz  16.7 ms"), "the exact line the overlay draws");
            t.Equals(fpsOverlayLine(7, 3.0, 142.9), std::string("7 fps  guest 3.0 Hz  142.9 ms"), "a stalled frame reads honestly");
            t.Equals(fpsOverlayLine(60, 0.0, 16.6), std::string("60 fps  guest 0.0 Hz  16.6 ms"), "a guest that stopped ticking is 0.0, not blank");
            t.Equals(fpsOverlayLine(-1, 59.94, 16.7), std::string("-- fps  guest 59.9 Hz  16.7 ms"), "no host reading yet");
            t.Equals(fpsOverlayLine(60, -1.0, 16.7), std::string("60 fps  guest -- Hz  16.7 ms"), "no guest reading yet");
            t.Equals(fpsOverlayLine(60, std::numeric_limits<double>::infinity(), 16.7), std::string("60 fps  guest -- Hz  16.7 ms"), "a divide by a zero interval prints --, never inf");
            t.Equals(fpsOverlayLine(60, 59.94, -1.0), std::string("60 fps  guest 59.9 Hz  -- ms"), "no frame time yet");
            t.IsTrue(fpsOverlayLine(60, 59.94, 16.67).size() <= 34u, "short enough to stay inside the 200 px the bar allows");
        });
    });
}
