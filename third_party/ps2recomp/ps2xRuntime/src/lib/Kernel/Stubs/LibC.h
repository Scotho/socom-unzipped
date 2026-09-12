#pragma once

#include "ps2_stubs.h"

namespace ps2_stubs
{
    void malloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void memalign(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void free(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void calloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void realloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void memcpy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void memset(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void memclr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void memmove(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void memcmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strcpy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strncpy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strlen(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strcmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strncmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strcat(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strncat(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strchr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strrchr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void strstr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void printf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void snprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void puts(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fopen(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fclose(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fwrite(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fseek(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void ftell(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fflush(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sqrt(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void sin(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void __kernel_sinf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void cos(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void __kernel_cosf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void __ieee754_rem_pio2f(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void tan(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void atan2(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void pow(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void exp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void log(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void log10(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void ceil(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void floor(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void fabs(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void abs(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void atan(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void memchr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void rand(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void srand(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    // Point rand()/srand() at the guest's own newlib `struct _reent._rand_next` so the stub pair
    // and the game's recompiled srand() share one state: `impurePtrAddr` is the guest address of
    // the pointer to struct _reent (newlib's _impure_ptr) and `randNextOffset` the offset of
    // _rand_next inside it.  Both are game-specific; a game override calls this (see
    // game_overrides_socom2.cpp).  Unregistered, the stubs keep an internal state instead.
    void setLibcRandState(uint32_t impurePtrAddr, uint32_t randNextOffset);
    void strcasecmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void vfprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void vsprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
    void __divdi3(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);
}
