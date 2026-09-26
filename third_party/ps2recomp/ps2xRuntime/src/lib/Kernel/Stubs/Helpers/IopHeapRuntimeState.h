#pragma once
// Issue #51: the IOP heap cursor, moved out of Helpers/Support.h's anonymous namespace the way Sprint
// 11 Task 8b moved its four groups and CdRuntimeState.h moved the CD group: one NAMED struct, OWNED BY
// THE PS2Runtime the stub was called with -- a std::unique_ptr member reached as
// runtime->iopHeapRuntimeState() -- with one process-wide fallback for a stub reached with no runtime
// (ps2_stubs::iopHeapRuntimeStateFor(nullptr)).
//
// This group is g_iopHeapNext alone, the end of the last block sceSifAllocIopHeap /
// sceSifAllocSysMemory handed out, back at the heap base when the last block is freed or the heap is
// re-initialised. In the anonymous namespace every translation unit that includes Support.h compiled
// its own copy (docs/KNOWN.md section 1). Readers: Stubs/SIF.cpp is the only unit that touches it
// (Task 8b's reader scan) and it only ever WRITES it -- the allocator walks its own block map -- so
// the move is a no-op for the guest; what it buys is that no translation unit holds a private cursor
// and a second runtime cannot inherit the first one's. The block map and its storage
// (g_sifHeapAllocations, g_sifHeapStorage) are SIF.cpp's own, one translation unit, and stay there.

#include <cstdint>

class PS2Runtime;

namespace ps2_stubs
{
    // The EE-visible window the IOP heap stubs allocate in, and their block alignment.
    constexpr uint32_t kIopHeapBase = 0x04000000;
    constexpr uint32_t kIopHeapLimit = 0x04500000;
    constexpr uint32_t kIopHeapAlign = 64;

    struct IopHeapRuntimeState
    {
        // The end of the last block allocated (written under SIF.cpp's g_sifHeapMutex).
        uint32_t next = kIopHeapBase;

        // Back to a freshly constructed runtime's cursor. PS2Runtime::resetStubRuntimeState() calls it
        // (and run() calls that); the guest's sceSifInitIopHeap resets it through SIF.cpp.
        void reset()
        {
            next = kIopHeapBase;
        }
    };

    // The state `runtime` owns; a null runtime gets one process-wide fallback instance.
    IopHeapRuntimeState &iopHeapRuntimeStateFor(PS2Runtime *runtime);
}
