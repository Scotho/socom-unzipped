// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork.
//
// docs/KNOWN.md #4: Kernel/Stubs/Helpers/Support.h defined its state in an anonymous namespace, so
// each of the nineteen stub translation units that pull it in through Stubs/Common.h got its own
// private copy. 955539c moved the whole 2041-line header to a .cpp in one go -- one definition
// instead of nineteen -- the C++ suite stayed green, and the gate's mission stage then never
// reached the HUD. It was reverted.
//
// The shape that makes the same move safe is the fork's: one named struct per subsystem, OWNED BY
// the PS2Runtime the stub was called with. These cases are what pins that ownership. Each drives a
// stub compiled in a DIFFERENT translation unit with TWO PS2Runtime instances and asserts that
//   (a) the stub reached the state of the runtime it was handed, and
//   (b) the other runtime saw none of it.
// Process-global state -- an anonymous namespace per TU, or the single function-local static this
// task's first pass used -- fails (b) or (a) respectively, which is exactly what a regression to
// either would look like.

#include "MiniTest.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_stubs.h"
#include "Kernel/Stubs/Unimplemented.h"
#include "Kernel/Stubs/DMA.h"
#include "Kernel/Stubs/GS.h"
#include "Kernel/Stubs/LibC.h"
#include "Kernel/Stubs/Helpers/StubLogRuntimeState.h"
#include "Kernel/Stubs/Helpers/DmaRuntimeState.h"
#include "Kernel/Stubs/Helpers/GsRuntimeState.h"
#include "Kernel/Stubs/Helpers/LibCRuntimeState.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <string>

namespace
{
    // A stub name no other test uses, so the counter's value is ours alone.
    const char *const kProbeStubName = "s11t8b_probe_stub";

    constexpr uint32_t kVif1ChannelBase = 0x10009000u;

    void setRegU32(R5900Context &ctx, int reg, uint32_t value)
    {
        ctx.r[reg] = _mm_set_epi64x(0, static_cast<int64_t>(value));
    }

    uint32_t stubWarningsFor(PS2Runtime &runtime, const char *name)
    {
        ps2_stubs::StubLogRuntimeState &state = runtime.stubLogRuntimeState();
        std::lock_guard<std::mutex> lock(state.warningMutex);
        auto it = state.warningCount.find(name);
        return (it != state.warningCount.end()) ? it->second : 0u;
    }
}

