// SOCOM II's msifrpc HLE (socom2_msifrpc.cpp): the four libnetb transport entry points, answered on the host.
#pragma once
#include <cstdint>

struct R5900Context;
class PS2Runtime;

namespace ps2_stubs
{
    void socom2_MsifInit(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);     // FUN_001bcd80
    void socom2_MsifBind(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);     // FUN_001bd050
    void socom2_MsifCall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);     // FUN_001bd320
    void socom2_MsifUnbind(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);   // FUN_001bd200
}
