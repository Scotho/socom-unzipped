#pragma once

// Sprint 9 Goal 1: the diagnostics zip's contents, as a pure function from what the launcher read off
// the disk to the entries ZipStore writes. Until now "Copy diagnostics" copied the log and config.json
// into a folder, verbatim (main.cpp copyDiagnostics).
//
// What must never be in it: a credential, and the player's home directory. config.json has no
// credential field today (the account lives on the memory card); the sanitiser is an allowlist so that
// stays true whatever a later build adds.

#include "ps2x/zip_store.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace launcher::diagnostics
{
    constexpr size_t kLogHeadBytes = 256u * 1024u;          // the boot: GL, audio, notices, preflight
    constexpr size_t kLogTailBytes = 4u * 1024u * 1024u;    // the ending: what went wrong

    std::string sanitizedConfigJson(const std::string &configText);
    std::string scrub(const std::string &text, const std::string &homeDir);
    std::string glCapsLines(const std::string &logText);
    std::string crashRecord(const std::string &logText);
    std::string joinClipped(const std::string &head, const std::string &tail, uint64_t omittedBytes);
    std::string clipLog(const std::string &logText, size_t headBytes = kLogHeadBytes, size_t tailBytes = kLogTailBytes);

    struct Inputs
    {
        std::string logName;      // "run_<stamp>.log"; empty when there is no log
        std::string logText;      // already clipped by the caller when it was read from a large file
        std::string configText;   // config.json as it is on disk; empty when there is none
        std::string version;      // version.txt's line; empty for a development build
        std::string platform;     // ExeDir::platformName()
        std::string homeDir;      // USERPROFILE / HOME; scrubbed out of every entry
        bool haveLastExit = false;
        long long lastExit = 0;   // GameProcess::exitCode(), raw
    };

    std::string versionsText(const Inputs &inputs);
    std::vector<ZipStore::Entry> entries(const Inputs &inputs);
}
