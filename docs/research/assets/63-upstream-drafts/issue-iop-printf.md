# Draft issue for ran-j/PS2Recomp: IOP `printf` logs the format string, not the formatted text

> Draft for the owner to file (docs/HUMAN_TASKS.md row O10). Nothing here has been posted. The text between the two
> rules is the issue body; the notes after it are for the owner, not for upstream.

---

**Title:** ps2xIOP: stdio `printf` / `fdprintf` log the bare format string, so a module's diagnostics lose their numbers

**What upstream does.** In `ps2xIOP/src/emulator/imports/iop_stdio.cpp` at `main` = `75d729c` (#244), `printf`
(stdio export 4) and `fdprintf` (export 9) go through `logString`, which reads the format string from IOP RAM and
logs it as it is (lines 24-35 and 51-52). The return value is the format string's length. `vfdprintf` (export 14,
line 60-61) does the same.

**What the IOP's stdio does.** `printf` is C `printf`: the conversions are rendered from the variadic arguments. Under
the o32 convention the IOP uses, the first four argument words are in `$a0`-`$a3` and the rest are in the caller's
outgoing-argument area at `$sp + 4*i`. The return value is the number of characters written.

So every IRX diagnostic of the form `"... cause %d -> %d, %d"` reaches the log as the literal `%d`s. When we ran a
commercial title's sound driver on ps2xIOP, its error lines were unreadable until the conversions were rendered.
With them rendered, each error named its cause code, and that was how the other findings of the run were read.

**Minimal reproduction** (unit-level, in the style of `ps2xIOP/tests/iop_import_tests.cpp`):

```cpp
struct CaptureHost : NullHost { std::string last; void log(LogLevel, std::string_view t) override { last = t; } };
CaptureHost host; IopMemory memory; IopStdio stdio(host, memory);
const char fmt[] = "n=%d x=%08x s=%s";
const char str[] = "ok";
memory.writeRam(0x1000u, fmt, sizeof(fmt));
memory.writeRam(0x1100u, str, sizeof(str));
IopCpuState cpu{};
cpu.gpr[4] = 0x1000u; cpu.gpr[5] = static_cast<uint32_t>(-7); cpu.gpr[6] = 0xBEEFu; cpu.gpr[7] = 0x1100u;
stdio.dispatchImport(4u, cpu);
// expected: host.last == "[IOP printf] n=-7 x=0000beef s=ok", cpu.gpr[2] == 20
// upstream: host.last == "[IOP printf] n=%d x=%08x s=%s",     cpu.gpr[2] == 16
```

A fifth argument would be read from `memory.read32(cpu.gpr[29] + 16)`.

**A fix.** The attached patch (`ps2recomp-printf.patch`, against `75d729c`, one file) adds a small formatter for
`%d %i %u %o %x %X %c %s %p %%` with flags, width and precision. The `h` and `l` length modifiers are accepted and
ignored, which is right for a 32-bit IOP. `printf` and `fdprintf` use it (the format string is argument 0 or 1). The
return value becomes the rendered length. It leaves `vfdprintf` alone, because its arguments arrive as a `va_list`
pointer. It does not handle `*` width/precision, and it adds no test.

---

## Notes for the owner (not part of the issue)

**Evidence in our tree.**
- The finding: `docs/research/40-upstream-divergence.md:230-231` (patch 2: "`printf` logged the bare format string;
  the patch renders `%d %u %x %s %c %p` from the o32 registers and the caller's stack, which is what made every ...
  Error: cause N -> a, b, c, d readable").
- The rendered output it produced: `docs/research/assets/40-irx-differential/results_run_20260922_150258.md:49` and
  the tables around it. Every `[IOP printf]` line with numbers in them exists because of this patch.
- The patch as it ran: `docs/research/assets/40-irx-differential/pr244-spike-patches.diff`, the second file section
  (`iop_stdio.cpp`), committed in `2accf38d`. Its pre-image blob `eed2b61` is upstream's `iop_stdio.cpp` at
  `75d729c` (checked 2026-09-25 with `git hash-object`).
- The external audit's row: `docs/audits/2026-09-25-project-audit/external.md:34` (finding 9).

**The patch file.** `ps2recomp-printf.patch` is `git format-patch` output. Its code lines are byte-identical to the
spike's `iop_stdio.cpp` section. Only the comment was reworded, and it now lists `%o`, which the code always handled.
It applies to `75d729c` with `git apply --check` (checked 2026-09-25). It has no commit in our tree, for the reason
the argv draft gives: #244 was never merged into the fork.

**The expected values in the reproduction** were computed by hand from the patch's code and have not been run. The
rendered text after the prefix is 20 characters, and the returned length counts only that text, as the
patch's `setV0(text.size())` does. Upstream's 16 is `strlen(fmt)`. Before filing, the owner can run it or drop the two
`cpu.gpr[2]` expectations.
