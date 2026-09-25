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
    // Stub names no other test uses, so the counters' values are ours alone.
    const char *const kProbeStubName = "s11t8b_probe_stub";
    const char *const kResetProbeStubName = "s11t8b_reset_probe_stub";

    constexpr uint32_t kVif1ChannelBase = 0x10009000u;

    void setRegU32(R5900Context &ctx, int reg, uint32_t value)
    {
        ctx.r[reg] = _mm_set_epi64x(0, static_cast<int64_t>(value));
    }

    void markDmaChannelPending(PS2Runtime &runtime, uint32_t channelBase)
    {
        ps2_stubs::DmaRuntimeState &state = runtime.dmaRuntimeState();
        std::lock_guard<std::mutex> lock(state.mutex);
        state.pendingPolls[channelBase] = 1u;
    }

    bool dmaChannelPending(PS2Runtime &runtime, uint32_t channelBase)
    {
        ps2_stubs::DmaRuntimeState &state = runtime.dmaRuntimeState();
        std::lock_guard<std::mutex> lock(state.mutex);
        auto it = state.pendingPolls.find(channelBase);
        return it != state.pendingPolls.end() && it->second > 0;
    }

    uint32_t registerGuestFile(PS2Runtime &runtime, FILE *file)
    {
        ps2_stubs::LibCRuntimeState &state = runtime.libcRuntimeState();
        std::lock_guard<std::mutex> lock(state.mutex);
        const uint32_t handle = state.allocateHandleLocked();
        state.openFiles[handle] = file;
        return handle;
    }

    bool guestFileOpen(PS2Runtime &runtime, uint32_t handle)
    {
        ps2_stubs::LibCRuntimeState &state = runtime.libcRuntimeState();
        std::lock_guard<std::mutex> lock(state.mutex);
        return state.openFiles.count(handle) != 0;
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

        tc.Run("Stubs/DMA.cpp's sceDmaSync reads the pending-poll map of the runtime it was handed", [](TestCase &t)
        {
            PS2Runtime first;
            PS2Runtime second;

            markDmaChannelPending(first, kVif1ChannelBase);

            // sceDmaSync lives in Stubs/DMA.cpp -- a different translation unit. Non-blocking mode
            // ($a1 != 0) reports the transfer busy once and consumes the mark.
            R5900Context ctx{};
            setRegU32(ctx, 4, kVif1ChannelBase);
            setRegU32(ctx, 5, 1u);

            ps2_stubs::sceDmaSync(nullptr, &ctx, &second);
            t.Equals(getRegU32(&ctx, 2), 0u,
                     "a second runtime in the same process must not see the transfer the first one "
                     "has in flight");
            t.IsTrue(dmaChannelPending(first, kVif1ChannelBase),
                     "and it must not consume the first runtime's pending mark either");

            ps2_stubs::sceDmaSync(nullptr, &ctx, &first);
            t.Equals(getRegU32(&ctx, 2), 1u,
                     "sceDmaSync should report busy for the channel THIS runtime marked pending; "
                     "0 means Stubs/DMA.cpp read process-wide state instead of the runtime's "
                     "(docs/KNOWN.md #4)");
            t.IsFalse(dmaChannelPending(first, kVif1ChannelBase),
                      "and it should have consumed that runtime's mark");
        });

        tc.Run("Stubs/DMA.cpp's sceDmaReset clears only its own runtime's DMA state", [](TestCase &t)
        {
            PS2Runtime first;
            PS2Runtime second;
            // sceDmaReset writes the DMAC's control registers, so this pair needs real memory.
            t.IsTrue(first.memory().initialize(), "runtime memory initialize should succeed");
            markDmaChannelPending(first, kVif1ChannelBase);
            markDmaChannelPending(second, kVif1ChannelBase);
            first.dmaRuntimeState().currentEnvironment.pcr = 0xFFu;
            second.dmaRuntimeState().currentEnvironment.pcr = 0xFFu;

            R5900Context ctx{};
            ps2_stubs::sceDmaReset(nullptr, &ctx, &first);

            t.IsFalse(dmaChannelPending(first, kVif1ChannelBase),
                      "a controller reset means no transfer is in flight, so sceDmaReset clears "
                      "the pending-poll map as well as the environment block");
            t.Equals(static_cast<uint32_t>(first.dmaRuntimeState().currentEnvironment.pcr), 0u,
                     "sceDmaReset should clear its runtime's environment block");
            t.IsTrue(dmaChannelPending(second, kVif1ChannelBase),
                     "and it must leave a second runtime's DMA state alone");
            t.Equals(static_cast<uint32_t>(second.dmaRuntimeState().currentEnvironment.pcr), 0xFFu,
                     "including that runtime's environment block");
        });

        tc.Run("Stubs/GS.cpp's sceGsResetGraph writes the GParam of the runtime it was handed", [](TestCase &t)
        {
            PS2Runtime first;
            PS2Runtime second;
            // sceGsResetGraph's mode-0 path runs syncCoreSubsystems and kicks a GIF packet, so
            // this pair needs real memory.
            t.IsTrue(first.memory().initialize(), "runtime memory initialize should succeed");

            R5900Context ctx{};
            setRegU32(ctx, 4, 0u);    // $a0 = mode 0
            setRegU32(ctx, 5, 1u);    // $a1 = interlace
            setRegU32(ctx, 6, 3u);    // $a2 = omode  (3, not the default 2)
            setRegU32(ctx, 7, 0u);    // $a3 = ffmode (0, not the default 1)
            ps2_stubs::sceGsResetGraph(nullptr, &ctx, &first);

            t.Equals(static_cast<uint32_t>(first.gsRuntimeState().gparam.omode), 3u,
                     "the GParam of the runtime the stub was called with should hold the omode "
                     "Stubs/GS.cpp just stored; 2 (the default) means that TU wrote process-wide "
                     "state instead of this runtime's (docs/KNOWN.md #4)");
            t.Equals(static_cast<uint32_t>(first.gsRuntimeState().gparam.ffmode), 0u,
                     "sceGsResetGraph's ffmode should have reached that runtime's state");
            t.Equals(static_cast<uint32_t>(second.gsRuntimeState().gparam.omode), 2u,
                     "a second runtime in the same process must keep its own video mode");
            t.Equals(static_cast<uint32_t>(second.gsRuntimeState().gparam.ffmode), 1u,
                     "including its own field mode");
        });

        tc.Run("Stubs/LibC.cpp's fclose closes the handle in the runtime it was handed", [](TestCase &t)
        {
            FILE *first_fp = std::tmpfile();
            FILE *second_fp = std::tmpfile();
            t.IsTrue(first_fp != nullptr && second_fp != nullptr,
                     "the host should give this test two temporary FILEs to hand over");
            if (!first_fp || !second_fp)
                return;

            PS2Runtime first;
            PS2Runtime second;
            // Both runtimes hand out handle 1, for two different host files. That is the whole
            // point: one shared table could not.
            const uint32_t firstHandle = registerGuestFile(first, first_fp);
            const uint32_t secondHandle = registerGuestFile(second, second_fp);
            t.Equals(firstHandle, secondHandle,
                     "each runtime numbers its own guest files from 1");

            R5900Context ctx{};
            setRegU32(ctx, 4, firstHandle);
            ps2_stubs::fclose(nullptr, &ctx, &first);

            t.Equals(static_cast<int32_t>(getRegU32(&ctx, 2)), 0,
                     "fclose should have found the handle registered with THIS runtime; EOF means "
                     "Stubs/LibC.cpp searched process-wide state instead (docs/KNOWN.md #4)");
            t.IsFalse(guestFileOpen(first, firstHandle),
                      "fclose should have erased the handle from that runtime's table");
            t.IsTrue(guestFileOpen(second, secondHandle),
                     "and it must not touch a second runtime's file of the same handle number");
        });

        tc.Run("Stubs/LibC.cpp's rand keeps its cursor in the runtime it was handed", [](TestCase &t)
        {
            PS2Runtime first;
            PS2Runtime second;

            // With no registered guest _impure_ptr the pair runs off the runtime's own fallback
            // cursor, so two runtimes seeded the same way must produce the same first number and
            // then diverge only because each advanced its own.
            R5900Context ctx{};
            setRegU32(ctx, 4, 12345u);
            ps2_stubs::srand(nullptr, &ctx, &first);
            ps2_stubs::rand(nullptr, &ctx, &first);
            const uint32_t firstDraw = getRegU32(&ctx, 2);

            setRegU32(ctx, 4, 12345u);
            ps2_stubs::srand(nullptr, &ctx, &second);
            ps2_stubs::rand(nullptr, &ctx, &second);
            const uint32_t secondDraw = getRegU32(&ctx, 2);

            t.Equals(secondDraw, firstDraw,
                     "the same seed in a fresh runtime should give the same first draw");

            ps2_stubs::rand(nullptr, &ctx, &first);
            const uint32_t firstSecondDraw = getRegU32(&ctx, 2);
            ps2_stubs::rand(nullptr, &ctx, &second);
            t.Equals(getRegU32(&ctx, 2), firstSecondDraw,
                     "and each runtime should advance its OWN cursor; a differing second draw "
                     "means Stubs/LibC.cpp shares one process-wide rand cursor");
        });

        tc.Run("PS2Runtime::resetStubRuntimeState, which run() calls, clears every subsystem's session state", [](TestCase &t)
        {
            PS2Runtime runtime;
            R5900Context ctx{};

            // StubLog: a warning count put there by the stub in Stubs/Unimplemented.cpp, and a
            // printf budget partly spent.
            try
            {
                ps2_stubs::TODO_NAMED(kResetProbeStubName, nullptr, &ctx, &runtime);
            }
            catch (const std::runtime_error &)
            {
            }
            {
                ps2_stubs::StubLogRuntimeState &log = runtime.stubLogRuntimeState();
                std::lock_guard<std::mutex> lock(log.printfMutex);
                log.printfLogCount = 7u;
            }
            t.Equals(stubWarningsFor(runtime, kResetProbeStubName), 1u,
                     "the stub-warning count should be set before the reset");

            // GS: a video mode that is not the default {1, 2, 1, 3}.
            runtime.gsRuntimeState().gparam = ps2_stubs::GsGParam{0, 3, 0, 3};

            // DMA: a transfer in flight.
            markDmaChannelPending(runtime, kVif1ChannelBase);

            // libc: an open guest FILE, and the rand registration the game override installs
            // during loadELF -- which runs BEFORE run().
            FILE *fp = std::tmpfile();
            t.IsTrue(fp != nullptr, "the host should give this test a temporary FILE");
            if (!fp)
                return;
            const uint32_t handle = registerGuestFile(runtime, fp);
            ps2_stubs::setLibcRandState(&runtime, 0x6000u, 0xA8u);

            runtime.resetStubRuntimeState();

            t.Equals(stubWarningsFor(runtime, kResetProbeStubName), 0u,
                     "resetStubRuntimeState should clear the stub-warning counts; a non-zero count "
                     "means StubLogRuntimeState::reset() never ran");
            {
                ps2_stubs::StubLogRuntimeState &log = runtime.stubLogRuntimeState();
                std::lock_guard<std::mutex> lock(log.printfMutex);
                t.Equals(log.printfLogCount, 0u,
                         "and it should give the run a fresh PS2-printf budget");
            }
            t.Equals(static_cast<uint32_t>(runtime.gsRuntimeState().gparam.omode), 2u,
                     "the GParam should be back to the default video mode; 3 means "
                     "GsRuntimeState::reset() never ran");
            t.Equals(static_cast<uint32_t>(runtime.gsRuntimeState().gparam.ffmode), 1u,
                     "including the default field mode");
            t.IsFalse(dmaChannelPending(runtime, kVif1ChannelBase),
                      "a new run starts with no DMA transfer in flight");
            t.IsFalse(guestFileOpen(runtime, handle),
                      "and with no guest FILE open; a surviving handle means "
                      "LibCRuntimeState::reset() never ran");

            // What the reset must NOT clear: the registration is the override's, installed before
            // run(), and wiping it would drop rand() back to its internal cursor.
            {
                ps2_stubs::LibCRuntimeState &libc = runtime.libcRuntimeState();
                std::lock_guard<std::mutex> lock(libc.randMutex);
                t.Equals(libc.impurePtrAddr, 0x6000u,
                         "the game override's _impure_ptr registration must survive the run-path "
                         "reset -- applySocom2 installs it inside loadELF, before run()");
                t.Equals(libc.randNextOffset, 0xA8u,
                         "and so must the _rand_next offset beside it");
            }
        });
    });
}
