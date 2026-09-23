// Sprint 11 Task 10 (milestone R): the per-revision guest address table.
//
// Every address the SOCOM II overrides reach into the game with -- the routines they wrap, the statics
// they read, the two static-constructor tables they run -- was written as a literal at its call site, and
// every one of them is an r0001 address. A second pressing of the game (r0004) is the same code relinked:
// the routine is byte for byte the same instruction stream at a different address. One table per revision
// turns supporting a second build into filling a second column, and turns "which of these literals is an
// address that moves" into a question the compiler can answer.
//
// The column for a new revision is not read by hand: tools_py/address_matcher.py fingerprints both images
// (tools_py/fingerprint.py: FNV-1a 64 over the instruction stream with every relocated immediate zeroed)
// and reports where each r0001 routine went, with how it knows.
//
// WHAT IS NOT HERE -- the loader. Everything below kOverlayBase (0x001d5600) is the boot ELF: the disc and
// memory-card game-code loaders, the overlay file reader, sceSifSendCmd, the msifrpc entry points,
// __initialize_cpp_rts. The loader is the same binary in every pressing -- it is what loads the overlays
// that differ -- so those addresses stay literal at their call sites in game_overrides_socom2.cpp. A
// loader address appearing in this table would be a mistake, and socom2_addresses_tests.cpp fails on one.
//
// current() is what call sites use. It answers r0001 until the runtime has read the loaded image's version
// string (game_overrides_socom2.cpp reads it out of the overlay at kR0001.versionString during
// applySocom2) and handed it to selectFromVersionString(). An image whose stamp names no revision, or one
// this table has no column for, keeps r0001 AND logs: a silently wrong address does not present as a bad
// address, it presents as a crash somewhere else entirely, hours later.
#pragma once
#include "runtime/socom2_osk_prefill.h"

#include <cctype>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>

namespace socom2_addresses
{
    // The lowest address the overlays occupy. Below this is the loader (see the note above).
    constexpr uint32_t kOverlayBase = 0x001D5600u;

    struct Table
    {
        const char *revision;

        uint32_t rtNetConfigInit;       // the RtNet config init the runtime replaces wholesale
        uint32_t packTrace;             // the level loader's "is this inner file there" probe (PS2X_PACK_TRACE)
        uint32_t cull;                  // the visibility cull the cull trace wraps
        uint32_t node;                  // scene node walk 1
        uint32_t node2;                 // scene node walk 2
        uint32_t lod;                   // the LOD selection
        uint32_t detail;                // the detail selection
        uint32_t camCfg;                // the camera config record apply
        uint32_t defer;                 // the deferred draw enqueue
        uint32_t flush;                 // the deferred draw flush
        uint32_t musicManager;          // the per-frame music manager (PS2X_SOCOM2_MUSIC_TRACE)
        uint32_t cuePush;               // the music cue push
        uint32_t cameraHolder;          // DATA: the camera holder pointer the cull trace reads
        uint32_t versionString;         // DATA: "SOCOM 2 r0001 17:22:21 Oct 11 2003" -- what picks the column
        uint32_t oskOpen;               // the on-screen keyboard's GetTextInput handler
        uint32_t oskOpenThunk;          // the one-instruction thunk the UI action table dispatches through
        uint32_t oskTextBuffer;         // DATA: the keyboard's initial-text buffer the prefill writes
        uint32_t chatFanoutRecv;        // the chat receive fan-out (milestone S)
        uint32_t dnasCheck;             // the DNAS tick the runtime answers done
        uint32_t ctorTableFtsBegin;     // DATA: FTSCore's static constructor table
        uint32_t ctorTableFtsEnd;
        uint32_t ctorTableZsealBegin;   // DATA: ZSealEtc's static constructor table
        uint32_t ctorTableZsealEnd;
    };

