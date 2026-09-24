// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork.
//
// docs/KNOWN.md #4: Kernel/Stubs/Helpers/Support.h defines its state in an anonymous namespace, so
// each of the nineteen stub translation units that pull it in through Stubs/Common.h gets its own
// private copy. 955539c moved the whole 2041-line header to a .cpp in one go -- one definition
// instead of nineteen -- the C++ suite stayed green, and the gate's mission stage then never
// reached the HUD. It was reverted. This suite is what makes the same move safe one subsystem at a
// time: for each subsystem moved to a named struct, a test that a SECOND translation unit
// (runtime_state_alias_probe.cpp) and the stub that actually reads the state both see the one
// instance -- so a regression to per-TU copies fails here rather than in a 280-second gate run.
//
// Each case does it twice over:
//   1. address identity  -- this TU and the probe TU name the same object;
//   2. cross-TU observation -- the test TU writes (or reads) the state and a stub compiled in a
//      DIFFERENT translation unit sees (or produced) it. This second half is the one that goes red
//      before the subsystem is moved, because the stub is still reading its own private copy.

#include "MiniTest.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_stubs.h"
#include "Kernel/Stubs/Unimplemented.h"
#include "Kernel/Stubs/Helpers/StubLogRuntimeState.h"

#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

namespace ps2x_test_rtstate_probe
{
    const void *stubLogStateAddress();
}

namespace
{
    // A stub name no other test uses, so the shared counter's value is ours alone.
    const char *const kProbeStubName = "s11t8b_probe_stub";
}

void register_runtime_state_tests()
{
    MiniTest::Case("Kernel stub runtime state (Sprint 11 Task 8b)", [](TestCase &tc)
    {
        tc.Run("StubLogRuntimeState is one object across translation units", [](TestCase &t)
        {
            t.Equals(static_cast<const void *>(&ps2_stubs::stubLogRuntimeState()),
                     ps2x_test_rtstate_probe::stubLogStateAddress(),
                     "runtime_state_tests.cpp and runtime_state_alias_probe.cpp must name one "
                     "StubLogRuntimeState; two addresses means the header is handing every "
                     "translation unit its own copy again (docs/KNOWN.md #4)");
        });

        tc.Run("Stubs/Unimplemented.cpp shares the stub-warning counter with this TU", [](TestCase &t)
        {
            ps2_stubs::StubLogRuntimeState &state = ps2_stubs::stubLogRuntimeState();
            {
                std::lock_guard<std::mutex> lock(state.warningMutex);
                state.warningCount.erase(kProbeStubName);
            }

            // TODO_NAMED lives in Stubs/Unimplemented.cpp -- a different translation unit. It bumps
            // the counter and then throws (its first kMaxStubWarningsPerName calls do).
            R5900Context ctx{};
            bool threw = false;
            try
            {
                ps2_stubs::TODO_NAMED(kProbeStubName, nullptr, &ctx, nullptr);
            }
            catch (const std::runtime_error &)
            {
                threw = true;
            }
            t.IsTrue(threw, "TODO_NAMED should still throw on an unimplemented stub");

            uint32_t seen = 0;
            {
                std::lock_guard<std::mutex> lock(state.warningMutex);
                auto it = state.warningCount.find(kProbeStubName);
                if (it != state.warningCount.end())
                    seen = it->second;
            }
            t.Equals(seen, 1u,
                     "the counter this TU reads should hold the call Stubs/Unimplemented.cpp just "
                     "made; 0 means that TU bumped its own private copy");
        });
    });
}
