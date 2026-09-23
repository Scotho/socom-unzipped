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
// and reports where each r0001 routine went, with how it knows. tools_py/addresses_from_match.py then
// prints the column below out of that report -- one value per member, in this order, with the method on
// each line. THIS COMMAND REPRODUCES THE kR0004 COLUMN EXACTLY, value for value (Task 19, 2026-09-23):
//
//   python -m tools_py.addresses_from_match game/r0004/match.json --revision r0004 \
//       --override packTrace=0x0025ac10:hand,relinked-body \
//       --override defer=0x00354750:hand,bracketed-neighbours \
//       --override cameraHolder=0x004429b0:hand,data-via-twin \
//       --override versionString=0x0040cc60:hand,build-banner \
//       --override oskOpenThunk=0x00281be0:hand,thunk-target \
//       --override oskTextBuffer=0x004a2440:hand,data-via-twin \
//       --override chatListHolders=0x00452928:hand,data-via-twin \
//       --override ctorTableFtsBegin=0x004315a0:hand,ctor-run \
//       --override ctorTableFtsEnd=0x00431798:hand,ctor-run \
//       --override ctorTableZsealBegin=0x00668a60:hand,ctor-run \
//       --override ctorTableZsealEnd=0x00668aa0:hand,ctor-run
//
// Thirty of the forty-one fields need no --override at all: the matcher places them itself, and since
// its fourth pass landed (relinked-body, e92691a) that includes the ten this column originally had to
// establish by hand -- node, node2, detail, camCfg, flush, musicManager, oskOpen, chatFanoutRecv,
// chatListRender and dnasCheck, every one reproduced on the same address with tie-breaker `unique`, by
// an independently written masking rule. The eleven overrides above are the eight DATA fields (the
// matcher places functions), oskOpenThunk (seed+delta, which this table does not accept as evidence on
// its own), and the two the matcher deliberately leaves unresolved: packTrace, whose body moved a
// vtable slot index, and defer, which lost two instructions. Each is written up, field by field, in
// .superpowers/sdd/2026-09-23-sprint-11/task-19-addresses-report.md.
//
// A field a revision's column could not establish is kUnavailable (0), never the other revision's
// address: the install guards skip that one override and say which field they skipped.
//
// WHAT IS NOT HERE -- the loader. Everything below kOverlayBase (0x001d5600) is the boot ELF: the disc and
// memory-card game-code loaders, the overlay file reader, sceSifSendCmd, the msifrpc entry points,
// __initialize_cpp_rts. The loader is the same binary in every pressing -- it is what loads the overlays
// that differ -- so those addresses stay literal at their call sites in game_overrides_socom2.cpp. A
// loader address appearing in this table would be a mistake, and socom2_addresses_tests.cpp fails on one.
//
// current() is what call sites use. It answers r0001 until the runtime has read the loaded image's build
// banner and handed it over. The banner MOVES WITH THE RELINK, so there is no one address to read it at:
// selectFromImage() probes every column's own versionString, NEWEST ROW FIRST, and takes the column
// whose text names that column (game_overrides_socom2.cpp does this once, at the top of applySocom2,
// before any install). Newest first because an image can answer at more than one row's address and
// r0001's row is the fallback every unknown image lands on -- see selectFromImage() for the whole of it. An
// image whose stamps name no revision, or one this table has no column for, keeps r0001 AND logs: a
// silently wrong address does not present as a bad address, it presents as a crash somewhere else
// entirely, hours later. That is not hypothetical -- until Task 19 the runtime read one fixed address
// that held a boot path rather than a banner, and the r0004 exe ran a whole session on r0001's addresses.
#pragma once
#include "runtime/socom2_chat.h"
#include "runtime/socom2_osk_prefill.h"

#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>

namespace socom2_addresses
{
    // The lowest address the overlays occupy. Below this is the loader (see the note above).
    constexpr uint32_t kOverlayBase = 0x001D5600u;

