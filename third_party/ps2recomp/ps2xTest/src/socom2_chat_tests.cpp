// Sprint 11 milestone S (r0004 spec Goal A): the chat path's two fixed-width fields, terminated before the game
// reads them. The runtime override wraps the receive callback and, since Task 2b, the second reader that walks a
// run of the same records (game_overrides_socom2.cpp, installChatBound); everything either wrap decides on the
// bytes is decided in socom2_chat.h, on plain values, so the suite can prove it without the game.
#include "MiniTest.h"
#include "ps2_runtime.h"
#include "runtime/ps2_memory.h"
#include "runtime/socom2_addresses.h"
#include "runtime/socom2_chat.h"
#include "runtime/socom2_server_records.h"

#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

// Sprint 13 Task U6: the same hardening's second shape. Two records the game's network library takes from
// whatever server it is connected to are refused before the library's own handler would run
// (runtime/socom2_server_records.h). The game's handlers are not in this binary, so each case registers a
// stand-in that does what the real one does with the record, installs the refusal through the same
// function-table registry the runner uses, and calls the entry the way the library's dispatcher would.
namespace
{
    constexpr uint32_t kRecordAt = 0x00100000u;   // where the synthetic record sits in guest memory
    constexpr uint32_t kTargetAt = 0x00200000u;   // the guest address the record names
    constexpr uint32_t kScratchAt = 0x00300000u;  // a second target, for proving the stand-in itself
    constexpr uint32_t kReturnTo = 0x00123450u;   // $ra: where a handler that returned leaves the pc
    constexpr uint32_t kPayload = 16u;            // the N bytes the record carries
    // What the stand-ins return. The real handlers return kHandled; the stand-ins return something else so
    // that "v0 is kHandled" after a call can only mean the refusal ran, not the stand-in.
    constexpr uint32_t kStandInReturn = 0x00005EEDu;

    void wr32(std::vector<uint8_t> &ram, uint32_t at, uint32_t v) { std::memcpy(&ram[at], &v, 4); }

    // A synthetic record of that kind, passed in the registers the dispatcher uses.
    void buildRecord(std::vector<uint8_t> &ram, R5900Context &ctx, uint32_t target)
    {
        wr32(ram, kRecordAt, target);
        wr32(ram, kRecordAt + 4, kPayload);
        std::memset(&ram[kRecordAt + 8], 0xCC, kPayload);
        std::memset(&ctx, 0, sizeof(ctx));
        setReturnU32(&ctx, 0xFFFFFFFFu);   // a value no handler returns, so "v0 was set" is observable
        ctx.r[7] = _mm_set_epi64x(0, kRecordAt);
        ctx.r[8] = _mm_set_epi64x(0, 8 + kPayload);
        ctx.r[31] = _mm_set_epi64x(0, kReturnTo);
    }

    // The stand-in for the write handler: what the real one does with the record, then a return.
    void standInWrite(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t rec = getRegU32(ctx, 7) & PS2_RAM_MASK;
        const uint32_t len = getRegU32(ctx, 8);
        uint32_t target, declared;
        std::memcpy(&target, rdram + rec, 4);
        std::memcpy(&declared, rdram + rec + 4, 4);
        if (rec != 0 && len > 8 && declared == len - 8)
            std::memcpy(rdram + (target & PS2_RAM_MASK), rdram + rec + 8, declared);
        setReturnU32(ctx, kStandInReturn);
        ctx->pc = getRegU32(ctx, 31);
    }

    // The stand-in for the read-back handler: whether it ran at all is the whole question.
    bool g_readStandInRan = false;
    void standInRead(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        g_readStandInRan = true;
        setReturnU32(ctx, kStandInReturn);
        ctx->pc = getRegU32(ctx, 31);
    }

    // Whatever function follows a handler in the table: its entries must survive the install.
    void standInNext(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        setReturnU32(ctx, kStandInReturn);
        ctx->pc = getRegU32(ctx, 31);
    }

