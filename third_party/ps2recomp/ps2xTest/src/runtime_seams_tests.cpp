// Sprint 13 Task C8 (audit F22): the runtime links without a game file.
//
// PS2Runtime::run calls ps2HostProfStart and the VIF1/VU1/GS trace modes read g_ps2xTraceArmed; both used to be
// defined only in game_overrides_socom2.cpp, so libps2_runtime.a had them undefined (llvm-nm on the 2026-09-25
// build-clang library: `U ps2HostProfStart(void*)` in ps2_runtime.cpp.obj, `U g_ps2xTraceArmed` in three objects,
// with no definition anywhere in the archive) and this binary and vu1_replay each carried a stand-in to link. That
// was the RED: this suite's executable no longer compiles socom2_link_stubs.cpp, and it links only because the
// runtime now owns both -- a weak no-op ps2HostProfStart the runner overrides (runtime/host_prof_start.h) and the
// latch itself (runtime/ps2_trace_armed.h). The cases below are the runtime's defaults as this binary sees them.
#include "MiniTest.h"
#include "runtime/host_prof_start.h"
#include "runtime/ps2_trace_armed.h"

#include <thread>

void register_runtime_seams_tests()
{
    MiniTest::Case("RuntimeSeams", [](TestCase &tc)
    {
        tc.Run("ps2HostProfStart resolves to the runtime's default, which starts nothing", [](TestCase &t)
        {
            // Linking this call at all is the point (no game file in this binary, so the weak default is what resolves);
            // the default ignores the handle and returns.
            ps2HostProfStart(std::thread::native_handle_type{});
            t.IsFalse(g_ps2xTraceArmed.load(), "and arms nothing on the way");
        });

        tc.Run("the PS2X_TRIGGER latch is the runtime's and starts disarmed", [](TestCase &t)
        {
            t.IsFalse(g_ps2xTraceArmed.load(), "never armed outside the runner");
        });
    });
}
