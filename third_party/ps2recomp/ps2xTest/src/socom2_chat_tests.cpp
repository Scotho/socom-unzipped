// Sprint 11 milestone S (r0004 spec Goal A): the chat receive path's two fixed-width fields, terminated before
// the game reads them. The runtime override wraps the receive callback (game_overrides_socom2.cpp,
// installChatBound); everything it decides on the packet's bytes is decided in socom2_chat.h, on plain values,
// so the suite can prove it without the game.
#include "MiniTest.h"
#include "runtime/socom2_chat.h"

#include <cstring>
#include <vector>

void register_socom2_chat_tests()
{
    MiniTest::Case("Socom2Chat", [](TestCase &tc)
    {
        tc.Run("fields filled to their declared width with no NUL are terminated in place", [](TestCase &t)
        {
            // One byte past the packet, so "nothing past the message is touched" has a guard byte to read.
            std::vector<uint8_t> pkt(socom2_chat::kPacketBytes + 1, 0xAA);
            std::memset(&pkt[socom2_chat::kNameOff], 'N', socom2_chat::kNameLen);
            std::memset(&pkt[socom2_chat::kMessageOff], 'M', socom2_chat::kMessageLen);
            t.Equals(socom2_chat::terminateFields(pkt.data()), 2, "both fields changed");
            t.Equals(pkt[socom2_chat::kNameOff + socom2_chat::kNameLen - 1], uint8_t(0), "name terminated at byte 31");
            t.Equals(pkt[socom2_chat::kMessageOff + socom2_chat::kMessageLen - 1], uint8_t(0), "message terminated at byte 63");
            t.Equals(std::strlen(reinterpret_cast<const char *>(&pkt[socom2_chat::kNameOff])), size_t(31), "name reads 31 chars");
            t.Equals(std::strlen(reinterpret_cast<const char *>(&pkt[socom2_chat::kMessageOff])), size_t(63), "message reads 63 chars");
            t.Equals(pkt[socom2_chat::kTypeOff], uint8_t(0xAA), "the type word between them is untouched");
            t.Equals(pkt[socom2_chat::kMessageOff + socom2_chat::kMessageLen], uint8_t(0xAA), "nothing past the message is touched");
        });
        tc.Run("fields already terminated within their width are left byte-for-byte alone", [](TestCase &t)
        {
            std::vector<uint8_t> pkt(socom2_chat::kPacketBytes, 0);
            std::memcpy(&pkt[socom2_chat::kNameOff], "socomc", 7);
            std::memcpy(&pkt[socom2_chat::kMessageOff], "gg", 3);
            std::vector<uint8_t> before = pkt;
            t.Equals(socom2_chat::terminateFields(pkt.data()), 0, "nothing changed");
            t.IsTrue(pkt == before, "packet identical");
        });
        // The two fields are decided independently: one already good must not make the other be skipped, and must
        // not itself be rewritten because the other was.
        tc.Run("a terminated name beside an unterminated message changes the message only", [](TestCase &t)
        {
            std::vector<uint8_t> pkt(socom2_chat::kPacketBytes, 0xAA);
            std::memset(&pkt[socom2_chat::kNameOff], 'N', socom2_chat::kNameLen);
            pkt[socom2_chat::kNameOff + socom2_chat::kNameLen - 1] = 0;   // already terminated, at its last byte
            std::memset(&pkt[socom2_chat::kMessageOff], 'M', socom2_chat::kMessageLen);
            std::vector<uint8_t> before = pkt;
            t.Equals(socom2_chat::terminateFields(pkt.data()), 1, "one field changed");
            t.IsTrue(std::memcmp(&pkt[socom2_chat::kNameOff], &before[socom2_chat::kNameOff], socom2_chat::kNameLen) == 0,
                     "the name is byte-for-byte what it was");
            t.Equals(pkt[socom2_chat::kMessageOff + socom2_chat::kMessageLen - 1], uint8_t(0), "message terminated at byte 63");
            t.Equals(std::strlen(reinterpret_cast<const char *>(&pkt[socom2_chat::kMessageOff])), size_t(63), "message reads 63 chars");
            t.Equals(pkt[socom2_chat::kTypeOff], uint8_t(0xAA), "the type word between them is untouched");
        });
        tc.Run("a 32-char name and a 64-char message each lose exactly their last byte", [](TestCase &t)
        {
            std::vector<uint8_t> pkt(socom2_chat::kPacketBytes, 0);
            std::memset(&pkt[socom2_chat::kNameOff], 'x', 32);
            std::memset(&pkt[socom2_chat::kMessageOff], 'y', 64);
            socom2_chat::terminateFields(pkt.data());
            t.Equals(std::strlen(reinterpret_cast<const char *>(&pkt[socom2_chat::kNameOff])), size_t(31), "31 x");
            t.Equals(std::strlen(reinterpret_cast<const char *>(&pkt[socom2_chat::kMessageOff])), size_t(63), "63 y");
        });
    });
}
