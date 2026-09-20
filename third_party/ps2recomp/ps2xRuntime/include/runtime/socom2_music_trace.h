#pragma once
// research/36 item 8 (2026-09-20): the EE's music manager, traced. PS2X_SOCOM2_MUSIC_TRACE=1 replaces two guest
// functions with logging thunks (game_overrides_socom2.cpp, installMusicTrace): FUN_0034afd0, the per-frame music
// manager (state byte at manager+9: 4 reset, 3 idle, 1 playing, 0 extension-started, 2 extension pending; its cue
// entry at +0x34), and FUN_0034b6c0, the cue push (game/analysis/socom2_game.elf.decomp.c:246909-246947).
//
// The push's decision, reproduced here so a test can pin it and the trace can name the reason a cue was or was not
// queued. From the decompilation:
//
//     if (mgr+0x28 == 0)                                   return 0;   // no free entry
//     else if (mgr+0xb != 0 || (def+0x1d >> 5) == 3 || (def+0x1c & 0x40)) {
//         idx = free list's last; if (idx == -1) return 0; queue it; return 1; }
//     else                                                 return 1;   // NOT queued -- but reported as accepted
//
// so a music cue whose sound-def has type != 3, +0x1c bit 6 clear, while the manager's +0xb flag is 0, is dropped
// silently with a 1. The runtime cannot see the free list's head, so "queued" versus "free list head -1" is told
// apart by the queue count (mgr+0x1c) before and after.
#include <cstdint>

namespace socom2_music
{
    struct PushVerdict
    {
        const char *label;      // "queued", "refused", "dropped"
        const char *reason;
    };

    inline PushVerdict pushVerdict(uint32_t freeCount, uint8_t mgrFlagB, uint8_t defFlags1c, uint8_t defFlags1d,
                                   uint32_t returned, uint32_t queueBefore, uint32_t queueAfter)
    {
        if (freeCount == 0u)
            return {"refused", "no free entry (mgr+0x28 == 0)"};
        const unsigned type = defFlags1d >> 5;
        const bool forced = mgrFlagB != 0u || type == 3u || (defFlags1c & 0x40u) != 0u;
        if (!forced)
            return {"dropped", "not a queued cue: mgr+0xb == 0, type != 3, def+0x1c bit 6 clear (returns 1 without queueing)"};
        if (returned == 0u)
            return {"refused", "free list head was -1"};
        if (queueAfter > queueBefore)
            return {"queued", "queue count grew"};
        return {"queued", "returned 1 (queue count unchanged: popped in the same frame?)"};
    }
}
