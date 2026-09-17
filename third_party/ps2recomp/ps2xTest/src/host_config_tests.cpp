// Task 8b: the knobs the launcher sets for the game, parsed on the runtime side.
#include "MiniTest.h"
#include "runtime/ps2_window_size.h"

#include <string>

void register_host_config_tests()
{
    MiniTest::Case("HostConfig", [](TestCase &tc)
    {
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
    });
}
