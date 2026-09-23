// socom2_chat.h -- the chat path's hardening.
// Sprint 11 milestone S (r0004 spec Goal A). The fields are fixed-width; these helpers guarantee the terminator the
// game's readers assume. Task 2b adds the second reader, which is handed a run of the same records rather than one,
// so the same guarantee is given to each record in the run. The helpers are pure so the suite can prove them
// without the game.
#pragma once
#include <cstdint>

namespace socom2_chat
{
    constexpr uint32_t kFanoutRecvAddr = 0x002f4ef0u;   // the callback that receives a forwarded chat line
    constexpr uint32_t kNameOff = 0x1c, kNameLen = 32;   // originator name, fixed width
    constexpr uint32_t kTypeOff = 0x3c;                  // the chat type word the callback switches on
    constexpr uint32_t kMessageOff = 0x40, kMessageLen = 64;
    constexpr uint32_t kPacketBytes = 0x80;              // the span this helper may touch

    inline int terminateFields(uint8_t *pkt)
    {
        int changed = 0;
        auto fix = [&](uint32_t off, uint32_t len) {
            for (uint32_t i = 0; i < len; ++i)
                if (pkt[off + i] == 0) return;           // terminated within its width: leave it
            pkt[off + len - 1] = 0;
            ++changed;
        };
        fix(kNameOff, kNameLen);
        fix(kMessageOff, kMessageLen);
        return changed;
    }

    // Task 2b. The second reader is given a run of records, reached through a holder taken from a list of them.
    constexpr uint32_t kRecordBytes = kPacketBytes;       // the run's records are the layout above
    constexpr uint32_t kListCountOff = 0x8c, kListDataOff = 0x90;   // the run's length and its first record
    constexpr uint32_t kListHeaderBytes = kListDataOff + 4;         // what a holder must have for both to be read
    constexpr uint32_t kHolderCountOff = 0x04, kHolderDataOff = 0x08, kHolderPtrBytes = 4;
    // Ceilings on the work one call may do, sitting past anything the game asks for (its own largest request
    // is 999). They cut a walk; they never call one off -- see walkCount.
    constexpr uint32_t kMaxRecords = 4096;
    constexpr uint32_t kMaxHolders = 4096;
    // The ceilings bound each walk; this bounds all of them together, so what one call costs does not
    // multiply out with the counts it reads. Spent across the call and never carried: the next call starts
    // with the whole budget again.
    constexpr uint32_t kRecordsPerCall = 8192;

    // How much of a count is walked. A count read out of the machine's memory decides the amount of work,
    // never whether the work happens: past the ceiling the walk is cut to the ceiling, so a long list gets
    // the guarantee for as far as the ceiling reaches rather than losing it altogether.
    inline uint32_t walkCount(uint32_t count, uint32_t cap)
    {
        return count < cap ? count : cap;
    }

    // The same cut, against the ceiling AND what is left of the call's budget, whichever binds first.
    inline uint32_t walkWithin(uint32_t count, uint32_t cap, uint32_t budget)
    {
        return walkCount(count, budget < cap ? budget : cap);
    }

    // Counting what a call left alone: it stops at the top rather than coming round to a small number,
    // because a small number reads as "almost nothing was left alone", which would be the opposite of true.
    inline uint32_t satAdd(uint32_t a, uint32_t b)
    {
        return a > 0xFFFFFFFFu - b ? 0xFFFFFFFFu : a + b;
    }

    // Nothing read out of the machine's memory is trusted here: a run is walked only when it is whole and
    // inside that memory. This is the only refusal; the ceilings above merely cut. Pure, so the suite can
    // prove it without the game.
    inline bool spanFits(uint32_t base, uint32_t count, uint32_t stride, uint32_t ramBytes)
    {
        if (base == 0 || stride == 0)
            return false;
        if (count > ramBytes / stride)
            return false;                        // after this the multiply below cannot wrap
        return base <= ramBytes - count * stride;
    }

    // Whether a walk of `count` items at `base` is declined. Having nothing to walk is not a refusal --
    // an empty list is a quiet return, and an empty list has no base -- so only something to walk that
    // does not fit is one.
    inline bool declines(uint32_t count, uint32_t base, uint32_t stride, uint32_t ramBytes)
    {
        return count != 0 && !spanFits(base, count, stride, ramBytes);
    }

    // Every record in the run gets exactly what one gets, and nothing past the run is touched.
    inline int terminateRecords(uint8_t *records, uint32_t count)
    {
        int changed = 0;
        for (uint32_t i = 0; i < count; ++i)
            changed += terminateFields(records + i * kRecordBytes);
        return changed;
    }
}
