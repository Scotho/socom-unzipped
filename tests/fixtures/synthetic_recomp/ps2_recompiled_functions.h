#ifndef PS2_RECOMPILED_FUNCTIONS_H
#define PS2_RECOMPILED_FUNCTIONS_H

// Synthetic (Sprint 13 Task C1): the recompiler's header shape over a hand-written toy program.
// Nothing here comes from the disc; see README.md beside this file.

#include <cstdint>

struct R5900Context;
class PS2Runtime;

void entry_0x100000(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime);
void sub_00100020_0x100020(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime);

#endif // PS2_RECOMPILED_FUNCTIONS_H
