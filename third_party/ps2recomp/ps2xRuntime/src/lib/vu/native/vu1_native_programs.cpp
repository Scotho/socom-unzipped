// Registry of hand-written VU1 native programs: host C++ that replaces one microprogram entry
// point outright, keyed by the FNV-1a 64-bit hash of the 16 KB VU1 code memory and the pc the
// program is entered at. VU1Interpreter::run looks an entry up before the generated known-program
// dispatch and calls it in place of the microcode; PS2X_VU1_NATIVE=1 enables the lookup.
#include "runtime/ps2_vu1.h"

// Add one line per native program (and its declaration above).
bool vu1native_socom2_dispatch(VU1Interpreter &vu, uint64_t budgetEnd);

// Every hash below is an image from one disc: SOCOM II U.S. Navy SEALs NTSC r0001 (SCUS_972.75),
// the revision the launcher's disc panel checks for. Another revision's microcode hashes to
// something else, matches nothing here, and runs on the interpreter -- VU1Interpreter::run says so
// once, through Vu1NativeWarning (runtime/vu1_native_warning.h).
extern const Vu1NativeProgram g_vu1NativePrograms[] = {
    // SOCOM II: the command dispatcher (src/lib/vu/native/socom2_dispatch_0x1b50.cpp). Entry 0 of
    // the same image is a command-list upload stub that emits nothing and is left to the
    // generated code.
    {0xd418194495c25213ull, 0x1b50u, &vu1native_socom2_dispatch},
};
extern const uint32_t g_vu1NativeProgramCount = 1u;
