#include "ps2x/process_fatal.h"

#include "ps2x/exit_codes.h"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace ProcessFatal
{
    namespace
    {
        void onOutOfMemory()
        {
            // No allocation, no iostream: the heap is what just failed.
            std::fputs("[oom] exit 71 out-of-memory: ", stderr);
            if (const ExitCodes::Entry *e = ExitCodes::find(ExitCodes::kOutOfMemory))
                std::fputs(e->sentence, stderr);
            std::fputs("\n", stderr);
            std::fflush(stderr);
            std::fflush(stdout);
            std::_Exit(ExitCodes::kOutOfMemory);
        }

        void *volatile g_sink = nullptr;
    }

    void installOutOfMemoryHandler()
    {
        std::set_new_handler(onOutOfMemory);
    }

    int failTest(const char *kind)
    {
        if (kind != nullptr && std::strcmp(kind, "crash") == 0)
        {
#ifdef _WIN32
            // No "socom2.exe has stopped working" dialog in front of a test run.
            SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#endif
            std::fputs("[fail-test] crash: writing through a null pointer\n", stderr);
            std::fflush(stderr);
            volatile int *nowhere = nullptr;
            *nowhere = 1;
            std::abort();   // not reached; SIGABRT / fast-fail still classifies as a crash
        }
        if (kind != nullptr && std::strcmp(kind, "oom") == 0)
        {
            std::fputs("[fail-test] oom: one allocation of half the address space\n", stderr);
            std::fflush(stderr);
            volatile std::size_t huge = static_cast<std::size_t>(-1) / 2;
            g_sink = ::operator new(huge);   // operator new calls the new_handler, which leaves with 71
            return ExitCodes::kFailed;       // reached only if the platform really had it
        }
        return ExitCodes::kFailed;
    }
}
