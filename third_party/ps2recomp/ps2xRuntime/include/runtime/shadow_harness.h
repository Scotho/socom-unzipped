#pragma once

// Sprint 19 task E2 (research/89 Q2): PS2X_SHADOW, the in-process proof that a rewritten function body does what
// the recompiled original does, on the game's own calls.
//
// An override module (a private one: cmake/PrivateOverrides.cmake) installs its body with installOverride(). With
// the function's address in PS2X_SHADOW="0xADDR[,0xADDR...]" (developer mode) it installs a shadow thunk instead,
// and every call of that address then:
//   1. snapshots the context and arms the guest-memory write log (runtime/shadow_write_log.h);
//   2. runs the ORIGINAL;
//   3. if the original did not reach its own return -- pc != the entry ra, or the runtime unwinding: the
//      eeCheckpointDue() back-edge return parks the guest inside the original (CZWeaponList_GetWeapon r0001
//      0x3c4b40 leaves pc on its loop head 0x3c4b50) and the scheduler resumes it there later, without this thunk
//      -- the call is SKIPPED: the original's state stands, nothing is compared, it is never a mismatch;
//      if it stored to an I/O address (the runtime's slow store path) it is skipped too: it cannot run twice;
//   4. otherwise reads the original's result, undoes its stores, restores the context and runs the BODY;
//   5. compares: every GPR's low 64 bits, v0 and v1 at the full 128, pc, f0's bits, and guest memory over every
//      byte either run stored to -- except the dead stack below the entry sp (a frame the body need not build);
//   6. keeps the body's result on a match; on a mismatch counts it, logs what differed and puts the original's
//      result back (context and memory), so a shadow run plays as the unmodified game.
// hi/lo, the FPU registers other than f0 and the VU0 state are not compared.
//
// That is the default, Compare::AllRegisters: right for a body transcribed from the recompiled original, which can
// reproduce every dead temporary. A body DERIVED from source cannot (C++ defines the result, not the scratch
// registers), so its module installs it with Compare::Abi, which compares only what the EE EABI lets a caller see:
// the return registers the function has (Mode::returns: v0 and v1 at 128 bits, f0, f1), the callee-saved s0-s7,
// gp, sp, fp and ra (low 64 bits), the callee-saved f20-f31, pc, and memory as above. The argument registers a0-a3,
// the temporaries at, t0-t9, k0, k1, v0/v1/f0/f1 when not returned, and f2-f19 may differ.
//
// Counts per address are printed every 10 s and at exit ("[shadow] ..." lines; the gate kills the game, so exit is
// not reliable). A function is "verified" by a run when it was compared at least once and never mismatched.
//
// The write log needs the hook in the inline store helpers, compiled in only by the CMake option
// PS2X_SHADOW_WRITE_LOG (OFF by default). In a build without it, installOverride refuses to shadow and leaves the
// ORIGINAL in place, so a shadow run can never quietly compare registers alone.

#include "ps2_runtime.h"

#include <cstdint>
#include <string>
#include <vector>

namespace ps2_shadow
{
    using Fn = PS2Runtime::RecompiledFunction;

    struct Counts
    {
        uint64_t calls = 0;           // every entry of the thunk
        uint64_t compared = 0;        // original and body both run and compared
        uint64_t matched = 0;
        uint64_t mismatched = 0;
        uint64_t skippedUnwound = 0;  // the original left with pc != ra (checkpoint): not comparable
        uint64_t skippedIo = 0;       // the original stored to an I/O address: not run twice
        uint64_t passedThrough = 0;   // entered at a pc other than the entry, or inside another shadowed call
    };

    // A derived batch is every executed leaf of a run, so the table holds a few thousand (a slot is ~150 bytes).
    constexpr int kMaxSlots = 4096;

    enum class Compare
    {
        AllRegisters,   // every GPR, pc, f0 (the default)
        Abi,            // what a caller can observe (see above)
    };

    // The EE EABI return registers a function uses: what Compare::Abi compares beyond the callee-saved state.
    enum Returns : uint32_t
    {
        kReturnsNone = 0u,
        kReturnsV0 = 1u,    // int, pointer, 64-bit
        kReturnsV1 = 2u,    // the second half of a 128-bit pair
        kReturnsF0 = 4u,    // float
        kReturnsF1 = 8u,
    };

    struct Mode
    {
        Compare compare = Compare::AllRegisters;
        uint32_t returns = kReturnsV0 | kReturnsV1 | kReturnsF0;   // used by Compare::Abi only
    };
    constexpr uint32_t kDeadStackBytes = 256u * 1024u;   // below the entry sp: not compared

    // Core: wraps the table entry at addr. -1 when the table has no room or the address is not a table slot.
    int add(PS2Runtime &runtime, uint32_t addr, const std::string &name, Fn original, Fn body, Mode mode = {});
    Counts counts(uint32_t addr);
    bool verified(uint32_t addr);
    std::vector<std::string> mismatchLines(uint32_t addr);   // the first few, for the log and tests
    std::string formatReport(const std::string &reason);
    void uninstall(PS2Runtime &runtime);   // tests: restore the originals, forget every slot

    // "0xADDR[,0xADDR...]" (spaces and empty items allowed). False on any item that is not a number.
    bool parseSpec(const char *spec, std::vector<uint32_t> &out);

    // True when this build's runtime was compiled with the write-log hook (CMake PS2X_SHADOW_WRITE_LOG=ON).
    bool writeLogBuilt();

    enum class Installed
    {
        Override,   // not shadowed: the body replaces the original
        Shadow,     // shadowed: original and body both run on every call
        Refused,    // shadowed, but the build has no write log: the original stays, the body is not used
    };

    // An override module's entry point (call it from its PS2_REGISTER_GAME_OVERRIDE apply function). Reads
    // PS2X_SHADOW once; prints one line per install; starts the periodic and exit reports with the first shadow.
    Installed installOverride(PS2Runtime &runtime, uint32_t addr, const char *name, Fn body, Mode mode = {});
    // The same decision with the list and the build's write-log state given (tests).
    Installed installOverride(PS2Runtime &runtime, uint32_t addr, const char *name, Fn body,
                              const std::vector<uint32_t> &shadowList, bool writeLog);
    Installed installOverride(PS2Runtime &runtime, uint32_t addr, const char *name, Fn body, Mode mode,
                              const std::vector<uint32_t> &shadowList, bool writeLog);
}
