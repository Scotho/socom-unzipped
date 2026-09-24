#include "Common.h"
#include "Thread.h"
#include "runtime/ee_scheduler.h"
#include "ps2x/exit_codes.h"

namespace ps2_syscalls
{
    namespace
    {
        EeScheduler &scheduler(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
        {
            EeScheduler &result = runtime->eeScheduler();
            result.bindMainContextForSyscall(*ctx, rdram);
            return result;
        }

        int rawThreadStatus(EeThreadStatus status)
        {
            switch (status)
            {
            case EeThreadStatus::Running:
                return THS_RUN;
            case EeThreadStatus::Ready:
                return THS_READY;
            case EeThreadStatus::Waiting:
                return THS_WAIT;
            case EeThreadStatus::WaitingSuspended:
                return THS_WAITSUSPEND;
            case EeThreadStatus::Suspended:
                return THS_SUSPEND;
            case EeThreadStatus::Dormant:
                return THS_DORMANT;
            }
            return THS_DORMANT;
        }

        int rawWaitType(EeWaitReason reason)
        {
            switch (reason)
            {
            case EeWaitReason::Sleep:
                return TSW_SLEEP;
            case EeWaitReason::Semaphore:
                return TSW_SEMA;
            case EeWaitReason::EventFlag:
                return TSW_EVENT;
            case EeWaitReason::VSync:
                return 4;
            case EeWaitReason::External:
            case EeWaitReason::Mpeg:
                return 5;
            case EeWaitReason::None:
                return TSW_NONE;
            }
            return TSW_NONE;
        }

        int waitId(const GuestThread &thread)
        {
            if (thread.wait.reason == EeWaitReason::Semaphore)
            {
                return std::get<EeSemaphoreWait>(thread.wait.payload).id;
            }
            if (thread.wait.reason == EeWaitReason::EventFlag)
            {
                return std::get<EeEventFlagWait>(thread.wait.payload).id;
            }
            return 0;
        }

        [[noreturn]] void exitThreadWithHandlers(int tid,
                                                 R5900Context *ctx,
                                                 PS2Runtime *runtime,
                                                 bool deleteThread)
        {
            EeScheduler &ee = runtime->eeScheduler();
            const auto handlers = runtime->takeEeExitHandlers(tid);
            std::vector<GuestInvocation> invocations;
            invocations.reserve(handlers.size());
            for (const PS2Runtime::EeExitHandlerRegistration &handler : handlers)
            {
                if (handler.function == 0u || !runtime->hasFunction(handler.function))
                {
                    continue;
                }
                GuestInvocation invocation{};
                invocation.kind = GuestInvocationKind::ExitHandler;
                invocation.context = *ctx;
                invocation.context.pc = handler.function;
                SET_GPR_U32(&invocation.context, 4, handler.argument);
                SET_GPR_U32(&invocation.context, 29, ee.invocationStackTop());
                SET_GPR_U32(&invocation.context, 31, 0u);
                invocations.push_back(std::move(invocation));
            }
            if (invocations.empty())
            {
                ee.exitCurrent(deleteThread);
            }
            invocations.back().onComplete = [runtime, deleteThread](const R5900Context &, R5900Context &)
            {
                runtime->eeScheduler().exitCurrent(deleteThread);
            };
            ee.invokeCurrentSequence(std::move(invocations));
        }

        void changePriorityImpl(uint8_t *rdram,
                                R5900Context *ctx,
                                PS2Runtime *runtime,
                                bool interruptSafe)
        {
            EeScheduler &ee = scheduler(rdram, ctx, runtime);
            const int id = static_cast<int>(getRegU32(ctx, 4));
            const int priority = static_cast<int>(getRegU32(ctx, 5));
            int oldPriority = 0;
            const int result = ee.changePriority(id, priority, interruptSafe, oldPriority);
            setReturnS32(ctx, result);
            ee.transferIfRequested(interruptSafe);
        }

        void rotateReadyQueueImpl(uint8_t *rdram,
                                  R5900Context *ctx,
                                  PS2Runtime *runtime,
                                  bool interruptSafe)
        {
            EeScheduler &ee = scheduler(rdram, ctx, runtime);
            const int result = ee.rotateReadyQueue(static_cast<int>(getRegU32(ctx, 4)), interruptSafe);
            setReturnS32(ctx, result);
            ee.transferIfRequested(interruptSafe);
        }

        void wakeupThreadImpl(uint8_t *rdram,
                              R5900Context *ctx,
                              PS2Runtime *runtime,
                              bool interruptSafe)
        {
            EeScheduler &ee = scheduler(rdram, ctx, runtime);
            const int result = ee.wakeupThread(static_cast<int>(getRegU32(ctx, 4)), interruptSafe);
            setReturnS32(ctx, result);
            ee.transferIfRequested(interruptSafe);
        }

        void releaseWaitImpl(uint8_t *rdram,
                             R5900Context *ctx,
                             PS2Runtime *runtime,
                             bool interruptSafe)
        {
            EeScheduler &ee = scheduler(rdram, ctx, runtime);
            const int result = ee.releaseWait(static_cast<int>(getRegU32(ctx, 4)), interruptSafe);
            setReturnS32(ctx, result);
            ee.transferIfRequested(interruptSafe);
        }
    }

