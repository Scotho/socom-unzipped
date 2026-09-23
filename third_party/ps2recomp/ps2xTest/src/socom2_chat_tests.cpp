// Sprint 11 milestone S (r0004 spec Goal A): the chat path's two fixed-width fields, terminated before the game
// reads them. The runtime override wraps the receive callback and, since Task 2b, the second reader that walks a
// run of the same records (game_overrides_socom2.cpp, installChatBound); everything either wrap decides on the
// bytes is decided in socom2_chat.h, on plain values, so the suite can prove it without the game.
#include "MiniTest.h"
#include "runtime/socom2_chat.h"

#include <cstring>
#include <vector>

void register_socom2_chat_tests()
{
    MiniTest::Case("Socom2Chat", [](TestCase &tc)
    {
        tc.Run("fields filled to their declared width with no terminator are terminated in place", [](TestCase &t)
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

        // Sprint 11 Task 2b: the second reader walks a run of these records rather than being handed one.
        // Every record in the run gets exactly what the single one gets, and the run's end is respected.
        tc.Run("every record in a run gets the same guarantee as a single one", [](TestCase &t)
        {
            const uint32_t records = 3;
            // One record past the run, so "nothing past the run is touched" has a guard to read.
            std::vector<uint8_t> run(socom2_chat::kRecordBytes * (records + 1), 0xAA);
            for (uint32_t i = 0; i < records + 1; ++i)
            {
                uint8_t *rec = &run[i * socom2_chat::kRecordBytes];
                std::memset(rec + socom2_chat::kNameOff, 'N', socom2_chat::kNameLen);
                std::memset(rec + socom2_chat::kMessageOff, 'M', socom2_chat::kMessageLen);
            }
            std::vector<uint8_t> before = run;
            t.Equals(socom2_chat::terminateRecords(run.data(), records), 6, "two fields in each of three records");
            for (uint32_t i = 0; i < records; ++i)
            {
                const uint8_t *rec = &run[i * socom2_chat::kRecordBytes];
                t.Equals(std::strlen(reinterpret_cast<const char *>(rec + socom2_chat::kNameOff)), size_t(31), "name reads 31 chars");
                t.Equals(std::strlen(reinterpret_cast<const char *>(rec + socom2_chat::kMessageOff)), size_t(63), "message reads 63 chars");
                t.Equals(rec[socom2_chat::kTypeOff], uint8_t(0xAA), "the type word between them is untouched");
            }
            t.IsTrue(std::memcmp(&run[records * socom2_chat::kRecordBytes],
                                 &before[records * socom2_chat::kRecordBytes],
                                 socom2_chat::kRecordBytes) == 0,
                     "the record past the run is byte-for-byte what it was");
        });
        tc.Run("a run whose records are already terminated is left byte-for-byte alone", [](TestCase &t)
        {
            std::vector<uint8_t> run(socom2_chat::kRecordBytes * 4, 0);
            for (uint32_t i = 0; i < 4; ++i)
            {
                uint8_t *rec = &run[i * socom2_chat::kRecordBytes];
                std::memcpy(rec + socom2_chat::kNameOff, "socomc", 7);
                std::memcpy(rec + socom2_chat::kMessageOff, "gg", 3);
            }
            std::vector<uint8_t> before = run;
            t.Equals(socom2_chat::terminateRecords(run.data(), 4), 0, "nothing changed");
            t.IsTrue(run == before, "the run is identical");
        });
        tc.Run("an empty run touches nothing", [](TestCase &t)
        {
            std::vector<uint8_t> run(socom2_chat::kRecordBytes, 0xAA);
            std::vector<uint8_t> before = run;
            t.Equals(socom2_chat::terminateRecords(run.data(), 0), 0, "nothing changed");
            t.IsTrue(run == before, "the first record was not touched");
        });
        // A count read out of guest memory decides how MUCH is walked, never WHETHER anything is: the cap
        // cuts the walk, it does not call the walk off. The caps also sit past anything the game asks for.
        tc.Run("a holder count past its cap is cut to the cap, never to nothing", [](TestCase &t)
        {
            t.Equals(socom2_chat::walkCount(socom2_chat::kMaxHolders + 1, socom2_chat::kMaxHolders),
                     socom2_chat::kMaxHolders, "one past the cap walks the cap");
            t.Equals(socom2_chat::walkCount(socom2_chat::kMaxHolders, socom2_chat::kMaxHolders),
                     socom2_chat::kMaxHolders, "exactly the cap walks all of it");
            t.Equals(socom2_chat::walkCount(7, socom2_chat::kMaxHolders), 7u, "under the cap walks every one");
            t.Equals(socom2_chat::walkCount(0xFFFFFFFFu, socom2_chat::kMaxHolders), socom2_chat::kMaxHolders,
                     "the largest count there is still walks the cap");
            t.IsTrue(socom2_chat::kMaxHolders > 999u, "the cap is past the largest list the game asks for");
        });
        tc.Run("a record count past its cap bounds the records up to the cap, not zero of them", [](TestCase &t)
        {
            const uint32_t cap = 3, count = cap + 1;
            std::vector<uint8_t> run(socom2_chat::kRecordBytes * count, 0xAA);
            for (uint32_t i = 0; i < count; ++i)
            {
                uint8_t *rec = &run[i * socom2_chat::kRecordBytes];
                std::memset(rec + socom2_chat::kNameOff, 'N', socom2_chat::kNameLen);
                std::memset(rec + socom2_chat::kMessageOff, 'M', socom2_chat::kMessageLen);
            }
            std::vector<uint8_t> before = run;
            t.Equals(socom2_chat::terminateRecords(run.data(), socom2_chat::walkCount(count, cap)), 6,
                     "two fields in each of the three records the cap allows");
            for (uint32_t i = 0; i < cap; ++i)
            {
                const uint8_t *rec = &run[i * socom2_chat::kRecordBytes];
                t.Equals(std::strlen(reinterpret_cast<const char *>(rec + socom2_chat::kNameOff)), size_t(31), "name reads 31 chars");
                t.Equals(std::strlen(reinterpret_cast<const char *>(rec + socom2_chat::kMessageOff)), size_t(63), "message reads 63 chars");
            }
            t.IsTrue(std::memcmp(&run[cap * socom2_chat::kRecordBytes], &before[cap * socom2_chat::kRecordBytes],
                                 socom2_chat::kRecordBytes) == 0,
                     "the record past the cap is byte-for-byte what it was");
            t.IsTrue(socom2_chat::kMaxRecords > 999u, "the real cap is past the largest run the game asks for");
        });
        // A count and a base read out of guest memory are not trusted: the run is walked only when it is
        // whole and inside the machine's memory.
        tc.Run("a run is accepted only when it is whole and inside memory", [](TestCase &t)
        {
            const uint32_t ram = 32u * 1024u * 1024u;
            const uint32_t stride = socom2_chat::kRecordBytes;
            t.IsTrue(socom2_chat::spanFits(0x100000u, 4, stride, ram), "four records well inside memory");
            t.IsTrue(socom2_chat::spanFits(ram - stride, 1, stride, ram), "a run that ends on the last byte");
            t.IsFalse(socom2_chat::spanFits(ram - stride + 1, 1, stride, ram), "a run that ends one byte past it");
            t.IsFalse(socom2_chat::spanFits(0, 4, stride, ram), "a null base");
            t.IsFalse(socom2_chat::spanFits(0x100000u, 0xFFFFFFFFu, stride, ram), "a count whose span would wrap");
            t.IsFalse(socom2_chat::spanFits(0x100000u, 4, 0, ram), "a zero stride");
            t.IsTrue(socom2_chat::spanFits(0x100000u, 0, stride, ram), "an empty run at a real base");
        });
    });
}
