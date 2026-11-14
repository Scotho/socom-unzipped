#pragma once

// Sprint 19 task E2 (research/89 Q2): PS2X_SHADOW, the in-process proof that a rewritten function body does what
// the recompiled original does, on the game's own calls.
//
// An override module (a private one: cmake/PrivateOverrides.cmake) installs its body with installOverride(). With
// the function's address in PS2X_SHADOW="0xADDR[,0xADDR...]" (developer mode) it installs a shadow thunk in the
// function table instead, and every call of that address THROUGH THE FUNCTION TABLE then:
//   1. snapshots the context and arms the guest-memory write log (runtime/shadow_write_log.h) through a scope guard,
//      so the log is disarmed however the phase ends;
//   2. runs the ORIGINAL;
//   3. if the original did not reach its own return -- pc != the entry ra, or the runtime unwinding: the
//      eeCheckpointDue() back-edge return parks the guest inside the original (r0001 0x3c4b40 leaves pc on its
//      loop head 0x3c4b50) and the scheduler resumes it there later, without this thunk -- the call is SKIPPED
//      (skipped_unwound): the original's state stands, nothing is compared, it is never a mismatch;
//      if it stored to an I/O address (the runtime's slow store path) it is skipped too (skipped_io): it cannot run
//      twice; if it THREW (EeDispatcherTransfer: a blocking wait, a yield, a thread exit, or a SignalSema/
//      SetEventFlag/WakeupThread that readied a higher-priority thread; or bad_alloc) it is counted
//      (skipped_transfer) and the exception goes on up to the scheduler, the original's partial state standing;
//   4. otherwise reads the original's result, undoes its stores, restores the context and runs the BODY under an
//      EeCheckpointHold (runtime/ee_scheduler.h): a transcribed body's eeCheckpointDue() back edges report nothing
//      due, so an event or slice end that fell due after the original returned does not park a correct body on a
//      loop head; the pending work is acted on at the caller's next checkpoint. The original is NOT held (its
//      checkpoint return is the skip above). The hold does not stop a stop request -- a body it cuts short is
//      skipped (skipped_unwound) with the original's result restored and the stop's unwind left standing -- nor
//      a transferring syscall, which throws as below;
//      a body that throws cannot be recovered (the original's result is already undone): it is counted
//      (body_threw), one "[shadow-error]" line names the address, the exception goes on up, and the address is
//      never verified;
//   5. compares (Compare::AllRegisters, the default): every GPR's low 64 bits, v0 and v1 at the full 128, pc, hi,
//      lo, hi1, lo1, sa, f0-f31 by their bits, the FPU accumulator, fcr31, and guest memory over every byte either
//      run stored to -- except the dead stack, the kDeadStackBytes (256 KB) below the entry sp (a frame the body
//      need not build);
//   6. keeps the body's result on a match; on a mismatch counts it, logs what differed ("[shadow-mismatch]") and
//      puts the original's result back (context and the guest memory the write log saw).
// Not compared: the upper 64 bits of GPRs other than v0/v1, the VU0 macro-mode state (vu0_vf, vi, Q/P/I/R, ACC,
// flags) and COP0 (cop0_status included).
//
// WHAT IT IS SAFE FOR: LEAF functions -- no calls, no syscalls -- whose stores all go to RDRAM or the scratchpad
// through the generated code's helpers. Only those stores are logged and undone. Everything else a callee can do
// escapes the log and runs TWICE (once for the original, once for the body) without being compared or undone:
// syscalls and kernel calls; host stubs (malloc, free, memcpy, memset, strcpy... are bound as host stubs that
// write through host pointers: Kernel/Stubs/LibC.cpp); slow-path loads with side effects (a FIFO or status read);
// VU0 microprograms; the GIF DMA kick (kickGifDmaChainFromMMIO). A non-leaf address may therefore double a side
// effect, free a block twice or allocate twice, and its comparison proves nothing about what escaped. Listing it
// is the developer's error; the harness does not check it yet.
//
// BLIND SPOTS. The thunk sits in the function table, so it sees only calls that go through it (a JAL dispatch, an
// indirect call, a stub tail call). Generated code turns a direct J to a named function into a plain C++ call
// (ps2xRecomp control_flow_emitter.cpp), as it does a jump-table case that is a named function
// (jump_table_switch_emitter.cpp); both bypass the table: such a tail jump runs the ORIGINAL, unshadowed and
// uncounted. A plain (unlisted) override has the same hole -- such a tail jump still runs the original.
//
// A body DERIVED from source cannot reproduce dead temporaries (C++ defines the result, not the scratch
// registers), so its module installs it with Compare::Abi, which compares only what the EE EABI lets a caller see:
// the return registers the function has (Mode::returns: v0 and v1, at 128 bits only with kReturnsWide, f0, f1), the
// callee-saved s0-s7, gp, sp, fp and ra (low 64 bits), the callee-saved f20-f31, pc, and memory as above. The
// argument registers a0-a3, the temporaries at, t0-t9, k0, k1, v0/v1/f0/f1 when not returned, f2-f19, hi/lo,
// hi1/lo1, sa, the FPU accumulator and fcr31 may differ.
//
// THE REPORT. Every 10 s, and at exit through flushReport() (the runner ends with std::_Exit, so src/main.cpp calls
// it; an atexit handler covers a std::exit path; the gate kills the game, so exit is not reliable), one line per
// shadowed address and a total:
//   [shadow] <reason>: 0x%08x <name> compare=abi|all calls=N compared=N matched=N mismatched=N skipped_unwound=N
//            skipped_io=N skipped_transfer=N body_threw=N passed_through=N verified=yes|no
//   [shadow] <reason>: total shadowed=N calls=N compared=N mismatched=N skipped_unwound=N skipped_io=N
//            skipped_transfer=N body_threw=N[; listed without an override body: 0x%x ...]
// (each one line; <reason> is "periodic" or "exit"). passed_through counts entries at a pc other than the
// function's (a resume pc) or inside another shadowed call: the original ran, nothing was compared. A function is
// "verified" by a run when it was compared at least once, never mismatched and its body never threw.
//
// The write log needs the hook in the inline store helpers, compiled in only by the CMake option
// PS2X_SHADOW_WRITE_LOG (OFF by default). In a build without it, installOverride refuses to shadow ANY listed
// address and leaves the ORIGINAL in place (the body is not used), so a shadow run can never quietly compare
// registers alone.

