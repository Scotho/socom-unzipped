// Sprint 19 task E2: the shadow harness (PS2X_SHADOW, runtime/shadow_harness.h).
//
// Each case installs a fake "original" (written the way generated code is: WRITE32 macros, `jr ra` leaving
// pc = ra) and a fake override body at a function-table address, then calls the address the way a JAL does
// (ctx->pc = the target, the table's function called). This file is compiled with PS2X_SHADOW_WRITE_LOG=1
// (ps2xTest/CMakeLists.txt), as the generated code is in a shadow build, so its stores reach the write log.
//
// The bar (Sprint 19 plan, E2): a planted mismatch is caught under test; an original that exits with pc != ra --
// the eeCheckpointDue() back-edge return, which leaves pc on a loop's resume entry -- is detected and that call
// skipped, under test. Every original and body here is synthetic: no game function's body is in this file (R355).
#include "MiniTest.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/shadow_harness.h"
#include "runtime/ee_scheduler.h"   // EeDispatcherTransfer

#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#if !PS2X_SHADOW_WRITE_LOG
#error "shadow_harness_tests.cpp must be compiled with PS2X_SHADOW_WRITE_LOG=1"
#endif

namespace
{
    constexpr uint32_t kFn = 0x003c4b40u;       // the address the cases shadow (any function-table address)
    constexpr uint32_t kResume = 0x003c4b50u;   // a loop-head resume entry inside it
    constexpr uint32_t kRa = 0x0053ef04u;
    constexpr uint32_t kSp = 0x01f00000u;
    constexpr uint32_t kOut = 0x00200000u;

    int g_bodyRuns = 0;
    int g_callNo = 0;
    int g_wrongOnCall = -1;
    bool g_bodyWrongV0 = false;
    bool g_bodyWrongMem = false;
    bool g_bodyStrayWrite = false;
    bool g_bodyWrongV1High = false;
    bool g_bodyWrongF0 = false;
    bool g_bodyThrows = false;
    bool g_origThrows = false;
    int g_bodyClobber = 0;   // S4: which non-GPR register the body changes (0: none; see body())

    void setU32(R5900Context &ctx, int reg, uint32_t v) { SET_GPR_U32((&ctx), reg, v); }

    // The original: v0 = a0 + 1, v1 = a0 & 0xff, one store to *a1, a register save in its own frame below sp, f0 = 2.
    void original(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        WRITE32(ADD32(GPR_U32(ctx, 29), 0xfffffff0u), GPR_U32(ctx, 16));   // sw s0, -16(sp): dead after return
        WRITE32(GPR_U32(ctx, 5), 0x00001234u);
        SET_GPR_U32(ctx, 2, GPR_U32(ctx, 4) + 1u);
        SET_GPR_U64(ctx, 3, GPR_U64(ctx, 4) & 0xffu);
        ctx->f[0] = 2.0f;
        ctx->pc = GPR_U32(ctx, 31);
    }

    // The override body: the same result without the frame store, unless a case plants a difference.
    void body(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        ++g_bodyRuns;
        if (g_bodyThrows)
        {
            // A body that blocks: a store, then the scheduler's transfer, as WaitSema does when it parks a thread.
            WRITE32(GPR_U32(ctx, 5), 0x0000deadu);
            throw EeDispatcherTransfer{};
        }
        const bool wrongNow = g_wrongOnCall >= 0 && g_callNo == g_wrongOnCall;
        WRITE32(GPR_U32(ctx, 5), (g_bodyWrongMem || wrongNow) ? 0x00001235u : 0x00001234u);
        if (g_bodyStrayWrite)
            WRITE8(kOut + 0x40u, 0x77u);
        SET_GPR_U32(ctx, 2, GPR_U32(ctx, 4) + (g_bodyWrongV0 ? 2u : 1u));
        SET_GPR_U64(ctx, 3, GPR_U64(ctx, 4) & 0xffu);
        if (g_bodyWrongV1High)
        {
            alignas(16) uint64_t parts[2];
            std::memcpy(parts, &ctx->r[3], 16);
            parts[1] ^= 1u;
            std::memcpy(&ctx->r[3], parts, 16);
        }
        ctx->f[0] = g_bodyWrongF0 ? 3.0f : 2.0f;
        switch (g_bodyClobber)
        {
        case 1: ctx->f[20] = 9.0f; break;          // callee-saved FPR
        case 2: ctx->f[31] = -1.0f; break;
        case 3: ctx->f[2] = 0.5f; break;           // a temporary FPR: a transcribed body reproduces it too
        case 4: ctx->fcr31 ^= 0x00800000u; break;  // the FPU condition bit
        case 5: ctx->hi = 0x11u; break;
        case 6: ctx->lo = 0x22u; break;
        case 7: ctx->hi1 = 0x33u; break;
        case 8: ctx->lo1 = 0x44u; break;
        case 9: ctx->f_acc = 4.0f; break;
        case 10: ctx->sa = 8u; break;
        default: break;
        }
        ctx->pc = GPR_U32(ctx, 31);
    }

    // An original that takes the back-edge checkpoint: it has read the list head and stores a partial result, then
    // eeCheckpointDue() says yes -- the runtime is marked unwinding and the body returns with pc on the loop head.
    void originalCheckpoint(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        WRITE32(GPR_U32(ctx, 5), 0x0000beefu);
        SET_GPR_U32(ctx, 6, 0x00400000u);
        ctx->pc = kResume;
        runtime->markDispatchUnwind();
    }

