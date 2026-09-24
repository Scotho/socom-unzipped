#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct with ONE instance for the whole program, in place
// of the anonymous-namespace block in Helpers/Support.h that handed each of the nineteen stub
// translation units its own private copy (docs/KNOWN.md #4, the reverted 955539c).
//
// This group is the two stderr throttles. The stubs that read it:
//   Stubs/Unimplemented.cpp  TODO / TODO_NAMED  -> warningMutex, warningCount
//   Stubs/Compatibility.cpp  printf             -> printfMutex, printfLogCount
//   Stubs/LibC.cpp           printf             -> printfMutex, printfLogCount
//   Stubs/TTY.cpp            scePrintf          -> printfMutex, printfLogCount
//
// Behaviour note, because 955539c is the cautionary tale: warningCount was already effectively
// single-TU (only Unimplemented.cpp reads it), so sharing it is a no-op. printfLogCount was three
// separate 200-line budgets; it is now the one budget the message beside it has always claimed
// ("PS2 printf logging suppressed after 200 lines"). Nothing guest-visible reads either field --
// both gate stderr only -- so no guest state is aliased by this move.

#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>

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

        // "PS2 printf:" lines are printed at most kMaxPrintfLogs times per process.
        std::mutex printfMutex;
        uint32_t printfLogCount = 0;
    };

    // The single instance. A function-local static inside an `inline` function has exactly one
    // definition across every translation unit that includes this header -- which is precisely what
    // the anonymous namespace did not give us. ps2xTest/src/runtime_state_tests.cpp pins that.
    inline StubLogRuntimeState &stubLogRuntimeState()
    {
        static StubLogRuntimeState state;
        return state;
    }
}
