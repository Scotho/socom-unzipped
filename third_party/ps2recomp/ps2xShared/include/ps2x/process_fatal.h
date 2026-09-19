#pragma once
// Sprint 9 Goal 1: the two endings no check can see coming -- out of memory, and a crash -- and the
// switch that lets a test drive each on purpose.
namespace ProcessFatal
{
    // std::set_new_handler: "[oom] exit 71 out-of-memory: <sentence>" on stderr, then _Exit(71). The
    // handler allocates nothing and is safe from any thread.
    void installOutOfMemoryHandler();

    // "crash": writes through a null pointer; the process dies the native way (R128). "oom": asks for
    // memory no machine has; the handler above leaves with 71. Neither returns. Anything else returns
    // ExitCodes::kFailed.
    int failTest(const char *kind);
}
