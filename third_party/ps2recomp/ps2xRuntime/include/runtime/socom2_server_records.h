// socom2_server_records.h -- Sprint 13 Task U6: two server-to-client records refused on the client.
//
// The game's network library accepts, from whatever server it is connected to, a record that writes game
// memory and a record that reads game memory back to the server. The project's server sends neither. Both
// are refused here, every time, on every revision, with no knob -- the chat receive bound's shape
// (game_overrides_socom2.cpp, installChatBound), with one difference: nothing of the original runs at all.
// The refusal is the whole replacement, so it happens BEFORE the original would have run, never after (a
// wrap's code after the original's call runs at the scheduler's unwind, not at the return; docs/KNOWN.md).
// Each refusal answers the library's own "handled", so the connection stays up. Nothing further about
// either record is written up here (SECURITY.md).
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
    // success, so a refused record is dropped without dropping the connection it arrived on.
    constexpr uint32_t kHandled = 0u;

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
            runtime.replaceFunction(b.address, b.fn);
            ++installed;
            std::cout << "[socom2] server memory " << b.what << " refused (every record, no knob)" << std::endl;
        }
        return installed;
    }
}
