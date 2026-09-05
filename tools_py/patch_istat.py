"""Implement EE INTC I_STAT (0x1000F000): raise VBLANK bits on the scheduler's vblank events,
and make I_STAT write-1-to-clear.  The engine's vsync wait (FUN_001a3fb0) clears I_STAT bit 2
and polls it until the next vblank sets it; without this the frame-pacing loop spins forever.
Idempotent."""
rt = 'C:/projects/socom_pc/third_party/ps2recomp/ps2xRuntime/'


def patch(path, pairs, marker):
    s = open(path, encoding='utf-8').read()
    if marker in s:
        print(path, 'already patched')
        return
    for old, new in pairs:
        assert old in s, path + ' :: ' + repr(old[:70])
        s = s.replace(old, new, 1)
    open(path, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched', path)


# 1. PS2Memory header: declare raiseIntcStatBit
patch(rt + 'include/runtime/ps2_memory.h', [
    ("    void queueIntcCause(uint32_t cause);",
     "    void queueIntcCause(uint32_t cause);\n    void raiseIntcStatBit(uint32_t bit);   // set I_STAT (0x1000F000) bit and OR into pending causes"),
], 'raiseIntcStatBit')

# 2. PS2Memory cpp: implement it + I_STAT read + write-1-to-clear
patch(rt + 'src/lib/ps2_memory.cpp', [
    ("void PS2Memory::queueIntcCause(uint32_t cause)\n{",
     "void PS2Memory::raiseIntcStatBit(uint32_t bit)\n{\n    m_ioRegisters[0x1000F000u] |= (1u << bit);\n}\n\nvoid PS2Memory::queueIntcCause(uint32_t cause)\n{"),
    # write-1-to-clear for I_STAT, inside writeIORegister (before the final return false)
    ("    if (address >= 0x10000000 && address < 0x10010000)\n    {\n        if (address >= 0x10000200 && address < 0x10000300)\n        {\n            return true;\n        }",
     "    if (address == 0x1000F000u)   // I_STAT: write-1-to-clear\n    {\n        m_ioRegisters[0x1000F000u] &= ~value;\n        return true;\n    }\n    if (address == 0x1000F010u)   // I_MASK: toggles on write\n    {\n        m_ioRegisters[0x1000F010u] ^= value;\n        return true;\n    }\n    if (address >= 0x10000000 && address < 0x10010000)\n    {\n        if (address >= 0x10000200 && address < 0x10000300)\n        {\n            return true;\n        }"),
    # I_STAT read
    ("    if (address >= 0x10000000 && address < 0x10010000)\n    {\n        if (address >= 0x10008000 && address < 0x1000F000)\n        {\n            if ((address & 0xFF) == 0x00)",
     "    if (address == 0x1000F000u)\n    {\n        return m_ioRegisters.count(0x1000F000u) ? m_ioRegisters[0x1000F000u] : 0u;\n    }\n    if (address == 0x1000F010u)\n    {\n        return m_ioRegisters.count(0x1000F010u) ? m_ioRegisters[0x1000F010u] : 0u;\n    }\n    if (address >= 0x10000000 && address < 0x10010000)\n    {\n        if (address >= 0x10008000 && address < 0x1000F000)\n        {\n            if ((address & 0xFF) == 0x00)"),
], 'raiseIntcStatBit')

# 3. scheduler: raise I_STAT bits on vblank + VIF1
patch(rt + 'src/lib/Kernel/EeScheduler.cpp', [
    ("        dispatchIrq(false, 2u);\n        break;\n    case EeEventType::ExternalWake:",
     "        m_runtime.memory().raiseIntcStatBit(2u);\n        dispatchIrq(false, 2u);\n        break;\n    case EeEventType::ExternalWake:"),
    ("        dispatchIrq(false, 3u);",
     "        m_runtime.memory().raiseIntcStatBit(3u);\n        dispatchIrq(false, 3u);"),
], 'raiseIntcStatBit(2u)')

# 4. runtime: raise I_STAT bit for drained INTC causes (VIF1=5, etc.)
patch(rt + 'src/lib/ps2_runtime.cpp', [
    ("    for (uint32_t cause : m_memory.consumePendingIntcCauses())\n    {\n        (void)rdram;\n        m_eeScheduler->dispatchIrq(false, cause);\n    }",
     "    for (uint32_t cause : m_memory.consumePendingIntcCauses())\n    {\n        (void)rdram;\n        m_memory.raiseIntcStatBit(cause);\n        m_eeScheduler->dispatchIrq(false, cause);\n    }"),
], 'raiseIntcStatBit(cause)')
