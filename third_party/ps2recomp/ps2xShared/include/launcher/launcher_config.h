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

    // The servers a player can pick. Ours is hosted (AWS Lightsail, us-east-2, a static address; Sprint 8 Goal 12). The
    // community server is PSRewired (67.222.156.250), which runs SOCOM II r0004 -- a different code package from the r0001
    // this client is built from -- so its preset keeps a placeholder until an r0004 build exists (a wishlist item).
    constexpr ServerPreset kServerPresets[] = {
        {"community", "SOCOM Community (public Horizon)", "COMMUNITY_SERVER_ADDRESS_TBC", "the public community server"},
        {"unzipped",  "SOCOM Unzipped (project server)",  "3.143.65.100",                 "the project's hosted server (US East)"},
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
        // Owner request 2026-09-19, R139: the host control that crouches -- "off" | "l3" | "touchpad" | "l2".
        // The default is "l3" (owner 2026-09-20: with no shortcut a pad cannot crouch at all). "off" sends no variable and is the runtime exactly as it was before the option.
        std::string crouchShortcut = "l3";   // owner 2026-09-20: without a shortcut a pad cannot crouch at all
        // Sprint 7 Task 9: the capture device by name; "" = none (no PS2X_MIC_DEVICE, no device opened).
        std::string micDevice;
        std::string serverPreset = "unzipped"; // an id out of kServerPresets; a fresh config plays on the project's hosted server (Sprint 8 Goal 12); "custom" means the address below
        std::string server = "127.0.0.1";
        std::string profile = "player";
        bool secondInstance = false;
    };

    // R139, the crouch shortcut (owner request 2026-09-19; runtime/host_crouch_shortcut.h has the mechanism).
    // SOCOM II's stance is TRIANGLE's pressure: a light press crouches, a firm one goes prone, and a PC pad's
    // digital Y / Triangle is always firm -- so on a PC pad crouch is unreachable, which is why the community binds
    // "Triangle, lightly" to a spare control. The ruling: the chosen host control sends that light Triangle INSTEAD
    // of its own PS2 button, never as well as it. "l3" therefore trades away fire mode on the pad and "l2" the
    // second weapon swap; both remain on the keyboard (2 and 1), which the runtime always reads, and the launcher
    // says so under the option. "touchpad" trades nothing: that control is unmapped today. The player's own
    // Triangle stays a firm press, so prone is always reachable. -- why: a plain rebind is what the convention is
    // on PCSX2, and one control doing two things at once is the surprise to avoid. -- cost if wrong: a player who
    // wanted fire mode moved somewhere else on the pad; the mapping is one table in host_crouch_shortcut.h.
    constexpr const char *kCrouchShortcuts[] = {"off", "l3", "touchpad", "l2"};
    constexpr int kCrouchShortcutCount = 4;
    // One of kCrouchShortcuts; anything else (a typo, a value from a newer build) is "off".
    std::string normalizeCrouchShortcut(const std::string &value);

    // The profile names a directory -- PS2X_MC_DIR is "cards/" + profile, and the runner resolves a relative
    // value under its own home -- so it must stay a NAME. Letters, digits, space, '_', '-' and '.' are kept and
    // the result is cut to 64; anything else (a separator, a drive letter, "." or ".." alone, empty) is refused
    // whole and becomes "player". Refused whole, not patched up: a config.json can be handed to a player by
    // someone else, and half-cleaning a path is how a cleaner gets walked around.
    std::string normalizeProfile(const std::string &value);
    // The cell's label and the one line under the row that states the trade. Never empty.
    const char *crouchShortcutLabel(const std::string &value);
    const char *crouchShortcutHint(const std::string &value);

    // Sprint 7 review finding F5: "Match display" resolved to TextFormat("%dx%d", GetMonitorWidth(...),
    // GetMonitorHeight(...)) in main.cpp, and raylib answers 0 for both before a monitor is known -- so a click
    // at the wrong moment stored "0x0" in config.json and the game opened at nothing at all. This is that
    // resolution as a pure function: "" when either dimension is not a usable size, so the caller keeps what it
    // had, and "<w>x<h>" otherwise.
    std::string monitorSizeOrEmpty(int width, int height);

    // Sprint 8 Goal 9 (fourth pass): can this preset actually be played? A preset carries a placeholder
    // address until its server exists -- the community one still does, because PSRewired runs game revision
    // r0004 and this client cannot play that yet. Custom is always available: the player types the address.
    bool presetAvailable(const ServerPreset &preset);

    // The preset with that id, or nullptr when the id is not one of ours.
    const ServerPreset *findServerPreset(const std::string &id);
    // The address the game is actually pointed at: the preset's for community/unzipped, the typed one for custom
    // (127.0.0.1 when nothing is typed).
    std::string effectiveServer(const Config &config);

    // config.json <-> Config. Unknown keys are ignored; a missing key keeps the default. parse returns false on
    // malformed JSON (the config is then the defaults).
    std::string toJson(const Config &config);
    bool fromJson(const std::string &json, Config &out);

    // What the game's exit status means, in a sentence for the player: ExitCodes::describe (ps2x/exit_codes.h). Never empty.
    std::string exitMessage(int exitCode);

    // Sprint 9 Goal 1: the PLAY page's LAST RUN line. `rawExitStatus` is GameProcess::exitCode() as the
    // glue reports it (an NT status on Windows, 128 + signal on POSIX, else the runner's own code);
    // `logText` is the head of that run's log, read for "[notice] " lines (no audio device), whose
    // sentences follow the exit's own.
    std::string lastRunLine(long long rawExitStatus, const std::string &logText);

    // What --selftest prints: "exit <code> <slug>: <sentence>" for every row of ExitCodes::kTable.
    std::vector<std::string> selftestExitLines();


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
