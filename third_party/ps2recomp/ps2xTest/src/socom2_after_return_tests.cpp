// Sprint 13 Task C3 (audit F10, F11): the after-return trap.
//
// A recompiled call can leave through an EE scheduler checkpoint: the C++ call chain unwinds, control comes back
// to a wrap at once with the guest thread parked inside the original, and the thread resumes there later without
// passing through the wrap again. So code a wrap places after the original runs too early: a write lands before
// the rest of the callee (and is overwritten, or skipped), a read sees a half-done call. The on-screen keyboard's
// wrap settled the rule (socom2_osk_prefill_tests.cpp): nothing a wrap needs is done after the original.
//
// The overrides file is linked into the runner, not into this binary (socom2_link_stubs.cpp says why), so these
// cases drive the pure halves the wraps are built from, the OSK suite's pattern: runtime/socom2_rtnet_config.h
// (the rt_net config init done on the host, the port written before the return) and
// runtime/socom2_trace_checkpoint.h (the point at which a trace's "after" values are final).
#include "MiniTest.h"
#include "runtime/socom2_rtnet_config.h"
#include "runtime/socom2_trace_checkpoint.h"

#include <cstdint>
#include <cstring>
#include <string>

namespace
{
    // Both pressings' routine, read out of game/overlays/socom2_game.elf at 0x00620648 and
    // game/overlays_r0004/socom2_game_r0004.elf at 0x00627f38 on 2026-09-25; they differ in word 9 only.
    constexpr uint32_t kR0001Body[socom2_rtnet::kBodyWords] = {
        0x27bdfff0u, 0x24020017u, 0xffb00000u, 0x0080802du, 0x1200000fu, 0xffbf0008u, 0x0000282du, 0x0c06566eu,
        0x2406001cu, 0x0c193d7eu, 0x00000000u, 0x24030001u, 0x24040e4au, 0xae030000u, 0xae04000cu, 0xae000018u,
        0xae000008u, 0xae000014u, 0xae020004u, 0x0000102du, 0xdfb00000u, 0xdfbf0008u, 0x03e00008u, 0x27bd0010u,
    };
    constexpr uint32_t kR0004GetterCall = 0x0c1936d8u;
    constexpr uint32_t kR0001Getter[3] = {0x3c020065u, 0x03e00008u, 0x8c426340u};   // at 0x0064f5f8
    constexpr uint32_t kR0004Getter[3] = {0x3c020065u, 0x03e00008u, 0x8c424e78u};   // at 0x0064db60

    uint32_t word(const uint8_t *p, uint32_t off)
    {
        uint32_t v = 0;
        std::memcpy(&v, p + off, 4);
        return v;
    }

    // A model of the recompiled routine as the scheduler sees it (recomp/output/rtNetConfigInit_0x620648.cpp):
    // two dispatches, `jal memset` at 0x620664 and `jal <getter>` at 0x62066c; the stores come after both. A
    // checkpoint is taken inside dispatchGuestBranch BEFORE the target runs, with ctx->pc already set to the
    // target, and the runtime's unwind flag set. So `unwindAt` 1 parks with pc = 0x001959b8 and the memset not
    // yet run; 2 parks with pc = 0x0064f5f8 after the memset; 0 runs whole and leaves pc = the entry ra.
    // finish() is the scheduler resuming the parked thread later, at that pc, without the wrap.
    struct GuestRoutine
    {
        uint8_t *object;
        uint32_t getterValue;
        int unwindAt;
        uint32_t entryRa;
        int parkedAt = 0;
        bool unwinding = false;   // PS2Runtime::dispatchUnwinding() as the wrap would read it

        uint32_t call()
        {
            if (unwindAt == 1)
                return park(1, 0x001959b8u);   // the memset's address: nothing written yet
            std::memset(object, 0, socom2_rtnet::kConfigBytes);
            if (unwindAt == 2)
                return park(2, 0x0064f5f8u);   // the getter's address: the object is the memset's zeros
            return stores();
        }

        uint32_t park(int at, uint32_t pc)
        {
            parkedAt = at;
            unwinding = true;
            return pc;
        }

        uint32_t finish()
        {
            unwinding = false;   // the scheduler clears it before the resuming dispatch
            if (parkedAt == 1)
                std::memset(object, 0, socom2_rtnet::kConfigBytes);
            parkedAt = 0;
            return stores();
        }

