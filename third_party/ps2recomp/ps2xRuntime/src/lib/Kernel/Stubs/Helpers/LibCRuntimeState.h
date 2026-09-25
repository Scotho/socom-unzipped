#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct per subsystem, OWNED BY THE PS2Runtime that the
// stub was called with -- a std::unique_ptr member reached as runtime->libcRuntimeState(), which is
// the fork's shape (its ps2_runtime.h:2341-2344, and its own LibCRuntimeState.h, which likewise
// carries the FILE table and the rand state in one struct). It replaces the anonymous-namespace
// block in Helpers/Support.h that handed each of the nineteen stub translation units its own
// private copy (docs/KNOWN.md #4, the reverted 955539c), and it replaces the process-wide singleton
// that the first pass of this task put in its place.
//
// This group is the whole libc stub's mutable state: the FILE* table behind the guest's fopen
// handles, and the newlib rand()/srand() cursor. The stubs that read it:
//   Stubs/LibC.cpp  fopen  -> allocates a handle and records the FILE*
//                   fclose -> closes and erases it
//                   fread / fwrite / fseek / ftell / fgets / fprintf / feof
//                          -> resolve the handle through get()
//                   rand / srand / setLibcRandState -> randMutex, impurePtrAddr,
//                          randNextOffset, randNextFallback
//
// Behaviour note: Stubs/LibC.cpp is the only translation unit that reaches either group, so its
// copy was the only live one and making it per-runtime is a no-op for a single-runtime game. The
// FILE table is nonetheless the group whose aliasing would matter most if a second stub ever opened
// a guest FILE: two copies would hand out the same handle number for two different files.

#include <cstdint>
#include <cstdio>
#include <mutex>
#include <unordered_map>

class PS2Runtime;

namespace ps2_stubs
{
    struct LibCRuntimeState
    {
        ~LibCRuntimeState()
        {
            closeAllFiles();
        }

        // ---- the guest's FILE handles -------------------------------------------------------
        // `mutex` guards openFiles and nextHandle. Two conventions used to sit on it with only a
        // comment between them; the -Locked suffix is now the whole contract (Task 8b review F7):
        // a method named *Locked expects `mutex` held by the caller, and no other method here
        // takes `mutex` while one is held.
        std::mutex mutex;
        std::unordered_map<uint32_t, FILE *> openFiles;
        uint32_t nextHandle = 1;   // guest file handles are > 0 (0 is NULL)

        // Call with `mutex` held.
        uint32_t allocateHandleLocked()
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

        // Takes `mutex` itself. Never call it with `mutex` already held.
        FILE *get(uint32_t handle)
        {
            if (handle == 0)
                return nullptr;
            std::lock_guard<std::mutex> lock(mutex);
            auto it = openFiles.find(handle);
            return (it != openFiles.end()) ? it->second : nullptr;
        }

        // ---- newlib rand()/srand() ----------------------------------------------------------
        // randMutex serialises the stub against itself. It does NOT serialise it against the
        // guest: srand() is not stubbed (recomp/socom2.toml), so the recompiled FUN_00197728
        // writes the same word with no lock at all. That is harmless while EE code runs on one
        // host thread, which is the case today -- but if EE execution is ever parallelised, this
        // word has two writers and only one of them takes the mutex.
        std::mutex randMutex;
        uint32_t impurePtrAddr = 0u;    // guest address OF THE POINTER to struct _reent
        uint32_t randNextOffset = 0u;   // offset of _rand_next within struct _reent
        uint64_t randNextFallback = 1u; // newlib's static initialiser for _rand_next

        // Back to a freshly constructed runtime's libc SESSION state, open host files closed.
        // PS2Runtime::run() reaches it through resetStubRuntimeState(), beside resetSifState(),
        // resetIop(), resetAudioStubState() and resetMpegStubState(); a save-state restore
        // (Task 8c) is the other caller.
        //
        // impurePtrAddr and randNextOffset are deliberately NOT cleared. They are not guest state:
        // they are the game override's registration (setLibcRandState, from applySocom2, which
        // runs inside PS2Runtime::loadELF -- BEFORE run()), and clearing them on the run path
        // would silently drop rand() back to its internal cursor, which is the exact defect the
        // long comment above ps2_stubs::rand in Stubs/LibC.cpp records. resetMpegStubState()
        // leaves its own override-installed knob (g_mpegDemuxIdleYields) alone for the same
        // reason; this follows that convention rather than inventing a second one.
        void reset()
        {
            closeAllFiles();
            std::lock_guard<std::mutex> lock(randMutex);
            randNextFallback = 1u;
        }

    private:
        void closeAllFiles()
        {
            std::lock_guard<std::mutex> lock(mutex);
            for (auto &[handle, file] : openFiles)
            {
                (void)handle;
                if (file)
                {
                    std::fclose(file);
                }
            }
            openFiles.clear();
            nextHandle = 1u;
        }
    };

    // The state `runtime` owns. A null runtime is a stub reached with no runtime at all -- which
    // fopen, fclose and rand all allow -- and gets one process-wide fallback instance, the only
    // instance here that is not per-runtime.
    LibCRuntimeState &libcRuntimeStateFor(PS2Runtime *runtime);
}
