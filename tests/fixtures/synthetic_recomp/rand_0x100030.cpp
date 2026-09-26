#include "ps2_runtime.h"
#include "ps2_syscalls.h"
#include "ps2_stubs.h"
#ifdef _DEBUG
#include "ps2_log.h"
#endif

// Synthetic (Sprint 13 Task C1): a stub wrapper in the recompiler's shape. See README.md beside this file.
void rand_0x100030(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {
#ifdef _DEBUG
    PS_LOG_ENTRY("rand_0x100030");
#endif
    ctx->pc = getRegU32(ctx, 31);
    ps2_stubs::rand(rdram, ctx, runtime);
}
