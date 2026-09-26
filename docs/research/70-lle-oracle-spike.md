# 70. The LLE IOP as an oracle -- the spike (Sprint 15 T1)

Date: 2026-09-26 (reading 18:15Z-19:25Z, the one build 19:27:28Z-19:27:36Z, by `date -u`). Sprint 15 Task T1 (plan
`docs/superpowers/plans/2026-09-26-sprint-15.md` "## Task T1"), the spike on the shortlist's first entry of
`docs/research/69-audio-survey.md` §6. Class S, the shape of `docs/research/14-gs-render-target-scale-spike.md`: a
question, a time box, a decision up front. No game run; nothing of #254's 3,311 lines, nothing of the disc and nothing
of the scratch glue is in the tree. The fork's head and the glue live under `C:/projects/scratch-s15-t1/` ("scratch"):
`fork/` (a depth-1 clone of `Sinan-Karakaya/PS2Recomp` at `e42efbe`), `oracle/` (the patched slice, the harness, its
CMake and build script, the replay driver). The disc's IRX files were read in place in the main tree under
`game/disc/RUN/IRX/`, by command, counts and behaviour only.

> **State at last commit** (T1, 2026-09-26 19:29Z):
> - **Recommendation: TRIED, NOT ADOPTED** -- the stop rule fired at the build: #254's `lle/` slice does not build
>   with llvm-mingw as shipped. Two of its five sources use a `<cstdlib>` function without including `<cstdlib>`
>   (`kernel.cpp:328` `std::strtol`, `spu2.cpp:73` `std::abs`); libc++ does not pull it in transitively (C6).
>   The other three sources, the oracle patch and the harness with its provider compiled clean in the same build.
> - **N = not measured**, the replay never ran (no binary); it is `grep -m1 "Compared answers" C:/projects/scratch-s15-t1/oracle/results_lle_232655.md`
>   after `python C:/projects/scratch-s15-t1/oracle/replay_lle.py --log logs/run_20260922_232655.log --harness C:/projects/scratch-s15-t1/oracle/build/harness_lle.exe --out C:/projects/scratch-s15-t1/oracle/results_lle_232655.md`.
>   Today our HLE disagrees with #244's blind oracle on 12,643 of 13,044 answers, and on the menus' replay on 19 of
>   1,794 (C8).
> - **After a refused read, 989SND.IRX fails cleanly; it does not spin** (§2, read from the disc's IRX, not run):
>   it checks `sceCdRead`'s own return first, and a `sceCdGetError` of 0 after a refused read is replaced by -1. A bank
>   load aborts with the read error (`snd_BankLoadByLoc` answers 0); a stream read marks the stream in error (cause
>   62). No retry loop sits on either path.
> - **A correction to research/40 §9:** the "cdvdman safe-read form (the callback form)" #244 lacked is not a cdvdman
>   call. The stub research/40 §9.1 names is `sifman`'s `sceSifSetDmaIntr` -- the IOP-to-EE DMA with a completion
>   callback -- and cause 66 is "Error DMAing data to EE memory" (§3). #254 leaves it unbound too (research/69 §2's
>   `sifman` 1 of 4), so the minimal provider is cdvdman's 7 imports **plus** that one.
> - **R287:** nothing of the 3,311 lines would enter the tree; the glue that would is ours, about 660 lines, and it
>   carries 80 lines of the fork's code only as diff context (§6). The register row does not move (the
>   oracle did not run). No owner line: the spike does not recommend the trial.

## Decision (short)

**Recommendation: TRIED, NOT ADOPTED.** The brief's stop rule reads: "if the slice does not build with llvm-mingw,
or 989SND.IRX does not reach its first bank load on the oracle with a minimal `cdvdman` provider, the spike ends
TRIED, NOT ADOPTED with the reason". The first half fired on the one build the time box allows. The reason is small
and is the fork's, not the approach's: two missing `#include <cstdlib>` lines. Everything the spike had to write --
the provider, the patch, the harness -- compiled in that build without an error (C6), so a second build with those two
lines added is the whole distance to the replay's N. Whether to spend it is the controller's call, not the owner's
(D1's trial is the owner's, R282; a spike is not the trial).

## 0. The commands

