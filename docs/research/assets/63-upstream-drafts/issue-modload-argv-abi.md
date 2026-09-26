# Draft issue for ran-j/PS2Recomp: an IRX's `_start` gets (byte count, raw buffer), not (argc, argv)

> Draft for the owner to file (docs/HUMAN_TASKS.md row O10). Nothing here has been posted. The text between the two
> rules is the issue body; the notes after it are for the owner, not for upstream.

---

**Title:** ps2xIOP: `loadImage` starts an IRX as `_start(argumentSize, rawBuffer)` instead of `_start(argc, argv)`

**What upstream does.** In `ps2xIOP/src/emulator/iop_emulator.cpp` at `main` = `75d729c` (#244), `loadImage` copies
the caller's argument buffer into IOP RAM and calls the module entry with the buffer's **byte count** as the first
argument and the **raw buffer address** as the second (lines 617-627):

```cpp
uint32_t args = 0u;
if (arguments && argumentSize)
{
    args = allocate(argumentSize + 1u, 16u);
    ...
}
const uint32_t startResult = callFunction(module.entry, argumentSize, args, 0u, 0u, module.gp);
```

**What modload does.** An IRX entry point is `int _start(int argc, char *argv[])`. modload builds `argv` from the load
request: `argv[0]` is the module's path, and each NUL-separated string of the argument buffer becomes the next
`argv` entry, with a NULL after the last. So `sceSifLoadModule("host:foo.irx", 8, "a=1\0b=2\0")` starts the module
with `argc == 3`, `argv[1] == "a=1"`, `argv[2] == "b=2"`.

With the current code a module that walks `argv[1..argc-1]` (most modules that take options do) reads the first
words of its own argument text as string pointers, and `argc` is the byte count. On a commercial title we loaded
this way, the SDK's sound driver rejected every option as unknown, and a thread-priority option silently did not
take effect.

**Minimal reproduction** (synthetic, in the style of `ps2xIOP/tests/iop_emulator_tests.cpp`'s `writeMinimalIrx`):

1. Build a one-segment IRX whose code is `jr ra` / `addu v0, a0, zero` (`0x03E00008`, `0x00801021`), i.e. `_start`
   returns `argc`.
2. `const char args[] = "a=1\0b=2";` then `iop.loadModuleBuffer(address, args, sizeof(args))` (8 bytes, two
   strings).
3. Expected `result.startResult == 3` (path + two arguments). Upstream returns **8**.

A second variant checks `argv` itself: code `lw t0, 4(a1)` / `nop` / `lbu v0, 0(t0)` / `jr ra` / `nop`
(`0x8CA80004`, `0`, `0x91020000`, `0x03E00008`, `0`) returns the first byte of `argv[1]`; expected `'a'` (0x61).
Upstream dereferences the argument text `"b=2\0"` as a pointer.

**A fix.** The attached patch (`ps2recomp-argv.patch`, against `75d729c`, one file) builds `argv[0]` = the module
path, one entry per NUL-separated string, and a NULL terminator in a single IOP allocation, and calls
`_start(argc, argv)`. It has run in an out-of-tree harness that loads six IRX modules through this path; it does
not add the test above.

Two details worth a maintainer's eye: the patch skips empty strings between consecutive NULs (we did not check what
modload does with them), and for `loadModuleBuffer` `argv[0]` becomes the `buffer@0x...` tag the loader already uses
as the path.

---

## Notes for the owner (not part of the issue)

**Evidence in our tree.**
- The finding and its effect: `docs/research/40-upstream-divergence.md:225-229` (patch 1: "`_start(argc, argv)`
  received `(byte count, raw buffer)`"; the sound driver's eighteen unknown-argument errors; the option "never
  took") and `:287-288` (finding 5: the option "was silently ignored by #244's argument ABI").
- The patch as it ran: `docs/research/assets/40-irx-differential/pr244-spike-patches.diff`, the third file section
  (`iop_emulator.cpp`), committed in `2accf38d`. Its pre-image blob `e5f63a9` is the blob of upstream's
  `iop_emulator.cpp` at `75d729c` (checked 2026-09-25 with `git hash-object` on the file fetched from GitHub).
- The harness that exercised it: `docs/research/assets/40-irx-differential/harness.cpp:253-260` (the `load`
  command hands a path and an argument string to `IopSubsystem::loadModule(path, args, size)`).
- Upstream unchanged since: `docs/research/63-upstream-triage-2026-09-25.md:392` (§2, the watch table: upstream `main` =
  `75d729c`); re-checked 2026-09-25 with `gh api repos/ran-j/PS2Recomp/commits/main`.
- The external audit's row: `docs/audits/2026-09-25-project-audit/external.md:34` (finding 9).

**The patch file.** `ps2recomp-argv.patch` is `git format-patch` output. Its code lines are byte-identical to the
spike diff's `iop_emulator.cpp` section. Only the comment was rewritten, to drop our project's wording and the
disc-derived details. It applies to upstream `75d729c` with `git apply --check` (checked 2026-09-25 against the
three files fetched from GitHub). Our tree has no commit that carries this change, because the fork never merged
#244 (`docs/research/40-upstream-divergence.md:200`). So the patch was built in a scratch repository on upstream's
files, which is why its `From` hash is not a commit in this repository.

**Kept out of the draft on purpose.** The module names, the option string and the error numbers come from the
disc's own IRX files and logs. They are in research/40 and not in the issue.
