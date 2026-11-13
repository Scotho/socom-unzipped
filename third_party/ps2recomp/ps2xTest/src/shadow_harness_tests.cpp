// Sprint 19 task E2: the shadow harness (PS2X_SHADOW, runtime/shadow_harness.h).
//
// Each case installs a fake "original" (written the way generated code is: WRITE32 macros, `jr ra` leaving
// pc = ra) and a fake override body at a function-table address, then calls the address the way a JAL does
// (ctx->pc = the target, the table's function called). This file is compiled with PS2X_SHADOW_WRITE_LOG=1
// (ps2xTest/CMakeLists.txt), as the generated code is in a shadow build, so its stores reach the write log.
//
// The bar (Sprint 19 plan, E2): a planted mismatch is caught under test; an original that exits with pc != ra --
// the eeCheckpointDue() back-edge return, which leaves pc on the resume entry (0x3c4b50 for r0001's
// CZWeaponList_GetWeapon at 0x3c4b40) -- is detected and that call skipped, under test.
#include "MiniTest.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/shadow_harness.h"

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#if !PS2X_SHADOW_WRITE_LOG
#error "shadow_harness_tests.cpp must be compiled with PS2X_SHADOW_WRITE_LOG=1"
#endif

namespace
{
    constexpr uint32_t kFn = 0x003c4b40u;       // the address the cases shadow (r0001 GetWeapon's, for the reader)
    constexpr uint32_t kResume = 0x003c4b50u;   // its loop-head resume entry
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

    // ABI mode (a body derived from source): the original leaves its scratch registers as its instructions do (a0
    // advanced, t0 and a1 used, f1 a temporary); a derived body computes the same result through other registers.
    bool g_abiClobberS0 = false;
    bool g_abiMoveSp = false;
    bool g_abiWrongV0 = false;
    bool g_abiWrongF0 = false;
    bool g_abiWrongV1 = false;

    void originalAbi(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        SET_GPR_U32(ctx, 8, GPR_U32(ctx, 4) ^ 0x5au);              // t0: a temporary
        SET_GPR_U32(ctx, 4, GPR_U32(ctx, 4) + 4u);                // a0 advanced
        SET_GPR_U32(ctx, 5, 0x77u);                               // a1 reused
        WRITE32(kOut, 0x00004321u);
        SET_GPR_U32(ctx, 2, GPR_U32(ctx, 4) + 1u);                // v0 = a0 + 5
        SET_GPR_U32(ctx, 3, 0x99u);                               // v1: a temporary unless returned
        ctx->f[1] = 7.0f;                                         // f1: a temporary unless returned
        ctx->f[0] = 2.0f;
        ctx->pc = GPR_U32(ctx, 31);
    }

    void bodyAbi(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        ++g_bodyRuns;
        WRITE32(kOut, 0x00004321u);
        SET_GPR_U32(ctx, 2, GPR_U32(ctx, 4) + (g_abiWrongV0 ? 6u : 5u));
        if (g_abiWrongV1)
            SET_GPR_U32(ctx, 3, 0x98u);
        if (g_abiClobberS0)
            SET_GPR_U32(ctx, 16, 0xdeadu);
        if (g_abiMoveSp)
            SET_GPR_U32(ctx, 29, kSp - 16u);
        ctx->f[0] = g_abiWrongF0 ? 3.0f : 2.0f;
        ctx->pc = GPR_U32(ctx, 31);
    }

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
            g_abiClobberS0 = g_abiMoveSp = g_abiWrongV0 = g_abiWrongF0 = g_abiWrongV1 = false;
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
            t.IsTrue(ps2_shadow::add(r.runtime, kFn, "GetWeapon", original, body) >= 0, "installed");
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
            ps2_shadow::add(r.runtime, kFn, "GetWeapon", original, body);
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
            ps2_shadow::add(r.runtime, kFn, "GetWeapon", original, body);
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
            ps2_shadow::add(r.runtime, kFn, "GetWeapon", original, body);
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
            ps2_shadow::add(r.runtime, kFn, "GetWeapon", originalCheckpoint, body);
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
            ps2_shadow::add(r.runtime, kFn, "GetWeapon", original, body);
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
            ps2_shadow::add(r.runtime, kFn, "GetWeapon", originalIo, body);
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
            ps2_shadow::add(r.runtime, kFn, "GetWeapon", original, body);
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
            t.IsTrue(ps2_shadow::installOverride(r.runtime, kFn, "GetWeapon", body, {}, true) == Installed::Override,
                     "not listed: a plain override");
            t.IsTrue(r.runtime.lookupFunction(kFn) == body, "the table holds the body");
            r.runtime.registerFunction(kFn, original);
            t.IsTrue(ps2_shadow::installOverride(r.runtime, kFn, "GetWeapon", body, {kFn}, false) == Installed::Refused,
                     "listed, no write log: refused");
            t.IsTrue(r.runtime.lookupFunction(kFn) == original, "and the original stays");
            t.IsTrue(ps2_shadow::installOverride(r.runtime, kFn, "GetWeapon", body, {kFn}, true) == Installed::Shadow,
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
    });
}
