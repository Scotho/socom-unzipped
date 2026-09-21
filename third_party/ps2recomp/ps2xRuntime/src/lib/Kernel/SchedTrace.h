#pragma once

// research/36 item 16 (2026-09-21): PS2X_SCHED_TRACE=1 (default OFF) -- the per-guest-thread run trace.
//
// What it prints, every line stamped like the [audio] / [cd-stream] lines (the mixer's output-frame clock,
// the VSync tick) plus host milliseconds since the first line:
//
//   [sched] frame=F tick=T host=H switch out=<tid> ran_ms=<x> waited_ms=<y> left=<why> in=<tid> prio=<p> pc=0x.. ready=<n>
//       the EE dispatcher chose a guest thread: <out> held the EE for ran_ms of host time, then the dispatcher
//       idled / paced for waited_ms before <in> was chosen. <why> is how the outgoing thread left the EE:
//       sleep / sema <id> / evf <id> / vsync until <tick> / external / mpeg (blockCurrent), yield
//       (yieldToAnyReady), rotate (RotateThreadReadyQueue), preempt (a higher-priority thread became
//       ready), slice (time slice expired with a higher-priority thread ready), suspend, exit, dormant.
//   [sched] ... ready tid=<tid> from=<wait> result=<r>          a waiting thread was made ready (who woke it
//       is the enclosing stub / syscall / event; <wait> is what it had been waiting on)
//   [sched] ... invoke kind=<k> on=<tid> pc=0x..               an interrupt / callback stacked on a thread
//   [sched] ... run tid=<tid> pc=0x.. ra=0x.. for_ms=<x>         a sample of the running thread, at most once per
//       PS2X_SCHED_TRACE_SAMPLE_MS (default 20) of host time, taken at a dispatcher checkpoint
//   [sched] ... idle ready=0 waited_ms=<x>                       the EE had no runnable thread (after the wait)
//   [sched] ... pace waited_ms=<x>                              the dispatcher slept for a VBlank's host deadline
//   [sched] ... stub <name> tid=<tid> ms=<x> [transfer]          a bound HLE stub (recomp/socom2.toml `stubs`) took
//       at least PS2X_SCHED_TRACE_STUB_MS (default 1) of host time; `transfer` = it left through a guest
//       thread switch (blocked, yielded) rather than returning
//   [sched] ... stub <name> tid=<tid> ms=<x> a0=0x.. a1=0x.. a2=0x.. ret=0x..   EVERY call of a stub named in
//       PS2X_SCHED_TRACE_STUBS (a comma-separated list), whatever it cost, with its arguments and its return
//
// Hooks: the scheduler lines come from EeScheduler (one `if (m_traceOn)` per site, a bool read once at reset);
// the stub lines wrap the function-table entries of every bound stub exactly as PS2X_HLE_STATS does
// (Kernel/HleStats.h), so with the knob off nothing is installed and the stubs run with zero added cost.

#include "HleStats.h"

#include <cstdint>
#include <string>
#include <vector>

class PS2Runtime;

namespace ps2_sched_trace
{
    // PS2X_SCHED_TRACE, read once and cached (empty, "0", "false", "off" = off).
    bool enabled();

    // PS2X_SCHED_TRACE_STUB_MS (default 1.0): a stub call shorter than this is not printed.
    int64_t stubThresholdNs();

    // PS2X_SCHED_TRACE_SAMPLE_MS (default 20): the running-thread sample interval.
    int64_t sampleIntervalNs();

    // Host milliseconds since the first call (the trace's own epoch).
    double hostMs();

    // The stamp every line carries.
    struct Stamp
    {
        uint64_t frame = 0u;   // the mixer's output-frame clock
        uint64_t tick = 0u;    // the VSync tick
        double hostMs = 0.0;
    };

    // "[sched] frame=F tick=T host=H.h " -- the line prefix.
    std::string prefix(const Stamp &stamp);

    // The threshold rule for a stub call: printed when it took at least the threshold (a threshold of 0
    // prints every call, a negative one never).
    bool stubReportable(int64_t elapsedNs, int64_t thresholdNs);

    // One "stub" line (without the newline).
    std::string formatStub(const Stamp &stamp, const std::string &name, int tid, int64_t elapsedNs, bool transferred);

    // Wraps the function-table entry of every stub that has one, timing each call. Returns the count wrapped.
    size_t installStubTiming(PS2Runtime &runtime, const std::vector<ps2_hle_stats::StubSpec> &stubs);

    // Tests: restore the wrapped entries and forget every slot.
    void uninstallStubTiming(PS2Runtime &runtime);

    // PS2X_SCHED_TRACE_STUBS parsing: the names listed (trimmed, empty entries dropped).
    std::vector<std::string> parseStubNames(const char *list);

    // One "stub" line for a call of a stub in that list (without the newline).
    std::string formatStubCall(const Stamp &stamp, const std::string &name, int tid, int64_t elapsedNs,
                               uint32_t a0, uint32_t a1, uint32_t a2, bool transferred, uint32_t ret);

    // Runner entry point: if enabled(), read the stub list (PS2X_SCHED_TRACE_TOML, else recomp/socom2.toml or
    // ../recomp/socom2.toml) and install the stub timing. Call after every other function-table override.
    void installFromEnvironment(PS2Runtime &runtime);
}
