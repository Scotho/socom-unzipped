#pragma once
// Issue #51: the CD stub's state, moved out of Helpers/Support.h's anonymous namespace the way Sprint
// 11 Task 8b moved the four groups beside it (StubLogRuntimeState.h, DmaRuntimeState.h,
// GsRuntimeState.h, LibCRuntimeState.h): one NAMED struct, OWNED BY THE PS2Runtime the stub was called
// with -- a std::unique_ptr member reached as runtime->cdRuntimeState() -- with one process-wide
// fallback for a stub reached with no runtime (ps2_stubs::cdRuntimeStateFor(nullptr)).
//
// The fourteen variables here were g_cdFilesByKey, g_cdLeafIndex, g_cdLoosePathIndex,
// g_cdLeafIndexRoot, g_cdLeafIndexBuilt, g_nextPseudoLbn, g_cdImageSizePath, g_cdImageSizeBytes,
// g_cdImageSizeValid, g_lastCdError, g_cdMode, g_cdStreamingLbn, g_cdStreamingEndLbn and
// g_cdInitialized. In the anonymous namespace every translation unit that includes Support.h (the
// nineteen stub units through Stubs/Common.h, and two test units directly) compiled its own copy, so
// a file one unit registered was invisible to a lookup compiled in another (docs/KNOWN.md section 1,
// "A header that defines its state in an anonymous namespace gives every translation unit its own
// copy"). The 2026-09-21 one-shot move of the whole header (50f8403) lost the gate's mission stage and
// was reverted (955539c); this group moves alone, under its own gate (docs/KNOWN.md section 2, "Which
// group of the stub helpers' per-TU state broke the mission stage").
//
// Readers: Stubs/CD.cpp is the only translation unit that reads or writes the group (Task 8b's reader
// scan), through the Support.h helpers registerCdFile, readCdSectors, readHostRange,
// isResolvableCdLbn, cdStreamingEndLbnForStart, ensureCdLeafIndex, findRegisteredCdFileForLbn and
// tryGetCdImageTotalSectors -- each now takes the CdRuntimeState it works on -- and getCdDebugSnapshot,
// which the debug panel calls with its runtime. For a single-runtime game this is a no-op: CD.cpp's
// copy was the only live one.

#include <cstdint>
#include <filesystem>
#include <string>
#include <unordered_map>

class PS2Runtime;

namespace ps2_stubs
{
    // The first pseudo LBN a host file registered by sceCdSearchFile is given: above any real disc
    // sector, so a registered file and the disc image never answer the same LBN.
    constexpr uint32_t kCdPseudoLbnStart = 0x00100000;

    struct CdFileEntry
    {
        std::filesystem::path hostPath;
        uint32_t sizeBytes = 0;
        uint32_t baseLbn = 0;
        uint32_t sectors = 0;
    };

    struct CdRuntimeState
    {
        // sceCdSearchFile's registrations, by normalised lower-case path, and the pseudo LBN the
        // next one is given.
        std::unordered_map<std::string, CdFileEntry> filesByKey;
        uint32_t nextPseudoLbn = kCdPseudoLbnStart;

        // The leaf-name and loose-numeric indexes of the CD root, built once per root on the first
        // lookup the direct and case-insensitive paths miss.
        std::unordered_map<std::string, std::filesystem::path> leafIndex;
        std::unordered_map<std::string, std::filesystem::path> loosePathIndex;
        std::filesystem::path leafIndexRoot;
        bool leafIndexBuilt = false;

        // The disc image's size, cached per path.
        std::filesystem::path imageSizePath;
        uint64_t imageSizeBytes = 0;
        bool imageSizeValid = false;

        // The drive: sceCdGetError's answer, sceCdMmode's mode, the stream cursor and its end
        // (sceCdSearchFile and the sceCdSt* entry points move them), and whether sceCdInit ran.
        int32_t lastError = 0;
        uint32_t mode = 0;
        uint32_t streamingLbn = 0;
        uint32_t streamingEndLbn = 0xFFFFFFFFu;
        bool initialized = false;

        // Back to a freshly constructed runtime's CD state. PS2Runtime::resetStubRuntimeState()
        // calls it (and run() calls that); no guest path does -- sceCdInit resets the drive, not the
        // registrations.
        void reset()
        {
            *this = CdRuntimeState{};
        }
    };

    // The state `runtime` owns. A null runtime is a stub reached with no runtime at all -- which the
    // ps2x tests do throughout -- and gets one process-wide fallback instance, the only instance here
    // that is not per-runtime.
    CdRuntimeState &cdRuntimeStateFor(PS2Runtime *runtime);
}
