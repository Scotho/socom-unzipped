#pragma once
// config.json next to the launcher, and the PS2X_* environment it becomes (Task 8b, packaging outline section 3).
#include <string>
#include <vector>

namespace launcher
{
    // The r0001 NTSC disc's SCUS_972.75, as hashed out of the image (and the loose file) on 2026-09-17.
    constexpr const char *kSocom2R0001ElfSha256 = "0172dc0bec19c83d1fe2d0fec0a290f41cc5d32efa14ed6859ca92773c05346c";
    constexpr const char *kSocom2ElfName = "SCUS_972.75";

    struct ServerPreset
    {
        const char *id;
        const char *label;
        const char *address;
        const char *note;
    };

    // The servers a player can pick. Addresses: the community server's is the one the SOCOM community's Horizon
    // ("PS2 Online Network" / socom.community) publishes for SOCOM II -- CONFIRM before release; ours is not hosted yet.
    constexpr ServerPreset kServerPresets[] = {
        {"community", "SOCOM Community (public Horizon)", "COMMUNITY_SERVER_ADDRESS_TBC", "the public community server"},
        {"unzipped",  "SOCOM Unzipped (project server)",  "UNZIPPED_SERVER_ADDRESS_TBC",  "not hosted yet"},
        {"custom",    "Custom",                            "",                             "any address or hostname"},
    };

    struct Config
    {
        std::string isoPath;
        int gsScale = 1;                       // 1 native, 2 sharp, 3 sharper (experimental)
        std::string presentFilter = "linear";  // linear | integer | point
        // Sprint 7 Task 1c: the launcher opens at 2x. The runtime's own default is still 640x448
        // (PS2X_WINDOW_SIZE unset), which is what the parity gate runs at.
        std::string windowSize = "1280x896";   // <w>x<h> | fullscreen
        bool fpsOverlay = false;               // Sprint 7 Task 10: PS2X_FPS_OVERLAY, off unless asked for
        int audioVolume = 100;                 // Sprint 7 Task 11: PS2X_AUDIO_VOLUME, 0-100, 100 = unity
        bool mouseLook = false;
        double mouseSensitivity = 1.0;
        // Sprint 7 Task 8: which host pad to read (-1 = the first available one, as the runtime did before)
        // and the stick dead zone the three pad paths apply.
        int gamepadIndex = -1;
        double padDeadZone = 0.15;
        // Sprint 7 Task 9: the capture device by name; "" = none (no PS2X_MIC_DEVICE, no device opened).
        std::string micDevice;
        std::string serverPreset = "custom";   // an id out of kServerPresets; "custom" means the address below
        std::string server = "127.0.0.1";
        std::string profile = "player";
        bool secondInstance = false;
    };

    // Sprint 7 review finding F5: "Match display" resolved to TextFormat("%dx%d", GetMonitorWidth(...),
    // GetMonitorHeight(...)) in main.cpp, and raylib answers 0 for both before a monitor is known -- so a click
    // at the wrong moment stored "0x0" in config.json and the game opened at nothing at all. This is that
    // resolution as a pure function: "" when either dimension is not a usable size, so the caller keeps what it
    // had, and "<w>x<h>" otherwise.
    std::string monitorSizeOrEmpty(int width, int height);

    // The preset with that id, or nullptr when the id is not one of ours.
    const ServerPreset *findServerPreset(const std::string &id);
    // The address the game is actually pointed at: the preset's for community/unzipped, the typed one for custom
    // (127.0.0.1 when nothing is typed).
    std::string effectiveServer(const Config &config);

    // config.json <-> Config. Unknown keys are ignored; a missing key keeps the default. parse returns false on
    // malformed JSON (the config is then the defaults).
    std::string toJson(const Config &config);
    bool fromJson(const std::string &json, Config &out);

    // Sprint 7 Task 1a: what the game's exit code means, in a sentence for the player. Empty when the code
    // carries no message of its own (0, or a crash the log already explains).
    //   65 -- GsGlCaps::kExitCode: the GL probe failed and the run fell back to the CPU rasterizer.
    std::string exitMessage(int exitCode);

    // The environment socom2.exe is started with, as KEY=VALUE strings (PS2X_SOCOM2_PAD=1 always; MOUSE only when on;
    // the second instance gets PS2X_SOCOM2_UDP_SHIFT=2, PS2X_SOCOM2_RSA_KEY=b and its own card directory).
    std::vector<std::string> environmentFor(const Config &config);

    // Sprint 8 Task 4: the child's environment, as both glues build it. `base` is a NULL-terminated KEY=VALUE
    // array (the Windows block widened, or POSIX `environ`); `ours` is environmentFor()'s knobs. Ours win by
    // key: an overridden base entry is dropped rather than duplicated, the rest of the base keeps its order,
    // and ours follow in theirs. Entries with no '=' are not environment entries and are skipped on both
    // sides (a bare key in `ours`, and Windows' "=C:"-style drive entries in `base`). Pure; both platforms.
    std::vector<std::string> mergeEnvironment(const char *const *base, const std::vector<std::string> &ours);
}