    template <typename Body>
    std::string captureOut(Body body)
    {
        std::ostringstream sink;
        std::streambuf *old = std::cout.rdbuf(sink.rdbuf());
        body();
        std::cout.rdbuf(old);
        return sink.str();
    }
}

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
        // One call's work is budgeted across everything it walks, so no single call can be talked into an
        // unbounded amount of it by the counts it reads.
        tc.Run("a budget spent across a call cuts every walk once it runs out", [](TestCase &t)
        {
            const uint32_t cap = socom2_chat::kMaxRecords;
            t.Equals(socom2_chat::walkWithin(10, cap, 4), 4u, "the budget is tighter than the cap");
            t.Equals(socom2_chat::walkWithin(10, 6, 100), 6u, "the cap is tighter than the budget");
            t.Equals(socom2_chat::walkWithin(3, cap, 100), 3u, "neither binds: the whole count walks");
            t.Equals(socom2_chat::walkWithin(10, cap, 0), 0u, "a spent budget walks nothing more");
            t.Equals(socom2_chat::walkWithin(0, cap, 100), 0u, "nothing to walk stays nothing");
            t.IsTrue(socom2_chat::kRecordsPerCall > 999u, "the budget is past the largest list the game asks for");
            t.IsTrue(socom2_chat::kRecordsPerCall < socom2_chat::kMaxRecords * socom2_chat::kMaxHolders,
                     "the budget really does bound the work a call can be given");
            // The whole list, every holder at the cap: one call still costs exactly the budget (review, round 2).
            uint32_t budget = socom2_chat::kRecordsPerCall, total = 0;
            for (uint32_t h = 0; h < socom2_chat::kMaxHolders; ++h)
            {
                const uint32_t w = socom2_chat::walkWithin(socom2_chat::kMaxRecords, socom2_chat::kMaxRecords, budget);
                budget -= w; total += w;
            }
            t.Equals(total, socom2_chat::kRecordsPerCall, "a list claiming every holder at the cap costs one call the budget, no more");
        });
        tc.Run("a run far past the budget bounds the budget's worth and touches nothing beyond it", [](TestCase &t)
        {
            const uint32_t budget = 2, count = 5;
            std::vector<uint8_t> run(socom2_chat::kRecordBytes * count, 0xAA);
            for (uint32_t i = 0; i < count; ++i)
            {
                uint8_t *rec = &run[i * socom2_chat::kRecordBytes];
                std::memset(rec + socom2_chat::kNameOff, 'N', socom2_chat::kNameLen);
                std::memset(rec + socom2_chat::kMessageOff, 'M', socom2_chat::kMessageLen);
            }
            std::vector<uint8_t> before = run;
            const uint32_t walk = socom2_chat::walkWithin(count, socom2_chat::kMaxRecords, budget);
            t.Equals(walk, budget, "the budget decides the walk");
            t.Equals(socom2_chat::terminateRecords(run.data(), walk), 4, "two fields in each of the two records");
            t.IsTrue(std::memcmp(&run[budget * socom2_chat::kRecordBytes], &before[budget * socom2_chat::kRecordBytes],
                                 socom2_chat::kRecordBytes * (count - budget)) == 0,
                     "every record past the budget is byte-for-byte what it was");
        });
        // The counter that says how much a call declined must not be able to read low by overflowing.
        tc.Run("the declined count saturates instead of wrapping", [](TestCase &t)
        {
            t.Equals(socom2_chat::satAdd(2, 3), 5u, "an ordinary sum");
            t.Equals(socom2_chat::satAdd(0, 0), 0u, "nothing plus nothing");
            t.Equals(socom2_chat::satAdd(0xFFFFFFFFu, 1), 0xFFFFFFFFu, "the top plus one stays at the top");
            t.Equals(socom2_chat::satAdd(0xFFFFFFF0u, 0x20u), 0xFFFFFFFFu, "a sum that would wrap saturates");
            t.Equals(socom2_chat::satAdd(0xFFFFFFFFu, 0xFFFFFFFFu), 0xFFFFFFFFu, "the top plus the top");
            t.Equals(socom2_chat::satAdd(1, 0xFFFFFFFEu), 0xFFFFFFFFu, "the last sum that still fits");
        });
        // An empty list is not a refusal: there is nothing to walk, so there is nothing to decline and
        // nothing to say about it. A list with entries that does not fit in memory IS a refusal.
        tc.Run("an empty list is a quiet return, not a refusal", [](TestCase &t)
        {
            const uint32_t ram = 32u * 1024u * 1024u;
            const uint32_t stride = socom2_chat::kRecordBytes;
            t.IsFalse(socom2_chat::declines(0, 0, stride, ram), "no entries and no base at all");
            t.IsFalse(socom2_chat::declines(0, 0x100000u, stride, ram), "no entries at a real base");
            t.IsFalse(socom2_chat::declines(4, 0x100000u, stride, ram), "entries that fit");
            t.IsTrue(socom2_chat::declines(4, 0, stride, ram), "entries with no base");
            t.IsTrue(socom2_chat::declines(4, ram - stride, stride, ram), "entries that run past the end");
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

    MiniTest::Case("Socom2ServerRecords", [](TestCase &tc)
    {
        // The library's success code. Both handlers set their return to 0 on the paths this task closes:
        // the write handler (r0001 FUN_00637900, game/analysis/socom2_game.elf.decomp.c:548278-548308)
        // ends `return uVar1;` with uVar1 == 0 on the copy path, and the read handler (r0001 FUN_00637510,
        // decomp.c:548117-548275) ends `return 0;`. The refusal returns that value so the dispatcher sees a
        // handled record; the stand-ins return kStandInReturn instead, so "v0 == kHandled" is decisive.
        tc.Run("kHandled is the handlers' own success value, 0", [](TestCase &t)
        {
            t.Equals(socom2_server_records::kHandled, 0u, "both decompiled handlers return 0 on success");
            t.IsTrue(kStandInReturn != socom2_server_records::kHandled,
                     "the stand-ins return something else, so the refusal is distinguishable from them");
        });

        tc.Run("a record that writes memory leaves the bytes where they were, on both revisions", [](TestCase &t)
        {
            for (const socom2_addresses::Table *tab : socom2_addresses::kTables)
            {
                const std::string rev = tab->revision;
                std::vector<uint8_t> ram(PS2_RAM_SIZE, 0);
                R5900Context ctx;
                PS2Runtime runtime;
                runtime.registerFunction(tab->serverMemWrite, standInWrite);

                // The stand-in is not vacuous: called directly, it lands the record's bytes AND returns
                // its own code, not kHandled -- so the assertions below cannot pass by accident.
                std::memset(&ram[kScratchAt], 0x5A, kPayload);
                buildRecord(ram, ctx, kScratchAt);
                standInWrite(ram.data(), &ctx, &runtime);
                t.Equals(ram[kScratchAt], uint8_t(0xCC), rev + ": the stand-in writes when it runs");
                t.Equals(getRegU32(&ctx, 2), kStandInReturn, rev + ": and returns its own code, not kHandled");

                std::memset(&ram[kTargetAt], 0x5A, kPayload);
                const std::vector<uint8_t> before(ram.begin() + kTargetAt, ram.begin() + kTargetAt + kPayload);
                socom2_server_records::install(runtime, *tab);
                buildRecord(ram, ctx, kTargetAt);
                runtime.lookupFunction(tab->serverMemWrite)(ram.data(), &ctx, &runtime);
                const std::vector<uint8_t> after(ram.begin() + kTargetAt, ram.begin() + kTargetAt + kPayload);
                t.IsTrue(after == before, rev + ": the N bytes at the named address are unchanged");
                t.Equals(getRegU32(&ctx, 2), socom2_server_records::kHandled,
                         rev + ": v0 is the library's success value, not the stand-in's code -- the refusal ran");
                t.Equals(ctx.pc, kReturnTo, rev + ": the call returns to its caller, the client keeps the connection");
                runtime.registerFunction(tab->serverMemWrite, nullptr);
            }
        });

        tc.Run("a record that reads memory back never reaches the handler, on both revisions", [](TestCase &t)
        {
            for (const socom2_addresses::Table *tab : socom2_addresses::kTables)
            {
                const std::string rev = tab->revision;
                std::vector<uint8_t> ram(PS2_RAM_SIZE, 0);
                R5900Context ctx;
                PS2Runtime runtime;
                runtime.registerFunction(tab->serverMemRead, standInRead);
                socom2_server_records::install(runtime, *tab);
                buildRecord(ram, ctx, kTargetAt);
                g_readStandInRan = false;
                runtime.lookupFunction(tab->serverMemRead)(ram.data(), &ctx, &runtime);
                t.IsFalse(g_readStandInRan, rev + ": the handler that would answer with guest memory never runs");
                t.Equals(getRegU32(&ctx, 2), socom2_server_records::kHandled,
                         rev + ": v0 is the success value, not the stand-in's code -- the refusal ran");
                t.Equals(ctx.pc, kReturnTo, rev + ": the call returns to its caller");
                runtime.registerFunction(tab->serverMemRead, nullptr);
            }
        });

        // The recompiler registers a body's entry AND every mid-body point a call returns to. A refusal on
        // the entry alone leaves those pointing at the original, so a hostile server that redirects control
        // flow to a resume PC would re-enter the original body. The install replaces all of them.
        tc.Run("every entry of a handler's body becomes the refusal; the next function is untouched", [](TestCase &t)
        {
            // r0001's dense table registers FUN_00637900 at 0x637900, +0x38, +0x68, +0x74, +0x94 (five
            // entries), and the next function starts at 0x6379b0. Lay the same shape out relative to each
            // column's own address, so the scan's "stop at the next function" is exercised on both.
            const uint32_t writeResumes[] = {0x00u, 0x38u, 0x68u, 0x74u, 0x94u};
            const uint32_t readResumes[]  = {0x00u, 0x54u, 0x88u, 0x1a0u};   // several, as the read body has
            for (const socom2_addresses::Table *tab : socom2_addresses::kTables)
            {
                const std::string rev = tab->revision;
                PS2Runtime runtime;
                for (uint32_t off : writeResumes)
                    runtime.registerFunction(tab->serverMemWrite + off, standInWrite);
                const uint32_t writeNext = tab->serverMemWrite + 0xb0u;
                runtime.registerFunction(writeNext, standInNext);
                for (uint32_t off : readResumes)
                    runtime.registerFunction(tab->serverMemRead + off, standInRead);
                const uint32_t readNext = tab->serverMemRead + 0x200u;
                runtime.registerFunction(readNext, standInNext);

                socom2_server_records::install(runtime, *tab);

                for (uint32_t off : writeResumes)
                    t.IsTrue(runtime.lookupFunction(tab->serverMemWrite + off) == socom2_server_records::refuseWrite,
                             rev + ": the write body's resume point at +0x" + std::to_string(off) + " is the refusal");
                for (uint32_t off : readResumes)
                    t.IsTrue(runtime.lookupFunction(tab->serverMemRead + off) == socom2_server_records::refuseRead,
                             rev + ": the read body's resume point at +0x" + std::to_string(off) + " is the refusal");
                t.IsTrue(runtime.lookupFunction(writeNext) == standInNext, rev + ": the function after the write body is left alone");
                t.IsTrue(runtime.lookupFunction(readNext) == standInNext, rev + ": the function after the read body is left alone");

                for (uint32_t off : writeResumes)
                    runtime.registerFunction(tab->serverMemWrite + off, nullptr);
                for (uint32_t off : readResumes)
                    runtime.registerFunction(tab->serverMemRead + off, nullptr);
                runtime.registerFunction(writeNext, nullptr);
                runtime.registerFunction(readNext, nullptr);
            }
        });

        tc.Run("the first refusal is said once and counted, regardless of run order", [](TestCase &t)
        {
            const socom2_addresses::Table &tab = socom2_addresses::kR0001;
            std::vector<uint8_t> ram(PS2_RAM_SIZE, 0);
            R5900Context ctx;
            PS2Runtime runtime;
            runtime.registerFunction(tab.serverMemWrite, standInWrite);
            runtime.registerFunction(tab.serverMemRead, standInRead);
            const std::string installed = captureOut([&] { socom2_server_records::install(runtime, tab); });
            t.IsTrue(installed.find("[socom2] server memory write refused") != std::string::npos,
                     "the install says the write record is refused: " + installed);
            t.IsTrue(installed.find("[socom2] server memory read refused") != std::string::npos,
                     "the install says the read record is refused: " + installed);
            t.IsTrue(installed.find("0x") == std::string::npos, "the install lines carry no address: " + installed);

            // The counters are process-wide, so pin them to a known start rather than depend on run order.
            socom2_server_records::detail::resetCountsForTest();
            const std::string firstWrite = captureOut([&] {
                buildRecord(ram, ctx, kTargetAt);
                runtime.lookupFunction(tab.serverMemWrite)(ram.data(), &ctx, &runtime);
            });
            t.IsTrue(firstWrite.find("server memory write refused (first one") != std::string::npos,
                     "the first refused write says so: " + firstWrite);
            t.IsTrue(firstWrite.find("0x") == std::string::npos, "and carries no address: " + firstWrite);
            const std::string firstRead = captureOut([&] {
                buildRecord(ram, ctx, kTargetAt);
                runtime.lookupFunction(tab.serverMemRead)(ram.data(), &ctx, &runtime);
            });
            t.IsTrue(firstRead.find("server memory read refused (first one") != std::string::npos,
                     "the first refused read says so: " + firstRead);
            // Every later refusal is silent, but still counted.
            const std::string more = captureOut([&] {
                for (int i = 0; i < 2; ++i)
                {
                    buildRecord(ram, ctx, kTargetAt);
                    runtime.lookupFunction(tab.serverMemWrite)(ram.data(), &ctx, &runtime);
                    buildRecord(ram, ctx, kTargetAt);
                    runtime.lookupFunction(tab.serverMemRead)(ram.data(), &ctx, &runtime);
                }
            });
            t.IsTrue(more.empty(), "repeat refusals are silent: '" + more + "'");
            t.Equals(socom2_server_records::writesRefused(), 3u, "every refused write is counted from the reset");
            t.Equals(socom2_server_records::readsRefused(), 3u, "every refused read is counted from the reset");
            runtime.registerFunction(tab.serverMemWrite, nullptr);
            runtime.registerFunction(tab.serverMemRead, nullptr);
        });

        tc.Run("a revision with no function at the handler installs nothing there and says so", [](TestCase &t)
        {
            const socom2_addresses::Table &tab = socom2_addresses::kR0004;
            PS2Runtime runtime;   // nothing registered: an image without the library
            int n = -1;
            const std::string out = captureOut([&] { n = socom2_server_records::install(runtime, tab); });
            t.Equals(n, 0, "nothing installed");
            t.IsFalse(runtime.hasFunction(tab.serverMemWrite), "no entry was created where there was none");
            t.IsFalse(runtime.hasFunction(tab.serverMemRead), "... at either handler");
            t.IsTrue(out.find("not refused") != std::string::npos, "the log says the refusal is missing: " + out);
            t.IsTrue(out.find("0x") == std::string::npos, "and carries no address: " + out);
        });
    });
}
