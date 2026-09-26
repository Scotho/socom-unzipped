#include <stdexcept>
#include "ps2_runtime_macros.h"
#include "ps2_runtime.h"

#include "ps2_syscalls.h"
#include "ps2_stubs.h"

#ifdef PS2_FUNCTION_LOG_TRACKER
#include "ps2_log.h"
#endif

// Function: FUN_00100000
// Address: 0x100000 - 0x100010
void FUN_00100000_0x100000(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {
#ifdef PS2_FUNCTION_LOG_TRACKER
    PS_LOG_ENTRY("FUN_00100000_0x100000");
#endif

    switch (ctx->pc) {
        case 0x100008u: goto label_100008;
        default: break;
    }

    ctx->pc = 0x100000u;

    // 0x100000: 0xc040004  jal         func_100010
    ctx->pc = 0x100000u;
    SET_GPR_U32(ctx, 31, 0x100008u);
    ctx->pc = 0x100010u;
    if (!runtime->dispatchGuestBranch(rdram, ctx, 0x100010u, 0x100000u, 0x100008u, PS2Runtime::GuestBranchKind::DirectCall, "JAL")) {
        return;
    }
    ctx->pc = 0x100008u;
label_100008:
    // 0x100008: 0x3e00008  jr          $ra
    ctx->pc = 0x100008u;
    {
        const uint32_t jumpTarget = GPR_U32(ctx, 31);
        ctx->pc = jumpTarget;
        #if defined(PS2X_STRICT_RETURN_DIAGNOSTICS) && PS2X_STRICT_RETURN_DIAGNOSTICS
        (void)runtime->dispatchGuestBranch(rdram, ctx, jumpTarget, 0x100008u, 0u, PS2Runtime::GuestBranchKind::Return, "JR $ra");
        return;
        #else
        ctx->pc = jumpTarget;
        return;
        #endif
    }
    ctx->pc = 0x100010u;
}
