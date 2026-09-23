// Sprint 11 Task 19 (round 3): does this executable's generated code belong on this image?
//
// A SOCOM Unzipped executable is the game's own code, recompiled from ONE pressing's overlay image
// (scripts/build_revision.sh: recomp/socom2_<rev>.toml -> recomp/output_<rev>/ -> dist/socom2_<rev>.exe).
// The overlay image it runs against is a separate file, chosen at launch. Until this header nothing tied
// the two together, and on 2026-09-23 two parity gates ran the r0004 executable on r0001's image because
// the launch scripts hard-coded `game/disc/socom2_game.elf`. It booted. It walked r0001's static
// constructor table into r0004 function bodies -- different code at the same addresses -- so the
// constructors did not construct, and it hung at the loading screen on a `jalr` through a function-pointer
// slot that was never filled. The log said nothing about any of it; three separate witnesses in it, read a
// night later, are what settled the cause (.superpowers/sdd/2026-09-23-sprint-11/task-19-addresses-report.md
// sections 8 and 10).
//
// So: one comparison at boot, and a REFUSAL rather than a warning, because nothing downstream of a
// mismatch is meaningful -- every override address, every constructor table, every function body is the
// other build's.
//
//   the executable's revision   PS2X_GAME_REVISION, a build-time define (below)
//   the image's revision        socom2_addresses::imageRevision(), what the image's own build banner said
//
// The comparison itself is a pure function of those two strings (compare()), so the three cases are pinned
// in ps2xTest without a game, a disc or a boot: socom2_revision_guard_tests.cpp.
#pragma once
#include "ps2x/exit_codes.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>

// WHICH REVISION THIS EXECUTABLE WAS RECOMPILED FROM.
//
// Set by the build: build.sh passes -DPS2X_GAME_REVISION=r0001 (the r0001 chain is the default one) and
// scripts/build_revision.sh passes the revision it is building. ps2xRuntime/CMakeLists.txt puts it on
// ps2_runtime as a PUBLIC definition, so the runner, the library and the test binary all see the same one.
//
// The fallback below exists only so this header compiles in a tree that does not define it; a build that
// falls back is a build whose executable cannot contradict anything, and the suite pins
// kCompiledRevisionFromBuild true so a build system that stops passing the define fails a test rather than
// quietly answering "r0001" for every revision again.
#if defined(PS2X_GAME_REVISION)
#define PS2X_GAME_REVISION_FROM_BUILD 1
#else
#define PS2X_GAME_REVISION "r0001"
#define PS2X_GAME_REVISION_FROM_BUILD 0
#endif

namespace socom2_revision
{
    inline constexpr const char *kCompiledRevision = PS2X_GAME_REVISION;
    inline constexpr bool kCompiledRevisionFromBuild = (PS2X_GAME_REVISION_FROM_BUILD != 0);

    enum class Verdict
    {
        Match,                  // the same pressing: carry on
        Mismatch,               // two different pressings: refuse, nothing after this means anything
        ImageNamesNoRevision,   // the image identified itself as nothing: it contradicts nothing, so boot
    };

    // The revision proper out of a build's revision name: "r0001" from "r0001", and from "r0001check" too.
    // build_revision.sh allows a suffix (`r` + four digits + an optional suffix that starts with a letter)
    // so a check build of a disc cannot overwrite that disc's own products -- but a check build of r0001 is
    // r0001 code and belongs on an r0001 image, so the suffix is not part of the comparison. Empty when the
    // text does not name a revision at all, which is what an unset define or an unrelated string looks like.
    inline std::string base(const char *rev)
    {
        if (!rev || (*rev != 'r' && *rev != 'R'))
            return std::string();
        std::size_t n = 0;
        while (std::isdigit(static_cast<unsigned char>(rev[1 + n])))
            ++n;
        if (n < 3)
            return std::string();
        std::string out(rev, 1 + n);
        out[0] = 'r';
        return out;
    }

    // THE COMPARISON. `compiled` is what the executable was recompiled from, `image` is what the loaded
    // image named itself (socom2_addresses::imageRevision(), empty when no column's banner claimed it).
    //
    // An image that names nothing is NOT a mismatch: it is every image this table has no column for, and
    // the pre-Task-19 world besides. It keeps today's behaviour -- the r0001 column, its warning, and a
    // boot. An executable that names nothing cannot contradict an image either; that case is a build-system
    // fault, and kCompiledRevisionFromBuild is what catches it, in the suite rather than at a player's boot.
    inline Verdict compare(const char *compiled, const char *image)
    {
        const std::string got = base(image);
        if (got.empty())
            return Verdict::ImageNamesNoRevision;
        const std::string want = base(compiled);
        if (want.empty() || want == got)
            return Verdict::Match;
        return Verdict::Mismatch;
    }

    // ONE line. It names both revisions, the image it read and the banner it read them from, because the
    // entire cost of the original defect was a log that named none of them.
    inline std::string refusalLine(const char *compiled, const char *image, const std::string &imagePath,
                                   const std::string &banner)
    {
        return std::string("[socom2] REFUSED: this executable was recompiled from ") + base(compiled)
               + " but the image at " + imagePath + " is " + base(image) + " (banner \"" + banner
               + "\"); pass the matching image (SOCOM_GAME_ELF) or the matching executable";
    }

    // The image named nothing. Said once, so a log shows the guard ran and could not check.
    inline std::string warningLine(const char *compiled)
    {
        return std::string("[socom2] revision guard: this executable was recompiled from ") + base(compiled)
               + ", and the image names no revision -- nothing to compare, carrying on with the r0001 addresses";
    }

    // Boot-time enforcement, called once from applySocom2 after the image has been identified. Returns on
    // a match or an unidentified image; on a mismatch it prints the line and the process leaves with
    // ExitCodes::kRevisionMismatch (73). _Exit, not exit: a bare run's stdout is a fully buffered file
    // (BareRun::redirectOutput), so the flushes below are the line's only way out (main.cpp::leaveWith).
    inline void enforce(const char *imageRevision, const std::string &imagePath, const std::string &banner)
    {
        switch (compare(kCompiledRevision, imageRevision))
        {
        case Verdict::Match:
            std::cout << "[socom2] revision guard: executable " << base(kCompiledRevision) << ", image "
                      << base(imageRevision) << " -- they agree" << std::endl;
            return;
        case Verdict::ImageNamesNoRevision:
            std::cout << warningLine(kCompiledRevision) << std::endl;
            return;
        case Verdict::Mismatch:
            break;
        }
        const std::string line = refusalLine(kCompiledRevision, imageRevision, imagePath, banner);
        std::cout << line << std::endl;
        std::cout.flush();
        std::cerr << line << std::endl;
        std::cerr.flush();
        std::fflush(stdout);
        std::fflush(stderr);
        std::_Exit(ExitCodes::kRevisionMismatch);
    }
}
