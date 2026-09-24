// Sprint 11 Task 8b: the SECOND translation unit of the *RuntimeState aliasing tests.
//
// runtime_state_tests.cpp is the first. This file exists only to include the same headers from a
// different translation unit and hand back the address each subsystem's state has HERE. If a
// header ever goes back to defining its state in an anonymous namespace (docs/KNOWN.md #4, the
// reverted 955539c), these addresses stop matching the ones the test file sees and the suite says
// so -- which is the whole point of the refactor.
//
// Nothing in here may be `inline`, `static` or in an anonymous namespace: that would defeat it.

#include "Kernel/Stubs/Helpers/StubLogRuntimeState.h"

namespace ps2x_test_rtstate_probe
{
    const void *stubLogStateAddress()
    {
        return &ps2_stubs::stubLogRuntimeState();
    }
}
