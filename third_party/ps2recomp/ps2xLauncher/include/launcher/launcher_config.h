#pragma once
// config.json next to the launcher, and the PS2X_* environment it becomes (Task 8b, packaging outline section 3).
#include <string>
#include <vector>

namespace launcher
{
    // The r0001 NTSC disc's SCUS_972.75, as hashed out of the image (and the loose file) on 2026-09-17.
    constexpr const char *kSocom2R0001ElfSha256 = "0172dc0bec19c83d1fe2d0fec0a290f41cc5d32efa14ed6859ca92773c05346c";
    constexpr const char *kSocom2ElfName = "SCUS_972.75";

    struct Config
    {
        std::string isoPath;
        int gsScale = 1;                       // 1 native, 2 sharp, 3 sharper (experimental)
        std::string presentFilter = "linear";  // linear | integer | point
        std::string windowSize = "640x448";    // <w>x<h> | fullscreen
        bool mouseLook = false;
        double mouseSensitivity = 1.0;
        std::string server = "127.0.0.1";
        std::string profile = "player";
        bool secondInstance = false;
    };

    // config.json <-> Config. Unknown keys are ignored; a missing key keeps the default. parse returns false on
    // malformed JSON (the config is then the defaults).
    std::string toJson(const Config &config);
    bool fromJson(const std::string &json, Config &out);

    // The environment socom2.exe is started with, as KEY=VALUE strings (PS2X_SOCOM2_PAD=1 always; MOUSE only when on;
    // the second instance gets PS2X_SOCOM2_UDP_SHIFT=2, PS2X_SOCOM2_RSA_KEY=b and its own card directory).
    std::vector<std::string> environmentFor(const Config &config);
}