    // "this revision's address for this field was never established". The one value below kOverlayBase a
    // column may carry, and the only honest alternative to a number somebody proved.
    constexpr uint32_t kUnavailable = 0u;

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
        uint32_t versionString;         // DATA: the build banner ("SOCOM 2 r0001 17:22:21 Oct 11 2003") -- what picks the column
        uint32_t oskOpen;               // the on-screen keyboard's GetTextInput handler
        uint32_t oskOpenThunk;          // the one-instruction thunk the UI action table dispatches through
        uint32_t oskTextBuffer;         // DATA: the keyboard's initial-text buffer the prefill writes
        uint32_t chatFanoutRecv;        // the chat receive fan-out (milestone S)
        uint32_t chatListRender;        // the second reader of the same records (milestone S, Task 2b)
        uint32_t chatListHolders;       // DATA: the holder list that reader's records are reached through
        uint32_t dnasCheck;             // the DNAS tick the runtime answers done
        uint32_t ctorTableFtsBegin;     // DATA: FTSCore's static constructor table
        uint32_t ctorTableFtsEnd;
        uint32_t ctorTableZsealBegin;   // DATA: ZSealEtc's static constructor table
        uint32_t ctorTableZsealEnd;

        // The libnetb_ex ring-buffer transport (socom2_libnetb.cpp answers all of these on host sockets).
        // Task 10 left them literal because its Table did not name them; on an r0004 image that meant ten
        // r0001 addresses, which is the defect this table exists to stop. They are columns now.
        uint32_t netbExOpen;
        uint32_t netbExTcpRecv;
        uint32_t netbExTcpSend;
        uint32_t netbExUdpRecv;
        uint32_t netbExUdpSend;
        uint32_t netbExAvailable;
        uint32_t netbExConnected;
        uint32_t netbExStartAsync;      // two entry points share one host implementation
        uint32_t netbExStartAsync2;
        uint32_t netbExDescriptorDma;   // the descriptor DMA helper, bound to "ret0" rather than replaced

