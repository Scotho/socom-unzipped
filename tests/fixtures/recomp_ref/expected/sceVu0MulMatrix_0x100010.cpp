#include <stdexcept>
#include "ps2_runtime_macros.h"
#include "ps2_runtime.h"

#include "ps2_syscalls.h"
#include "ps2_stubs.h"

#ifdef PS2_FUNCTION_LOG_TRACKER
#include "ps2_log.h"
#endif

// Function: sceVu0MulMatrix
// Name source: names.csv row 0x00100010 (map name sub_00100010)
// Address: 0x100010 - 0x100020
void sceVu0MulMatrix_0x100010(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {
#ifdef PS2_FUNCTION_LOG_TRACKER
    PS_LOG_ENTRY("sceVu0MulMatrix_0x100010");
#endif

    ctx->pc = 0x100010u;

    // 0x100010: 0x0  nop
    ctx->pc = 0x100010u;
    // NOP
    // 0x100014: 0x0  nop
    ctx->pc = 0x100014u;
    // NOP
    // 0x100018: 0x3e00008  jr          $ra
    ctx->pc = 0x100018u;
    {
        const uint32_t jumpTarget = GPR_U32(ctx, 31);
        ctx->pc = jumpTarget;
        #if defined(PS2X_STRICT_RETURN_DIAGNOSTICS) && PS2X_STRICT_RETURN_DIAGNOSTICS
        (void)runtime->dispatchGuestBranch(rdram, ctx, jumpTarget, 0x100018u, 0u, PS2Runtime::GuestBranchKind::Return, "JR $ra");
        return;
        #else
        ctx->pc = jumpTarget;
        return;
        #endif
    }
    ctx->pc = 0x100020u;
}
