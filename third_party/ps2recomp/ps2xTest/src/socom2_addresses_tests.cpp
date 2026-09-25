// Sprint 11 Task 10 (milestone R): the per-revision address table.
//
// Every guest address the SOCOM II overrides use is an r0001 address written as a literal at the call
// site. socom2_addresses.h gathers them into one table per revision so a second build of the game is a
// second column rather than a second search through game_overrides_socom2.cpp. These cases pin the r0001
// column against the literals it replaced, and pin what current() does when the image is not one this
// table knows: it keeps r0001 and says so, because a silently wrong address would present as a crash
// somewhere else entirely.
#include "MiniTest.h"
#include "runtime/socom2_addresses.h"
#include "runtime/socom2_chat.h"
#include "runtime/socom2_osk_prefill.h"

#include <cstddef>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace
{
    // current() is process-wide state; the suites after this one must find it as they were.
    struct SelectionGuard
    {
        const socom2_addresses::Table *saved = &socom2_addresses::current();
        ~SelectionGuard() { socom2_addresses::select(*saved); }
    };

    // Everything this table logs goes to std::cout, as the rest of the SOCOM II runtime does.
    template <typename Body>
    std::string capture(Body body)
    {
        std::ostringstream sink;
        std::streambuf *old = std::cout.rdbuf(sink.rdbuf());
        body();
        std::cout.rdbuf(old);
        return sink.str();
    }

    bool contains(const std::string &haystack, const char *needle)
    {
        return haystack.find(needle) != std::string::npos;
    }

    // The two build banners, exactly as they read in the two images (game/overlays/socom2_game.elf at
    // 0x003e17e0, game/overlays_r0004/socom2_game_r0004.elf at 0x0040cc60).
    const char *kR0001Version = "SOCOM 2 r0001 17:22:21 Oct 11 2003";
    const char *kR0004Version = "SOCOM 2 r0004 10:14:38 Nov  3 2004";
    // What the runtime was reading instead, and what the s11_r0004_gate title log carried: the boot path
    // that lives at 0x003e5c60 in r0001. It names no revision, so every image looked like r0001.
    const char *kDiscPath = "cdrom0:\\SCUS_972.75;1";

    // Every address field of one column, in the header's order. The cases below that hold a column to an
    // invariant read it through this, so a field added to the Table and not added here is a field no
    // invariant covers -- which is why it is one list and not one per case.
    std::vector<uint32_t> fieldsOf(const socom2_addresses::Table &a)
    {
        return {a.rtNetConfigInit, a.packTrace, a.cull, a.node, a.node2, a.lod, a.detail, a.camCfg,
                a.defer, a.flush, a.musicManager, a.cuePush, a.cameraHolder, a.versionString,
                a.oskOpen, a.oskOpenThunk, a.oskTextBuffer, a.chatFanoutRecv, a.chatListRender,
                a.chatListHolders, a.dnasCheck, a.ctorTableFtsBegin, a.ctorTableFtsEnd,
                a.ctorTableZsealBegin, a.ctorTableZsealEnd,
                a.netbExOpen, a.netbExTcpRecv, a.netbExTcpSend, a.netbExUdpRecv, a.netbExUdpSend,
                a.netbExAvailable, a.netbExConnected, a.netbExStartAsync, a.netbExStartAsync2,
                a.netbExDescriptorDma, a.dnasRsaBlock, a.dnasSha1Hash, a.dnasRc4SetKeyHash,
                a.dnasRc4SetKey, a.dnasRc4Encrypt, a.dnasRc4Decrypt};
    }

    // A stand-in for the loaded image: the text at each address a table's versionString names.
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
        return std::string();   // unmapped, or data that is not text: no revision either way
    }
}