    void originalIo(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        ps2_shadow::noteIoStore(0x1000f000u);   // what PS2Runtime::Store32 does for a hardware register
        original(rdram, ctx, runtime);
    }

    // An original that may block: on g_origThrows it stores, then the scheduler parks the thread by throwing
    // EeDispatcherTransfer (constructed as EeScheduler.cpp does), which only EeScheduler::run catches.
    void originalMayTransfer(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (g_origThrows)
        {
            WRITE32(GPR_U32(ctx, 5), 0x0000cafeu);
            throw EeDispatcherTransfer{};
        }
        original(rdram, ctx, runtime);
    }

    // Round 2, item 1: a loop function as generated code is, with an eeCheckpointDue() back edge, original and body
    // alike. The original passes its back edge (nothing due), computes the result, then something makes a checkpoint
    // due before the body runs: g_dueAfterOriginal 1 posts a scheduler event (a deadline arriving), 2 requests stop.
    int g_dueAfterOriginal = 0;
    void originalLoop(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (runtime->eeCheckpointDue())
        {
            ctx->pc = kResume;   // parks on its loop head, as generated code does
            return;
        }
        original(rdram, ctx, runtime);
        if (g_dueAfterOriginal == 1)
            runtime->eeScheduler().postEvent(EeEvent{});
        else if (g_dueAfterOriginal == 2)
            runtime->requestStop();
    }

    void bodyLoop(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (runtime->eeCheckpointDue())
        {
            ++g_bodyRuns;
            ctx->pc = kResume;
            return;
        }
        body(rdram, ctx, runtime);
    }

    // Round 2, item 6: while the original runs, another host thread (an IOP or DMA thread, say) looks at the write
    // log and makes a slow-path store. The log is this thread's: the other thread must not see it.
    bool g_ownThreadSawLog = false;
    bool g_otherThreadSawLog = true;
    void originalWithHelperThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        g_ownThreadSawLog = ps2_shadow::writeLogArmedForTest();
        std::thread([] {
            g_otherThreadSawLog = ps2_shadow::writeLogArmedForTest();
            ps2_shadow::noteIoStore(0x1000f000u);   // what PS2Runtime::Store32 does, on that thread
        }).join();
        original(rdram, ctx, runtime);
    }

    // An original that leaves with pc != ra and WITHOUT the runtime's unwind flag: only the pc clause of the skip
    // test sees it (a jump out of the function, or a resume pc the generated code set without unwinding).
    void originalExitsElsewhere(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        WRITE32(GPR_U32(ctx, 5), 0x0000beefu);
        ctx->pc = kResume;
    }

    // An original that stores to a GS privileged register through the generated code's own path: WRITE32 of a
    // special address goes to PS2Runtime::Store32, whose hook (ps2_runtime.cpp) marks the call as an I/O store.
    constexpr uint32_t kGsBgColor = 0x120000E0u;
    void originalMmio(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        WRITE32(kGsBgColor, 0x00102030u);
        original(rdram, ctx, runtime);
    }

    // ABI mode (a body derived from source): the original leaves its scratch registers as its instructions do (a0
    // advanced, t0 and a1 used, f1 a temporary); a derived body computes the same result through other registers.
    bool g_abiClobberS0 = false;
    bool g_abiMoveSp = false;
    bool g_abiWrongV0 = false;
    bool g_abiWrongF0 = false;
    bool g_abiWrongV1 = false;
    bool g_abiStaleV0High = false;
    bool g_abiWrongV1High = false;

    void originalAbi(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        SET_GPR_U32(ctx, 8, GPR_U32(ctx, 4) ^ 0x5au);              // t0: a temporary
        SET_GPR_U32(ctx, 4, GPR_U32(ctx, 4) + 4u);                // a0 advanced
        SET_GPR_U32(ctx, 5, 0x77u);                               // a1 reused
        WRITE32(kOut, 0x00004321u);
        SET_GPR_U32(ctx, 2, GPR_U32(ctx, 4) + 1u);                // v0 = a0 + 5
        SET_GPR_U32(ctx, 3, 0x99u);                               // v1: a temporary unless returned
        ctx->f[1] = 7.0f;                                         // f1: a temporary unless returned
        ctx->f[5] = 6.0f;                                         // f5: a temporary
        ctx->lo = 0x1234u;                                        // a mult's lo and hi: caller-saved
        ctx->hi = 0x5678u;
        ctx->f[0] = 2.0f;
        ctx->pc = GPR_U32(ctx, 31);
    }

    void bodyAbi(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        ++g_bodyRuns;
        WRITE32(kOut, 0x00004321u);
        SET_GPR_U32(ctx, 2, GPR_U32(ctx, 4) + (g_abiWrongV0 ? 6u : 5u));
        if (g_abiStaleV0High)
        {
            alignas(16) uint64_t parts[2];
            std::memcpy(parts, &ctx->r[2], 16);
            parts[1] = 0x6c07800001000101ull;   // what the register held before: a 32-bit return leaves it
            std::memcpy(&ctx->r[2], parts, 16);
        }
        if (g_abiWrongV1)
            SET_GPR_U32(ctx, 3, 0x98u);
        if (g_abiWrongV1High)
        {
            // v1 = the original's 0x99 in its low word as the original leaves it; only v1[127:64] differs.
            SET_GPR_U32(ctx, 3, 0x99u);
            alignas(16) uint64_t parts[2];
            std::memcpy(parts, &ctx->r[3], 16);
            parts[1] ^= 0x10u;
            std::memcpy(&ctx->r[3], parts, 16);
        }
        if (g_abiClobberS0)
            SET_GPR_U32(ctx, 16, 0xdeadu);
        if (g_abiMoveSp)
            SET_GPR_U32(ctx, 29, kSp - 16u);
        ctx->f[0] = g_abiWrongF0 ? 3.0f : 2.0f;
        ctx->pc = GPR_U32(ctx, 31);
    }

    // std::cout redirected for one scope (what the harness prints goes to std::cout).
    struct CaptureStdout
    {
        std::ostringstream sink;
        std::streambuf *old;
        CaptureStdout() : old(std::cout.rdbuf(sink.rdbuf())) {}
        ~CaptureStdout() { std::cout.rdbuf(old); }
        std::string text() const { return sink.str(); }
    };

    struct Rig
    {
        PS2Runtime runtime;
        std::vector<uint8_t> rdram = std::vector<uint8_t>(PS2_RAM_SIZE, 0u);
        R5900Context ctx{};

        Rig()
        {
            g_bodyRuns = 0;
            g_callNo = 0;
            g_wrongOnCall = -1;
            g_bodyWrongV0 = g_bodyWrongMem = g_bodyStrayWrite = g_bodyWrongV1High = g_bodyWrongF0 = false;
            g_bodyThrows = g_origThrows = false;
            g_bodyClobber = 0;
            g_dueAfterOriginal = 0;
            g_abiClobberS0 =g_abiMoveSp = g_abiWrongV0 = g_abiWrongF0 = g_abiWrongV1 = g_abiStaleV0High = false;
            g_abiWrongV1High = false;
            ps2_shadow::uninstall(runtime);
        }
        ~Rig()
        {
            ps2_shadow::uninstall(runtime);
            runtime.clearDispatchUnwind();
        }

        void call(uint32_t a0 = 0x004b5210u)
        {
            setU32(ctx, 4, a0);
            setU32(ctx, 5, kOut);
            setU32(ctx, 16, 0x5555u);
            setU32(ctx, 29, kSp);
            setU32(ctx, 31, kRa);
            ctx.pc = kFn;   // dispatchGuestBranch sets pc to the target before calling it
            runtime.lookupFunction(kFn)(rdram.data(), &ctx, &runtime);
            ++g_callNo;
        }

        uint32_t word(uint32_t addr) const
        {
            uint32_t v = 0;
            std::memcpy(&v, rdram.data() + addr, 4);
            return v;
        }
    };
}