| Id | Command (local unless a `gh api` GET; 2026-09-26) |
|---|---|
| C1 | `git init fork && git -C fork fetch --depth 1 origin e42efbe6434403018b80cda23034abf9644830ec` (origin `https://github.com/Sinan-Karakaya/PS2Recomp.git`), checkout `FETCH_HEAD`; `wc -l fork/ps2xIOP/src/lle/*` (3,311 over 11 files); `head -3 fork/LICENSE` (GPL-3.0) |
| C2 | research/69 C4's coverage scan re-run on the clone: `python irx_cover.py fork/ps2xIOP/src/lle/kernel.cpp game/disc/RUN/IRX/SOUND/989SND.IRX game/disc/RUN/IRX/LIBSD.IRX game/disc/RUN/IRX/SOUND/989SND.IRX` and the same for `989DSTRM.IRX` (12 and 1 imports returning zero, as research/69 read) |
| C3 | the names of the unbound imports: `gh api -H "Accept: application/vnd.github.raw" repos/ps2dev/ps2sdk/contents/iop/cdvd/cdvdman/include/cdvdman.h \| grep DECLARE_IMPORT`, the same for `iop/system/sifman/include/sifman.h` and `iop/system/ioman/include/ioman.h` |
| C4 | the static reading, a scratch script on capstone 5.0.7 (`python irxdis.py 989SND.IRX callers <stub>` / `dis <from> <to>` / `func <addr>`) that disassembles the IRX's text in memory and prints to the terminal only: call sites per import (`sceCdRead` 4, `sceCdGetError` 5, `sceCdSync` 6, `sceCdCallback` 4, `sceCdBreak` 3, `sceSifSetDmaIntr` 6), then the code after each `sceCdRead` and in the bank loader that calls it |
| C5 | the decomp's error table: `sed -n 360,381p research/989snd-ziemas/iop/error.c` (cause 61 "snd_KickDataRead: Error calling sceCdRead()!", 62 the same for `snd_KickVAGRead`, 66 "snd_VAGStreamLoadDoneThread: Error DMAing data to EE memory!!!"); `grep -n sceSifSetDmaIntr research/989snd-ziemas/iop/*.c` (5 call sites in v3.01) |
| C6 | the one build: `bash scripts/loop_lock.sh run agent-s15-t1 --purpose "T1 spike: the lle slice" --class build --wait 240 -- bash C:/projects/scratch-s15-t1/oracle/build.sh` (granted 19:27:28Z after a queue refused for the WIP cap from 18:29Z); `grep -nE "error:\|EXIT" C:/projects/scratch-s15-t1/oracle/build.log`: `PRISTINE EXIT 1`, `HARNESS EXIT 1`, 3 errors each, all at `kernel.cpp` `std::strtol` and `spu2.cpp` `std::abs`; `grep -n "#include" fork/ps2xIOP/src/lle/kernel.cpp fork/ps2xIOP/src/lle/spu2.cpp` (no `<cstdlib>`) |
| C7 | #244's `sifman`: `sed -n 28,131p research/ps2recomp-244/ps2xIOP/src/emulator/services/iop_rpc.cpp` (`dispatchSifManImport`: cases 4, 5, 7, 8, 29; `default:` answers 0 at line 128) |
| C8 | today's numbers: `grep -m1 "Compared answers" docs/research/assets/40-irx-differential/results_run_20260922_232655.md` (13,044 and 12,643) and the same on `results_run_20260922_150258.md` (1,794 and 19) |
| C9 | the glue's size: `diff --strip-trailing-cr fork/ps2xIOP/src/lle/<f> oracle/lle/<f> \| grep -c "^[<>]"` per patched file; `wc -l oracle/harness_lle.cpp oracle/CMakeLists.txt oracle/build.sh oracle/oracle-patch.diff`; `grep -c "^ " oracle/oracle-patch.diff` (80 context lines); `diff docs/research/assets/40-irx-differential/replay.py oracle/replay_lle.py \| grep -c "^[<>]"` |

## 1. The question and the time box

The question (the plan's T1): can #254's LLE IOP run this game's `989SND.IRX` to its first bank load as an oracle out
of the tree, given a minimal `cdvdman` provider (read, sync, the callback form) -- and what does the driver do after a
refused read, which research/69 §2 left open because `sceCdSync` 0 and `sceCdGetError` 0 read as success and a retry
loop would spin. The number: of the mission replay's 13,044 answers, how many the oracle disagrees on.

The box: one lock-free day of reading plus ONE build of the `lle/` slice with llvm-mingw under the lock. Spent: the
reading and the writing 18:15Z-19:25Z; the build waited for the queue's WIP cap (two build tickets ahead, ten refusals
from 18:29Z, queued 18:59Z) and ran 8 seconds at 19:27Z.

