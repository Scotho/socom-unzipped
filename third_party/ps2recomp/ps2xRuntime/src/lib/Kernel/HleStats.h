#pragma once

// PS2X_HLE_STATS=1 (default OFF): per bound HLE stub (recomp/socom2.toml `stubs = [...]`), count
// calls and returns, the distinct return values (saturating at 64), and the first and last return.
// Prints the table for EVERY bound stub -- zero-call ones included -- every
// PS2X_HLE_STATS_PERIOD seconds (default 30; the harness kills the game, so exit is not reliable)
// and once more at a normal exit.
//
// Where it hooks: every bound stub is one generated wrapper at the stub's guest address that calls
// its ps2_stubs:: / ps2_syscalls:: handler, and every guest call reaches that wrapper through the
// dense function table (PS2Runtime::dispatchGuestBranch / lookupFunction). installation wraps
// those table entries, exactly like PS2X_CALL_TRACE. Knob off: nothing is installed, so the stubs
// run with zero added cost.
//
// The return value is $v0 as 64 bits (soft-double and long long stubs return the whole pattern
// there), except for the stubs whose guest ABI returns a float in $f0 (__kernel_cosf,
// __kernel_sinf), which record $f0's bit pattern and print it as a float.
//
// Blind: a varying-but-wrong return passes a distinct count; a stub that returns through a guest
// thread switch (the C++ call does not come back) counts as a call without a return.

#include <cstdint>
#include <istream>
#include <string>
#include <vector>

class PS2Runtime;

namespace ps2_hle_stats
{
    struct StubSpec
    {
        std::string name;
        uint32_t addr = 0u;
    };

    // PS2X_HLE_STATS, read once and cached (empty, "0", "false", "off" = off).
    bool enabled();

    // Parses the `stubs = [ "name@0xADDR", ... ]` array of a PS2Recomp TOML config.
    std::vector<StubSpec> parseTomlStubs(std::istream &in);

    // Wraps the function-table entry of every stub. A stub with no function at its address stays
    // in the table, marked unbound. Returns the number of entries wrapped.
    size_t install(PS2Runtime &runtime, const std::vector<StubSpec> &stubs);

    // The table, one "[hle-stats]" line per stub in install order.
    std::string formatTable(const std::string &reason);

    // Tests: restore the wrapped function-table entries and forget every slot.
    void uninstall(PS2Runtime &runtime);

    // Runner entry point: if enabled(), read the stub list (PS2X_HLE_STATS_TOML, else
    // recomp/socom2.toml or ../recomp/socom2.toml), install, and start the periodic and exit
    // reports. Call after every other function-table override is in place.
    void installFromEnvironment(PS2Runtime &runtime);
}
