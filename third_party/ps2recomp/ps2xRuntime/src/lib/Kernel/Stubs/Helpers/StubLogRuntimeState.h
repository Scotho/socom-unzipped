#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct per subsystem, OWNED BY THE PS2Runtime that the
// stub was called with -- a std::unique_ptr member reached as runtime->stubLogRuntimeState(), which
// is the fork's shape (its ps2_runtime.h:2341-2344, 3724-3726). It replaces the anonymous-namespace
// block in Helpers/Support.h that handed each of the nineteen stub translation units its own private
// copy (docs/KNOWN.md #4, the reverted 955539c), and it replaces the process-wide singleton that the
// first pass of this task put in its place: two PS2Runtime instances in one process now share none
// of this, and Task 8c's save-state writer can enumerate it per runtime.
//
// This group is the two stderr throttles. The stubs that read it:
//   Stubs/Unimplemented.cpp  TODO / TODO_NAMED  -> warningMutex, warningCount
//   Stubs/Compatibility.cpp  printf             -> printfMutex, printfLogCount
//   Stubs/LibC.cpp           printf             -> printfMutex, printfLogCount
//   Stubs/TTY.cpp            scePrintf          -> printfMutex, printfLogCount
//
// Behaviour note, because 955539c is the cautionary tale: warningCount was already effectively
// single-TU (only Unimplemented.cpp reads it), so sharing it is a no-op. printfLogCount was three
// separate 200-line budgets and is now the one budget the message beside it has always claimed
// ("PS2 printf logging suppressed after 200 lines"), so a gate log can carry up to 400 fewer
// "PS2 printf:" / "PS2 scePrintf:" lines than the same run produced before this change and the
// suppression notice fires once per runtime rather than once per stub file. Nothing guest-visible
// reads either field -- both gate stderr only -- so no guest state is aliased by this move.

#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>

class PS2Runtime;

namespace ps2_stubs
{
    inline constexpr uint32_t kMaxStubWarningsPerName = 8;
    inline constexpr uint32_t kMaxPrintfLogs = 200;

    struct StubLogRuntimeState
    {
        // "Warning: Unimplemented PS2 stub called" is printed at most kMaxStubWarningsPerName
        // times per stub name; the count per name lives here.
        std::mutex warningMutex;
        std::unordered_map<std::string, uint32_t> warningCount;

        // "PS2 printf:" lines are printed at most kMaxPrintfLogs times per runtime.
        std::mutex printfMutex;
        uint32_t printfLogCount = 0;

        // Back to a freshly constructed runtime's throttles. PS2Runtime::resetStubRuntimeState()
        // calls it; no guest path does, because the EE stubs have no "reset the log budget"
        // service -- it is the entry point a save-state restore (Task 8c) needs.
        void reset()
        {
            std::lock_guard<std::mutex> warningLock(warningMutex);
            std::lock_guard<std::mutex> printfLock(printfMutex);
            warningCount.clear();
            printfLogCount = 0;
        }
    };

    // The state `runtime` owns. A null runtime is a stub reached with no runtime at all -- which
    // the EE stubs allow and several tests use -- and gets one process-wide fallback instance,
    // the only instance here that is not per-runtime.
    StubLogRuntimeState &stubLogRuntimeStateFor(PS2Runtime *runtime);
}