## 2. What 989SND.IRX does after a refused read

Read from the disc's own IRX (C4), cross-read with the decomp's error strings (C5); nothing was executed, so this is
**Believed**, not Proven. On #254's unpatched kernel every `cdvdman` import answers 0 (research/69 §2), which is what a
refused read looks like to the driver.

- **At the read.** Each of the two read kick functions (the data read behind bank loads and the VAG read behind
  streams) tests `sceCdRead`'s own return before anything else. On 0 it asks `sceCdGetError`; **an answer of 0 there
  is replaced by -1** before it is stored, so "no error" never survives a refused read. The data kick then prints
  cause 61 (and a console line unless the driver's quiet flag is set), clears its in-progress state, wakes the thread waiting on the read
  and hands the error to a registered requester; the VAG kick sets an error bit on the stream's record, prints cause 62 and
  drops the request. Neither calls `sceCdRead` again.
- **In the bank loader.** The loader reads a bank in sector runs through the stream-safe read. When that read
  refuses, or the stored error after its sync is non-zero, it stops: it reports the error (0x30, cdvdman's read error,
  or the kick's -1) to the loader's caller, signals its semaphore and returns 0. `snd_BankLoadByLoc` therefore answers
  0 for a bank whose read was refused -- a clean failure the EE sees, not a hang and not a silent success over an
  unfilled buffer.
- **Where `sceCdSync` 0 would matter.** Only after a read that was accepted: the loader trusts sync and error then, as
  it should. A provider that accepts a read must make both honest -- `sceCdSync(1)` 1 while the read is in flight,
  `sceCdGetError` the read's own result -- or the loader would parse a buffer the provider has not filled. The scratch
  provider does (§4).

So research/69 §2's worry does not hold for this driver: it does not spin and does not carry on over an unfilled
buffer. The cascade research/40 §9.2 recorded on #244 (stream torn down, "handle not found" on every later poll)
is the stream half of this clean failure, compounded by the DMA gap of §3.

## 3. A correction to research/40 §9: the "callback form" is `sceSifSetDmaIntr`

research/40 §9.1 attributed run 1's seven `snd_StreamSafeCdRead` disagreements and run 2's stream failures to "the safe-read
path's cdvdman call (`FUN_0001a52c(&buf, 1, callback, &data)`, the callback form)", and §9.3 item 2 named "#244's
cdvdman safe-read form" as one of the two gaps. The IRX's own import table (C4) places the stub at that address in the
`sifman` import block, fourth of four, and ps2sdk's name for that import is `sceSifSetDmaIntr` (C3): a SIF DMA from IOP to
EE memory with a completion callback -- `(descriptors, 1, callback, data)` is exactly its signature. The cause the
failure prints, 66, is "Error DMAing data to EE memory" (C5). #244's `sifman` answers 0 for every import but five,
and this is not one of the five (C7). research/40's reading is left as written (the plan's rule: a disagreement is
stated with its evidence, not by editing the note); research/69 §2's "for want of one `cdvdman` form (the callback
read)" inherits the same slip. What it changes: the minimal provider is not "cdvdman read, sync, the callback form" but
**cdvdman's seven imports plus `sifman`'s `sceSifSetDmaIntr`**; `ioman`'s four serve by-name loads, which the replay
may not reach (unverified).

## 4. The provider, the patch and the harness (scratch, not in the tree)

