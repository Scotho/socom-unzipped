#pragma once

// Sprint 19 task B1 (research/89 Q6): PS2X_COVERAGE=<path> records which recompiled functions a run calls.
//
// One bit per slot of the dense function table (g_ps2RecompiledFunctionTable: one slot per guest word from
// g_ps2RecompiledFunctionTableBase), set the first time PS2Runtime::lookupFunction hands that slot's function out.
// Every dispatched call -- JAL, JALR, a scheduler resume -- takes that path. A resume pc inside a function (the
// `switch (ctx->pc)` entries of a generated body) has a slot of its own; the reader (tools_py/coverage_bitmap.py)
// folds those into their function, which it counts as reached by its entry or any of them.
//
// What a bit means, printed by the reader every time: a guest call reached this address through the function table.
// An overridden or stubbed address counts although its generated body did not run (the table hands out the
// override), and the scheduler's resume lookup marks a slot before its own checkpoint test, which may switch
// threads before the body runs (it runs later). A direct tail jump (`j`) to a known function is emitted as a C++ call and never passes the table, so a
// function reached ONLY that way reads as not reached.
//
// Cost: off, one load and one branch per lookup. On, one relaxed load per lookup and one relaxed OR the first
// time a slot is hit. The bitmap is written every 10 s (the gate kills the game, so exit is not reliable) and once
// more by flush() when the runner exits: main.cpp calls it before each std::_Exit (which runs no atexit hook), and
// an atexit hook calls it on the std::exit paths (the LoadExecPS2 reboot). flush() stops the periodic writer first.
//
// The dump (little-endian): "PS2XCOV1", u32 table base, u32 slot count, then (slot count + 7) / 8 bytes; slot s is
// bit (s & 7) of byte (s >> 3), LSB first.

#include <atomic>
#include <cstdint>
#include <string>
#include <vector>

namespace ps2_coverage
{
    namespace detail
    {
        // Non-null while recording. Set before the EE runs and cleared only by tests.
        extern std::atomic<uint8_t> *g_bits;
        extern uint32_t g_slotCount;

        inline void mark(std::atomic<uint8_t> *bits, uint32_t slot) noexcept
        {
            if (slot >= g_slotCount)
                return;
            std::atomic<uint8_t> &byte = bits[slot >> 3];
            const uint8_t bit = static_cast<uint8_t>(1u << (slot & 7u));
            if ((byte.load(std::memory_order_relaxed) & bit) == 0u)
                byte.fetch_or(bit, std::memory_order_relaxed);
        }
    }

    // The hook PS2Runtime::lookupFunction calls with the slot it resolved.
    inline void noteSlot(uint32_t slot) noexcept
    {
        if (std::atomic<uint8_t> *bits = detail::g_bits)
            detail::mark(bits, slot);
    }

    // Start recording over a table of slotCount slots from tableBase (clears any earlier bitmap). dumpPath is where
    // flush() writes; empty, flush() writes nothing.
    void enable(uint32_t tableBase, uint32_t slotCount, const std::string &dumpPath = {});
    // Stop recording, free the bitmap and forget the dump path (tests only: a run never frees the bitmap, so an EE
    // thread still marking during static destruction on the std::exit path never touches freed memory).
    void disable();
    bool enabled();

    bool hit(uint32_t slot);
    uint32_t hitCount();

    // The dump as described above; empty when not recording.
    std::vector<uint8_t> serialize();
    // Writes serialize() to path through a temporary file and a rename, so a reader never sees half a dump.
    bool writeDump(const std::string &path);
    // The final write: stops the periodic writer, writes the dump to the path given to enable() and prints the
    // "[coverage] exit:" line. False and a no-op when not recording or no path was given.
    bool flush();

    // Runner entry point: PS2X_COVERAGE=<path> (developer mode) enables recording over the given table, starts the
    // periodic writer and registers flush() with atexit for the std::exit paths. Once per process; later calls do
    // nothing.
    void installFromEnvironment(uint32_t tableBase, uint32_t slotCount);
}