    // SCUS_972.75, "SOCOM 2 r0001 17:22:21 Oct 11 2003" -- the build this port was made against.
    inline constexpr Table kR0001 = {
        "r0001",
        0x00620648u,   // rtNetConfigInit
        0x0025a5d0u,   // packTrace
        0x00290c30u,   // cull
        0x00338480u,   // node
        0x003389c0u,   // node2
        0x003b7b90u,   // lod
        0x003b6e10u,   // detail
        0x002918b0u,   // camCfg
        0x003371b0u,   // defer
        0x00336cb0u,   // flush
        0x0034afd0u,   // musicManager
        0x0034b6c0u,   // cuePush
        0x00415ff0u,   // cameraHolder
        0x003e5c60u,   // versionString
        socom2_osk::kOskOpenAddr,         // oskOpen -- one definition, in the header that documents the handler
        socom2_osk::kOskOpenThunkAddr,    // oskOpenThunk -- ditto; the table dispatches here, not at the handler
        socom2_osk::kOskTextBufferAddr,   // oskTextBuffer -- ditto
        0x002f4ef0u,   // chatFanoutRecv
        0x002cc670u,   // dnasCheck
        0x00404d10u,   // ctorTableFtsBegin
        0x00404f04u,   // ctorTableFtsEnd
        0x006690e0u,   // ctorTableZsealBegin
        0x00669120u,   // ctorTableZsealEnd
    };

    // Every column this build knows. A second revision is one more entry here and one more Table above.
    inline const Table *const kTables[] = {&kR0001};

    // The revision token in a version string: an `r` that starts a word and is followed by digits
    // ("SOCOM 2 r0001 17:22:21 Oct 11 2003" -> "r0001"). Empty when the text names none, which is what
    // an unrelated string, a blank one, or unmapped memory read as text all look like.
    inline std::string revisionOf(const char *text)
    {
        if (!text)
            return std::string();
        for (const char *p = text; *p; ++p)
        {
            if (*p != 'r' && *p != 'R')
                continue;
            if (p != text && (std::isalnum(static_cast<unsigned char>(p[-1])) || p[-1] == '_'))
                continue;                                   // mid-word: the 'r' of "garbage"
            std::size_t n = 0;
            while (std::isdigit(static_cast<unsigned char>(p[1 + n])))
                ++n;
            if (n >= 3 && !std::isalnum(static_cast<unsigned char>(p[1 + n])))
                return std::string(p, 1 + n);
        }
        return std::string();
    }

    inline const Table &forRevision(const char *rev)
    {
        if (rev && *rev)
        {
            for (const Table *t : kTables)
                if (std::strcmp(rev, t->revision) == 0)
                    return *t;
        }
        std::cout << "[socom2] address table: no column for revision \"" << (rev ? rev : "(none)")
                  << "\" -- using " << kR0001.revision << std::endl;
        return kR0001;
    }

    namespace detail
    {
        inline const Table *&slot()
        {
            static const Table *t = &kR0001;   // until the image says otherwise
            return t;
        }
    }

    // The table every call site reads. Process-wide: one image is loaded per run.
    inline const Table &current() { return *detail::slot(); }

    // Choose the column directly (the tests, and any caller that already knows the revision).
    inline void select(const Table &t) { detail::slot() = &t; }

    // Choose the column from the loaded image's version string, read at current().versionString.
    inline void selectFromVersionString(const char *versionText)
    {
        const std::string rev = revisionOf(versionText);
        if (rev.empty())
        {
            std::cout << "[socom2] address table: the version string names no revision (\""
                      << (versionText ? versionText : "") << "\") -- using " << kR0001.revision
                      << ", every override address is an " << kR0001.revision << " address" << std::endl;
            select(kR0001);
            return;
        }
        const Table &t = forRevision(rev.c_str());
        select(t);
        std::cout << "[socom2] address table: image is " << rev << ", using the " << t.revision
                  << " addresses" << std::endl;
    }
}
