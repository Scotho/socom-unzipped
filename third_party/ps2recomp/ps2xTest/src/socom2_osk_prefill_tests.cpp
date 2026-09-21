// Sprint 10 Goal 9 (research/38): the on-screen keyboard's prefill -- the pure half of the runtime override that
// makes the login keyboards open already holding the launcher's persona name and password (R180: prefilled,
// never submitted). The override itself wraps FUN_0038d770 at runtime (game_overrides_socom2.cpp); everything it
// decides is decided here, on plain values, so the suite can say what the game will be handed without a launch.
#include "MiniTest.h"
#include "runtime/socom2_osk_prefill.h"

#include <cstring>
#include <string>

void register_socom2_osk_prefill_tests()
{
    MiniTest::Case("Socom2OskPrefill", [](TestCase &tc)
    {
        // The first two driven logins (2026-09-21, s10_g9_prefill_gate run1/run2) armed the prefill and filled
        // nothing: the UI action table dispatches through the thunk at 0x2808d0, whose recompiled body calls
        // FUN_0038d770 as a direct C++ call, so a wrap at the handler alone is never entered. The wrap must sit on
        // every entry the table can reach.
        tc.Run("the wrap is installed on the thunk the action table calls as well as on the handler", [](TestCase &t)
        {
            constexpr std::size_t n = sizeof(socom2_osk::kOskOpenEntries) / sizeof(socom2_osk::kOskOpenEntries[0]);
            t.Equals(n, static_cast<std::size_t>(2), "two entries: the thunk and the handler");
            t.Equals(socom2_osk::kOskOpenEntries[0], 0x002808D0u, "the thunk the action table points at (j func_38D770)");
            t.Equals(socom2_osk::kOskOpenEntries[1], socom2_osk::kOskOpenAddr, "the handler itself, for any direct dispatch");
        });

        tc.Run("the keyboard prefill picks the field's own variable, cut to the field's cap, or nothing", [](TestCase &t)
        {
            using socom2_osk::Field;
            t.Equals(socom2_osk::prefillFor(Field::PersonaName, "socomc", "socom", 16), std::string("socomc"), "the name field takes the name");
            t.Equals(socom2_osk::prefillFor(Field::Password, "socomc", "socom", 16), std::string("socom"), "the password field takes the password");
            t.Equals(socom2_osk::prefillFor(Field::PersonaName, nullptr, "socom", 16), std::string(), "no name variable: nothing is written");
            t.Equals(socom2_osk::prefillFor(Field::Password, "socomc", nullptr, 16), std::string(), "no password variable: nothing is written");
            t.Equals(socom2_osk::prefillFor(Field::PersonaName, "", "socom", 16), std::string(), "an empty variable is unset");
            t.Equals(socom2_osk::prefillFor(Field::PersonaName, "abcdefghijklmnopqrstuvwxyz", "", 16), std::string("abcdefghijklmnop"), "cut to the cap, never past the buffer");
            t.Equals(socom2_osk::prefillFor(Field::Other, "socomc", "socom", 16), std::string(), "any other keyboard (a game name, a clan tag) is left alone");
            t.Equals(socom2_osk::prefillFor(Field::PersonaName, "socomc", "socom", 0), std::string(), "a zero cap writes nothing");
        });

        // research/38: the two login keyboards are the same handler with different argument blocks; the Purpose
        // key (the script's message id) and the keyboard's name are what tell them apart. Every other
        // GetTextInput in the game -- the LAN name, a game password, chat -- must be left exactly as it is.
        tc.Run("the field is read off the GetTextInput arguments: purpose key and keyboard name", [](TestCase &t)
        {
            using socom2_osk::Field;
            t.IsTrue(socom2_osk::fieldFor("_455_EnterPlayerName_MSG", "CREATEPLAYERNAME") == Field::PersonaName, "the online persona name keyboard");
            t.IsTrue(socom2_osk::fieldFor("_604_EnterPassword_MSG", "CREATEPLAYERNAME") == Field::Password, "the online persona password keyboard");
            t.IsTrue(socom2_osk::fieldFor("_455_EnterPlayerName_MSG", "MPPLAYERNAME") == Field::Other, "the LAN name keyboard is a different variable: left alone");
            t.IsTrue(socom2_osk::fieldFor("_423_EnterPassword_MSG", "MPPLAYERNAME") == Field::Other, "a game's join password is not the persona's");
            t.IsTrue(socom2_osk::fieldFor("_306_EnterGamePassword_MSG", "MPPLAYERNAME") == Field::Other, "nor a created game's");
            t.IsTrue(socom2_osk::fieldFor("_361_EnterChatMessage_MSG", "PlayerChatSkb") == Field::Other, "chat");
            t.IsTrue(socom2_osk::fieldFor("", "") == Field::Other, "an empty block");
            t.IsTrue(socom2_osk::fieldFor(nullptr, nullptr) == Field::Other, "no block at all");
        });

        // The cap the override applies is the smaller of the live MaxChars and MaxBytes (both int32 in the
        // block; a script may leave one at 0 = unlimited) and the room in the initial-text buffer itself.
        tc.Run("the cap is the tightest of MaxChars, MaxBytes and the buffer's room", [](TestCase &t)
        {
            t.Equals(socom2_osk::capFor(14, 31, 0x48), static_cast<std::size_t>(14), "the name keyboard: MaxChars 14 binds");
            t.Equals(socom2_osk::capFor(12, 31, 0x48), static_cast<std::size_t>(12), "the password keyboard: MaxChars 12");
            t.Equals(socom2_osk::capFor(0, 31, 0x48), static_cast<std::size_t>(31), "MaxChars 0 means unlimited: MaxBytes binds");
            t.Equals(socom2_osk::capFor(0, 0, 0x48), static_cast<std::size_t>(0x47), "neither set: the buffer minus its terminator");
            t.Equals(socom2_osk::capFor(200, 200, 0x48), static_cast<std::size_t>(0x47), "never past the buffer");
            t.Equals(socom2_osk::capFor(-1, 31, 0x48), static_cast<std::size_t>(31), "a negative (garbage) count is ignored");
        });

        // The argument block itself, as FUN_00395f40 lays it out: the override reads these four fields and nothing else.
        tc.Run("the argument block's fields are read at research/38's offsets", [](TestCase &t)
        {
            std::string block(socom2_osk::kArgBlockBytes, '\0');
            std::memcpy(&block[socom2_osk::kArgPurposeOffset], "_604_EnterPassword_MSG", 23);
            std::memcpy(&block[socom2_osk::kArgSkbNameOffset], "CREATEPLAYERNAME", 17);
            const int32_t maxBytes = 31, maxChars = 12;
            std::memcpy(&block[socom2_osk::kArgMaxBytesOffset], &maxBytes, 4);
            std::memcpy(&block[socom2_osk::kArgMaxCharsOffset], &maxChars, 4);
            const socom2_osk::Request r = socom2_osk::readRequest(reinterpret_cast<const uint8_t *>(block.data()));
            t.Equals(r.purpose, std::string("_604_EnterPassword_MSG"), "the purpose key at +0x10");
            t.Equals(r.skbName, std::string("CREATEPLAYERNAME"), "the keyboard name at +0x58");
            t.Equals(r.maxBytes, 31, "MaxBytes at +0x98");
            t.Equals(r.maxChars, 12, "MaxChars at +0x9C");
            t.IsTrue(r.field == socom2_osk::Field::Password, "and the field follows");
            // An unterminated purpose (a corrupt block) is cut at the field's width, never read past it.
            std::string wild(socom2_osk::kArgBlockBytes, 'x');
            const socom2_osk::Request w = socom2_osk::readRequest(reinterpret_cast<const uint8_t *>(wild.data()));
            t.Equals(w.purpose.size(), static_cast<std::size_t>(socom2_osk::kArgPurposeBytes), "the purpose stops at its 0x40 bytes");
            t.Equals(w.skbName.size(), static_cast<std::size_t>(socom2_osk::kArgSkbNameBytes), "the name at its 0x20");
            t.IsTrue(w.field == socom2_osk::Field::Other, "and matches nothing");
        });
    });
}
