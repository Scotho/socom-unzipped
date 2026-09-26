#include "ps2_runtime.h"
#include "ps2_recompiled_functions.h"
#include "ps2_stubs.h"
#include "ps2_recompiled_stubs.h"//this will give duplicated erros because runtime maybe has it define already, just delete the TODOS ones
#include "ps2_syscalls.h"

extern const uint32_t g_ps2RecompiledFunctionTableBase = 0x100000u;
extern const uint32_t g_ps2RecompiledFunctionTableEnd = 0x100014u;
extern const uint32_t g_ps2RecompiledFunctionTableSlotCount = 5u;
PS2Runtime::RecompiledFunction g_ps2RecompiledFunctionTable[5u] = {};

namespace {
struct GeneratedFunctionTableInitializer {
    GeneratedFunctionTableInitializer() {
        g_ps2RecompiledFunctionTable[0] = FUN_00100000_0x100000; // 0x100000
        g_ps2RecompiledFunctionTable[2] = FUN_00100000_0x100000; // 0x100008
        g_ps2RecompiledFunctionTable[4] = sceVu0MulMatrix_0x100010; // 0x100010
    }
};
static const GeneratedFunctionTableInitializer g_generatedFunctionTableInitializer;
}