    void FlushCache(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        setReturnS32(ctx, KE_OK);
    }

    void iFlushCache(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        FlushCache(rdram, ctx, runtime);
    }

    void EnableCache(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        setReturnS32(ctx, KE_OK);
    }

    void DisableCache(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        setReturnS32(ctx, KE_OK);
    }

    void ResetEE(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        setReturnS32(ctx, KE_OK);
    }

    // LoadExecPS2(const char *filename, int argc, char **argv): the game asks the kernel to
    // replace itself with another ELF (self-relaunch with arguments, or the network GUI).
    // This runtime cannot re-exec, so the honest answer is to say so loudly and leave with a code
    // of its own (74, reboot-requested). Reaching here is the game's own decision -- SOCOM II's
    // FUN_0022ed10 tears the sound system and the SIF RPCs down and reboots into
    // "--menu_state dlgAfterErrorReboot.rdr" after an internal error -- so a log that states the
    // decision beats a process that dies further downstream (Sprint 11 Task 19).
    void LoadExecPS2(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t pathAddr = getRegU32(ctx, 4);
        const uint32_t argc = getRegU32(ctx, 5);
        const uint32_t argvAddr = getRegU32(ctx, 6);
        auto cstr = [rdram](uint32_t addr) {
            std::string out;
            for (uint32_t i = 0; addr && i < 256; ++i)
            {
                const char c = static_cast<char>(rdram[(addr + i) & PS2_RAM_MASK]);
                if (!c) break;
                out.push_back(c);
            }
            return addr ? out : std::string("<null>");
        };
        auto u32 = [rdram](uint32_t addr) {
            uint32_t v; std::memcpy(&v, rdram + (addr & PS2_RAM_MASK), 4); return v;
        };
        const std::string path = cstr(pathAddr);
        std::cerr << "[LoadExecPS2] path=\"" << path << "\" argc=" << argc;
        std::string argvLine;
        for (uint32_t i = 0; i < argc && i < 16; ++i)
        {
            const std::string arg = cstr(u32(argvAddr + i * 4));
            std::cerr << " argv[" << i << "]=\"" << arg << "\"";
            if (!argvLine.empty())
                argvLine.push_back(' ');
            argvLine += arg;
        }
        std::cerr << std::endl;
        const ExitCodes::Entry *code = ExitCodes::find(ExitCodes::kRebootRequested);
        std::cerr << "[LoadExecPS2] REBOOT requested: " << path
                  << (argvLine.empty() ? "" : " ") << argvLine
                  << " -- this build cannot re-exec; exiting with "
                  << ExitCodes::kRebootRequested << " ("
                  << (code ? code->slug : "reboot-requested") << ")." << std::endl;
        std::cerr.flush();
        std::exit(ExitCodes::kRebootRequested);
    }

    void SetMemoryMode(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        setReturnS32(ctx, KE_OK);
    }

    void InitThread(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        setReturnS32(ctx, EeScheduler::kMainThreadId);
    }

    void CreateThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t address = getRegU32(ctx, 4);
        if (address == 0u)
        {
            setReturnS32(ctx, KE_ERROR);
            return;
        }
        const auto *param = getEeGuestStruct<ee_thread_t>(rdram, address);
        if (!param)
        {
            setReturnS32(ctx, KE_ERROR);
            return;
        }

        if (param->stack_size < 0)
        {
            setReturnS32(ctx, KE_ERROR);
            return;
        }
        if (param->stack != 0u)
        {
            uint32_t stackOffset = 0u;
            bool scratch = false;
            if (!resolveEeGuestRange(param->stack,
                                     static_cast<size_t>(param->stack_size),
                                     stackOffset,
                                     scratch))
            {
                setReturnS32(ctx, KE_ERROR);
                return;
            }
        }

        // PS2SDK EE t_ee_thread: status, func, stack, stack_size, gp_reg,
        // initial_priority, current_priority, attr, option.
        const EeThreadCreateParams decoded{
            param->attr,
            param->func,
            param->stack,
            static_cast<uint32_t>(param->stack_size),
            param->gp_reg,
            param->initial_priority,
            param->option,
        };
        setReturnS32(ctx, scheduler(rdram, ctx, runtime).createThread(decoded));
    }

