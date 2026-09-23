// Sprint 11 Task 19 (round 3): the revision guard.
//
// Two parity gates on 2026-09-23 ran an r0004 executable -- generated from the r0004 image -- on r0001's
// overlay image, because the launch scripts hard-coded game/disc/socom2_game.elf. The runtime booted, ran
// r0001's constructor table into r0004 function bodies, and hung at the loading screen on a JALR through a
// slot the constructors never filled. Nothing in the log said the code and the image disagreed; it took a
// night of reading three separate witnesses to work out that they did
// (.superpowers/sdd/2026-09-23-sprint-11/task-19-addresses-report.md sections 8 and 10).
//
// The guard is one comparison: the revision the EXECUTABLE was recompiled from (a build-time define,
// PS2X_GAME_REVISION, which build.sh and build_revision.sh set) against the revision the IMAGE names for
// itself (socom2_addresses::selectFromImage, which reads every column's build banner). The comparison is a
// pure function over two strings so it can be pinned here without a game, a disc or a boot.
//
// Three cases, and they are the whole of it: same revision -> carry on; different revisions -> REFUSE,
// because nothing downstream of a mismatch is meaningful; the image names no revision at all -> today's
// behaviour, the r0001 fallback with its warning, since an image that identifies itself as nothing
// contradicts nothing.
#include "MiniTest.h"
#include "ps2x/exit_codes.h"
#include "runtime/socom2_addresses.h"
#include "runtime/socom2_revision_guard.h"

#include <cstddef>
#include <cstring>
#include <iostream>
#include <string>

namespace
{
    using socom2_revision::Verdict;

    bool contains(const std::string &haystack, const char *needle)
    {
        return haystack.find(needle) != std::string::npos;
    }

    // current() is process-wide state; the suites after this one must find it as they were.
    struct SelectionGuard
    {
        const socom2_addresses::Table *saved = &socom2_addresses::current();
        ~SelectionGuard() { socom2_addresses::select(*saved); }
    };

    // A stand-in for the loaded image: the text at each column's versionString (socom2_addresses_tests.cpp
    // has the same shape, for the same reason).
    struct FakeImage
    {
        uint32_t addr[4] = {0, 0, 0, 0};
        const char *text[4] = {"", "", "", ""};
        int n = 0;
        void put(uint32_t a, const char *s) { addr[n] = a; text[n] = s; ++n; }
    };

    std::string readFake(uint32_t addr, void *user)
    {
        const FakeImage *img = static_cast<const FakeImage *>(user);
        for (int i = 0; i < img->n; ++i)
            if (img->addr[i] == addr)
                return std::string(img->text[i]);
        return std::string();
    }

    const char *kR0001Version = "SOCOM 2 r0001 17:22:21 Oct 11 2003";
    const char *kR0004Version = "SOCOM 2 r0004 10:14:38 Nov  3 2004";
}

