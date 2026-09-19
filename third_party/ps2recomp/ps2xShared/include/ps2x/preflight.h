#pragma once

// Sprint 9 Goal 1: what the runner checks BEFORE it opens a window. Today main() calls
// runtime.initialize() (InitWindow, InitAudioDevice) and only then looks at the ELF, and a missing
// disc is a WARNING followed by a black screen (game_overrides_socom2.cpp:577). Each failure here is
// one exit code out of ps2x/exit_codes.h, decided before anything is shown.

#include "launcher/launcher_config.h"
#include "ps2x/exit_codes.h"

#include <filesystem>
#include <string>

namespace Preflight
{
    struct Input
    {
        std::filesystem::path elfPath;       // what main() is about to hand loadELF
        std::string cdImageEnv;              // PS2X_CD_IMAGE's value; empty when unset
        std::filesystem::path cardDir;       // where saves will go: PS2X_MC_DIR, else <elf dir>/mc0
        bool checkDisc = true;               // false for an ELF that is not SOCOM II's
        std::string discElfName = launcher::kSocom2ElfName;
        std::string expectedElfSha256 = launcher::kSocom2R0001ElfSha256;
    };

    struct Result
    {
        int code = ExitCodes::kOk;
        std::string detail;                  // the path or the reason, for the log line
        std::filesystem::path disc;          // the image that was checked, when one was
    };

    // The search configureCdImage() performs (game_overrides_socom2.cpp:552): the environment's image,
    // else the first *.iso beside the ELF, else the first one folder up. Empty when there is none.
    std::filesystem::path findDisc(const std::filesystem::path &elfPath, const std::string &cdImageEnv);

    // Creates `dir` when absent, then writes and removes a probe file in it.
    bool directoryWritable(const std::filesystem::path &dir, std::string &why);

    // ELF -> card folder -> disc found -> disc is r0001. The first failure wins.
    Result run(const Input &input);

    // "[preflight] exit 66 disc-not-found: <sentence> (<detail>)"
    std::string logLine(const Result &result);
}
