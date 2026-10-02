#pragma once
// Sprint 18 T2 (R339 = R-A): config.pcsx2.json beside the launcher -- the PCSX2 client's settings, a struct of its
// own. No key is shared with config.json and no value is copied between them: a setting that leaks across the two
// clients is a setting a player cannot find. The revision and the preset are normalised by the same rules the
// native config uses (launcher_config.h), one rule with two callers.
#include <string>

namespace launcher
{
    constexpr const char *kPcsx2ConfigFile = "config.pcsx2.json";
    constexpr const char *kPcsx2RevisionNote = "needs the card package -- later";   // R-E, the greyed r0004 cell
    struct Pcsx2Config {
        std::string isoPath;
        std::string pcsx2Exe;                 // full path of pcsx2-qt.exe; "" = none selected or installed
        std::string gameRevision = "r0001";   // normalizeGameRevision; r0004 is drawn greyed this sprint (R-E)
        std::string serverPreset = "unzipped";
        std::string server = "127.0.0.1";     // Custom's typed address or name
        std::string ethDevice;                // PCSX2's EthDevice GUID; "" = the launcher picks (T4 pickAdapter)
        bool operator==(const Pcsx2Config &) const = default;
    };
    std::string pcsx2ToJson(const Pcsx2Config &c);
    bool pcsx2FromJson(const std::string &json, Pcsx2Config &out);     // false on malformed JSON; out = defaults then
    std::string pcsx2EffectiveServer(const Pcsx2Config &c);            // the preset's address, or the typed one
}