        uint32_t stores()
        {
            socom2_rtnet::configure(object, getterValue, socom2_rtnet::kBasePort);   // the stores, unshifted
            return entryRa;
        }
    };
}

void register_socom2_after_return_tests()
{
    MiniTest::Case("Socom2AfterReturn", [](TestCase &tc)
    {
        // The defect, pinned: the old wrap called the original and then rewrote +0xc only if it read 3658 there.
        // When the original unwinds at either of its dispatches, the wrap's "after" runs before the store at
        // 0x620680, reads something that is not 3658 (the heap's old bytes, or the memset's zero), declines, and
        // the resumed original stores 3658 -- the shift is lost without a line.
        tc.Run("a rewrite placed after an unwinding original loses the port shift, at either dispatch", [](TestCase &t)
        {
            for (int at = 1; at <= 2; ++at)
            {
                uint8_t obj[socom2_rtnet::kConfigBytes];
                std::memset(obj, 0xAA, sizeof(obj));
                GuestRoutine g{obj, 0x1234u, at, 0x00400000u};
                const uint32_t pc = g.call();
                t.Equals(pc, at == 1 ? 0x001959b8u : 0x0064f5f8u, "parked at the dispatch's target");
                // the old wrap's after-step
                if (word(obj, 0xC) == socom2_rtnet::kBasePort)
                {
                    const uint32_t shifted = socom2_rtnet::shiftedPort(2);
                    std::memcpy(obj + 0xC, &shifted, 4);
                }
                t.IsFalse(socom2_trace::reachedReturn(pc, g.entryRa, g.unwinding), "the call came back unwound");
                t.Equals(word(obj, 0xC), at == 1 ? 0xAAAAAAAAu : 0u, "the after-step saw a field not yet written and did nothing");
                g.finish();   // the scheduler resumes the parked original later, not through the wrap
                t.Equals(word(obj, 0xC), socom2_rtnet::kBasePort, "and the guest ends up with the unshifted 3658");
            }
        });

        // The fix: the override is the routine. Its whole effect on the object, with the shifted port, is done
        // inside the call -- configure() returns with the object final, so there is no after-step to lose.
        tc.Run("the rt_net config init writes the shifted port before it returns", [](TestCase &t)
        {
            uint8_t obj[socom2_rtnet::kConfigBytes];
            std::memset(obj, 0xAA, sizeof(obj));   // whatever the heap held
            socom2_rtnet::configure(obj, 0x00C0FFEEu, socom2_rtnet::shiftedPort(2));
            t.Equals(word(obj, 0x0), 1u, "+0x0 is 1");
            t.Equals(word(obj, 0x4), 0x00C0FFEEu, "+0x4 is the getter's word");
            t.Equals(word(obj, 0x8), 0u, "+0x8 is zero");
            t.Equals(word(obj, 0xC), 3660u, "+0xc is the SHIFTED base port, already, when the call returns");
            t.Equals(word(obj, 0x10), 0u, "+0x10 is the memset's zero");
            t.Equals(word(obj, 0x14), 0u, "+0x14 is zero");
            t.Equals(word(obj, 0x18), 0u, "+0x18 is zero");
            socom2_rtnet::configure(obj, 7u, socom2_rtnet::shiftedPort(0));
            t.Equals(word(obj, 0xC), socom2_rtnet::kBasePort, "shift 0 is the game's own 3658");
        });

        tc.Run("the routine is taken over only when the image's body is the one the host does", [](TestCase &t)
        {
            t.IsTrue(socom2_rtnet::bodyMatches(kR0001Body), "r0001's routine");
            uint32_t r0004[socom2_rtnet::kBodyWords];
            std::memcpy(r0004, kR0001Body, sizeof(r0004));
            r0004[socom2_rtnet::kGetterCallWord] = kR0004GetterCall;
            t.IsTrue(socom2_rtnet::bodyMatches(r0004), "r0004's, whose getter jal differs");
            uint32_t other[socom2_rtnet::kBodyWords];
            std::memcpy(other, kR0001Body, sizeof(other));
            other[12] = 0x24040e4cu;   // the pnach's 3660 already in the image: not the body we know
            t.IsFalse(socom2_rtnet::bodyMatches(other), "a patched store word is refused");
            std::memcpy(other, kR0001Body, sizeof(other));
            other[socom2_rtnet::kGetterCallWord] = 0x00000000u;
            t.IsFalse(socom2_rtnet::bodyMatches(other), "word 9 must still be a jal");
            t.IsFalse(socom2_rtnet::bodyMatches(nullptr), "no image, no takeover");
        });

        tc.Run("the getter and its global are decoded out of the image for both pressings", [](TestCase &t)
        {
            t.Equals(socom2_rtnet::jalTarget(kR0001Body[socom2_rtnet::kGetterCallWord], 0x00620648u + 0x24u), 0x0064f5f8u,
                     "r0001's jal reaches 0x0064f5f8");
            t.Equals(socom2_rtnet::jalTarget(kR0004GetterCall, 0x00627f38u + 0x24u), 0x0064db60u, "r0004's reaches 0x0064db60");
            uint32_t g = 0;
            t.IsTrue(socom2_rtnet::getterGlobal(kR0001Getter, g), "r0001's getter has the lui/jr/lw shape");
            t.Equals(g, 0x00656340u, "and reads 0x00656340");
            t.IsTrue(socom2_rtnet::getterGlobal(kR0004Getter, g), "r0004's too");
            t.Equals(g, 0x00654e78u, "and reads 0x00654e78");
            const uint32_t negative[3] = {0x3c020065u, 0x03e00008u, 0x8c42fff0u};
            t.IsTrue(socom2_rtnet::getterGlobal(negative, g), "a negative displacement");
            t.Equals(g, 0x0064fff0u, "is sign-extended as the lw does");
            const uint32_t notGetter[3] = {0x27bdfff0u, 0x03e00008u, 0x8c426340u};
            t.IsFalse(socom2_rtnet::getterGlobal(notGetter, g), "any other shape is refused");
        });

        // F11: the traces read their "after" values at the checkpoint, the original's own return.
        tc.Run("a trace's after-values are read only when the original reached its own return", [](TestCase &t)
        {
            uint8_t obj[socom2_rtnet::kConfigBytes] = {};
            GuestRoutine whole{obj, 5u, 0, 0x00401000u};
            const uint32_t pcWhole = whole.call();
            t.IsTrue(socom2_trace::reachedReturn(pcWhole, whole.entryRa, whole.unwinding), "a whole call: its effects are final, read them");
            t.Equals(word(obj, 0xC), socom2_rtnet::kBasePort, "and what is read is the call's result");

            std::memset(obj, 0, sizeof(obj));
            GuestRoutine parked{obj, 5u, 2, 0x00401000u};
            const uint32_t pcParked = parked.call();
            t.IsFalse(socom2_trace::reachedReturn(pcParked, parked.entryRa, parked.unwinding), "an unwound call: not at the checkpoint");
            t.Equals(word(obj, 0xC), 0u, "what an after-read would have logged here is not the call's result");
            parked.finish();
            t.Equals(word(obj, 0xC), socom2_rtnet::kBasePort, "the result exists only once the guest resumes the call");
            t.IsFalse(socom2_trace::reachedReturn(0u, 0x00401000u, false), "a pc of 0 is not the return either");
        });

        // The runtime's own case (ps2_runtime.h, markDispatchUnwind): a recursive callee that unwinds at the
        // dispatch of its own entry leaves pc equal to an address the pc test would accept. The unwind flag is
        // what tells them apart, so it is checked with the pc, never instead of it.
        tc.Run("a pc equal to the ra is not a return while the runtime is unwinding", [](TestCase &t)
        {
            t.IsFalse(socom2_trace::reachedReturn(0x00401000u, 0x00401000u, true), "pc == ra, unwind flag set: not final");
            t.IsTrue(socom2_trace::reachedReturn(0x00401000u, 0x00401000u, false), "pc == ra, flag clear: the return");
            t.IsFalse(socom2_trace::reachedReturn(0x00401004u, 0x00401000u, false), "flag clear but pc elsewhere: not the return");
        });

        tc.Run("an unwound call is counted, and said once", [](TestCase &t)
        {
            socom2_trace::UnwoundCount c;
            t.IsTrue(c.note(), "the first unwound call earns the line");
            t.IsFalse(c.note(), "the second does not");
            t.IsFalse(c.note(), "nor the third");
            t.Equals(c.n.load(), 3u, "but all three are counted");
            t.Equals(std::string(socom2_trace::kUnwoundMark), std::string("unwound"), "the mark a trace row carries instead of a result");
        });
    });
}