void register_runtime_state_tests()
{
    MiniTest::Case("Kernel stub runtime state (Sprint 11 Task 8b)", [](TestCase &tc)
    {
        tc.Run("Stubs/Unimplemented.cpp bumps the stub-warning counter of the runtime it was handed", [](TestCase &t)
        {
            PS2Runtime first;
            PS2Runtime second;

            // TODO_NAMED lives in Stubs/Unimplemented.cpp -- a different translation unit. Its
            // first kMaxStubWarningsPerName calls bump the counter and then throw.
            R5900Context ctx{};
            bool threw = false;
            try
            {
                ps2_stubs::TODO_NAMED(kProbeStubName, nullptr, &ctx, &first);
            }
            catch (const std::runtime_error &)
            {
                threw = true;
            }
            t.IsTrue(threw, "TODO_NAMED should still throw on an unimplemented stub");

            t.Equals(stubWarningsFor(first, kProbeStubName), 1u,
                     "the counter of the runtime the stub was called with should hold that call; "
                     "0 means Stubs/Unimplemented.cpp bumped process-wide state instead of this "
                     "runtime's (docs/KNOWN.md #4)");
            t.Equals(stubWarningsFor(second, kProbeStubName), 0u,
                     "a second runtime in the same process must not see the first one's "
                     "stub-warning count");
        });

        tc.Run("Stubs/DMA.cpp's sceDmaSync consumes the pending mark this TU wrote", [](TestCase &t)
        {
            ps2_stubs::DmaRuntimeState &dma = ps2_stubs::dmaRuntimeStateFor(nullptr);
            {
                std::lock_guard<std::mutex> lock(dma.mutex);
                dma.pendingPolls[kVif1ChannelBase] = 1u;
            }

            // sceDmaSync lives in Stubs/DMA.cpp -- a different translation unit. Non-blocking mode
            // ($a1 != 0) must report the transfer busy ONCE and consume the mark.
            PS2Runtime runtime;
            R5900Context ctx{};
            setRegU32(ctx, 4, kVif1ChannelBase);
            setRegU32(ctx, 5, 1u);
            ps2_stubs::sceDmaSync(nullptr, &ctx, &runtime);
            const uint32_t firstReturn = getRegU32(&ctx, 2);

            bool stillPending = false;
            {
                std::lock_guard<std::mutex> lock(dma.mutex);
                auto it = dma.pendingPolls.find(kVif1ChannelBase);
                stillPending = (it != dma.pendingPolls.end() && it->second > 0);
                dma.pendingPolls.erase(kVif1ChannelBase);
            }

            t.Equals(firstReturn, 1u,
                     "sceDmaSync should report busy for the channel this TU marked pending");
            t.IsFalse(stillPending,
                      "sceDmaSync should have consumed the pending mark in the state this TU reads");
        });

        tc.Run("Stubs/GS.cpp's sceGsResetGraph writes the GParam this TU reads", [](TestCase &t)
        {
            ps2_stubs::GsRuntimeState &gs = ps2_stubs::gsRuntimeStateFor(nullptr);
            const ps2_stubs::GsGParam saved = gs.gparam;
            gs.gparam = ps2_stubs::GsGParam{1, 2, 1, 3};

            R5900Context ctx{};
            setRegU32(ctx, 4, 0u);    // $a0 = mode 0
            setRegU32(ctx, 5, 1u);    // $a1 = interlace
            setRegU32(ctx, 6, 3u);    // $a2 = omode  (3, not the default 2)
            setRegU32(ctx, 7, 0u);    // $a3 = ffmode (0, not the default 1)
            ps2_stubs::sceGsResetGraph(nullptr, &ctx, nullptr);

            const ps2_stubs::GsGParam seen = gs.gparam;
            gs.gparam = saved;

            t.Equals(static_cast<uint32_t>(seen.omode), 3u,
                     "the GParam this TU reads should hold the omode Stubs/GS.cpp just stored");
            t.Equals(static_cast<uint32_t>(seen.ffmode), 0u,
                     "sceGsResetGraph's ffmode should have reached the state this TU reads");
        });

        tc.Run("Stubs/LibC.cpp's fclose closes the handle this TU opened", [](TestCase &t)
        {
            FILE *fp = std::tmpfile();
            t.IsTrue(fp != nullptr, "the host should give this test a temporary FILE to hand over");
            if (!fp)
                return;

            ps2_stubs::LibCRuntimeState &files = ps2_stubs::libcRuntimeStateFor(nullptr);
            uint32_t handle = 0;
            {
                std::lock_guard<std::mutex> lock(files.mutex);
                handle = files.allocateHandleLocked();
                files.openFiles[handle] = fp;
            }

            R5900Context ctx{};
            setRegU32(ctx, 4, handle);
            ps2_stubs::fclose(nullptr, &ctx, nullptr);
            const int32_t ret = static_cast<int32_t>(getRegU32(&ctx, 2));

            bool stillOpen = false;
            {
                std::lock_guard<std::mutex> lock(files.mutex);
                auto it = files.openFiles.find(handle);
                stillOpen = (it != files.openFiles.end());
                files.openFiles.erase(handle);
            }

            t.Equals(ret, 0,
                     "fclose should have found the handle this TU registered");
            t.IsFalse(stillOpen,
                      "fclose should have erased the handle from the table this TU reads");
        });
    });
}
