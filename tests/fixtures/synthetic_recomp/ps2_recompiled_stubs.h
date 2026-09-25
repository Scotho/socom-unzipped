#pragma once

// Synthetic (Sprint 13 Task C1): the recompiler's stub-header shape. See README.md beside this file.

#include <cstdint>
#include "ps2_runtime.h"
#include "ps2_syscalls.h"

void rand_0x100030(uint8_t* rdram, R5900Context* ctx, PS2Runtime* runtime);
