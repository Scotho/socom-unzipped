#pragma once

#include "ps2_syscalls.h"

namespace ps2_syscalls
{
    // Runs the guest's registered handler for this syscall, if there is one the runtime can
    // execute. It either does not return (the handler runs as a scheduler invocation, which is
    // [[noreturn]]) or returns having changed nothing, so the caller always goes on to the
    // built-in: since Sprint 11 Task 19 there is no "claimed with an error" answer for the
    // caller to distinguish, and a bool return would document a contract this cannot honour.
    void dispatchSyscallOverride(uint32_t syscallNumber, uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GsSetCrt(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void SetGsCrt(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GsGetIMR(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void iGsGetIMR(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GsPutIMR(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void iGsPutIMR(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GsSetVideoMode(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GetOsdConfigParam(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void SetOsdConfigParam(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void SetOsdConfigParam2(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GetOsdConfigParam2(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GetRomName(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void SifLoadElfPart(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceSifLoadElf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceSifLoadElfPart(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceSifLoadModule(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sceSifLoadModuleBuffer(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void TODO(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime, uint32_t encodedSyscallId);
    void initializeGuestKernelState(uint8_t *rdram, PS2Runtime *runtime);
    void SetSyscall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void SetupThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void SetupHeap(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void EndOfHeap(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GetMemorySize(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void InitTLB(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void FindAddress(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void Deci2Call(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void QueryBootMode(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GetThreadTLS(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void Copy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void GetEntryAddress(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void RegisterExitHandler(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
}
