#pragma once
// PS2X_HOST_PROF=<ms>: the host-level sampling profiler of the game thread. PS2Runtime::run calls this once, right
// after it creates the game thread, with the thread's native handle as std::thread hands it over: a HANDLE (void *)
// on Windows, a pthread_t on Linux (Sprint 8 Goal 1 design item 3).
//
// Sprint 13 Task C8 (audit F22): the runtime declares it and owns a WEAK no-op default (ps2_runtime.cpp), so the
// runtime library links on its own -- the test binary and any other executable need no stand-in. The SOCOM II runner
// supplies the real sampler with an ordinary (strong) definition in game_overrides_socom2.cpp, which the linker
// prefers over the weak one. Weak definitions are chosen over a function-pointer hook because both toolchains the
// project builds with take them: llvm-mingw's ld.lld on Windows (COFF weak externals, checked 2026-09-25 with a
// weak default in a static archive member overridden by a strong definition in an object, in either link order) and
// clang/lld on Linux (ELF STB_WEAK). A weak definition is never inlined into its caller, even in its own TU.
#include <thread>

#if defined(__clang__) || defined(__GNUC__)
#define PS2X_WEAK __attribute__((weak))
#else
#error "runtime/host_prof_start.h: PS2X_WEAK needs clang or GCC (the runtime's weak defaults)"
#endif

void ps2HostProfStart(std::thread::native_handle_type nativeHandle);
