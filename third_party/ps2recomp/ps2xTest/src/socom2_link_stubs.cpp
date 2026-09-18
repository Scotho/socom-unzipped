// libps2_runtime.a references a handful of symbols that the SOCOM II runner defines in
// game_overrides_socom2.cpp, a translation unit attached to the ps2EntryRunner executable rather
// than to the static runtime library (ps2xRuntime/CMakeLists.txt explains why: its static
// self-registration objects would be dropped from a static lib). vu1_replay.cpp carries the same
// kind of definition for the same reason. The unit tests never run SOCOM code, so inert
// definitions are all the link needs.
#include <thread>
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_stubs.h"

#include <atomic>
#include <cstdint>

// PS2X_HOST_PROF host-thread sampler (ps2_runtime.cpp): never started in the test binary.
void ps2HostProfStart(std::thread::native_handle_type) {}   // the runtime's signature (a HANDLE on Windows, a pthread_t on Linux)

// Set by PS2X_TRIGGER in the runner, read by the "trig" trace modes in the VIF1/VU1/GS code.
// Never armed here.
std::atomic<bool> g_ps2xTraceArmed{false};

// Game-specific HLE handlers, resolved by name in game_overrides.cpp. Each returns to the caller
// ($ra) without touching guest memory or any return value.
namespace ps2_stubs
{
    static inline void returnToCaller(R5900Context *ctx) { ctx->pc = GPR_U32(ctx, 31); }

    void socom2_RsaGenerateKeyPair(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void socom2_LumReadPixel(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void scePad2Init(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void scePad2CreateSocket(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void scePad2GetState(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void scePad2Read(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void scePad2GetButtonInfo(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void scePad2GetButtonProfile(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void sceVibGetProfile(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
    void sceVibSetActParam(uint8_t *, R5900Context *ctx, PS2Runtime *) { returnToCaller(ctx); }
}