        // libdnas2's crypto entry points (socom2_crypto.cpp does these on the host).
        uint32_t dnasRsaBlock;
        uint32_t dnasSha1Hash;
        uint32_t dnasRc4SetKeyHash;
        uint32_t dnasRc4SetKey;
        uint32_t dnasRc4Encrypt;
        uint32_t dnasRc4Decrypt;
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
        // The BANNER, not 0x003e5c60. That address holds the boot path "cdrom0:\SCUS_972.75;1", which names
        // no revision -- so until Task 19 every image, r0004 included, fell back to the r0001 column and the
        // r0004 exe ran the whole session on r0001's override addresses (s11_r0004_gate/title.game.log).
        0x003e17e0u,   // versionString
        socom2_osk::kOskOpenAddr,         // oskOpen -- one definition, in the header that documents the handler
        socom2_osk::kOskOpenThunkAddr,    // oskOpenThunk -- ditto; the table dispatches here, not at the handler
        socom2_osk::kOskTextBufferAddr,   // oskTextBuffer -- ditto
        socom2_chat::kFanoutRecvAddr,     // chatFanoutRecv -- one definition, in the header that documents it
        0x002f5020u,   // chatListRender
        0x0044f568u,   // chatListHolders
        0x002cc670u,   // dnasCheck
        0x00404d10u,   // ctorTableFtsBegin
        0x00404f04u,   // ctorTableFtsEnd
        0x006690e0u,   // ctorTableZsealBegin
        0x00669120u,   // ctorTableZsealEnd
        0x002472c8u,   // netbExOpen
        0x002474f8u,   // netbExTcpRecv
        0x00247738u,   // netbExTcpSend
        0x00247d30u,   // netbExUdpRecv
        0x00247fe8u,   // netbExUdpSend
        0x002479b8u,   // netbExAvailable
        0x00247bd8u,   // netbExConnected
        0x00248350u,   // netbExStartAsync
        0x002483f8u,   // netbExStartAsync2
        0x00247c98u,   // netbExDescriptorDma
        0x0062b948u,   // dnasRsaBlock
        0x0062eec0u,   // dnasSha1Hash
        0x0062a638u,   // dnasRc4SetKeyHash
        0x0062a5a8u,   // dnasRc4SetKey
        0x0062a720u,   // dnasRc4Encrypt
        0x0062a7c8u,   // dnasRc4Decrypt
    };

    // SCUS_972.75 relinked, "SOCOM 2 r0004 10:14:38 Nov  3 2004" -- the pressing PSRewired's community
    // server expects. Not a patch of r0001: FTSCore's code section grew by 176 544 bytes and ZSealEtc's
    // shrank by 6 784, so every routine below sits at a new address and a few have changed bodies.
    //
    // The `method` on each line is what established that address, against
    // game/overlays_r0004/socom2_game_r0004.elf. In descending order of strength:
    //   exact           tools_py/address_matcher.py: one occurrence of the fingerprint in each image.
    //   relinked-body   the same instruction stream at a new address: same length, unique in BOTH images
    //                   under a fingerprint that also zeroes load/store displacements (the EE compiler
    //                   reaches a global as `lui $at,hi` + `lw rt,lo($at)`, so for a global the
    //                   displacement IS a relocation -- which is the one thing address_matcher.py's
    //                   fingerprint deliberately keeps, and why it left these unresolved), and every
    //                   differing word the same opcode and registers with only its immediate moved.
    //   +string         and the body reaches a string that occurs once in each image, whose r0004
    //                   address only this r0004 function references.
    //   capsule-table   and the r0004 capsule's own second patch table names the same address.
    //   thunk-target    the only `j <handler>` thunk in each image, once the handler was established.
    //   data-via-twin   a data address, read out of a twinned function at the same instruction offset;
    //                   every twin that reaches it agrees (cameraHolder: 66 of them, unanimous).
    //   build-banner    the string itself, found in the image.
    //   ctor-run        the maximal run of words that are all function starts around the table -- a rule
    //                   that reproduces r0001's two tables' declared bounds exactly, both ends.
    //   bracketed       neither fingerprint places it (its body really changed): it is the one row in the
    //                   r0004 image between two neighbours that ARE placed, and 124 of its 126
    //                   instructions match r0001's in shape. The weakest line in this column.
    inline constexpr Table kR0004 = {
        "r0004",
        0x00627f38u,   // rtNetConfigInit      r0001 0x00620648  exact
        0x0025ac10u,   // packTrace            r0001 0x0025a5d0  relinked-body
        0x00291fc0u,   // cull                 r0001 0x00290c30  exact
        0x00355a10u,   // node                 r0001 0x00338480  relinked-body
        0x00355f50u,   // node2                r0001 0x003389c0  relinked-body
        0x003d9ce0u,   // lod                  r0001 0x003b7b90  exact
        0x003d8f60u,   // detail               r0001 0x003b6e10  relinked-body
        0x00292d10u,   // camCfg               r0001 0x002918b0  relinked-body
        0x00354750u,   // defer                r0001 0x003371b0  bracketed (body changed: two instructions fewer)
        0x00354250u,   // flush                r0001 0x00336cb0  relinked-body
        0x00368660u,   // musicManager         r0001 0x0034afd0  relinked-body
        0x00368d50u,   // cuePush              r0001 0x0034b6c0  exact
        0x004429b0u,   // cameraHolder         r0001 0x00415ff0  data-via-twin
        0x0040cc60u,   // versionString        r0001 0x003e17e0  build-banner
        0x003adbc0u,   // oskOpen              r0001 0x0038d770  relinked-body+string ("KEYBOARD")
        0x00281be0u,   // oskOpenThunk         r0001 0x002808d0  thunk-target
        0x004a2440u,   // oskTextBuffer        r0001 0x0049ec70  data-via-twin (oskOpen +0xd8)
        0x00312100u,   // chatFanoutRecv       r0001 0x002f4ef0  relinked-body+string ("%s: %s")
        0x00312230u,   // chatListRender       r0001 0x002f5020  relinked-body+string ("%s %s: %s")
        0x00452928u,   // chatListHolders      r0001 0x0044f568  data-via-twin (21 twins, unanimous)
        0x002cf330u,   // dnasCheck            r0001 0x002cc670  capsule-table + relinked-body+string ("DNAS_ERROR_CODE")
        0x004315a0u,   // ctorTableFtsBegin    r0001 0x00404d10  ctor-run (126 entries; r0001 has 125)
        0x00431798u,   // ctorTableFtsEnd      r0001 0x00404f04  ctor-run
        0x00668a60u,   // ctorTableZsealBegin  r0001 0x006690e0  ctor-run (16 entries, as r0001)
        0x00668aa0u,   // ctorTableZsealEnd    r0001 0x00669120  ctor-run + data-via-twin (3 twins agree)
        // libnetb_ex DID NOT MOVE. Every entry point is at its r0001 address in r0004, eight of the ten
        // byte for byte and the other two differing only in `jal` targets into code that did move. That
        // is a finding, not a copied column: it is why the suite pins these ten as equal across the two
        // columns and every other field as different.
        0x002472c8u,   // netbExOpen           r0001 0x002472c8  identity (exact; bytes unchanged)
        0x002474f8u,   // netbExTcpRecv        r0001 0x002474f8  identity (exact; 2 relocation words differ)
        0x00247738u,   // netbExTcpSend        r0001 0x00247738  identity (exact; 4 relocation words differ)
        0x00247d30u,   // netbExUdpRecv        r0001 0x00247d30  identity (exact; bytes unchanged)
        0x00247fe8u,   // netbExUdpSend        r0001 0x00247fe8  identity (exact; bytes unchanged)
        0x002479b8u,   // netbExAvailable      r0001 0x002479b8  identity (exact; bytes unchanged)
        0x00247bd8u,   // netbExConnected      r0001 0x00247bd8  identity (exact; bytes unchanged)
        // These two are byte-identical to EACH OTHER, so no fingerprint can tell them apart in either
        // image -- address_matcher.py leaves both unresolved. What places them is that each is byte for
        // byte the same at its own address in r0004, and a function starts there: identity, the one
        // piece of evidence an ambiguous pair cannot spoil.
        0x00248350u,   // netbExStartAsync     r0001 0x00248350  identity (bytes unchanged at the same address)
        0x002483f8u,   // netbExStartAsync2    r0001 0x002483f8  identity (bytes unchanged at the same address)
        0x00247c98u,   // netbExDescriptorDma  r0001 0x00247c98  identity (exact; bytes unchanged)
        // libdnas2 moved WHOLESALE: every entry point by the same +0x7ac0, four of the six byte for byte
        // after the move. One delta for the whole library is itself a check on the six.
        0x00633408u,   // dnasRsaBlock         r0001 0x0062b948  exact, block +0x7ac0 (1 relocation word)
        0x00636980u,   // dnasSha1Hash         r0001 0x0062eec0  exact, block +0x7ac0 (3 relocation words)
        0x006320f8u,   // dnasRc4SetKeyHash    r0001 0x0062a638  exact, block +0x7ac0 (bytes unchanged)
        0x00632068u,   // dnasRc4SetKey        r0001 0x0062a5a8  exact, block +0x7ac0 (bytes unchanged)
        0x006321e0u,   // dnasRc4Encrypt       r0001 0x0062a720  exact, block +0x7ac0 (bytes unchanged)
        0x00632288u,   // dnasRc4Decrypt       r0001 0x0062a7c8  exact, block +0x7ac0 (bytes unchanged)
    };

    // Every column this build knows. A second revision is one more entry here and one more Table above.
    inline const Table *const kTables[] = {&kR0001, &kR0004};

    // Is this a field the column established? kUnavailable is not, and neither is a loader address --
    // nothing below kOverlayBase belongs in a per-revision column at all.
    inline bool available(uint32_t addr) { return addr >= kOverlayBase; }

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

    // The guard every install site puts in front of an override: true when the chosen column has an
    // address for this field, otherwise ONE log line naming the field and no override. A field nobody
    // established is a missing feature, which is survivable; the r0001 address in its place is a crash
    // somewhere else entirely, hours later, which is not.
    inline bool require(uint32_t addr, const char *field)
    {
        if (available(addr))
            return true;
        std::cout << "[socom2] address table: " << current().revision << " has no address for "
                  << (field ? field : "(unnamed field)") << " -- that override is not installed"
                  << std::endl;
        return false;
    }

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

    // Read up to a stamp's worth of NUL-terminated text at a guest address; empty when there is none.
    // The runtime passes a reader over RDRAM; the suite passes one over a table of strings.
    using StampReader = std::string (*)(uint32_t addr, void *user);

    // Choose the column by probing the loaded image. selectFromVersionString() can only judge a string
    // somebody has already read -- but the address to read it AT is itself per-revision (r0001's banner
    // is at 0x003e17e0, r0004's at 0x0040cc60, and in an r0004 image 0x003e17e0 is code). So each
    // column's own versionString is read and the column whose text names THAT column wins. This is what
    // the r0004 capsule does too: it probes both builds' layouts and takes the one that answers.
    //
    // NEWEST FIRST. kTables is oldest first, so the walk runs backwards. An image can answer at more
    // than one row's stamp address -- a second copy of an older banner, a library's own stamp, an older
    // overlay still resident in RAM from before the newer one was loaded -- and r0001's row is exactly
    // the one every unknown image falls back to, so checking it first would let a stale r0001 answer
    // decide before the newer rows had been read at all. A row only ever claims an image whose text
    // names that row's own revision, so this changes which row gets to answer first, never what
    // counts as an answer.
    //
    // Every stamp read is logged, chosen or not: when this picks the wrong column the log is the only
    // place the reason can be. No column answering keeps r0001 AND logs, through the same warning as
    // an unreadable stamp.
    inline const Table &selectFromImage(StampReader read, void *user = nullptr)
    {
        // EVERY row's stamp is read and logged before any of them is acted on -- not just up to the one
        // that answers. When this picks the wrong column the log is the only place the reason can be,
        // and "what the other rows said" is exactly the part that tells a wrong column apart from a
        // wrong image. (It is how the s11_r0004_gate2 run was diagnosed: the r0001 row answered on an
        // r0004 build, and only the r0004 row's stamp -- unread, so unlogged -- could say whether the
        // table or the resident overlay was at fault. It was the overlay.)
        const std::size_t n = sizeof(kTables) / sizeof(kTables[0]);
        std::string fallbackText;
        const Table *chosen = nullptr;
        for (std::size_t i = n; i-- > 0;)
        {
            const Table *t = kTables[i];
            const std::string text = read ? read(t->versionString, user) : std::string();
            const std::string rev = revisionOf(text.c_str());
            std::cout << "[socom2] address table: stamp@0x" << std::hex << t->versionString << std::dec
                      << " (the " << t->revision << " row) = \"" << text << "\""
                      << (rev == t->revision ? "  <- names this row" : "") << std::endl;
            if (t == &kR0001)
                fallbackText = text;
            if (!chosen && rev == t->revision)
                chosen = t;                                   // newest first, so the first is the newest
        }
        if (chosen)
        {
            select(*chosen);
            std::cout << "[socom2] address table: the image names itself " << chosen->revision
                      << " -- using the " << chosen->revision << " addresses" << std::endl;
            return *chosen;
        }
        // No row named itself. r0001, and never silently.
        //
        // The fallback does NOT ask selectFromVersionString() what the r0001 slot's text names, except
        // when it names nothing -- which is the real case, and gets that function's warning verbatim. A
        // stamp that names some OTHER revision while sitting at r0001's address has not identified the
        // image; it has only proved that something is where it should not be, and choosing a column on
        // it would be choosing on exactly the evidence this ordering exists to distrust.
        if (revisionOf(fallbackText.c_str()).empty())
        {
            selectFromVersionString(fallbackText.c_str());
            return current();
        }
        select(kR0001);
        std::cout << "[socom2] address table: no row's stamp named its own revision (the "
                  << kR0001.revision << " row read \"" << fallbackText << "\") -- using "
                  << kR0001.revision << ", every override address is an " << kR0001.revision
                  << " address" << std::endl;
        return current();
    }
}
