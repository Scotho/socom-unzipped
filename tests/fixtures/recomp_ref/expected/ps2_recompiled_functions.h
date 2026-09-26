#ifndef PS2_RECOMPILED_FUNCTIONS_H
#define PS2_RECOMPILED_FUNCTIONS_H

#include <cstdint>

struct R5900Context;
class PS2Runtime;

void FUN_00100000_0x100000(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime);
void sceVu0MulMatrix_0x100010(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime);

#endif // PS2_RECOMPILED_FUNCTIONS_H
