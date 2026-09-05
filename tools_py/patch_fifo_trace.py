"""Add PS2X_TRACE_FIFO=1 tracing of the VIF1/GIF/fromSPR DMA and INTC path, to diagnose the
frame-0 render-thread bootstrap deadlock.  Idempotent."""
rt = 'C:/projects/socom_pc/third_party/ps2recomp/ps2xRuntime/'


def patch(path, pairs, marker):
    s = open(path, encoding='utf-8').read()
    if marker in s:
        print(path, 'already patched')
        return
    for old, new in pairs:
        assert old in s, path + ' :: ' + old[:70]
        s = s.replace(old, new, 1)
    open(path, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched', path)


# a shared trace helper in ps2_memory.cpp
patch(rt + 'src/lib/ps2_memory.cpp', [
    ('#include <cstring>\n',
     '#include <cstring>\n#include <cstdlib>\n#include <cstdio>\nstatic const bool g_traceFifo = (std::getenv("PS2X_TRACE_FIFO") != nullptr);\n', ),
    # trace VIF1/GIF/fromSPR/toSPR CHCR starts inside writeIORegister's DMAC block
    ('            const uint32_t channelBase = address & 0xFFFFFF00;\n            const uint32_t madr = m_ioRegisters[channelBase + 0x10];\n            const uint32_t qwc = m_ioRegisters[channelBase + 0x20];\n            m_dmaStartCount.fetch_add(1, std::memory_order_relaxed);\n',
     '            const uint32_t channelBase = address & 0xFFFFFF00;\n            const uint32_t madr = m_ioRegisters[channelBase + 0x10];\n            const uint32_t qwc = m_ioRegisters[channelBase + 0x20];\n            m_dmaStartCount.fetch_add(1, std::memory_order_relaxed);\n            if (g_traceFifo)\n                std::fprintf(stderr, "[fifo] CHCR w ch=%08x val=%08x madr=%08x qwc=%08x tadr=%08x mfd=%x\\n", channelBase, value, madr, qwc, m_ioRegisters[channelBase+0x30], (m_ioRegisters.count(0x1000E000u)?((m_ioRegisters[0x1000E000u]>>2)&3):0));\n'),
    # trace VIF1 stall / end
    ('                    if (mfifoDrain)\n                    {\n                        m_mfifoStalled = mfifoStalledNow;\n                        m_mfifoStalledChannel = mfifoStalledNow ? channelBase : 0u;',
     '                    if (g_traceFifo && mfifoDrain)\n                        std::fprintf(stderr, "[fifo] drain ch=%08x tags=%d stalled=%d chainBytes=%zu newTadr=%08x\\n", channelBase, tagsProcessed, (int)mfifoStalledNow, chainBuf.size(), ringWrap(tagAddr));\n                    if (mfifoDrain)\n                    {\n                        m_mfifoStalled = mfifoStalledNow;\n                        m_mfifoStalledChannel = mfifoStalledNow ? channelBase : 0u;'),
], 'g_traceFifo')

# trace the VIF1 INTC raise
patch(rt + 'src/lib/ps2_vif1_interpreter.cpp', [
    ('            queueIntcCause(5u);           // EE INTC VIF1 -> game\'s render-thread waker',
     '            queueIntcCause(5u);           // EE INTC VIF1 -> game\'s render-thread waker\n            if (std::getenv("PS2X_TRACE_FIFO")) std::fprintf(stderr, "[fifo] VIF1 interrupt VIFcode -> INTC5\\n");'),
    ('#include', '#include <cstdlib>\n#include <cstdio>\n#include', ),
], 'INTC5"')

# trace dispatchIrq + thread wake/sleep in the scheduler
patch(rt + 'src/lib/Kernel/EeScheduler.cpp', [
    ('void EeScheduler::dispatchIrq(bool dmac, uint32_t cause)\n{\n    assertExecutor();',
     'void EeScheduler::dispatchIrq(bool dmac, uint32_t cause)\n{\n    assertExecutor();\n    if (std::getenv("PS2X_TRACE_FIFO")) std::fprintf(stderr, "[fifo] dispatchIrq dmac=%d cause=%u\\n", (int)dmac, cause);'),
], '[fifo] dispatchIrq')