#include "ps2_runtime.h"

#include <cstdint>
#include <string>
#include <vector>

namespace ps2_shadow
{
    using Fn = PS2Runtime::RecompiledFunction;

    struct Counts
    {
        uint64_t calls = 0;           // calls=            every entry of the thunk
        uint64_t compared = 0;        // compared=         original and body both run and compared
        uint64_t matched = 0;         // matched=
        uint64_t mismatched = 0;      // mismatched=
        uint64_t skippedUnwound = 0;  // skipped_unwound=  the original left with pc != ra (checkpoint): not comparable
        uint64_t skippedIo = 0;       // skipped_io=       the original stored to an I/O address: not run twice
        uint64_t passedThrough = 0;   // passed_through=   entered at a pc other than the entry, or inside another
                                      //                   shadowed call: the original ran alone
        uint64_t skippedTransfer = 0; // skipped_transfer= the original threw (EeDispatcherTransfer: it blocked or
                                      //                   yielded; or bad_alloc): rethrown, its state stands
        uint64_t bodyThrew = 0;       // body_threw=       the BODY threw after the original's result was undone:
                                      //                   unrecoverable, "[shadow-error]", never verified
    };

    // A derived batch is every executed leaf of a run, so the table holds a few thousand (a slot is ~150 bytes).
    constexpr int kMaxSlots = 4096;

    enum class Compare
    {
        AllRegisters,   // every GPR, pc, hi/lo, hi1/lo1, sa, f0-f31, the FPU accumulator, fcr31 (the default)
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
        kReturnsWide = 16u, // v0/v1 hold a 128-bit value: compared whole (else their low 64 bits, all a caller reads)
    };

    struct Mode
    {
        Compare compare = Compare::AllRegisters;
        uint32_t returns = kReturnsV0 | kReturnsV1 | kReturnsF0;   // used by Compare::Abi only
    };
    constexpr uint32_t kDeadStackBytes = 256u * 1024u;   // below the entry sp: not compared

    // TEST-ONLY core: wraps the table entry at addr. -1 when the table has no room, the address is shadowed already
    // or is not a table slot. It does NOT check writeLogBuilt(): in a build without the write log it would compare
    // registers alone. An override module calls installOverride(), which refuses that case.
    int add(PS2Runtime &runtime, uint32_t addr, const std::string &name, Fn original, Fn body, Mode mode = {});
    Counts counts(uint32_t addr);
    bool verified(uint32_t addr);
    std::vector<std::string> mismatchLines(uint32_t addr);   // the first few, for the log and tests
    std::string formatReport(const std::string &reason);
    int flushReport();   // the exit report now, on std::cout, flushed; the lines printed (0 when nothing is shadowed)
    void uninstall(PS2Runtime &runtime);   // tests: restore the originals, forget every slot
    bool writeLogArmedForTest();           // tests: true while a write log is armed (only inside a shadowed call)

    // "0xADDR[,0xADDR...]" (spaces and empty items allowed). Each item is 0x/0X and 1-8 hex digits, or plain
    // decimal (no sign, no leading zero) up to 4294967295; a repeated address is listed once. False on any other
    // item (a sign, octal, a value past 32 bits, a word).
    bool parseSpec(const char *spec, std::vector<uint32_t> &out);

    // True when this build's runtime was compiled with the write-log hook (CMake PS2X_SHADOW_WRITE_LOG=ON).
    bool writeLogBuilt();

    enum class Installed
    {
        Override,   // not shadowed: the body replaces the original
        Shadow,     // shadowed: original and body both run on every call through the function table
        Refused,    // the original stays, the body is unused: listed in a build with no write log or with no free
                    // slot, or the address is not a function-table slot
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
