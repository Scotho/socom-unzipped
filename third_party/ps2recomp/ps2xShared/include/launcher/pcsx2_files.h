#pragma once
// Sprint 18 T3: what the launcher writes for the PCSX2 client -- the guarded pnach (embedded at configure time from
// scripts/parity/pcsx2/0F6FC6CF.pnach), the [DEV9/Eth] keys merged into the player's PCSX2.ini (Review Focus 2: only
// our keys of our section are touched, every other byte is kept), where that PCSX2 keeps its files, and the DNS
// address PCSX2's DNS1/DNS2 get (Review Focus 3: a name that does not resolve refuses LAUNCH, naming the name).
#include "launcher/pcsx2_config.h"

#include <filesystem>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace launcher::pcsx2files {
    extern const char *const kPnachMaster;     // generated: the bytes of scripts/parity/pcsx2/0F6FC6CF.pnach
    constexpr const char *kPnachName = "0F6FC6CF.pnach";
    constexpr const char *kIniName = "PCSX2.ini";
    constexpr const char *kPortableMarker = "portable.txt";
    // Where this PCSX2 keeps inis/, patches/, bios/, memcards/: beside the exe when portable (portable.txt or
    // portable.ini beside it), else <documents>/PCSX2 (PCSX2's own rule).
    std::filesystem::path dataRoot(const std::filesystem::path &exeDir, bool portableMarkerBesideExe,
                                   const std::filesystem::path &documentsDir);
    // Sprint 18 T6 review: the Documents folder dataRoot's non-portable case reads. `knownFolder` is the system's answer
    // (Windows: SHGetKnownFolderPath(FOLDERID_Documents), which follows OneDrive's Known Folder Move; POSIX:
    // $XDG_DOCUMENTS_DIR) and wins when it is absolute; else <profileOrHome>/Documents; else empty.
    std::filesystem::path documentsDirRule(const std::filesystem::path &knownFolder, const std::filesystem::path &profileOrHome);
    // The [DEV9/Eth] keys the launcher owns, in order. ethDevice "" leaves EthDevice out (T4 fills it when known).
    std::vector<std::pair<std::string, std::string>> dev9Keys(const std::string &dnsIp, const std::string &ethDevice);
    // The [UI] keys the launcher owns (T10, R347), in order: SettingsVersion = 1, SetupWizardIncomplete = false. PCSX2
    // 2.8.2 runs its first-run wizard even under -batch and the wizard rewrites the whole ini, [DEV9/Eth] included.
    std::vector<std::pair<std::string, std::string>> uiKeys();
    // `text` with `keys` set inside `[section]`: an existing key's line replaced in place, a missing key appended at
    // the section's end, the section appended at the end of the file when absent; every other byte kept. CRLF kept.
    std::string mergeIniSection(const std::string &text, const std::string &section,
                                const std::vector<std::pair<std::string, std::string>> &keys);
    bool isDottedIpv4(const std::string &s);
    struct DnsPick { std::string ip; std::string error; };     // error non-empty = LAUNCH is refused with it
    // The address PCSX2's DNS1/DNS2 get: the effective server when it is dotted, else resolver(name) (which returns
    // "" when it cannot). The error names the name: "cannot resolve socom.scotho.com -- check your connection".
    DnsPick dnsServerFor(const Pcsx2Config &c, const std::function<std::string(const std::string &)> &resolver);
    // Write `bytes` to `path` only when the file's bytes differ; when a different file was there, keep it once as
    // "<path>.bak-<stamp>" (never overwritten). Returns true when written. Creates the parent folders.
    bool writeIfDifferent(const std::filesystem::path &path, const std::string &bytes, const std::string &stamp, std::string &error);
}