- **The oracle patch** to four of the slice's files (`oracle/oracle-patch.diff`, +122/-2 lines, C9): an `EeLink`
  hook for a host to claim an import the kernel does not bind, the stub-to-import map and one kernel handler that
  dispatches a claimed import to the host; deferred host work serviced on the IOP clock (a read or a DMA completing);
  a work counter; and `printf` rendering `%d %u %x %s %c %p`, so "989snd Error: cause N" says which N (research/40's
  patch 2 found the same need on #244).
- **The provider** in `oracle/harness_lle.cpp` (487 lines with the REPL): `sceCdRead` fills IOP memory from the disc
  image after 1 ms plus 4 MB/s (the latency is ours, research/69 §2) and refuses while busy; `sceCdSync` blocks or
  polls by its mode's bit 0; `sceCdGetError` returns the read's result; `sceCdCallback` stores the function and its
  `$gp` and the completion calls it with the read code; `sceCdStop`/`sceCdBreak` cancel; `sceCdStatus` answers read or
  pause; `sceSifSetDmaIntr` writes the descriptors to EE memory at once and calls the completion a SIF round trip later;
  `ioman` open/close/read/lseek on the extracted disc. `ORACLE_NO_PROVIDER=1` leaves them all unbound, so the same
  binary replays the refused-read case of §2 by execution.
- **The harness** speaks research/40's line protocol (`load`, `rpc`, `tick`, `peek`, `snap`), so research/40's
  `replay.py` runs against it; the scratch copy `oracle/replay_lle.py` changes only its root, its title and a `--no-usb`
  switch (19 diff lines). A `tick` of 4,920,000 EE cycles steps the IOP 800 or 801 samples and reports the SPU2's peak,
  so a replay would also say whether the oracle made sound. An RPC waits on the IOP clock up to 2 s, as #254's
  `NativeIop::call` does.

## 5. The build (C6)

llvm-mingw's clang 23.1.0, CMake and Ninja from `tools/`, one lock run of 8 seconds. Target 1, the slice as #254
ships it: `cpu.cpp`, `irx.cpp`, `iop.cpp` compile; `spu2.cpp` (line 73, `std::abs`) and `kernel.cpp` (line 328,
`std::strtol`) do not -- neither includes `<cstdlib>`, and libc++ does not reach it through `<algorithm>`,
`<cstring>` or `<cstdio>`. Target 2, the patched copy plus the harness: the same two errors and no other; the harness
and every patched line compiled. Nothing linked. research/69 C10's "the LLE slice itself uses standard headers only"
stands; it did not ask whether they are the right ones. Last line of the build log: `build end 2026-09-26T19:27:36Z`,
after `PRISTINE EXIT 1` and `HARNESS EXIT 1`.

## 6. R287: what would enter the tree

As research/40's assets did for #244, the glue would enter under `docs/research/assets/` and the take would not:

| What | Lines | Whose |
|---|---|---|
| #254's `lle/` slice (11 files) | 3,311 | the fork's; stays in an out-of-tree clone, as `docs/research/assets/40-irx-differential/CMakeLists.txt` points at #244's |
| the oracle patch, as a diff | 226 (+122/-2 changed; 80 lines of the fork's code as context) | ours, over theirs |
| the harness with the provider | 487 | ours |
| CMake and the build script | 14 + 15 | ours |
| the replay driver's change | 19 diff lines (or a copy of 211) | ours |
| the two-include fix the slice needs | +2 | ours, in the patch |

**The answer:** the TAKE entering the tree is zero lines; what enters is about 660 lines of our own glue and 80
lines of the fork's GPL-3.0 code as diff context (the same licence as ours). R287's bar ("a TAKE over about five
hundred lines needs a ruling") is not crossed by the take. If the controller counts the glue as part of the take, it
is over five hundred and needs a ruling; this note reads R287 as written and does not ask for one.

## 7. The register, the owner, the next step

- **The register row** ("the IOP host's audio path", research/68) stays **Untested**: the oracle did not run, and the
  plan moves it only with the artefact of a run.
- **The owner:** no line. The spike does not recommend the trial (D1 stays with the owner under R282, unasked).
- **For the controller, one sentence:** a second build of the scratch oracle with `#include <cstdlib>` added to
  `kernel.cpp` and `spu2.cpp` (lock class build, seconds) is all that stands between this spike and the replay's N; the
  provider and harness it would run are written and compiled, at `C:/projects/scratch-s15-t1/oracle/`.

## 8. What this note does not do

No second build (the box allows one), no replay, no game run, no runtime change: the dip count stays 6 (max 2 a
minute) and audio parity 31/48 by construction. No edit to research/40, 68 or 69, to KNOWN or to `docs/HUMAN_TASKS.md`.
Nothing is filed upstream (R284); the two missing includes are a note for #254's author in O10's words, not an issue.
The static reading of §2 names behaviour, error causes from the public decomp and the one stub address research/40
already printed; no byte, other address or ordinal of the disc's files is here.
