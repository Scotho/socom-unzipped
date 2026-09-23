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

#include <iostream>
#include <sstream>
#include <string>

namespace
{
    // current() is process-wide state; the suites after this one must find it as they were.
    struct SelectionGuard
    {
        const socom2_addresses::Table *saved = &socom2_addresses::current();
        ~SelectionGuard() { socom2_addresses::select(*saved); }
    };

    // Everything this table logs goes to std::cout, as the rest of the SOCOM II runtime does.
    std::string capture(void (*body)())
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

    const char *kR0001Version = "SOCOM 2 r0001 17:22:21 Oct 11 2003";
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
            t.Equals(a.versionString, 0x003e5c60u, "versionString: the FTSCore build stamp");
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
            // here would mean someone moved the wrong literal.
            const socom2_addresses::Table &a = socom2_addresses::forRevision("r0001");
            const uint32_t fields[] = {a.rtNetConfigInit, a.packTrace, a.cull, a.node, a.node2, a.lod,
                                       a.detail, a.camCfg, a.defer, a.flush, a.musicManager, a.cuePush,
                                       a.cameraHolder, a.versionString, a.oskOpen, a.oskOpenThunk,
                                       a.oskTextBuffer, a.chatFanoutRecv, a.chatListRender, a.chatListHolders,
                                       a.dnasCheck, a.ctorTableFtsBegin, a.ctorTableFtsEnd,
                                       a.ctorTableZsealBegin, a.ctorTableZsealEnd};
            for (uint32_t v : fields)
                t.IsTrue(v >= socom2_addresses::kOverlayBase, "0x" + std::to_string(v) + " is at or above the overlay base");
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
            t.IsTrue(socom2_addresses::revisionOf("SOCOM 2 r0004 09:11:02 Feb 20 2004") == "r0004", "an r0004 stamp");
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