    void DeleteThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        const int id = static_cast<int>(getRegU32(ctx, 4));
        uint32_t ownedStack = 0;
        const int result = ee.deleteThread(id, ownedStack);
        if (result == KE_OK)
        {
            runtime->removeEeExitHandlers(id);
        }
        if (ownedStack != 0u)
        {
            runtime->guestFree(ownedStack);
        }
        setReturnS32(ctx, result);
    }

    void StartThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        const int id = static_cast<int>(getRegU32(ctx, 4));
        const uint32_t arg = getRegU32(ctx, 5);
        GuestThread *target = ee.thread(id);
        if (!target)
        {
            setReturnS32(ctx, KE_UNKNOWN_THID);
            return;
        }
        if (target->status != EeThreadStatus::Dormant)
        {
            setReturnS32(ctx, KE_NOT_DORMANT);
            return;
        }
        if (!runtime->hasFunction(target->entry))
        {
            setReturnS32(ctx, KE_ERROR);
            return;
        }
        if (target->stack == 0u && target->stackSize != 0u)
        {
            target->stack = runtime->guestMalloc(target->stackSize, 16u);
            if (target->stack == 0u)
            {
                setReturnS32(ctx, KE_ERROR);
                return;
            }
            target->ownsStack = true;
        }
        const int result = ee.startThread(id, arg, *ctx, false);
        setReturnS32(ctx, result);
        ee.transferIfRequested(false);
    }

    void ExitThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        exitThreadWithHandlers(ee.currentThreadId(), ctx, runtime, false);
    }

    void ExitDeleteThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        exitThreadWithHandlers(ee.currentThreadId(), ctx, runtime, true);
    }

    void TerminateThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        uint32_t ownedStack = 0;
        const int result = ee.terminateThread(static_cast<int>(getRegU32(ctx, 4)), ownedStack, false);
        if (ownedStack != 0u)
        {
            runtime->guestFree(ownedStack);
        }
        setReturnS32(ctx, result);
    }

    void SuspendThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        const int result = ee.suspendThread(static_cast<int>(getRegU32(ctx, 4)), false);
        setReturnS32(ctx, result);
        ee.transferIfRequested(false);
    }

    void ResumeThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        const int result = ee.resumeThread(static_cast<int>(getRegU32(ctx, 4)), false);
        setReturnS32(ctx, result);
        ee.transferIfRequested(false);
    }

    void GetThreadId(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx, scheduler(rdram, ctx, runtime).currentThreadId());
    }

    void ReferThreadStatus(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        int id = static_cast<int>(getRegU32(ctx, 4));
        if (id == 0)
        {
            id = ee.currentThreadId();
        }
        const GuestThread *thread = ee.thread(id);
        if (!thread)
        {
            setReturnS32(ctx, KE_UNKNOWN_THID);
            return;
        }
        auto *status = getEeGuestStruct<ee_thread_status_t>(rdram, getRegU32(ctx, 5));
        if (!status)
        {
            setReturnS32(ctx, KE_ERROR);
            return;
        }
        *status = {};
        status->status = rawThreadStatus(thread->status);
        status->func = thread->entry;
        status->stack = thread->stack;
        status->stack_size = static_cast<int>(thread->stackSize);
        status->gp_reg = thread->gp;
        status->initial_priority = thread->initialPriority;
        status->current_priority = thread->currentPriority;
        status->attr = thread->attr;
        status->option = thread->option;
        status->waitType = rawWaitType(thread->wait.reason);
        status->waitId = waitId(*thread);
        status->wakeupCount = thread->wakeupCount;
        setReturnS32(ctx, KE_OK);
    }

    void iReferThreadStatus(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        ReferThreadStatus(rdram, ctx, runtime);
    }

    void SleepThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        EeScheduler &ee = scheduler(rdram, ctx, runtime);
        ee.sleepCurrent();
        setReturnS32(ctx, KE_OK);
    }

    void WakeupThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        wakeupThreadImpl(rdram, ctx, runtime, false);
    }

    void iWakeupThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        wakeupThreadImpl(rdram, ctx, runtime, true);
    }

    void CancelWakeupThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx,
                     scheduler(rdram, ctx, runtime).cancelWakeup(static_cast<int>(getRegU32(ctx, 4))));
    }

    void iCancelWakeupThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (getRegU32(ctx, 4) == 0u)
        {
            setReturnS32(ctx, KE_ILLEGAL_THID);
            return;
        }
        CancelWakeupThread(rdram, ctx, runtime);
    }

    void ChangeThreadPriority(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        changePriorityImpl(rdram, ctx, runtime, false);
    }

    void iChangeThreadPriority(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        changePriorityImpl(rdram, ctx, runtime, true);
    }

    void RotateThreadReadyQueue(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        rotateReadyQueueImpl(rdram, ctx, runtime, false);
    }

    void iRotateThreadReadyQueue(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        rotateReadyQueueImpl(rdram, ctx, runtime, true);
    }

    void ReleaseWaitThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        releaseWaitImpl(rdram, ctx, runtime, false);
    }

    void iReleaseWaitThread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        releaseWaitImpl(rdram, ctx, runtime, true);
    }
}
