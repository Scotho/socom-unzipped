// socom2_server_records.h -- Sprint 13 Task U6: two server-to-client records refused on the client.
//
// The game's network library accepts, from whatever server it is connected to, a record that writes game
// memory and a record that reads game memory back to the server. The project's server sends neither. Both
// are refused here, every time, on every revision, with no knob -- the chat receive bound's shape
// (game_overrides_socom2.cpp, installChatBound), with one difference: nothing of the original runs at all.
// The refusal is the whole replacement, so it happens BEFORE the original would have run, never after (a
// wrap's code after the original's call runs at the scheduler's unwind, not at the return; docs/KNOWN.md).
//
// Each refusal answers the library's own "handled", so the CLIENT keeps the connection up. That is not
// the whole story for the read record: it is a query the original answers with a reply, and the refusal
// sends none. A server that waits for that reply may time the client out or drop it -- most likely a
// community server; the project's server never sends the query. Nothing further about either record is
// written up here (SECURITY.md).
//
// Every entry the function table holds for a handler's body is replaced, not only its first address: the
// recompiler also registers the body at the points inside it where a call returns, and those entries
// would otherwise still lead into the original.
//
// The functions are here rather than in game_overrides_socom2.cpp so that ps2xTest can install them
// through the same function-table registry the runner uses and drive them the way the dispatcher does.
#pragma once
#include "ps2_runtime.h"
#include "runtime/socom2_addresses.h"

#include <atomic>
#include <cstdint>
#include <iostream>

namespace socom2_server_records
{
    // What the library's receive handlers return for a record they took. The dispatcher treats it as
    // success, so a refused record is dropped without the client dropping the connection it arrived on.
    constexpr uint32_t kHandled = 0u;

    // How far past a handler's first address the install looks for more entries of the same body. The
    // walk stops earlier, at the first entry that belongs to another function; this only bounds it.
    // (The largest of the four handler bodies is 2124 bytes.)
    constexpr uint32_t kBodyScanBytes = 0x1000u;

    namespace detail
    {
        // Written from whatever guest thread runs the library's receive path; only the log and the
        // suite read them.
        inline std::atomic<uint32_t> &writes()
        {
            static std::atomic<uint32_t> n{0};
            return n;
        }
        inline std::atomic<uint32_t> &reads()
        {
            static std::atomic<uint32_t> n{0};
            return n;
        }

        // The suite's hook: the counters are process-wide, and "the first refusal says so" is only
        // provable from a known start.
        inline void resetCountsForTest()
        {
            writes().store(0);
            reads().store(0);
        }

        // The first refusal of each kind says so, once, with no address; every later one is only
        // counted -- a server sending these in a loop must not turn the log into this line.
        inline void refuse(R5900Context *ctx, std::atomic<uint32_t> &count, const char *what)
        {
            // The count stops at the top rather than coming round to 0, which would say "first" again.
            uint32_t prev = count.load();
            while (prev != UINT32_MAX && !count.compare_exchange_weak(prev, prev + 1))
            {
            }
            if (prev == 0)
                std::cout << "[socom2] server memory " << what << " refused (first one; every one is)" << std::endl;
            setReturnU32(ctx, kHandled);
            ctx->pc = getRegU32(ctx, 31);
        }
    }

    inline uint32_t writesRefused() { return detail::writes().load(); }
    inline uint32_t readsRefused() { return detail::reads().load(); }

    // The replacements. Neither calls the original; neither reads the record.
    inline void refuseWrite(uint8_t *, R5900Context *ctx, PS2Runtime *) { detail::refuse(ctx, detail::writes(), "write"); }
    inline void refuseRead(uint8_t *, R5900Context *ctx, PS2Runtime *) { detail::refuse(ctx, detail::reads(), "read"); }

    // Replace every entry of the body that starts at `entry`: the entry itself, then each later address
    // (up to kBodyScanBytes) whose entry is the same function, stopping at the first entry that is some
    // other function. Returns how many entries were replaced past the first, or -1 when the first could
    // not be replaced.
    inline int replaceBody(PS2Runtime &runtime, uint32_t entry, PS2Runtime::RecompiledFunction fn)
    {
        const PS2Runtime::RecompiledFunction original = runtime.lookupFunction(entry);
        if (!runtime.replaceFunction(entry, fn))
            return -1;
        int extra = 0;
        for (uint32_t pc = entry + 4; pc < entry + kBodyScanBytes; pc += 4)
        {
            if (!runtime.hasFunction(pc))
                continue;
            if (runtime.lookupFunction(pc) != original)
                break;                                   // the next function starts here
            if (runtime.replaceFunction(pc, fn))
                ++extra;
        }
        return extra;
    }

    // Install both on the column's addresses. Independent, like the chat bound's two wraps: one missing
    // from the loaded image must not take the other with it. Returns how many were installed.
    inline int install(PS2Runtime &runtime, const socom2_addresses::Table &addr)
    {
        struct Bound { uint32_t address; const char *field; PS2Runtime::RecompiledFunction fn; const char *what; };
        const Bound bounds[] = {
            {addr.serverMemWrite, "serverMemWrite", refuseWrite, "write"},
            {addr.serverMemRead, "serverMemRead", refuseRead, "read"},
        };
        int installed = 0;
        for (const Bound &b : bounds)
        {
            if (!socom2_addresses::require(b.address, b.field))
                continue;
            if (!runtime.hasFunction(b.address))
            {
                std::cout << "[socom2] no function for " << b.field << "; server memory " << b.what
                          << " not refused" << std::endl;
                continue;
            }
            const int extra = replaceBody(runtime, b.address, b.fn);
            if (extra < 0)
            {
                std::cout << "[socom2] " << b.field << " could not be replaced; server memory " << b.what
                          << " not installed" << std::endl;
                continue;
            }
            ++installed;
            std::cout << "[socom2] server memory " << b.what << " refused (every record, no knob; "
                      << extra << " more entries of the body)" << std::endl;
        }
        return installed;
    }
}
