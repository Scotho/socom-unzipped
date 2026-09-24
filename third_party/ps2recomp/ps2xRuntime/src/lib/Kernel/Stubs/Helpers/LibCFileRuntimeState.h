#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct with ONE instance for the whole program, in place
// of the anonymous-namespace block in Helpers/Support.h that handed each of the nineteen stub
// translation units its own private copy (docs/KNOWN.md #4, the reverted 955539c).
//
// This group is the libc FILE* table behind the guest's fopen handles.
// The stubs that read it:
//   Stubs/LibC.cpp  fopen  -> allocates a handle and records the FILE*
//                   fclose -> closes and erases it
//                   fread / fwrite / fseek / ftell / fgets / fprintf / feof
//                          -> resolve the handle through get()
//
// Behaviour note: Stubs/LibC.cpp is the only translation unit that reaches this table, so its copy
// was the only live one and sharing one is a no-op for the guest. It is, however, the group whose
// aliasing would matter most if a second stub ever opened a guest FILE: two copies would hand out
// the same handle number for two different files.

#include <cstdint>
#include <cstdio>
#include <mutex>
#include <unordered_map>

namespace ps2_stubs
{
    struct LibCFileRuntimeState
    {
        // Call with `mutex` held.
        uint32_t allocateHandle()
        {
            uint32_t handle = 0;
            do
            {
                handle = nextHandle++;
                if (nextHandle == 0)
                    nextHandle = 1;   // handle 0 is the guest's NULL
            } while (handle == 0 || openFiles.count(handle));
            return handle;
        }

        FILE *get(uint32_t handle)
        {
            if (handle == 0)
                return nullptr;
            std::lock_guard<std::mutex> lock(mutex);
            auto it = openFiles.find(handle);
            return (it != openFiles.end()) ? it->second : nullptr;
        }

        std::mutex mutex;
        std::unordered_map<uint32_t, FILE *> openFiles;
        uint32_t nextHandle = 1;   // guest file handles are > 0 (0 is NULL)
    };

    // The single instance. A function-local static inside an `inline` function has exactly one
    // definition across every translation unit that includes this header -- which is precisely what
    // the anonymous namespace did not give us. ps2xTest/src/runtime_state_tests.cpp pins that.
    inline LibCFileRuntimeState &libcFileRuntimeState()
    {
        static LibCFileRuntimeState state;
        return state;
    }
}