void register_shadow_harness_tests()
{
    MiniTest::Case("ShadowHarness", [](TestCase &tc)
    {
        tc.Run("an equal body is compared and matches; frame stores below the entry sp are not compared", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, original);
            t.IsTrue(ps2_shadow::add(r.runtime, kFn, "FakeFn", original, body) >= 0, "installed");
            r.call();
            const ps2_shadow::Counts c = ps2_shadow::counts(kFn);
            t.Equals(c.calls, uint64_t{1}, "one call");
            t.Equals(c.compared, uint64_t{1}, "compared");
            t.Equals(c.matched, uint64_t{1}, "matched");
            t.Equals(c.mismatched, uint64_t{0}, "no mismatch");
            t.Equals(g_bodyRuns, 1, "the body ran");
            t.Equals(r.word(kOut), uint32_t{0x1234u}, "the store stands");
            t.Equals(GPR_U32((&r.ctx), 2), uint32_t{0x004b5211u}, "v0");
            t.Equals(r.ctx.pc, kRa, "returned to ra");
        });

        tc.Run("a planted register mismatch is caught and the original's result is kept", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, original);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", original, body);
            g_bodyWrongV0 = true;
            r.call();
            const ps2_shadow::Counts c = ps2_shadow::counts(kFn);
            t.Equals(c.mismatched, uint64_t{1}, "the mismatch is counted");
            t.Equals(c.matched, uint64_t{0}, "and not as a match");
            t.Equals(GPR_U32((&r.ctx), 2), uint32_t{0x004b5211u}, "v0 is the original's");
            const std::vector<std::string> lines = ps2_shadow::mismatchLines(kFn);
            t.IsTrue(!lines.empty() && lines[0].find("v0") != std::string::npos, "the line names v0");
            t.IsTrue(ps2_shadow::formatReport("test").find("mismatched=1") != std::string::npos, "the report says so");
        });

        tc.Run("a planted memory mismatch is caught and memory holds the original's bytes", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, original);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", original, body);
            g_bodyWrongMem = true;
            g_bodyStrayWrite = true;
            r.call();
            t.Equals(ps2_shadow::counts(kFn).mismatched, uint64_t{1}, "counted");
            t.Equals(r.word(kOut), uint32_t{0x1234u}, "the original's value is back");
            t.Equals(static_cast<int>(r.rdram[kOut + 0x40u]), 0, "the body's stray byte is undone");
            const std::vector<std::string> lines = ps2_shadow::mismatchLines(kFn);
            t.IsTrue(!lines.empty() && lines[0].find("mem") != std::string::npos, "the line names memory");
        });

        tc.Run("v1 is compared at full width and f0 by its bits", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, original);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", original, body);
            g_bodyWrongV1High = true;
            r.call();
            t.Equals(ps2_shadow::counts(kFn).mismatched, uint64_t{1}, "v1's upper half differs");
            g_bodyWrongV1High = false;
            g_bodyWrongF0 = true;
            r.call();
            t.Equals(ps2_shadow::counts(kFn).mismatched, uint64_t{2}, "f0 differs");
        });

        tc.Run("an original that exits with pc != ra (the checkpoint return) is skipped, not compared", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, originalCheckpoint);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", originalCheckpoint, body);
            r.call();
            const ps2_shadow::Counts c = ps2_shadow::counts(kFn);
            t.Equals(c.calls, uint64_t{1}, "the call is counted");
            t.Equals(c.skippedUnwound, uint64_t{1}, "as skipped");
            t.Equals(c.compared, uint64_t{0}, "not compared");
            t.Equals(c.mismatched, uint64_t{0}, "and never a mismatch (AE1)");
            t.Equals(g_bodyRuns, 0, "the body did not run");
            t.Equals(r.ctx.pc, kResume, "pc stays on the resume entry, where the scheduler resumes the original");
            t.IsTrue(r.runtime.dispatchUnwinding(), "the unwind is left to the runtime");
            t.Equals(r.word(kOut), uint32_t{0xbeefu}, "the original's partial state is kept");
        });

        tc.Run("AE2: a body wrong once in a thousand calls gives a non-zero mismatch count", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, original);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", original, body);
            g_wrongOnCall = 500;
            for (int i = 0; i < 1000; ++i)
                r.call(0x004b5210u + static_cast<uint32_t>(i) * 4u);
            const ps2_shadow::Counts c = ps2_shadow::counts(kFn);
            t.Equals(c.calls, uint64_t{1000}, "a thousand calls");
            t.Equals(c.mismatched, uint64_t{1}, "one mismatch");
            t.Equals(c.matched, uint64_t{999}, "the rest match");
            t.IsFalse(ps2_shadow::verified(kFn), "not verified");
        });

        tc.Run("an I/O store in the original skips the comparison and keeps the original's result", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, originalIo);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", originalIo, body);
            r.call();
            const ps2_shadow::Counts c = ps2_shadow::counts(kFn);
            t.Equals(c.skippedIo, uint64_t{1}, "skipped for I/O");
            t.Equals(g_bodyRuns, 0, "the body did not run (the store must not happen twice)");
        });

        tc.Run("PS2X_SHADOW takes a comma-separated list; each address keeps its own counts", [](TestCase &t)
        {
            std::vector<uint32_t> list;
            t.IsTrue(ps2_shadow::parseSpec("0x3c4b40, 0x003c4c40,", list), "parsed");
            t.Equals(list.size(), size_t{2}, "two addresses");
            t.Equals(list[1], uint32_t{0x003c4c40u}, "second");
            std::vector<uint32_t> bad;
            t.IsFalse(ps2_shadow::parseSpec("0x3c4b40,fish", bad), "a word that is not an address is refused");

            Rig r;
            constexpr uint32_t kOther = 0x003c4c40u;
            r.runtime.registerFunction(kFn, original);
            r.runtime.registerFunction(kOther, original);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", original, body);
            ps2_shadow::add(r.runtime, kOther, "Other", original, body);
            r.call();
            r.call();
            setU32(r.ctx, 31, kRa);
            r.ctx.pc = kOther;
            r.runtime.lookupFunction(kOther)(r.rdram.data(), &r.ctx, &r.runtime);
            t.Equals(ps2_shadow::counts(kFn).calls, uint64_t{2}, "first address: two calls");
            t.Equals(ps2_shadow::counts(kOther).calls, uint64_t{1}, "second address: one call");
            t.IsTrue(ps2_shadow::verified(kFn) && ps2_shadow::verified(kOther), "both verified");
        });

        tc.Run("installOverride: unlisted replaces, listed shadows, listed in a build with no write log refuses", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, original);
            using ps2_shadow::Installed;
            t.IsTrue(ps2_shadow::installOverride(r.runtime, kFn, "FakeFn", body, {}, true) == Installed::Override,
                     "not listed: a plain override");
            t.IsTrue(r.runtime.lookupFunction(kFn) == body, "the table holds the body");
            r.runtime.registerFunction(kFn, original);
            t.IsTrue(ps2_shadow::installOverride(r.runtime, kFn, "FakeFn", body, {kFn}, false) == Installed::Refused,
                     "listed, no write log: refused");
            t.IsTrue(r.runtime.lookupFunction(kFn) == original, "and the original stays");
            t.IsTrue(ps2_shadow::installOverride(r.runtime, kFn, "FakeFn", body, {kFn}, true) == Installed::Shadow,
                     "listed: shadowed");
            r.call();
            t.Equals(ps2_shadow::counts(kFn).matched, uint64_t{1}, "and compared");
        });

        tc.Run("ABI mode: temporaries and argument registers may differ; the result, memory and pc are compared", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalAbi);
            t.IsTrue(add(r.runtime, kFn, "Derived", originalAbi, bodyAbi, Mode{Compare::Abi, kReturnsV0}) >= 0, "installed");
            r.call();
            Counts c = counts(kFn);
            t.Equals(c.compared, uint64_t{1}, "compared");
            t.Equals(c.matched, uint64_t{1}, "a0, a1, t0, v1 and f1 differ, and that is a match");
            t.Equals(GPR_U32((&r.ctx), 2), uint32_t{0x004b5215u}, "the body's v0 stands");
            t.IsTrue(formatReport("test").find("compare=abi") != std::string::npos, "the report names the mode");

            Rig all;
            all.runtime.registerFunction(kFn, originalAbi);
            add(all.runtime, kFn, "Derived", originalAbi, bodyAbi);
            all.call();
            t.Equals(counts(kFn).mismatched, uint64_t{1}, "the same pair under the all-register default mismatches");
            t.IsTrue(formatReport("test").find("compare=all") != std::string::npos, "and the report says all");
        });

        tc.Run("ABI mode catches a wrong v0, a clobbered s0, a moved sp and a wrong f0", [](TestCase &t)
        {
            using namespace ps2_shadow;
            const auto run = [&](bool &flag, uint32_t returns, const char *what, const char *reg) {
                Rig r;
                r.runtime.registerFunction(kFn, originalAbi);
                add(r.runtime, kFn, "Derived", originalAbi, bodyAbi, Mode{Compare::Abi, returns});
                flag = true;
                r.call();
                t.Equals(counts(kFn).mismatched, uint64_t{1}, what);
                const std::vector<std::string> lines = mismatchLines(kFn);
                t.IsTrue(!lines.empty() && lines[0].find(reg) != std::string::npos, std::string(what) + ": the line names it");
                t.Equals(GPR_U32((&r.ctx), 2), uint32_t{0x004b5215u}, std::string(what) + ": the original's v0 is back");
                flag = false;
            };
            run(g_abiWrongV0, kReturnsV0, "a wrong v0", "v0");
            run(g_abiClobberS0, kReturnsV0, "a clobbered callee-saved s0", "s0");
            run(g_abiMoveSp, kReturnsV0, "a moved sp", "sp");
            run(g_abiWrongF0, kReturnsF0, "a wrong f0 when the function returns a float", "f0");
            run(g_abiWrongV1, kReturnsV0 | kReturnsV1, "a wrong v1 when the function returns in v1", "v1");
        });

        tc.Run("ABI mode compares only the return registers the function has", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalAbi);
            add(r.runtime, kFn, "Derived", originalAbi, bodyAbi, Mode{Compare::Abi, kReturnsNone});
            g_abiWrongV0 = true;
            g_abiWrongF0 = true;
            r.call();
            t.Equals(counts(kFn).matched, uint64_t{1}, "a void function: v0 and f0 are not results");
        });

        tc.Run("installOverride passes the mode on", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalAbi);
            t.IsTrue(installOverride(r.runtime, kFn, "Derived", bodyAbi, Mode{Compare::Abi, kReturnsV0}, {kFn}, true) ==
                         Installed::Shadow, "shadowed");
            r.call();
            t.Equals(counts(kFn).matched, uint64_t{1}, "compared in ABI mode");
        });

        tc.Run("one run shadows more than 128 addresses (a derived batch)", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            constexpr int kMany = 1500;
            t.IsTrue(kMaxSlots >= kMany, "the table holds a batch of 1500");
            for (int i = 0; i < kMany; ++i)
            {
                const uint32_t a = kFn + 0x10000u + static_cast<uint32_t>(i) * 8u;
                r.runtime.registerFunction(a, original);
                if (add(r.runtime, a, "Many", original, body) < 0)
                {
                    t.IsTrue(false, "slot " + std::to_string(i) + " refused");
                    return;
                }
            }
            const uint32_t last = kFn + 0x10000u + static_cast<uint32_t>(kMany - 1) * 8u;
            setU32(r.ctx, 4, 0x004b5210u);
            setU32(r.ctx, 5, kOut);
            setU32(r.ctx, 29, kSp);
            setU32(r.ctx, 31, kRa);
            r.ctx.pc = last;
            r.runtime.lookupFunction(last)(r.rdram.data(), &r.ctx, &r.runtime);
            t.Equals(counts(last).matched, uint64_t{1}, "the last one is compared");
        });

        tc.Run("ABI mode compares v0's upper 64 bits only for a 128-bit return", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalAbi);
            add(r.runtime, kFn, "Derived", originalAbi, bodyAbi, Mode{Compare::Abi, kReturnsV0});
            g_abiStaleV0High = true;
            r.call();
            t.Equals(counts(kFn).matched, uint64_t{1}, "an int or pointer result is the low 64 bits (strrchr, in the game)");

            Rig wide;
            wide.runtime.registerFunction(kFn, originalAbi);
            add(wide.runtime, kFn, "Derived", originalAbi, bodyAbi, Mode{Compare::Abi, kReturnsV0 | kReturnsWide});
            g_abiStaleV0High = true;
            wide.call();
            t.Equals(counts(kFn).mismatched, uint64_t{1}, "a 128-bit result is compared whole");
        });

        tc.Run("ABI mode with kReturnsWide catches a v1 that differs only in bits 127:64", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig narrow;
            narrow.runtime.registerFunction(kFn, originalAbi);
            add(narrow.runtime, kFn, "Derived", originalAbi, bodyAbi, Mode{Compare::Abi, kReturnsV0 | kReturnsV1});
            g_abiWrongV1High = true;
            narrow.call();
            t.Equals(counts(kFn).matched, uint64_t{1}, "without kReturnsWide only v1's low 64 bits are a result");

            Rig wide;
            wide.runtime.registerFunction(kFn, originalAbi);
            add(wide.runtime, kFn, "Derived", originalAbi, bodyAbi,
                Mode{Compare::Abi, kReturnsV0 | kReturnsV1 | kReturnsWide});
            g_abiWrongV1High = true;
            wide.call();
            t.Equals(counts(kFn).mismatched, uint64_t{1}, "a 128-bit return compares v1 whole");
            const std::vector<std::string> lines = mismatchLines(kFn);
            t.IsTrue(!lines.empty() && lines[0].find("v1[127:64]") != std::string::npos, "the line names v1's upper half");
            t.IsTrue(lines.empty() || lines[0].find("v1 orig=") == std::string::npos, "and not its low half");
        });

        tc.Run("an original that leaves with pc != ra and no unwind flag is skipped (the pc clause alone)", [](TestCase &t)
        {
            Rig r;
            r.runtime.registerFunction(kFn, originalExitsElsewhere);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", originalExitsElsewhere, body);
            r.call();
            const ps2_shadow::Counts c = ps2_shadow::counts(kFn);
            t.IsFalse(r.runtime.dispatchUnwinding(), "the runtime is not unwinding: only pc says the call did not return");
            t.Equals(c.skippedUnwound, uint64_t{1}, "skipped");
            t.Equals(c.compared, uint64_t{0}, "not compared");
            t.Equals(g_bodyRuns, 0, "the body did not run");
            t.Equals(r.ctx.pc, kResume, "pc is the original's");
            t.Equals(r.word(kOut), uint32_t{0xbeefu}, "the original's store stands");
        });

        tc.Run("a store through the runtime's slow path (PS2Runtime::Store32 to a GS register) is an I/O skip", [](TestCase &t)
        {
            Rig r;
            r.runtime.memory().gs().bgcolor = 0u;
            r.runtime.registerFunction(kFn, originalMmio);
            ps2_shadow::add(r.runtime, kFn, "FakeFn", originalMmio, body);
            r.call();
            const ps2_shadow::Counts c = ps2_shadow::counts(kFn);
            t.Equals(c.skippedIo, uint64_t{1}, "skipped for I/O by the Store32 hook");
            t.Equals(c.compared, uint64_t{0}, "not compared");
            t.Equals(g_bodyRuns, 0, "the body did not run");
            t.Equals(r.runtime.memory().gs().bgcolor & 0xffffffffull, uint64_t{0x00102030u}, "the store reached the register once");
            t.Equals(r.word(kOut), uint32_t{0x1234u}, "the original's RDRAM store stands");
        });

        tc.Run("the 4097th distinct address is refused with its message", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            for (int i = 0; i < kMaxSlots; ++i)
            {
                const uint32_t a = 0x00400000u + static_cast<uint32_t>(i) * 8u;
                r.runtime.registerFunction(a, original);
                if (add(r.runtime, a, "Many", original, body) < 0)
                {
                    t.IsTrue(false, "slot " + std::to_string(i) + " refused before the table was full");
                    return;
                }
            }
            const uint32_t extra = 0x00400000u + static_cast<uint32_t>(kMaxSlots) * 8u;
            r.runtime.registerFunction(extra, original);
            Installed what = Installed::Shadow;
            std::string printed;
            {
                CaptureStdout out;
                what = installOverride(r.runtime, extra, "FakeExtra", body, {extra}, true);
                printed = out.text();
            }
            t.IsTrue(what == Installed::Refused, "refused");
            t.IsTrue(r.runtime.lookupFunction(extra) == original, "the original stays in the table");
            t.IsTrue(printed.find("REFUSED") != std::string::npos &&
                         printed.find(std::to_string(kMaxSlots) + " slots are taken") != std::string::npos,
                     "the refusal names the full table: " + printed);
            uninstall(r.runtime);   // the shared function table: leave no fake behind for other cases
            for (int i = 0; i <= kMaxSlots; ++i)
                r.runtime.replaceFunction(0x00400000u + static_cast<uint32_t>(i) * 8u, nullptr);
        });

        tc.Run("S1: an original that throws EeDispatcherTransfer disarms the log, is skipped, and the next call compares", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalMayTransfer);
            add(r.runtime, kFn, "FakeFn", originalMayTransfer, body);
            g_origThrows = true;
            bool caught = false;
            try
            {
                r.call();
            }
            catch (const EeDispatcherTransfer &)
            {
                caught = true;
            }
            t.IsTrue(caught, "the transfer is rethrown to the scheduler (here, the test)");
            const bool armed = writeLogArmedForTest();
            t.IsFalse(armed, "no write log is armed after the throw");
            if (armed)
            {
                // The log pointer names the dead stack log of the call that threw: one more store would write
                // through it. Disarm (uninstall clears it) and stop here.
                uninstall(r.runtime);
                return;
            }
            Counts c = counts(kFn);
            t.Equals(c.skippedTransfer, uint64_t{1}, "counted as a skip (skipped_transfer)");
            t.Equals(c.compared, uint64_t{0}, "not compared");
            t.Equals(g_bodyRuns, 0, "the body did not run");
            t.Equals(r.word(kOut), uint32_t{0xcafeu}, "the original's store before the transfer stands");
            t.IsTrue(formatReport("test").find("skipped_transfer=1") != std::string::npos, "the report says so");

            g_origThrows = false;
            r.call();
            c = counts(kFn);
            t.Equals(c.passedThrough, uint64_t{0}, "the next call is not passed through");
            t.Equals(c.compared, uint64_t{1}, "the next call is compared");
            t.Equals(c.matched, uint64_t{1}, "and matches");
            t.IsFalse(writeLogArmedForTest(), "and disarms on its return");
        });

        tc.Run("S1: a body that throws is counted, named in one [shadow-error] line, rethrown, and the log disarmed", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, original);
            add(r.runtime, kFn, "FakeFn", original, body);
            g_bodyThrows = true;
            bool caught = false;
            std::string printed;
            {
                CaptureStdout out;
                try
                {
                    r.call();
                }
                catch (const EeDispatcherTransfer &)
                {
                    caught = true;
                }
                printed = out.text();
            }
            t.IsTrue(caught, "the transfer is rethrown");
            const bool armed = writeLogArmedForTest();
            t.IsFalse(armed, "no write log is armed after the throw");
            if (armed)
            {
                uninstall(r.runtime);
                return;
            }
            Counts c = counts(kFn);
            t.Equals(c.bodyThrew, uint64_t{1}, "counted as body_threw");
            t.Equals(c.compared, uint64_t{0}, "not compared");
            t.Equals(c.mismatched, uint64_t{0}, "not a mismatch either");
            size_t errors = 0;
            for (size_t at = printed.find("[shadow-error]"); at != std::string::npos; at = printed.find("[shadow-error]", at + 1))
                ++errors;
            t.Equals(errors, size_t{1}, "one [shadow-error] line: " + printed);
            t.IsTrue(printed.find("0x003c4b40") != std::string::npos, "naming the address: " + printed);
            t.IsTrue(formatReport("test").find("body_threw=1") != std::string::npos, "the report says so");

            g_bodyThrows = false;
            r.call();
            c = counts(kFn);
            t.Equals(c.passedThrough, uint64_t{0}, "the next call is not passed through");
            t.Equals(c.compared, uint64_t{1}, "the next call is compared");
            t.Equals(c.matched, uint64_t{1}, "and matches");
            t.IsFalse(verified(kFn), "an address whose body threw is never verified");
        });

        tc.Run("S4: All mode compares every FPR, fcr31, f_acc, sa, hi/lo and hi1/lo1, and keeps the original's", [](TestCase &t)
        {
            using namespace ps2_shadow;
            struct Clobber
            {
                int which;
                const char *name;
            };
            const Clobber clobbers[] = {{1, "f20"}, {2, "f31"}, {3, "f2"},  {4, "fcr31"}, {5, "hi"},
                                        {6, "lo"},  {7, "hi1"}, {8, "lo1"}, {9, "f_acc"}, {10, "sa"}};
            for (const Clobber &k : clobbers)
            {
                Rig r;
                r.runtime.registerFunction(kFn, original);
                add(r.runtime, kFn, "FakeFn", original, body);
                g_bodyClobber = k.which;
                const R5900Context before = r.ctx;
                r.call();
                const std::string what = std::string("a body that changes ") + k.name;
                t.Equals(counts(kFn).mismatched, uint64_t{1}, what + ": mismatched");
                const std::vector<std::string> lines = mismatchLines(kFn);
                t.IsTrue(!lines.empty() && lines[0].find(std::string(" ") + k.name + " orig=") != std::string::npos,
                         what + ": the line names it");
                t.IsTrue(std::memcmp(&r.ctx.f[20], &before.f[20], sizeof(float) * 12) == 0 && r.ctx.hi == before.hi &&
                             r.ctx.lo == before.lo && r.ctx.hi1 == before.hi1 && r.ctx.lo1 == before.lo1 &&
                             r.ctx.fcr31 == before.fcr31 && r.ctx.sa == before.sa &&
                             std::memcmp(&r.ctx.f_acc, &before.f_acc, sizeof(float)) == 0 &&
                             std::memcmp(&r.ctx.f[2], &before.f[2], sizeof(float)) == 0,
                         what + ": the original's state is back");
                g_bodyClobber = 0;
            }
        });

        tc.Run("S4: ABI mode still leaves hi/lo and the temporary FPRs free", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalAbi);
            add(r.runtime, kFn, "Derived", originalAbi, bodyAbi, Mode{Compare::Abi, kReturnsV0});
            r.call();
            t.Equals(counts(kFn).matched, uint64_t{1}, "the original's lo, hi and f5 are not results: a match");
            t.Equals(r.ctx.lo, uint64_t{0}, "and the body's lo stands");
        });

        tc.Run("S7: PS2X_SHADOW takes 0x-hex or plain decimal fitting 32 bits, nothing else, and drops repeats", [](TestCase &t)
        {
            using ps2_shadow::parseSpec;
            std::vector<uint32_t> v;
            t.IsTrue(parseSpec("0x3c4b40, 0X003C4C40 ,4000000", v), "hex either case, decimal (0x3d0900), spaces");
            t.Equals(v.size(), size_t{3}, "three addresses");
            t.IsTrue(v.size() == 3 && v[0] == 0x003c4b40u && v[1] == 0x003c4c40u && v[2] == 4000000u, "their values");
            t.IsTrue(parseSpec("0xFFFFFFFF,4294967295,0", v), "the 32-bit edges and zero");
            t.Equals(v.size(), size_t{2}, "0xFFFFFFFF and 4294967295 are one address");
            t.IsTrue(parseSpec("0x10,16,0x0010", v), "the same address three ways");
            t.Equals(v.size(), size_t{1}, "listed once");

            const char *const refused[] = {"-1", "010", "0x100000000", "4294967296", "0x", "+5", "0x-5", "0x 10",
                                           "1e3", "0b101", "99999999999999999999999"};
            for (const char *bad : refused)
            {
                std::vector<uint32_t> out;
                t.IsFalse(parseSpec(bad, out), std::string("'") + bad + "' is refused");
            }
        });

        tc.Run("S6: flushReport prints the exit report now (the runner _Exits, so atexit never runs)", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, original);
            add(r.runtime, kFn, "FakeFn", original, body);
            r.call();
            int lines = -1;
            std::string printed;
            {
                CaptureStdout out;
                lines = flushReport();
                printed = out.text();
            }
            t.Equals(lines, 2, "two lines: the address and the total");
            t.IsTrue(printed.find("[shadow] exit: 0x003c4b40 FakeFn") != std::string::npos, "the address line: " + printed);
            t.IsTrue(printed.find("calls=1") != std::string::npos, "with its counts: " + printed);
            t.IsTrue(printed.find("[shadow] exit: total shadowed=1") != std::string::npos, "the total line: " + printed);
            t.Equals(printed, formatReport("exit"), "exactly the periodic report's lines, reason 'exit'");
        });

        tc.Run("S6: flushReport is a no-op when nothing is shadowed", [](TestCase &t)
        {
            Rig r;
            int lines = -1;
            std::string printed;
            {
                CaptureStdout out;
                lines = ps2_shadow::flushReport();
                printed = out.text();
            }
            t.Equals(lines, 0, "no lines");
            t.IsTrue(printed.empty(), "nothing printed: " + printed);
        });

        tc.Run("R2.1: the body runs under a checkpoint hold: a checkpoint due after the original does not cut it short", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalLoop);
            add(r.runtime, kFn, "FakeFn", originalLoop, bodyLoop);
            g_dueAfterOriginal = 1;
            r.call();
            const Counts c = counts(kFn);
            t.Equals(c.compared, uint64_t{1}, "compared");
            t.Equals(c.matched, uint64_t{1}, "a correct body matches although an event became due before it ran");
            t.Equals(c.mismatched, uint64_t{0}, "not a mismatch (pc orig=ra body=loop head)");
            t.Equals(r.ctx.pc, kRa, "returned to ra");
            t.IsFalse(r.runtime.dispatchUnwinding(), "the body did not unwind");
            t.IsTrue(r.runtime.eeCheckpointDue(), "the event is still pending: the caller's next checkpoint acts on it");
            r.runtime.clearDispatchUnwind();
        });

        tc.Run("R2.1: the original phase is not held: a due checkpoint still parks the original and skips the call", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalLoop);
            add(r.runtime, kFn, "FakeFn", originalLoop, bodyLoop);
            r.runtime.eeScheduler().postEvent(EeEvent{});
            r.call();
            const Counts c = counts(kFn);
            t.Equals(c.skippedUnwound, uint64_t{1}, "the original parked at its back edge: skipped");
            t.Equals(c.compared, uint64_t{0}, "not compared");
            t.Equals(g_bodyRuns, 0, "the body did not run");
            t.Equals(r.ctx.pc, kResume, "pc on the loop head");
            t.IsTrue(r.runtime.dispatchUnwinding(), "unwinding to the scheduler");
        });

        tc.Run("R2.1: a stop request (which a hold does not stop) cutting the body short is a skip, not a mismatch", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalLoop);
            add(r.runtime, kFn, "FakeFn", originalLoop, bodyLoop);
            g_dueAfterOriginal = 2;
            r.call();
            const Counts c = counts(kFn);
            t.Equals(c.mismatched, uint64_t{0}, "not a mismatch");
            t.Equals(c.compared, uint64_t{0}, "not compared");
            t.Equals(c.skippedUnwound, uint64_t{1}, "counted skipped_unwound");
            t.Equals(g_bodyRuns, 1, "the body ran and was cut short");
            t.Equals(GPR_U32((&r.ctx), 2), uint32_t{0x004b5211u}, "the original's v0 is back");
            t.Equals(r.ctx.pc, kRa, "and its pc");
            t.Equals(r.word(kOut), uint32_t{0x1234u}, "and its store");
            t.IsTrue(r.runtime.dispatchUnwinding(), "the stop's unwind is left to the runtime");
        });

        tc.Run("R2.6: the write log is the arming thread's: another thread neither sees it nor notes into it", [](TestCase &t)
        {
            using namespace ps2_shadow;
            Rig r;
            r.runtime.registerFunction(kFn, originalWithHelperThread);
            add(r.runtime, kFn, "FakeFn", originalWithHelperThread, body);
            g_ownThreadSawLog = false;
            g_otherThreadSawLog = true;
            r.call();
            t.IsTrue(g_ownThreadSawLog, "the calling thread's log is armed inside the original");
            t.IsFalse(g_otherThreadSawLog, "another thread reads no log (g_writeLog is thread_local)");
            const Counts c = counts(kFn);
            t.Equals(c.skippedIo, uint64_t{0}, "the other thread's I/O store is not this call's");
            t.Equals(c.matched, uint64_t{1}, "the call is compared and matches");
            t.IsFalse(writeLogArmedForTest(), "disarmed after the call");
        });
    });
}