void register_socom2_revision_guard_tests()
{
    MiniTest::Case("Socom2RevisionGuard", [](TestCase &tc)
    {
        tc.Run("a build and an image that name the same revision agree", [](TestCase &t)
        {
            t.IsTrue(socom2_revision::compare("r0001", "r0001") == Verdict::Match, "r0001 code on an r0001 image");
            t.IsTrue(socom2_revision::compare("r0004", "r0004") == Verdict::Match, "r0004 code on an r0004 image");
        });

        tc.Run("a build and an image that name different revisions are a refusal", [](TestCase &t)
        {
            t.IsTrue(socom2_revision::compare("r0004", "r0001") == Verdict::Mismatch,
                     "the two gate runs of 2026-09-23: r0004 code, r0001 image");
            t.IsTrue(socom2_revision::compare("r0001", "r0004") == Verdict::Mismatch, "and the other way round");

            // The line has to name BOTH revisions and the image it read, because the whole cost of the
            // original defect was that the log named neither.
            const std::string line = socom2_revision::refusalLine(
                "r0004", "r0001", "C:\\projects\\socom_pc\\game\\disc\\socom2_game.elf", kR0001Version);
            t.IsTrue(contains(line, "REFUSED"), "it refuses, in a word: " + line);
            t.IsTrue(contains(line, "recompiled from r0004"), "it names what the executable is: " + line);
            t.IsTrue(contains(line, "is r0001"), "and what the image is: " + line);
            t.IsTrue(contains(line, "socom2_game.elf"), "and which image it read: " + line);
            t.IsTrue(contains(line, kR0001Version), "and the banner it read it from: " + line);
            t.IsTrue(contains(line, "SOCOM_GAME_ELF"), "and the knob that fixes it: " + line);
            t.IsTrue(line.find('\n') == std::string::npos, "ONE line, so it cannot be scrolled past: " + line);
        });

        tc.Run("an image that names no revision is allowed, with a warning", [](TestCase &t)
        {
            // This is the pre-Task-19 world and every image this table has no banner for: r0001's column,
            // the existing warning, and a boot. Refusing here would refuse images that are simply unknown.
            t.IsTrue(socom2_revision::compare("r0004", "") == Verdict::ImageNamesNoRevision, "an empty banner");
            t.IsTrue(socom2_revision::compare("r0004", nullptr) == Verdict::ImageNamesNoRevision, "no banner at all");
            t.IsTrue(socom2_revision::compare("r0001", "cdrom0:\\SCUS_972.75;1") == Verdict::ImageNamesNoRevision,
                     "the boot path the runtime used to read instead of the banner");

            const std::string line = socom2_revision::warningLine("r0004");
            t.IsTrue(contains(line, "r0004"), "the warning names what the executable was built from: " + line);
            t.IsTrue(!contains(line, "REFUSED"), "and it is a warning, not a refusal: " + line);
        });

        tc.Run("the build's revision reaches the runtime", [](TestCase &t)
        {
            // The define is the executable's half of the comparison. If the build system stops passing it
            // the header's fallback would quietly answer r0001 for every build, and an r0004 exe would
            // once again agree with an r0001 image -- exactly the failure this guard exists to catch.
            t.IsTrue(socom2_revision::kCompiledRevisionFromBuild,
                     "PS2X_GAME_REVISION came from the build, not from the header's fallback");
            const std::string rev = socom2_revision::base(socom2_revision::kCompiledRevision);
            t.IsTrue(rev.size() == 5 && rev[0] == 'r', "and it looks like a revision: \"" + rev + "\"");
            t.IsTrue(std::string(socom2_addresses::forRevision(rev.c_str()).revision) == rev,
                     "and this build's address table has a column for it: " + rev);
        });

        tc.Run("a suffixed build revision compares as its base", [](TestCase &t)
        {
            // build_revision.sh allows r0001check -- a check build of the r0001 disc, under names that do
            // not collide with r0001's products. It is r0001 code and belongs on an r0001 image.
            t.IsTrue(socom2_revision::base("r0001check") == "r0001", "the suffix is not part of the revision");
            t.IsTrue(socom2_revision::compare("r0001check", "r0001") == Verdict::Match, "so a check build agrees");
            t.IsTrue(socom2_revision::compare("r0001check", "r0004") == Verdict::Mismatch, "and still refuses r0004");
        });

        tc.Run("the refusal leaves with a code of its own", [](TestCase &t)
        {
            // Distinct from the preflight's, so a launcher (and a gate script) can tell a revision mismatch
            // from a missing disc (66), the wrong disc (67) or a missing ELF (68).
            t.Equals(ExitCodes::kRevisionMismatch, 73, "revision-mismatch");
            t.IsTrue(ExitCodes::kRevisionMismatch != ExitCodes::kDiscNotFound
                         && ExitCodes::kRevisionMismatch != ExitCodes::kDiscNotR0001
                         && ExitCodes::kRevisionMismatch != ExitCodes::kElfMissing
                         && ExitCodes::kRevisionMismatch != ExitCodes::kNoUsableGl,
                     "and it is nobody else's code");
            t.IsNotNull(ExitCodes::find(ExitCodes::kRevisionMismatch), "the launcher can say what it means");
        });

        tc.Run("the image's revision is what selectFromImage identified, not the column it fell back to",
               [](TestCase &t)
        {
            // The guard's second argument. On the fallback path current().revision is "r0001" although
            // nothing identified the image as r0001 -- reading the guard's input off current() would turn
            // every unknown image into a refusal for an r0004 build, which is the one case that must boot.
            SelectionGuard guard;

            FakeImage r0004;
            r0004.put(socom2_addresses::kR0004.versionString, kR0004Version);
            (void)socom2_addresses::selectFromImage(readFake, &r0004);
            t.IsTrue(socom2_addresses::imageRevision() == "r0004", "an image that names itself is named");
            t.IsTrue(contains(socom2_addresses::imageBanner(), "SOCOM 2 r0004"),
                     "and the banner it said it with is kept for the refusal: " + socom2_addresses::imageBanner());

            FakeImage r0001;
            r0001.put(socom2_addresses::kR0001.versionString, kR0001Version);
            (void)socom2_addresses::selectFromImage(readFake, &r0001);
            t.IsTrue(socom2_addresses::imageRevision() == "r0001", "and the other one too");

            FakeImage nothing;
            nothing.put(socom2_addresses::kR0001.versionString, "cdrom0:\\SCUS_972.75;1");
            (void)socom2_addresses::selectFromImage(readFake, &nothing);
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "the fallback column is still r0001");
            t.IsTrue(socom2_addresses::imageRevision().empty(),
                     "but NOTHING identified the image, and the guard is told so: \""
                         + socom2_addresses::imageRevision() + "\"");
        });
    });
}
