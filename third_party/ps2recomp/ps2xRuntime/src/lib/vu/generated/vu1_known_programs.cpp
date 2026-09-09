// Table of VU1 microcode images recompiled to host code (vu1_replay --gen). Each entry pairs the
// FNV-1a 64-bit hash of the 16 KB VU1 code memory with the generated function; the interpreter
// (VU1Interpreter::run) rehashes the code memory whenever the VIF MPG generation changes and runs
// the matching function, falling back to the fast interpreter otherwise.
#include "runtime/ps2_vu1.h"

struct Vu1KnownProgram
{
    uint64_t hash;
    VU1Interpreter::KnownProgramFn fn;
};

// Add one line per generated file (vu1_<hash>.cpp).
bool vu1gen_d418194495c25213(VU1Interpreter &vu, uint64_t budgetEnd); // SOCOM II mission image (md5 638cb8f0)

extern const Vu1KnownProgram g_vu1KnownPrograms[] = {
    {0xd418194495c25213ull, &vu1gen_d418194495c25213},
};
extern const uint32_t g_vu1KnownProgramCount = 1u;
