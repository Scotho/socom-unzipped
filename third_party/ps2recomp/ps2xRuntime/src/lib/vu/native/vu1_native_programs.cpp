// Registry of hand-written VU1 native programs: host C++ that replaces one microprogram entry
// point outright, keyed by the FNV-1a 64-bit hash of the 16 KB VU1 code memory and the pc the
// program is entered at. VU1Interpreter::run looks an entry up before the generated known-program
// dispatch and calls it in place of the microcode; PS2X_VU1_NATIVE=1 enables the lookup.
#include "runtime/ps2_vu1.h"

// Add one line per native program (and its declaration above).
extern const Vu1NativeProgram g_vu1NativePrograms[] = {
    {0ull, 0u, nullptr}, // placeholder: the array must not be empty while the registry has no entries
};
extern const uint32_t g_vu1NativeProgramCount = 0u;