void register_socom2_addresses_tests()
{
    MiniTest::Case("Socom2Addresses", [](TestCase &tc)
    {
        tc.Run("the r0001 column is the literals it replaced", [](TestCase &t)
        {
            const socom2_addresses::Table &a = socom2_addresses::forRevision("r0001");
            t.IsTrue(std::string(a.revision) == "r0001", "revision is r0001");
            t.Equals(a.rtNetConfigInit, 0x00620648u, "rtNetConfigInit: FUN_00620648");
            t.Equals(a.packTrace, 0x0025a5d0u, "packTrace: FUN_0025a5d0");
            t.Equals(a.cull, 0x00290c30u, "cull: FUN_00290c30");
            t.Equals(a.node, 0x00338480u, "node: FUN_00338480");
            t.Equals(a.node2, 0x003389c0u, "node2: FUN_003389c0");
            t.Equals(a.lod, 0x003b7b90u, "lod: FUN_003b7b90");
            t.Equals(a.detail, 0x003b6e10u, "detail: FUN_003b6e10");
            t.Equals(a.camCfg, 0x002918b0u, "camCfg: FUN_002918b0");
            t.Equals(a.defer, 0x003371b0u, "defer: FUN_003371b0");
            t.Equals(a.flush, 0x00336cb0u, "flush: FUN_00336cb0");
            t.Equals(a.musicManager, 0x0034afd0u, "musicManager: FUN_0034afd0");
            t.Equals(a.cuePush, 0x0034b6c0u, "cuePush: FUN_0034b6c0");
            t.Equals(a.cameraHolder, 0x00415ff0u, "cameraHolder: the camera holder pointer");
            // Task 19: the build banner, NOT 0x003e5c60 -- that address holds the boot path
            // "cdrom0:\SCUS_972.75;1", which names no revision, so every image selected r0001.
            t.Equals(a.versionString, 0x003e17e0u, "versionString: the FTSCore build stamp");
            t.Equals(a.oskOpen, 0x0038D770u, "oskOpen: FUN_0038d770, the GetTextInput handler");
            t.Equals(a.oskOpen, socom2_osk::kOskOpenAddr, "oskOpen: socom2_osk::kOskOpenAddr, not a second copy");
            t.Equals(a.oskOpenThunk, 0x002808D0u, "oskOpenThunk: thunk_FUN_0038d770, what the action table calls");
            t.Equals(a.oskOpenThunk, socom2_osk::kOskOpenThunkAddr, "oskOpenThunk: one definition, not a second copy");
            t.Equals(a.oskTextBuffer, 0x0049EC70u, "oskTextBuffer: the keyboard's initial-text buffer");
            t.Equals(a.oskTextBuffer, socom2_osk::kOskTextBufferAddr, "oskTextBuffer: one definition, not a second copy");
            t.Equals(a.chatFanoutRecv, 0x002f4ef0u, "chatFanoutRecv: FUN_002f4ef0");
            t.Equals(a.chatFanoutRecv, socom2_chat::kFanoutRecvAddr, "chatFanoutRecv: socom2_chat::kFanoutRecvAddr, not a second copy");
            t.Equals(a.chatListRender, 0x002f5020u, "chatListRender: FUN_002f5020");
            t.Equals(a.chatListHolders, 0x0044f568u, "chatListHolders: the holder list it renders from");
            t.Equals(a.dnasCheck, 0x002cc670u, "dnasCheck: FUN_002cc670");
            t.Equals(a.ctorTableFtsBegin, 0x00404d10u, "ctorTableFtsBegin: FTSCore static constructors");
            t.Equals(a.ctorTableFtsEnd, 0x00404f04u, "ctorTableFtsEnd");
            t.Equals(a.ctorTableZsealBegin, 0x006690e0u, "ctorTableZsealBegin: ZSealEtc static constructors");
            t.Equals(a.ctorTableZsealEnd, 0x00669120u, "ctorTableZsealEnd");
        });

        tc.Run("every entry is an overlay address, never a loader one", [](TestCase &t)
        {
            // The loader is the same in every revision and is NOT in this table (its addresses stay
            // literal at their call sites, with the comment saying why). A loader address appearing
            // here would mean someone moved the wrong literal. The one value below the overlay base a
            // column may carry is kUnavailable -- 0, "this revision's address was never established".
            for (const socom2_addresses::Table *tab : socom2_addresses::kTables)
                for (uint32_t v : fieldsOf(*tab))
                    t.IsTrue(v == socom2_addresses::kUnavailable || v >= socom2_addresses::kOverlayBase,
                             std::string(tab->revision) + ": 0x" + std::to_string(v) + " is an overlay address or kUnavailable");
        });

        tc.Run("the r0004 column is the r0004 image's addresses", [](TestCase &t)
        {
            // Every value here was established against game/overlays_r0004/socom2_game_r0004.elf and is
            // recorded field by field, with how it was established, in
            // .superpowers/sdd/2026-09-23-sprint-11/task-19-addresses-report.md.
            const socom2_addresses::Table &b = socom2_addresses::forRevision("r0004");
            t.IsTrue(std::string(b.revision) == "r0004", "revision is r0004");
            t.Equals(b.rtNetConfigInit, 0x00627f38u, "rtNetConfigInit");
            t.Equals(b.packTrace, 0x0025ac10u, "packTrace");
            t.Equals(b.cull, 0x00291fc0u, "cull");
            t.Equals(b.node, 0x00355a10u, "node");
            t.Equals(b.node2, 0x00355f50u, "node2");
            t.Equals(b.lod, 0x003d9ce0u, "lod");
            t.Equals(b.detail, 0x003d8f60u, "detail");
            t.Equals(b.camCfg, 0x00292d10u, "camCfg");
            t.Equals(b.defer, 0x00354750u, "defer");
            t.Equals(b.flush, 0x00354250u, "flush");
            t.Equals(b.musicManager, 0x00368660u, "musicManager");
            t.Equals(b.cuePush, 0x00368d50u, "cuePush");
            t.Equals(b.cameraHolder, 0x004429b0u, "cameraHolder");
            t.Equals(b.versionString, 0x0040cc60u, "versionString: \"SOCOM 2 r0004 10:14:38 Nov  3 2004\"");
            t.Equals(b.oskOpen, 0x003adbc0u, "oskOpen");
            t.Equals(b.oskOpenThunk, 0x00281be0u, "oskOpenThunk");
            t.Equals(b.oskTextBuffer, 0x004a2440u, "oskTextBuffer");
            t.Equals(b.chatFanoutRecv, 0x00312100u, "chatFanoutRecv");
            t.Equals(b.chatListRender, 0x00312230u, "chatListRender");
            t.Equals(b.chatListHolders, 0x00452928u, "chatListHolders");
            t.Equals(b.dnasCheck, 0x002cf330u, "dnasCheck: the capsule's second table names the same address");
            t.Equals(b.ctorTableFtsBegin, 0x004315a0u, "ctorTableFtsBegin");
            t.Equals(b.ctorTableFtsEnd, 0x00431798u, "ctorTableFtsEnd");
            t.Equals(b.ctorTableZsealBegin, 0x00668a60u, "ctorTableZsealBegin");
            t.Equals(b.ctorTableZsealEnd, 0x00668aa0u, "ctorTableZsealEnd");
        });

        tc.Run("not one field of the r0004 column is an r0001 address by accident", [](TestCase &t)
        {
            // The defect this task exists for: the r0004 exe ran the whole session on r0001's override
            // addresses. A field that could not be established is 0 and its override is skipped; it is
            // never quietly the other revision's address.
            //
            // Ten fields ARE the same address in both columns, and that is a finding, not an omission:
            // the whole libnetb_ex block sits at the same addresses in both builds (eight of the ten
            // byte for byte). They are named here so that "equal" has to be the proven kind -- any
            // OTHER field turning up equal means somebody copied a column instead of establishing it.
            const std::vector<uint32_t> a = fieldsOf(socom2_addresses::kR0001);
            const std::vector<uint32_t> b = fieldsOf(socom2_addresses::kR0004);
            t.Equals(a.size(), b.size(), "the two columns have the same fields");
            const std::size_t kNetbFirst = 25, kNetbLast = 35;   // netbExOpen .. netbExDescriptorDma
            for (std::size_t i = 0; i < a.size(); ++i)
            {
                if (i >= kNetbFirst && i < kNetbLast)
                    t.IsTrue(a[i] == b[i], "field " + std::to_string(i) + " is libnetb_ex: unmoved, proven");
                else
                    t.IsTrue(a[i] != b[i], "field " + std::to_string(i) + " differs between the revisions");
            }
        });

        tc.Run("the libnetb_ex and libdnas2 entry points are columns, not literals", [](TestCase &t)
        {
            // Task 10 left these sixteen overlay addresses literal in game_overrides_socom2.cpp because
            // its Table did not name them. On an r0004 image every one of them was an r0001 address --
            // the last place this defect's shape survived.
            const socom2_addresses::Table &a = socom2_addresses::kR0001;
            const socom2_addresses::Table &b = socom2_addresses::kR0004;
            t.Equals(a.netbExOpen, 0x002472c8u, "r0001 netbExOpen");
            t.Equals(a.netbExTcpRecv, 0x002474f8u, "r0001 netbExTcpRecv");
            t.Equals(a.netbExTcpSend, 0x00247738u, "r0001 netbExTcpSend");
            t.Equals(a.netbExUdpRecv, 0x00247d30u, "r0001 netbExUdpRecv");
            t.Equals(a.netbExUdpSend, 0x00247fe8u, "r0001 netbExUdpSend");
            t.Equals(a.netbExAvailable, 0x002479b8u, "r0001 netbExAvailable");
            t.Equals(a.netbExConnected, 0x00247bd8u, "r0001 netbExConnected");
            t.Equals(a.netbExStartAsync, 0x00248350u, "r0001 netbExStartAsync");
            t.Equals(a.netbExStartAsync2, 0x002483f8u, "r0001 netbExStartAsync2");
            t.Equals(a.netbExDescriptorDma, 0x00247c98u, "r0001 netbExDescriptorDma");
            t.Equals(a.dnasRsaBlock, 0x0062b948u, "r0001 dnasRsaBlock");
            t.Equals(a.dnasSha1Hash, 0x0062eec0u, "r0001 dnasSha1Hash");
            t.Equals(a.dnasRc4SetKeyHash, 0x0062a638u, "r0001 dnasRc4SetKeyHash");
            t.Equals(a.dnasRc4SetKey, 0x0062a5a8u, "r0001 dnasRc4SetKey");
            t.Equals(a.dnasRc4Encrypt, 0x0062a720u, "r0001 dnasRc4Encrypt");
            t.Equals(a.dnasRc4Decrypt, 0x0062a7c8u, "r0001 dnasRc4Decrypt");

            // libnetb_ex did not move at all: same addresses, and eight of the ten byte for byte.
            t.Equals(b.netbExOpen, 0x002472c8u, "r0004 netbExOpen: unmoved");
            t.Equals(b.netbExTcpRecv, 0x002474f8u, "r0004 netbExTcpRecv: unmoved");
            t.Equals(b.netbExTcpSend, 0x00247738u, "r0004 netbExTcpSend: unmoved");
            t.Equals(b.netbExUdpRecv, 0x00247d30u, "r0004 netbExUdpRecv: unmoved");
            t.Equals(b.netbExUdpSend, 0x00247fe8u, "r0004 netbExUdpSend: unmoved");
            t.Equals(b.netbExAvailable, 0x002479b8u, "r0004 netbExAvailable: unmoved");
            t.Equals(b.netbExConnected, 0x00247bd8u, "r0004 netbExConnected: unmoved");
            t.Equals(b.netbExStartAsync, 0x00248350u, "r0004 netbExStartAsync: unmoved");
            t.Equals(b.netbExStartAsync2, 0x002483f8u, "r0004 netbExStartAsync2: unmoved");
            t.Equals(b.netbExDescriptorDma, 0x00247c98u, "r0004 netbExDescriptorDma: unmoved");
            // libdnas2 moved wholesale, every entry point by the same +0x7ac0.
            t.Equals(b.dnasRsaBlock, 0x00633408u, "r0004 dnasRsaBlock");
            t.Equals(b.dnasSha1Hash, 0x00636980u, "r0004 dnasSha1Hash");
            t.Equals(b.dnasRc4SetKeyHash, 0x006320f8u, "r0004 dnasRc4SetKeyHash");
            t.Equals(b.dnasRc4SetKey, 0x00632068u, "r0004 dnasRc4SetKey");
            t.Equals(b.dnasRc4Encrypt, 0x006321e0u, "r0004 dnasRc4Encrypt");
            t.Equals(b.dnasRc4Decrypt, 0x00632288u, "r0004 dnasRc4Decrypt");
            const uint32_t kDnasDelta = 0x7ac0u;
            t.Equals(b.dnasRsaBlock - a.dnasRsaBlock, kDnasDelta, "libdnas2 moved as one block");
            t.Equals(b.dnasSha1Hash - a.dnasSha1Hash, kDnasDelta, "... every entry point by the same delta");
            t.Equals(b.dnasRc4SetKeyHash - a.dnasRc4SetKeyHash, kDnasDelta, "...");
            t.Equals(b.dnasRc4SetKey - a.dnasRc4SetKey, kDnasDelta, "...");
            t.Equals(b.dnasRc4Encrypt - a.dnasRc4Encrypt, kDnasDelta, "...");
            t.Equals(b.dnasRc4Decrypt - a.dnasRc4Decrypt, kDnasDelta, "...");
        });

        tc.Run("both shipped columns are complete -- no field left unestablished", [](TestCase &t)
        {
            // kUnavailable is honest, not desirable: if a field of either column is ever zeroed, that is
            // an override the loaded game will not get, and the suite says so here rather than in a log.
            for (const socom2_addresses::Table *tab : socom2_addresses::kTables)
                for (uint32_t v : fieldsOf(*tab))
                    t.IsTrue(socom2_addresses::available(v),
                             std::string(tab->revision) + " has an established address for every field");
        });

        tc.Run("an unavailable field is skipped, and the guard names it", [](TestCase &t)
        {
            const std::string log = capture([] { (void)socom2_addresses::require(socom2_addresses::kUnavailable, "chatFanoutRecv"); });
            t.IsFalse(socom2_addresses::available(socom2_addresses::kUnavailable), "0 is not an address");
            t.IsFalse(socom2_addresses::require(socom2_addresses::kUnavailable, "chatFanoutRecv"), "the guard refuses it");
            t.IsTrue(contains(log, "chatFanoutRecv"), "the one log line names the field: " + log);
            t.IsTrue(contains(log, "[socom2]"), "on the runtime's own channel: " + log);
            const std::string quiet = capture([] { (void)socom2_addresses::require(socom2_addresses::kR0001.dnasCheck, "dnasCheck"); });
            t.IsTrue(socom2_addresses::require(socom2_addresses::kR0001.dnasCheck, "dnasCheck"), "a real address passes");
            t.IsTrue(quiet.empty(), "and passes silently: " + quiet);
            // A loader address is not an available overlay address either -- see the invariant above.
            t.IsFalse(socom2_addresses::available(0x001c5b30u), "a loader address is not one of ours");
        });

        tc.Run("the keyboard wrap needs all three of its addresses from one column", [](TestCase &t)
        {
            // The prefill replaces the handler AND the thunk the action table dispatches through, then
            // writes the initial-text buffer. All three move together in a relink, so all three are
            // fields: a column that carried the handler alone would arm the wrap and fill nothing.
            const socom2_addresses::Table &a = socom2_addresses::forRevision("r0001");
            t.IsTrue(a.oskOpen != a.oskOpenThunk, "the handler and the thunk are different addresses");
            t.IsTrue(a.oskTextBuffer != a.oskOpen && a.oskTextBuffer != a.oskOpenThunk, "the buffer is neither");
            t.IsTrue(a.oskOpen >= socom2_addresses::kOverlayBase, "the handler is overlay content");
            t.IsTrue(a.oskOpenThunk >= socom2_addresses::kOverlayBase, "the thunk is overlay content");
            t.IsTrue(a.oskTextBuffer >= socom2_addresses::kOverlayBase, "the buffer is overlay content");
        });

        // The chat wraps reach into the image by two things: the addresses above, and the record layout in
        // socom2_chat.h. The addresses are pinned here to the literals they replaced; the layout is pinned
        // the same way, because every case in socom2_chat_tests.cpp spells it symbolically and would pass
        // unchanged against a wrong constant.
        tc.Run("the chat record layout is the offsets and widths it was written from", [](TestCase &t)
        {
            t.Equals(socom2_chat::kNameOff, 0x1cu, "kNameOff");
            t.Equals(socom2_chat::kNameLen, 32u, "kNameLen");
            t.Equals(socom2_chat::kTypeOff, 0x3cu, "kTypeOff");
            t.Equals(socom2_chat::kMessageOff, 0x40u, "kMessageOff");
            t.Equals(socom2_chat::kMessageLen, 64u, "kMessageLen");
            t.Equals(socom2_chat::kPacketBytes, 0x80u, "kPacketBytes");
            t.Equals(socom2_chat::kRecordBytes, 0x80u, "kRecordBytes: the run's stride");
            t.Equals(socom2_chat::kListCountOff, 0x8cu, "kListCountOff");
            t.Equals(socom2_chat::kListDataOff, 0x90u, "kListDataOff");
            t.Equals(socom2_chat::kListHeaderBytes, 0x94u, "kListHeaderBytes: through the last of the two");
            t.Equals(socom2_chat::kHolderCountOff, 0x04u, "kHolderCountOff");
            t.Equals(socom2_chat::kHolderDataOff, 0x08u, "kHolderDataOff");
            t.Equals(socom2_chat::kHolderPtrBytes, 4u, "kHolderPtrBytes");
            t.IsTrue(socom2_chat::kMessageOff + socom2_chat::kMessageLen <= socom2_chat::kRecordBytes,
                     "both fields lie inside one record");
        });

        tc.Run("the revision token is read out of the version string", [](TestCase &t)
        {
            t.IsTrue(socom2_addresses::revisionOf(kR0001Version) == "r0001", "the r0001 stamp");
            t.IsTrue(socom2_addresses::revisionOf(kR0004Version) == "r0004", "the r0004 stamp, two spaces and all");
            // The string the runtime actually read until tonight. It is not a stamp at all.
            t.IsTrue(socom2_addresses::revisionOf(kDiscPath).empty(), "the boot path names no revision");
            t.IsTrue(socom2_addresses::revisionOf("").empty(), "an empty string names no revision");
            t.IsTrue(socom2_addresses::revisionOf(nullptr).empty(), "a null string names no revision");
            t.IsTrue(socom2_addresses::revisionOf("\xff\xfe garbage \x01").empty(), "garbage names no revision");
            t.IsTrue(socom2_addresses::revisionOf("SOCOM 2 rabbit").empty(), "r followed by letters is not a revision");
        });

        tc.Run("an unknown version string keeps r0001 and says so", [](TestCase &t)
        {
            SelectionGuard guard;
            const std::string log = capture([] { socom2_addresses::selectFromVersionString("PS2 DISC ID SLUS-20880"); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "current() is still r0001");
            t.IsTrue(contains(log, "[socom2]"), "it logged on the runtime's own channel: " + log);
            t.IsTrue(contains(log, "r0001"), "the log names the revision it kept: " + log);
        });

        tc.Run("an empty version string keeps r0001 and says so", [](TestCase &t)
        {
            SelectionGuard guard;
            const std::string log = capture([] { socom2_addresses::selectFromVersionString(""); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "current() is still r0001");
            t.IsTrue(!log.empty(), "an unreadable version string is never silent");
        });

        tc.Run("the r0001 stamp selects r0001 without a complaint", [](TestCase &t)
        {
            SelectionGuard guard;
            const std::string log = capture([] { socom2_addresses::selectFromVersionString(kR0001Version); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "current() is r0001");
            t.Equals(socom2_addresses::current().chatFanoutRecv, 0x002f4ef0u, "current() hands out the r0001 addresses");
            t.IsFalse(contains(log, "unknown"), "nothing to complain about: " + log);
        });

        tc.Run("the r0004 stamp selects the r0004 column", [](TestCase &t)
        {
            SelectionGuard guard;
            const std::string log = capture([] { socom2_addresses::selectFromVersionString(kR0004Version); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0004", "current() is r0004");
            t.Equals(socom2_addresses::current().dnasCheck, 0x002cf330u, "current() hands out the r0004 addresses");
            t.Equals(socom2_addresses::current().chatFanoutRecv, 0x00312100u, "... for every field, not just the one");
            t.IsFalse(contains(log, "no column"), "nothing to complain about: " + log);
        });

        tc.Run("the boot path keeps r0001 and says every address is an r0001 address", [](TestCase &t)
        {
            // The exact line logs/parity/gate/s11_r0004_gate/title.game.log carried, from an r0004 exe.
            SelectionGuard guard;
            socom2_addresses::select(socom2_addresses::kR0004);
            const std::string log = capture([] { socom2_addresses::selectFromVersionString(kDiscPath); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "it falls back to r0001");
            t.IsTrue(contains(log, "names no revision"), "the existing warning, unchanged: " + log);
            t.IsTrue(contains(log, "every override address is an r0001 address"), "and what it costs: " + log);
        });

        tc.Run("the column is chosen by probing each revision's stamp in the loaded image", [](TestCase &t)
        {
            // selectFromVersionString can only judge a string somebody already read -- and the address to
            // read it AT is itself per-revision. So the runtime probes each column's own versionString and
            // takes the one whose text names that column. Anything else keeps r0001, with the warning.
            SelectionGuard guard;
            FakeImage r0004Image;
            r0004Image.put(socom2_addresses::kR0001.versionString, "\xe0\xff\xbd\x27");   // r0004: code lives there
            r0004Image.put(socom2_addresses::kR0004.versionString, kR0004Version);
            const std::string chosen = capture([&r0004Image] { socom2_addresses::selectFromImage(readFake, &r0004Image); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0004", "the r0004 image picks r0004");
            t.IsTrue(contains(chosen, "SOCOM 2 r0004"), "the log carries the stamp it read: " + chosen);

            FakeImage r0001Image;
            r0001Image.put(socom2_addresses::kR0001.versionString, kR0001Version);
            capture([&r0001Image] { socom2_addresses::selectFromImage(readFake, &r0001Image); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "the r0001 image picks r0001");

            // An image that is neither: the r0001 slot holds the old boot path, the r0004 slot nothing.
            FakeImage stranger;
            stranger.put(socom2_addresses::kR0001.versionString, kDiscPath);
            socom2_addresses::select(socom2_addresses::kR0004);
            const std::string log = capture([&stranger] { socom2_addresses::selectFromImage(readFake, &stranger); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "an unknown image keeps r0001");
            t.IsTrue(contains(log, "names no revision"), "and is never silent about it: " + log);
        });

        tc.Run("an image holding BOTH stamps is the newest revision that names itself", [](TestCase &t)
        {
            // The rows are probed newest first. An image that answers at more than one row's stamp
            // address -- a second copy of an older banner, a library's own stamp, a stale overlay left
            // in RAM -- must not be decided by whichever row happens to be checked first, and r0001's
            // row is exactly the one every unknown image falls back to.
            SelectionGuard guard;
            FakeImage both;
            both.put(socom2_addresses::kR0001.versionString, kR0001Version);
            both.put(socom2_addresses::kR0004.versionString, kR0004Version);
            const std::string log = capture([&both] { socom2_addresses::selectFromImage(readFake, &both); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0004", "the newest row that names itself wins");
            t.IsTrue(contains(log, "SOCOM 2 r0001") || contains(log, "0x3e17e0"),
                     "and both stamps read are on the record: " + log);

            // A row only ever claims an image that names THAT row's revision: r0004's banner sitting at
            // r0001's stamp address decides nothing, because "r0004" is not "r0001".
            SelectionGuard guard2;
            FakeImage crossed;
            crossed.put(socom2_addresses::kR0001.versionString, kR0004Version);
            const std::string cross = capture([&crossed] { socom2_addresses::selectFromImage(readFake, &crossed); });
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "no row claimed it, so r0001");
            t.IsTrue(contains(cross, "every override address is an r0001 address"),
                     "and it says what that costs: " + cross);
            t.IsTrue(contains(cross, "SOCOM 2 r0004"), "naming the text it would not act on: " + cross);
        });

        tc.Run("kTables is oldest first, so probing it backwards really is newest first", [](TestCase &t)
        {
            // selectFromImage walks kTables in reverse to get newest-first. That is only true while the
            // array is in ascending revision order, and kR0001 must stay the first entry because it is
            // the fallback. Both are invariants of the array, not of the loop, so they are pinned here.
            const std::size_t n = sizeof(socom2_addresses::kTables) / sizeof(socom2_addresses::kTables[0]);
            t.IsTrue(n >= 2, "there is more than one column to order");
            t.IsTrue(socom2_addresses::kTables[0] == &socom2_addresses::kR0001, "r0001 is first: it is the fallback");
            for (std::size_t i = 1; i < n; ++i)
                t.IsTrue(std::strcmp(socom2_addresses::kTables[i - 1]->revision,
                                     socom2_addresses::kTables[i]->revision) < 0,
                         std::string("kTables[") + std::to_string(i) + "] is newer than the one before it");
        });

        tc.Run("an unknown revision name falls back to r0001", [](TestCase &t)
        {
            const std::string log = capture([] { (void)socom2_addresses::forRevision("r9999"); });
            t.IsTrue(std::string(socom2_addresses::forRevision("r9999").revision) == "r0001", "the fallback table");
            t.IsTrue(contains(log, "r9999"), "the log names what it did not recognise: " + log);
            t.IsTrue(std::string(socom2_addresses::forRevision(nullptr).revision) == "r0001", "a null revision falls back too");
        });

        tc.Run("the default before any selection is r0001", [](TestCase &t)
        {
            SelectionGuard guard;
            socom2_addresses::select(socom2_addresses::kR0001);
            t.IsTrue(std::string(socom2_addresses::current().revision) == "r0001", "the table a fresh process starts with");
        });
    });
}
