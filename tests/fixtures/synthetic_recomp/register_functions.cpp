#include "ps2_runtime.h"
#include "ps2_recompiled_functions.h"
#include "ps2_stubs.h"
#include "ps2_recompiled_stubs.h"
#include "ps2_syscalls.h"

// Synthetic (Sprint 13 Task C1): the recompiler's dense function table over the toy program at
// 0x100000..0x100040 -- one slot per instruction word, each naming the function that owns the word.
// See README.md beside this file.

extern const uint32_t g_ps2RecompiledFunctionTableBase = 0x100000u;
extern const uint32_t g_ps2RecompiledFunctionTableEnd = 0x100040u;
extern const uint32_t g_ps2RecompiledFunctionTableSlotCount = 16u;
PS2Runtime::RecompiledFunction g_ps2RecompiledFunctionTable[16u] = {};

namespace {
struct GeneratedFunctionTableInitializer {
    GeneratedFunctionTableInitializer() {
        g_ps2RecompiledFunctionTable[0] = entry_0x100000; // 0x100000
        g_ps2RecompiledFunctionTable[1] = entry_0x100000; // 0x100004
        g_ps2RecompiledFunctionTable[2] = entry_0x100000; // 0x100008
        g_ps2RecompiledFunctionTable[3] = entry_0x100000; // 0x10000c
        g_ps2RecompiledFunctionTable[4] = entry_0x100000; // 0x100010
        g_ps2RecompiledFunctionTable[5] = entry_0x100000; // 0x100014
        g_ps2RecompiledFunctionTable[6] = entry_0x100000; // 0x100018
        g_ps2RecompiledFunctionTable[7] = entry_0x100000; // 0x10001c
        g_ps2RecompiledFunctionTable[8] = sub_00100020_0x100020; // 0x100020
        g_ps2RecompiledFunctionTable[9] = sub_00100020_0x100020; // 0x100024
        g_ps2RecompiledFunctionTable[10] = sub_00100020_0x100020; // 0x100028
        g_ps2RecompiledFunctionTable[11] = sub_00100020_0x100020; // 0x10002c
        g_ps2RecompiledFunctionTable[12] = rand_0x100030; // 0x100030
    }
};
static const GeneratedFunctionTableInitializer g_generatedFunctionTableInitializer;
}
