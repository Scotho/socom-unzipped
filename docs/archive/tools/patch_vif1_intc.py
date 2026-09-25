# ARCHIVED 2026-09-25 (Sprint 13 Task H4, harness audit H27/H28) -- was tools_py/patch_vif1_intc.py.
#   A one-off source patcher: INTC cause 5 (VIF1) raised on interrupt VIFcodes. Applied and committed in 4716869a, 2026-09-05, the last time it mattered.
#   It rewrote files under third_party/ps2recomp/ps2xRuntime/ in place, at the owner's absolute path. The change
#   has lived in the runtime's own source since that commit; run now, it would patch the tree a second time or
#   fail an assert. The raise below keeps it from running. Nothing here is an instruction.
raise SystemExit("archived 2026-09-25 (Sprint 13 Task H4): a one-off source patcher, long applied; it writes into the vendored runtime -- do not run it")
"""Raise EE INTC cause 5 (VIF1) when the VIF1 interpreter processes a VIFcode with the interrupt
bit set, so the game's registered INTC-5 handler (which wakes the render thread) runs.  Adds a
pending-INTC-cause queue to PS2Memory, drained by the runtime into EeScheduler::dispatchIrq.
Idempotent."""

rt = 'C:/projects/socom_pc/third_party/ps2recomp/ps2xRuntime/'


def patch(path, pairs, marker):
    s = open(path, encoding='utf-8').read()
    if marker in s:
        print(path, 'already patched')
        return
    for old, new in pairs:
        assert old in s, path + ' :: ' + old[:60]
        s = s.replace(old, new, 1)
    open(path, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched', path)


# 1. header: queue + API
patch(rt + 'include/runtime/ps2_memory.h', [
    ("    std::vector<uint32_t> consumeCompletedDmacCauses();",
     "    std::vector<uint32_t> consumeCompletedDmacCauses();\n"
     "    // EE INTC unit interrupts (VIF1 = 5, etc.) raised from the VIF/GIF interpreters.\n"
     "    void queueIntcCause(uint32_t cause);\n"
     "    std::vector<uint32_t> consumePendingIntcCauses();"),
    ("    std::mutex m_completedDmacMutex;",
     "    std::mutex m_completedDmacMutex;\n    std::vector<uint32_t> m_pendingIntcCauses;\n    std::mutex m_pendingIntcMutex;"),
], 'consumePendingIntcCauses')

# 2. cpp: implement queue + raise in VIF1
patch(rt + 'src/lib/ps2_memory.cpp', [
    ("void PS2Memory::queueCompletedDmacCause(uint32_t cause)\n{",
     "void PS2Memory::queueIntcCause(uint32_t cause)\n"
     "{\n"
     "    std::lock_guard<std::mutex> lock(m_pendingIntcMutex);\n"
     "    m_pendingIntcCauses.push_back(cause);\n"
     "}\n\n"
     "std::vector<uint32_t> PS2Memory::consumePendingIntcCauses()\n"
     "{\n"
     "    std::lock_guard<std::mutex> lock(m_pendingIntcMutex);\n"
     "    std::vector<uint32_t> causes;\n"
     "    causes.swap(m_pendingIntcCauses);\n"
     "    return causes;\n"
     "}\n\n"
     "void PS2Memory::queueCompletedDmacCause(uint32_t cause)\n{"),
], 'PS2Memory::queueIntcCause')

patch(rt + 'src/lib/ps2_vif1_interpreter.cpp', [
    ("        vif1_regs.code = cmd;\n        vif1_regs.num = num;\n        if (irq)\n            vif1_regs.stat |= (1u << 11); // INT",
     "        vif1_regs.code = cmd;\n        vif1_regs.num = num;\n        if (irq)\n        {\n"
     "            vif1_regs.stat |= (1u << 11); // INT\n"
     "            queueIntcCause(5u);           // EE INTC VIF1 -> game's render-thread waker\n        }"),
], 'render-thread waker')

# 3. runtime: drain INTC causes alongside DMAC causes
patch(rt + 'src/lib/ps2_runtime.cpp', [
    ("void PS2Runtime::drainCompletedDmacHandlers(uint8_t *rdram)\n{\n    for (uint32_t cause : m_memory.consumeCompletedDmacCauses())\n    {\n        ps2_syscalls::dispatchDmacHandlersForCause(rdram, this, cause);\n    }",
     "void PS2Runtime::drainCompletedDmacHandlers(uint8_t *rdram)\n{\n    for (uint32_t cause : m_memory.consumeCompletedDmacCauses())\n    {\n        ps2_syscalls::dispatchDmacHandlersForCause(rdram, this, cause);\n    }\n"
     "    for (uint32_t cause : m_memory.consumePendingIntcCauses())\n    {\n        (void)rdram;\n        m_eeScheduler->dispatchIrq(false, cause);\n    }"),
], 'consumePendingIntcCauses()')
