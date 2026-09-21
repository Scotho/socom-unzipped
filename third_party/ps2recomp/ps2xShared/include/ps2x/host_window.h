#pragma once
// Sprint 10 Q4 (owner 2026-09-20: "stylize the actual game client window if possible like the client. Use the same
// UI"): what the game's window can carry of the launcher's look, decided once for both executables.
//
// THE MEASUREMENT (the Q4 plan has the long form). The runtime owns its raylib window's TITLE and ICON on every
// platform, and on Windows 11 the colours of the caption the system draws (DwmSetWindowAttribute: caption, caption
// text, border -- build 22000 and later; Windows 10 ignores the calls). It owns nothing else outside the client
// area: the client area IS the game's frame, the one the parity gate captures at 640x448 and compares pixel for
// pixel, so a header bar drawn by the runtime -- the owner's "button on the game client's header that focuses
// options" -- would move every capture and is not done in this pass (R214). On Linux the window
// manager draws the decorations from the title and the _NET_WM_ICON raylib sets; nothing more is reachable.
//
// PURE: no raylib, no windows.h. The runtime applies these through raylib and dwmapi (host_window_chrome.cpp);
// the launcher applies the icon to its own window and holds the palette below to its theme in a test.
#include <cstdint>
#include <string>

namespace ps2x::host_window
{
    constexpr const char *kProduct = "SOCOM Unzipped";
    // Every game-window title ENDS with this, tag or no tag, known game or not. It is the harness's key:
    // tools_py/parity/keys.py's WINDOW_TITLES["ours"] is this string, pinned by test_host_window_title.py, and
    // it must never appear in the launcher's own title ("SOCOM Unzipped", no dashes) or PCSX2's, or the
    // harness would drive the wrong window.
    constexpr const char *kTitleSuffix = " -- SOCOM Unzipped";
    // The project's ELF, whose name the runner sees; the game database (games_database.cpp) does not know it.
    constexpr const char *kSocom2Elf = "socom2_game.elf";
    constexpr const char *kSocom2Name = "SOCOM II U.S. Navy SEALs";

    // "<game> -- SOCOM Unzipped", with "<tag> | " in front when PS2X_WINDOW_TITLE is set (the second instance
    // of the online harness: "SOCOM-B | SOCOM II U.S. Navy SEALs -- SOCOM Unzipped", found by "SOCOM-B" as it
    // always was). `gameName` is the database's name or null; the project's ELF gets its own name; anything
    // else is the ELF's file name.
    std::string title(const char *tag, const char *gameName, const std::string &elfName);

    // The launcher's palette on the chrome the runtime owns (ui/theme.h: the top bar's ground, its text, its
    // rule). Held equal to the theme by launcher_tests.cpp, since the runtime cannot include the launcher's
    // header. As COLORREF (0x00BBGGRR), which is what DwmSetWindowAttribute takes.
    struct Rgb
    {
        uint8_t r, g, b;
    };
    constexpr Rgb kCaption = {0x08, 0x16, 0x1A};       // theme::mix(theme::panel, theme::ground, 0.5f)
    constexpr Rgb kCaptionText = {0xDD, 0xE8, 0xEA};   // theme::text
    constexpr Rgb kBorder = {0x1B, 0x5A, 0x64};        // theme::line
    constexpr uint32_t colorref(Rgb c)
    {
        return static_cast<uint32_t>(c.r) | (static_cast<uint32_t>(c.g) << 8) | (static_cast<uint32_t>(c.b) << 16);
    }
}
