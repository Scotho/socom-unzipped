#include "Common.h"
#include "DMA.h"

namespace ps2_stubs
{
    namespace
    {
        constexpr uint32_t DMA_REG_CTRL = 0x1000E000u;
        constexpr uint32_t DMA_REG_PCR = 0x1000E020u;
        constexpr uint32_t DMA_REG_SQWC = 0x1000E030u;
        constexpr uint32_t DMA_REG_RBSR = 0x1000E040u;
        constexpr uint32_t DMA_REG_RBOR = 0x1000E050u;
        constexpr uint32_t DMA_REG_STADR = 0x1000E060u;

        constexpr std::array<uint8_t, 10> kStsTable = {0u, 0u, 0u, 3u, 0u, 1u, 0u, 0u, 2u, 0u};
        constexpr std::array<uint8_t, 10> kStdTable = {0u, 1u, 2u, 0u, 0u, 0u, 3u, 0u, 0u, 0u};
        constexpr std::array<uint8_t, 10> kMfdTable = {0u, 2u, 3u, 0u, 0u, 0u, 0u, 0u, 0u, 0u};

        // SceDmaEnv, the environment block and the in-flight model all live in
        // Helpers/DmaRuntimeState.h now, owned by the runtime (Task 8b, review F2).
    }

    void DmaAddr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnU32(ctx, getRegU32(ctx, 4));
    }

    void sceDmaCallback(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaCallback", rdram, ctx, runtime);
    }

    void sceDmaDebug(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaDebug", rdram, ctx, runtime);
    }

    void sceDmaGetChan(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t chanArg = getRegU32(ctx, 4);
        const uint32_t channelBase = resolveDmaChannelBase(rdram, chanArg);
        setReturnU32(ctx, channelBase);
    }

    void sceDmaGetEnv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t envAddr = getRegU32(ctx, 4);
        if (uint8_t *dst = getMemPtr(rdram, envAddr))
        {
            DmaRuntimeState &state = dmaRuntimeStateFor(runtime);
            std::lock_guard<std::mutex> lock(state.environmentMutex);
            std::memcpy(dst, &state.currentEnvironment, sizeof(state.currentEnvironment));
        }
        setReturnU32(ctx, envAddr);
    }

    void sceDmaLastSyncTime(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaLastSyncTime", rdram, ctx, runtime);
    }

    void sceDmaPause(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaPause", rdram, ctx, runtime);
    }

    void sceDmaPutEnv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t envAddr = getRegU32(ctx, 4);
        const uint8_t *src = getConstMemPtr(rdram, envAddr);
        if (!src || !runtime)
        {
            setReturnS32(ctx, -1);
            return;
        }

        SceDmaEnv env{};
        std::memcpy(&env, src, sizeof(env));

        if (env.sts >= kStsTable.size())
        {
            setReturnS32(ctx, -1);
            return;
        }
        if (env.std >= kStdTable.size())
        {
            setReturnS32(ctx, -2);
            return;
        }
        if (env.mfd >= kMfdTable.size())
        {
            setReturnS32(ctx, -3);
            return;
        }
        if (env.rele >= 7u)
        {
            setReturnS32(ctx, -4);
            return;
        }

        PS2Memory &mem = runtime->memory();
        uint32_t ctrl = mem.readIORegister(DMA_REG_CTRL);
        ctrl = (ctrl & 0xFFFFFFCFu) | (static_cast<uint32_t>(kStsTable[env.sts]) << 4);
        ctrl = (ctrl & 0xFFFFFF3Fu) | (static_cast<uint32_t>(kStdTable[env.std]) << 6);
        ctrl = (ctrl & 0xFFFFFFF3u) | (static_cast<uint32_t>(kMfdTable[env.mfd]) << 2);
        if (env.rele == 0u)
        {
            ctrl &= 0xFFFFFFFDu;
        }
        else
        {
            ctrl = ((ctrl | 0x2u) & 0xFFFFFCFFu) | ((static_cast<uint32_t>(env.rele - 1u) & 0x7u) << 8);
        }

        mem.writeIORegister(DMA_REG_CTRL, ctrl);
        mem.writeIORegister(DMA_REG_PCR, env.pcr);
        mem.writeIORegister(DMA_REG_SQWC, env.sqwc);
        mem.writeIORegister(DMA_REG_RBOR, env.rbor);
        mem.writeIORegister(DMA_REG_RBSR, env.rbsr);

        {
            DmaRuntimeState &state = dmaRuntimeStateFor(runtime);
            std::lock_guard<std::mutex> lock(state.environmentMutex);
            state.currentEnvironment = env;
        }

        setReturnS32(ctx, 0);
    }

    void sceDmaPutStallAddr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t newAddr = getRegU32(ctx, 4);
        uint32_t oldAddr = 0;
        if (runtime)
        {
            PS2Memory &mem = runtime->memory();
            oldAddr = mem.readIORegister(DMA_REG_STADR);
            if (newAddr != 0xFFFFFFFFu)
            {
                mem.writeIORegister(DMA_REG_STADR, newAddr);
            }
        }
        setReturnU32(ctx, oldAddr);
    }

    void sceDmaRecv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaRecv", rdram, ctx, runtime);
    }

    void sceDmaRecvI(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaRecvI", rdram, ctx, runtime);
    }

    void sceDmaRecvN(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaRecvN", rdram, ctx, runtime);
    }

    void sceDmaReset(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (runtime)
        {
            PS2Memory &mem = runtime->memory();

            // libdma reset leaves the controller runnable; DMAE must be re-enabled or chain submissions will be accepted but never execute.
            mem.writeIORegister(DMA_REG_CTRL, 0u);
            mem.writeIORegister(DMA_REG_PCR, 0u);
            mem.writeIORegister(DMA_REG_SQWC, 0u);
            mem.writeIORegister(DMA_REG_RBOR, 0u);
            mem.writeIORegister(DMA_REG_RBSR, 0u);
            mem.writeIORegister(DMA_REG_STADR, 0u);
            mem.writeIORegister(DMA_REG_CTRL, 1u);
        }

        // A controller reset means no transfer is in flight: clear the pending-poll map with
        // the environment block, which is the fork's resetDmaState (its Stubs/DMA.cpp:91-97) and
        // closes the asymmetry our version had.
        dmaRuntimeStateFor(runtime).reset();

        setReturnS32(ctx, 0);
    }

    void sceDmaRestart(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaRestart", rdram, ctx, runtime);
    }

    void sceDmaSend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx, submitDmaSend(rdram, ctx, runtime, false));
    }

    void sceDmaSendI(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx, submitDmaSend(rdram, ctx, runtime, false));
    }

    void sceDmaSendM(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx, submitDmaSend(rdram, ctx, runtime, false));
    }

    void sceDmaSendN(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx, submitDmaSend(rdram, ctx, runtime, true));
    }

    void sceDmaSync(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx, submitDmaSync(rdram, ctx, runtime));
    }

    void sceDmaSyncN(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        setReturnS32(ctx, submitDmaSync(rdram, ctx, runtime));
    }

    void sceDmaWatch(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        TODO_NAMED("sceDmaWatch", rdram, ctx, runtime);
    }
}
