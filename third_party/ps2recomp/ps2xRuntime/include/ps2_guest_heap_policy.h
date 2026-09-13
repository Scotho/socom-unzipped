#pragma once

// Allocation policy knobs for the runtime's guest heap (PS2Runtime::guestMalloc / guestCalloc /
// guestRealloc), kept out of ps2_runtime.h so that toggling them does not rebuild every
// translation unit that includes the runtime.
namespace ps2_guest_heap
{
    // PS2X_GUEST_MALLOC_ZERO=1 (default OFF): zero-fill every block PS2Runtime::guestMalloc hands
    // out, and the grown tail [old block size, new block size) of a PS2Runtime::guestRealloc that
    // grows in place or moves (the old prefix is preserved). guestCalloc zeroes regardless.
    //
    // Why: those allocators back the bound guest _malloc_r / _memalign_r / _realloc_r / malloc
    // (recomp/socom2.toml) and recycle freed blocks, so a field the game never initialises reads
    // whatever an earlier allocation left there (0xAF on our build) where the console's fresh
    // newlib heap reads 0x00 -- Sprint 5 Task 1's ghost flag CZNetGame+0xd2 is the case in point.
    // This is an allocator policy (what a fresh block contains), not a guest-memory patch.
    //
    // Read from the environment once and cached. Empty, "0", "false" and "off" mean off.
    bool zeroFillEnabled();

    // Tests only: 0 = force off, 1 = force on, -1 = drop the cached value so the next
    // zeroFillEnabled() re-reads the environment.
    void setZeroFillForTesting(int state);
}
