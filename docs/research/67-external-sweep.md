# 67. The external sweep for Sprint 15: upstream, the forks, PR #254, the peers, and the watch rows to add

Date: 2026-09-26 (all reads 11:23Z-11:37Z by `date -u`). Sprint 14 Task X1, the filler. Read-only: nothing was built,
run or opened upstream; every network read was a `gh api` GET against a public repository. **This note gives no
verdict.** No TAKE, LEAVE or REIMPLEMENT appears in it: Sprint 15's register decides what any of this is worth, and a
row here is an input to that register, not a ruling. Nothing under `game/` or `recomp/output/` was read or is cited.
It starts where `docs/research/63-upstream-triage-2026-09-25.md` stopped (verdicts for #205-#253, the watch table of
2026-09-25) and does not repeat it; `docs/research/40-upstream-divergence.md` §1 gives the lineage (base `14b1e5c`,
vendored as `8736759`; upstream `main` = `75d729c`, #244, one squash commit past the base).

**How to read the numbers.** Every number carries the id of the command that produced it, `[C1]` to `[C24]`, listed
in §0. "Ours" always means this tree's `third_party/ps2recomp/` on `sprint-14` at `c5ea07a6`.

## 0. The commands

| Id | Command (every `gh api` a GET, run 2026-09-26) |
|---|---|
| C1 | `gh api repos/ran-j/PS2Recomp/compare/75d729c...main` (`status`, `ahead_by`, `.commits`, `.files`) |
| C2 | `gh api repos/ran-j/PS2Recomp/commits/main` |
| C3 | `gh api repos/ran-j/PS2Recomp` (`pushed_at`, `forks_count`, `open_issues_count`) |
| C4 | `gh api repos/ran-j/PS2Recomp/branches --paginate --jq '.[].name'` |
| C5 | `gh api repos/ran-j/PS2Recomp/compare/main...feature/iop-emulator` |
| C6 | `gh api repos/ran-j/PS2Recomp/commits/feature/iop-emulator --jq .commit.tree.sha`, and the same for `75d729c` |
| C7 | `gh api repos/ran-j/PS2Recomp/compare/main...feature/performance-patch-1` (files, additions, deletions, patches) |
| C8 | `gh api 'repos/ran-j/PS2Recomp/pulls?state=closed&per_page=100' --paginate`, kept `closed_at >= 2026-08-18T22:50:14Z` (the base's merge) |
| C9 | `gh api repos/ran-j/PS2Recomp/pulls/<n>`, `.../pulls/<n>/files`, `.../issues/<n>/comments` for n = 234, 236, 238 |
| C10 | `gh api 'repos/ran-j/PS2Recomp/pulls?state=open&per_page=100' --paginate`; `gh api 'search/issues?q=repo:ran-j/PS2Recomp+is:pr+is:open' --jq .total_count` |
| C11 | `gh api 'repos/ran-j/PS2Recomp/issues?since=2026-09-20T00:00:00Z&state=all&per_page=100'` |
| C12 | `gh api repos/ran-j/PS2Recomp/forks --paginate` |
| C13 | per fork: `gh api repos/<full_name>/compare/ran-j:main...<owner>:<default_branch>` (`status`, `ahead_by`, `behind_by`, merge base) |
| C14 | per fork with `ahead_by > 0`: C13's `.commits` subjects and `.files`; `gh api repos/<full_name>/readme`; `gh api repos/<full_name> --jq .license.spdx_id` |
| C15 | `gh api repos/ran-j/PS2Recomp/pulls/254` |
| C16 | `gh api repos/ran-j/PS2Recomp/pulls/254/files --paginate` |
| C17 | `gh api repos/ran-j/PS2Recomp/pulls/254/commits --paginate`; the lengths of `.../pulls/254/reviews`, `.../pulls/254/comments`, `.../issues/254/comments` |
| C18 | `gh api repos/ran-j/PS2Recomp/commits/e42efbe6434403018b80cda23034abf9644830ec/check-runs`, `.../status`; `gh api 'repos/ran-j/PS2Recomp/actions/runs?head_sha=e42efbe...'` |
| C19 | `gh api 'repos/Sinan-Karakaya/PS2Recomp/actions/runs?per_page=5'`; `.../actions/runs/36109199170/jobs`; `gh api --allow-escape-sequences .../actions/jobs/<id>/logs` for each of the run's three job ids as the jobs endpoint lists them (windows-msvc-x86_64, linux-clang, linux-gcc; the ids are not copied here: twelve-digit numbers trip the leak check's account-id rule) |
| C20 | `gh api repos/ran-j/PS2Recomp/compare/14b1e5c...75d729c --jq '.files[].filename'` (#244's files), then `comm -12` with C16's sorted names |
| C21 | for each C16 file: `test -e third_party/ps2recomp/<f>` and `git log --oneline 8736759..HEAD -- third_party/ps2recomp/<f> \| wc -l` |
| C22 | `gh api repos/ran-j/PS2Recomp/compare/ran-j:main...Sinan-Karakaya:main`; `gh api repos/Sinan-Karakaya/PS2Recomp/branches --paginate`; `gh api repos/ran-j/PS2Recomp/compare/main...GTTeancum:codex/xmen-legends-bringup`; `gh api repos/GTTeancum/PS2Recomp/branches --paginate` |
| C23 | peers: `gh api repos/<o>/<r>` (licence, `pushed_at`), `.../readme`, `.../contents/<path>?ref=<branch>`, `.../git/trees/<branch>?recursive=1` for N64Recomp/N64Recomp, N64Recomp/N64ModernRuntime, Zelda64Recomp/Zelda64Recomp, hedge-dev/XenonRecomp, hedge-dev/UnleashedRecomp |
| C24 | local, read-only: `find tools/llvm-mingw -name ucontext.h \| wc -l`; `sed -n 405,440p third_party/ps2recomp/ps2xRecomp/src/lib/control_flow_emitter.cpp`; `grep -n PMADDH third_party/ps2recomp/ps2xRecomp/include/ps2recomp/instructions.h`; `grep -c 'Run(' third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp` |

## 1. Upstream `ran-j/PS2Recomp`: `main`, the two branches, the closed PRs

**`main` has not moved.** `compare/75d729c...main` is `identical`, `ahead_by` 0, 0 commits, 0 files [C1]; `main` is
still `75d729c` "Feature/iop emulator (#244)", 2026-09-20T00:31:44Z [C2]. The repository's `pushed_at` of
2026-09-25T18:49:53Z [C3] is the `feature/performance-patch-1` push below, not a `main` merge: the 2026-09-25 cloud
handoff's "it has moved" read `pushed_at` as `main`. Three branches exist: `main`, `feature/iop-emulator`,
`feature/performance-patch-1` [C4]. The repository shows 137 forks and 95 open issues and PRs [C3].

**`feature/iop-emulator` is #244 before the squash.** Against `main` it is `diverged`, 22 ahead, 1 behind, merge base
`14b1e5c`, 139 files [C5]; its tree SHA equals `75d729c`'s, `8c4585e2...` both [C6]. So it carries nothing `main` does
not; its 22 commit subjects are the unsquashed history of #244 (the GS refactor 2026-08-13, "feat: IOP emulator"
2026-08-19, a batch of analyzer and ELF-parser commits 2026-09-02, "feat: remove LLE IOPs" 2026-09-20T00:17:58Z) [C5].
The last subject is the one worth knowing: #244's branch had an LLE IOP and removed it 14 minutes before the merge.

**`feature/performance-patch-1` is new work on top of `main`.** One commit, `e27a658` 2026-09-25T17:29:05Z, "feat: wip
performance patch", `ahead` 1, merge base `75d729c`, 46 files, +3,139/-675 [C7]. Its message lists "added parallel
gs", "optmized IOP emulator", "added guest and game fps count", "small vu1 optmization and guards" [C7]. What the
files say [C7]:
- **A second GS backend, paraLLEl-GS, is the default.** `ps2xRuntime/CMakeLists.txt` adds `PS2X_GS_BACKEND` with the
  values `CPU` or `PARALLEL_GS`, default `PARALLEL_GS`, refused on anything but Windows and Linux desktop.
  `cmake/ParallelGS.cmake` fetches `https://github.com/Arntzen-Software/parallel-gs.git` at
  `3a66c1976170cbc2cb53a3593fabbc7c4b2ccfbd` with `FetchContent`, links `parallel-gs`, defines `PS2X_GS_PARALLEL=1`
  and installs its `COPYING.LGPLv3`. New `gs_parallel_backend.cpp` (+501) and `gs_gl_interop.cpp` (+410).
- The same CMake file flips `PS2X_ENABLE_RUNTIME_LOGS` and `PS2X_ENABLE_AGRESSIVE_LOGS` from `ON` to `OFF`.
- VU1: `ps2_vu1_core.cpp` +279/-382, `ps2_vu1_upper.cpp` +50/-48, `ps2_vu1.h` +68/-13; `ps2_vu1_tests.cpp` +208.
- The post-#244 IOP emulator: `iop_kernel.cpp` +73/-30 and a new `ps2xIOP/tests/iop_execution_tests.cpp` (+230).
- GS tests: `ps2xTest/gs_parallel_tests.cpp` (+312), `gs_cache/gs_raw_routing_tests.cpp` (+170).

**Closed and merged PRs since our base.** 118 closed PRs in all; 5 closed at or after the base's merge time [C8]:

| PR | Closed | Merged | Author | Title | What the thread says [C9] |
|---|---|---|---|---|---|
| #214 | 2026-08-18T22:50:14Z | yes | Sinan-Karakaya | Start the main thread with COP0 Status.IE set | our base itself (research/63, row #214) |
| #234 | 2026-08-29T18:00:52Z | no | hedgeg0d | Bind the EE scheduler executor thread on first IRQ dispatch | 3 files +12; the author rebased it as #235 "so the test fix from #233 stays out of this PR" |
| #236 | 2026-08-29T19:15:41Z | no | hedgeg0d | Clamp same-start functions to Ghidra map boundaries | 3 files +70/-2; "Measured on Katamari Damacy (SLUS_210.08): 893k spurious decode errors with the Ghidra map loaded, 0 after this fix"; closed by its author as a duplicate of #206 |
| #238 | 2026-08-30T03:51:51Z | no | hedgeg0d | fix(runtime): contain translated PS2 paths | 4 files +152/-2; "Replaced by #239" |
| #244 | 2026-09-20T00:31:45Z | yes | ran-j | Feature/iop emulator | `75d729c` (research/40 §1) |

So since `14b1e5c` exactly one PR has merged (#244), and nothing has merged since 2026-09-20 [C1, C8]. Open PRs: 72
by the paginated list and 72 by the search count (research/63 had 71 on 2026-09-25) [C10]; the one new number is
#254, opened 2026-09-25T07:45:31Z [C10]. Issues and PRs updated since 2026-09-20: only #254 and #244 [C11].

## 2. The forks

`forks --paginate` lists **136** forks (the repository's `forks_count` says 137 [C3]; one is not listed) [C12].
Compared per fork against `ran-j:main` [C13]: **25 `diverged`, every one with `ahead_by > 0`**, 104 `behind`, 6
`identical`, and 1 that answers 404 (`Chris421X/PS2Recomp`: listed by the forks endpoint, not found by `repos/` or
`compare`). The 25 by `ahead_by`, each with its default branch's last push, its target and one line [C13, C14]:

| Owner / repo | ahead | behind | Last push | Target game (as the fork names it) | One line |
|---|---|---|---|---|---|
| MrCoolTheCucumber/PS2Recomp | 546 | 10 | 2026-08-16 | none named in the 250 subjects the compare returns | read in research/41; unchanged since `7978365` (research/63 §2); the API caps the list at 250 commits and 300 files |
| hkmodd/RESWIII-PS2recomp | 85 | 33 | 2026-04-10 | Star Wars Episode III: Revenge of the Sith, `SLES_531.55` (the description) | 64 files +58,756/-404; subjects mostly "Checkpoint"; `starwars_sif_overrides.cpp`, a Ghidra bridge cache; dormant since April |
| Sinan-Karakaya/PS2Recomp | 69 | 3 | 2026-09-25 | Dragon Quest VIII (PR #254's title) | the head of PR #254, §3; merge base `d74a3ce` |
| jrodales-dev/PS2Recomp | 48 | 3 | 2026-08-17 | none | GitHub Actions workflows that recompile a game from URL inputs; 5 files +621/-3 |
| dustindustindustin/PS2Recomp | 42 | 6 | 2026-09-12 | a title the subjects call "Duelists" | 62 files +11,493/-549: typed IOP RPC services (LOADFILE, CDVD, PADMAN, FILEIO, MCSERV), "Duelists" sound RPCs (auto-DMA fade, stop-all), movie bootstrap, GS fidelity, overlay load segments |
| xms0g/PS2Recomp | 19 | 63 | 2026-02-07 | none | refactors (`const`, `static_cast`, brace style), a GPR_U32/S32 SSE macro fix; the compare returned no file list |
| lucasnribeiro/PS2Recomp | 16 | 94 | 2026-01-30 | none | an Apple-silicon port, Rabbitizer via FetchContent, empty IOP stubs |
| Sorachi00/PS2Recomp-Drakengard | 15 | 1 | 2026-09-21 | Drakengard (README: "Fork of PS2Recomp focused on Drakengard") | branched at our base `14b1e5c`; `CdvdServices`, an `ezsound` service, "Emulate periodic GIF DMA channel 2 IRQ in EE scheduler", `GS_FFMD_FRAME`, the likely-branch sign at bit 63; its README forbids AI-agent contributions |
| 0xjjjjjj/PS2Recomp | 12 | 49 | 2026-07-25 | none named (a headless "halogen" harness) | headless boot, cooperative VBlank, PCSX2-compatible `.gs` dump export, synthetic pad input by env var |
| liorv63-afk/PS2Recomp | 10 | 1 | 2026-08-28 | Dragon Quest VIII | branched at `14b1e5c`; 52 files +187,399/-180 (it commits a generated `register_functions.cpp`); DQ8 SIF boot status, disc reads, "Ghidra boundary authority" |
| Sh2dow/PS2RecompNFSHP2 | 8 | 34 | 2026-03-25 | Need for Speed: Hot Pursuit 2 (the repo name) | 107 files +14,544/-112; a `build.ps1` and runtime fixes; the last subject is a blocker in input polling |
| LuisFellp/PS2Recomp | 8 | 11 | 2026-07-22 | Taiko no Tatsujin, `SLPS-20414` | SIF set/get reg dispatch, `sceSifSetDma` on `dst==0`, the COP0 IE boot fix (the fix #214 made), a texture-decompress override |
| chrisking1981/PS2Recomp | 6 | 101 | 2025-12-19 | Crash Bandicoot (a config), "sly_runner" disabled | goto labels, name sanitisation; licence field `none` |
| zmodsalt001/BEMURecomp | 5 | 1 | 2026-09-04 | Mortal Kombat: Shaolin Monks (description "Shaolin Monks Recomp attempt.") | README edits and one `register_functions.cpp` edit |
| maxigasparini/ReInPS | 5 | 1 | 2026-09-14 | Sly Cooper (the README) | MMIO address resolution for LUI-based accesses, IOP heap HLE and ROMVER, split GIF IMAGE transfers, interlaced presentation jitter |
| mathews52gb/PS2Recomp | 4 | 72 | 2026-02-02 | none | a basic GS renderer on raylib, syscall dispatch, Linux build fixes |
| BlackLineInteractive/PS2Recomp-Studio | 4 | 6 | 2026-08-06 | none | a `ps2xStudio` GUI on raylib/rlImGui |
| JustArmandoTV/PS2Recomp | 2 | 24 | 2026-06-30 | Sonic Riders: Zero Gravity (a subject) | 300 files (the API cap) +1,114,398: generated output committed |
| gustavoauneth/PS2Recomp | 2 | 7 | 2026-08-02 | none | the MMI2 opcode map for PMADDH/PHMADH/PMSUBH/PHMSBH (`d87bff4`); ours has the same values at `instructions.h:291-296` [C24] |
| phmdacosta/PS2Recomp | 1 | 1 | 2026-09-06 | none | `.gitignore` only |
| JeanxPereira/PS2Recomp | 1 | 76 | 2026-02-02 | none | "added support to stripped ELFs" (5 files +267) |
| hedgeg0d/PS2Recomp | 1 | 1 | 2026-09-05 | none | the VU0 S1/S2 test cwd fix (the content of #233) |
| flifloa/PS2Recomp | 1 | 58 | 2026-02-17 | none | a one-line `elf_analyzer.cpp` edit |
| Fernando3445/PS2Recomp | 1 | 42 | 2026-02-27 | none | `build.yml` |
| 3sx-testing/PS2Recomp | 1 | 36 | 2026-03-07 | none | `build2.yml` |

Every one of the 25 declares GPL-3.0 except chrisking1981 (`none`) [C14].

**What the single-title forks say about the hardware their titles leaned on** (subjects and file lists only; no fork
was built or run):
- **The IOP RPC boundary is where every title-specific fork spends its effort.** Drakengard: `CdvdServices` and an
  `ezsound` service body. "Duelists": typed LOADFILE/CDVD/PADMAN/FILEIO/MCSERV services and four sound RPCs by number.
  DQ8 (liorv63-afk): SIF boot status and read replies. Taiko: SIF register dispatch and a `sceSifSetDma` hang.
  RESWIII: a `starwars_sif_overrides.cpp`. Sly Cooper (ReInPS): IOP heap HLE. Each writes its title's sound-module RPC
  surface by hand, which is what our 989snd model does for SOCOM II [C14].
- **GS presentation is the second cluster**: interlaced presentation jitter (ReInPS), `GS_FFMD_FRAME` (Drakengard),
  "Stabilize interlaced presentation" and point-filtered edge sampling ("Duelists"), a PCSX2 `.gs` dump export
  (0xjjjjjj) [C14].
- **Fixes that recur across forks and are already in our tree**: the COP0 IE boot fix (LuisFellp, 2026-07-22, before
  #214); the likely-branch sign at bit 63 (Drakengard, 2026-09-20; ours at `control_flow_emitter.cpp:423-440` covers
  BLEZL/BGTZL/BLTZALL/BGEZALL [C24]); the MMI2 opcode map (gustavoauneth [C24]). Ghidra-map boundary authority recurs
  too (liorv63-afk; dustindustindustin's first subject; #236 on Katamari) and is research/63's #206 row [C9, C14].

**The limit of this method.** A compare of each fork's default branch misses work on other branches. Two known cases
[C22]: GTTeancum's default `main` is `behind` 1 with 0 ahead [C13], while its `codex/xmen-legends-bringup` is still
108 ahead, 3 behind, last commit `d885f1b` 2026-09-09 (unchanged since research/63), one of 28 branches; and
Sinan-Karakaya's fork has 16 branches (`feat/native-iop`, `feat/sound-and-vu-programs`, `perf/vu-programs`,
`perf/gs-row-reads`, `recomp/lower-memory-usage`, ten `fix/*`, `main`). A branch scan of the 136 forks was not done.

## 3. PR #254, as it stands on 2026-09-26

**State** [C15, C17, C18]: open, **draft**, created 2026-09-25T07:45:31Z and not updated since (`updated_at` equals
`created_at`). `mergeable: false`, `mergeable_state: "dirty"`, `rebaseable: false`. 69 commits, 120 changed files,
+20,730/-3,241. Head `Sinan-Karakaya:main` at `e42efbe`; base `main` at `75d729c`. 0 reviews, 0 review comments, 0
conversation comments. **No CI has run on the PR's head in the upstream repository**: 0 check runs, combined status
`pending` with 0 statuses, 0 workflow runs for that SHA [C18].

**The design** (the PR body [C15], the two README hunks it adds [C16], the commit subjects [C17]):
- **Compiled VU1 programs.** The microcode is recorded, not guessed: running with `PS2_VU_PROGRAM_PROFILE=<dir>` saves
  each entry point reached without a compiled routine as a 16 KiB code image plus a line in `entries.txt`; configuring
  with `-DPS2X_VU_PROGRAM_PROFILES=dir1;dir2` runs `tools/compile_vu_programs.py` over the recordings and compiles
  whole programs, entry point to E bit, into C++ in 8 shards by default. "Every pair still issues in order with the
  interpreter's stall rules"; "anything the compiled code cannot express, or microcode that changed since it was
  recorded, falls back to the interpreter". FMAC arithmetic has NEON and SSE2 fast paths "with exact fallbacks" and a
  plain C++ path. Its README: "Recordings and the generated sources contain game code; keep them local." Beneath it a
  VU pipeline model with compiled regions and loops: 25 `vu/ps2_vu1_*` files, +7,199/-2,836 [C16].
- **The differential test.** `ps2xTest/src/ps2_vu1_program_tests.cpp` (+330) holds one case, "compiled routines match
  the interpreter on authored programs": each compiled routine and the interpreter (`VU1Interpreter`) run side by side
  on synthetic programs that `ps2xTest/data/vu_programs.py` (+423) writes, and a failure names the first differing VF
  register, ACC, flag or VU1 data qword ("compiled first, so that a failure says where to look"); it also hands an
  entry to the interpreter part-way and runs "the rest in uneven slices" [C16]. Ten `*.vublocks` fixtures and two
  Python test files (`tools/tests/test_compile_vu_blocks.py`, `test_compile_vu_programs.py`) ride with it; 28 test
  files in all, +4,549 [C16]. Our counterpart for Sprint 15's X2 to compare is
  `third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp` (5 `Run(` cases [C24]); not compared here.
- **The LLE IOP and SPU2** (the "Native IRX modules" section added to `ps2xIOP/README.md` [C16]): the game's own sound
  modules (the body names LIBSD, SDRDRV, the Standard Kit, PCMPLAY) run unmodified on a small emulated IOP under
  `ps2xIOP/src/lle/`, 11 files, +3,311 [C16]. `cpu.*` is an R3000A interpreter with load delay slots and no caches or
  MMU; `irx.*` parses and relocates IRX files; `kernel.cpp` (+1,013) is a high-level IOP kernel (threads, semaphores,
  event flags, mailboxes, alarms, timers, interrupts, heap, SIF DMA and RPC, sysclib); `spu2.*` (+692, +122) is both
  cores: 48 ADPCM voices, ADSR, noise, pitch modulation, reverb, AutoDMA and 2 MiB of sound memory. Its contract: "An
  import the kernel does not provide returns zero, and an instruction the CPU does not implement stops its thread with
  a log message." **Its clock is the audio device's**: IOP time is counted at 36.864 MHz and advances only as the SPU2
  produces samples, 768 cycles per 48 kHz stereo pair, from the host audio callback; RPC work runs without moving the
  clock ("Charging that work to the clock let heavy RPC traffic push the drivers' timers ahead of the audio, and music
  played fast"); with no device, an RPC waiting on IOP time steps the IOP itself and gives up after two seconds. It
  hooks in at three places: `sceSifLoadModule` of a named module, `IopSubsystem::handleRpc` (a native server wins
  over a high-level one with the same SID), and the IOP heap and EE-to-IOP `sceSifSetDma`. `PS2X_AUDIO_DUMP=path`
  writes everything played as raw 48 kHz stereo s16 "for comparing against a reference offline". Its tests,
  `ps2_native_iop_tests.cpp` (+188), are 5 cases: AutoDMA order across restarts, AutoDMA from a fresh stream, BVOL
  against AVOL, the DMA registers taking LIBSD's halfword writes, a manual DMA into sound memory and back [C16]. No
  test in the file list runs an IRX.
- **The rest**: an ordered GS worker thread (`gs_threaded_backend.cpp` +344), movie audio kept in stream order in the
  MPEG stub (`MPEG.cpp` +334/-23), EE fibers (`EeFiber.cpp` +380, `ee_fiber_tests.cpp` 2 cases), host pacing
  (`EeHostPacing.h`, `ps2_ee_pacing_tests.cpp` 6 cases), `ps2_pad.cpp` +397/-77; and it carries #205-#209 (its first
  three commits, `8baabba`, `5c906dd`, `2084841` of 2026-08-17, have the subjects of #206, #207, #208) [C16, C17].
- **What the API does not show**: 11 of the 120 files report 0/0 lines, and some patches are omitted (among them
  `ps2_vu1_tests.cpp`'s +2,048); the per-file additions sum to 19,613 of the PR's 20,730 [C16].

**The conflict with #244.** The fork's merge base with upstream is `d74a3ce`: 69 ahead, 3 behind (`d9ea4fb`,
`14b1e5c`, `75d729c`) [C22]. #244 touched 139 files [C20]; **35 files are touched by both #244 and #254** [C20]: 5 in
`ps2xIOP/` (`CMakeLists.txt`, `README.md`, `iop_host.h`, `iop_subsystem.h`, `iop_subsystem.cpp`), 3 in `ps2xRecomp/`
(`elf_parser.cpp`, `function_table_emitter.cpp`, `ps2_recompiler.cpp`), 21 in `ps2xRuntime/` (among them
`EeScheduler.cpp`, `ee_scheduler.h`, `SIF.cpp`, `RPC.cpp`, `System.cpp`, `ps2_iop_host.*`, `ps2_iop_transport.h`,
`gs_frontend.cpp`, `gs_cpu_backend.*`, `ps2_gs_memory.*`, `ps2_memory.*`, `ps2_runtime.*`, `ps2_vif1_interpreter.cpp`)
and 6 in `ps2xTest/`. The PR body says it "conflicts with it in 20 files", i.e. textual conflicts; that count was not
re-measured (it needs a merge in a clone, outside this task's `gh api`-only rule). The body proposes to move the SPU2
and "the kernel calls these drivers need" onto #244's IOP emulator "rather than keep two".

**Against ours.** 57 of #254's 120 files exist in our tree, and we have changed 50 of those since the vendoring [C21];
the heaviest by our commit count are `ps2_runtime.cpp` 42, `ps2xTest/src/main.cpp` 34, `ps2xTest/CMakeLists.txt` 34,
`ps2xRuntime/CMakeLists.txt` 32, `ps2_vu1_core.cpp` 29, `EeScheduler.cpp` 21, `ps2_memory.cpp` 18 [C21]. We are on
`14b1e5c`, not `75d729c`, so the #244 conflict is a second-order cost for us; the first is these 50 files.

**Does MSVC build it now? No, and neither does GCC.** The fork's own CI on `main` at `e42efbe` (run `36109199170`,
2026-09-25T07:44:35Z) failed on all three jobs [C19]:
- `windows-msvc-x86_64`, step Build: `EeFiber.cpp(78)` cannot open `ucontext.h`; `EeFiber.cpp(43)` `aligned_alloc` is
  not a member of `std`; `EeScheduler.cpp(1852)` `__builtin_ctzll` not found; `gs_frontend.cpp(8)` `weak` undeclared;
  `gs_frontend.cpp(645)` `ps2PadCurrentGuestFrame` undeclared.
- `linux-gcc`, step Build: the LTO link of `ps2EntryRunner` and `ps2x_tests` fails, `undefined reference to
  'eeFiberEnter'`.
- `linux-clang`, step Tests: it builds, then "Passed: 485", "Failed: 1", the failing case "latched host presentation
  line-doubles interlaced field output".
The five newest runs on the fork's branches, 2026-09-24/25, are all `failure` [C19]. Our toolchain is llvm-mingw, not
MSVC, and it ships no `ucontext.h` (0 files [C24]), so the fiber path as the MSVC log shows it would not compile here
either, unless the file has a Windows branch that was not read.

**Licence.** The fork declares GPL-3.0 [C14], as upstream and our vendored copy do.

## 4. The peers: N64Recomp and its ports, XenonRecomp

The question for each: how does it validate a native replacement of a hardware unit, and what happens when native
code meets something it cannot run.

**N64Recomp** (`N64Recomp/N64Recomp`, where `Mr-Wiseguy/N64Recomp` now redirects; MIT; pushed 2026-05-27) [C23].
- The CPU path is literal translation with no interpreter behind it: `jal` becomes a call, `jr` becomes a switch when
  a jump table is recognised, function pointers go through a runtime lookup (README "How it Works", "Overlays").
- **RSP microcode is recompiled by the same project** (`RSPRecomp/src/rsp_recomp.cpp`, 1,196 lines). A per-microcode
  TOML may list `extra_indirect_branch_targets` and `unsupported_instructions`; an unsupported instruction is emitted
  as `return RspExitReason::Unsupported`, an unknown indirect target as a printf and `return
  RspExitReason::UnhandledJumpTarget`, and an unhandled opcode at generation time is `assert(false)` [C23].
- **There is no interpreter fallback at run time.** `N64ModernRuntime`'s `librecomp/src/rsp.cpp` (62 lines) calls the
  microcode function and, if the exit reason is not `Broke`, prints "RSP ucode ... exited unexpectedly" and asserts
  [C23]. The fallback is the toolchain's: a microcode that cannot be recompiled is fixed in its TOML before it ships.
- **Validation borrows an emulator's semantics rather than diffing against one.**
  `librecomp/include/librecomp/rsp_vu_impl.hpp` opens "This file is modified from the Ares N64 emulator core";
  Zelda64Recomp's README credits Ares "for RSP vector instruction reference implementations, used in RSP
  recompilation" [C23]. The CPU recompiler's own test, `LiveRecomp/live_recompiler_test.cpp` (364 lines), runs a
  recompiled function from a test file and compares memory with a "good data" block the file carries; the test
  directory is a command-line argument and no test data is in the 31-file tree; the `validate` workflow builds and
  uploads `LiveRecompTest` on five OS images and, by its text, does not run it [C23].
- **Zelda64Recomp** (GPL-3.0; default branch `dev`, pushed 2026-09-25) [C23] recompiles Majora's Mask's **audio
  microcode** (`aspMain.us.rev1.toml`, 24 extra indirect branch targets) and its JPEG microcode
  (`njpgdspMain.us.rev1.toml`), so the game's own audio code runs natively; **graphics microcode is not recompiled**:
  RT64 renders the display lists at a high level. The split: the sound unit's own code made native, the graphics
  unit replaced by a renderer written for the host.

**XenonRecomp** (`hedge-dev/XenonRecomp`, MIT, pushed 2025-08-04) [C23].
- **Instruction validation uses an emulator's test corpus as the oracle**: the README's "Tests" section recompiles
  Xenia's PPC tests (`src/xenia/cpu/ppc/testing/bin`) and runs them through `XenonTests` "to compare the results of
  instructions against the expected values" [C23].
- **Missing cases are loud at generation time**: "When a missing case is encountered, a warning is generated, or a
  debug break is inserted into the converted C++ code." Bytes that are not code are skipped by an explicit
  `invalid_instructions` list; there is no interpreter [C23].
- **Hardware units are not emulated.** "MMIO, which is typically used for hardware operations such as XMA decoding,
  is currently unimplemented" [C23]. Its port **UnleashedRecomp** (GPL-3.0, pushed 2026-06-29) replaced the GPU with
  "a new renderer ... written from scratch to translate the game's draw calls to modern APIs", because "emulation of
  the Xbox 360's GPU is not required in a recompilation", and has its own `apu/` audio layer (`audio.cpp`,
  `embedded_player.cpp`, an SDL2 driver) [C23].

**Side by side, as facts for the register** (no ranking): N64Recomp and XenonRecomp both refuse at build time what
they cannot translate and keep no run-time interpreter; #254 compiles only what was recorded and keeps the
interpreter as the run-time fallback, with a differential test between the two. The N64 ports borrow a reference
emulator's semantics (Ares) into the native code; XenonRecomp tests against an emulator's corpus (Xenia). Both the
N64 and the Xbox 360 ports replaced the graphics unit with a host renderer; for sound, Zelda64Recomp runs the game's
own microcode natively and #254 runs the game's own IRX modules on an interpreted IOP.

## 5. The rows to add to research/63 §2's watch table

Not written into research/63 (a class S note is superseded, never rewritten); Sprint 15's X1 carries them into its
own table. "Last read" is 2026-09-26 for every row.

| Source | What to watch | Why | How often | State on 2026-09-26 |
|---|---|---|---|---|
| ran-j/PS2Recomp `main` (amends research/63's row) | `compare/75d729c...main` `ahead_by` [C1] | a merge is the only event that changes the fork base; `pushed_at` is not a `main` signal | weekly, and at every sprint open | identical, 0 ahead [C1] |
| ran-j `feature/performance-patch-1` | `compare/main...feature/performance-patch-1` `ahead_by` and files [C7]; a PR opened from it | the maintainer's next direction: paraLLEl-GS as the default GS, logs off, IOP emulator and VU1 changes | weekly | 1 ahead, 46 files, 2026-09-25 [C7] |
| ran-j `feature/iop-emulator` | its tree SHA against `main`'s [C6] | carries nothing today; a new commit there would be post-#244 IOP work | at sprint open | tree = `75d729c`'s [C6] |
| ran-j closed PRs | C8's filter from the last read's date | a merge, or a close that names a duplicate or successor (#236 to #206, #238 to #239) | weekly | 5 since the base, 2 merged [C8] |
| PR #254 (Sinan-Karakaya:main) | `mergeable_state`, `draft`, `updated_at`, commits, reviews [C15, C17]; the fork's CI conclusion [C19] | the only upstream work on both native VU1 confidence and native sound; split PRs would change what can be taken | weekly while open | draft, dirty, 69 commits, 0 reviews, fork CI red on 3 of 3 jobs [C15, C19] |
| Sinan-Karakaya fork branches | `branches` and each head [C22] | #254 is assembled from `feat/native-iop` and `perf/vu-programs`; `perf/gs-row-reads` and `recomp/lower-memory-usage` are not in it | fortnightly | 16 branches [C22] |
| the fork set | C12 and C13 over all forks, `ahead_by > 0` | a new single-title fork shows which hardware a title needs | monthly, and at sprint open | 136 listed, 25 ahead, 1 dead [C12, C13] |
| Sorachi00/PS2Recomp-Drakengard | C13 `ahead_by`, subjects | our base (`14b1e5c`), active: IOP services, GIF DMA IRQ timing | fortnightly | 15 ahead, pushed 2026-09-21 [C13] |
| dustindustindustin/PS2Recomp | C13, subjects | the most detailed typed-RPC and sound-RPC work of any fork | monthly | 42 ahead, pushed 2026-09-12 [C13] |
| liorv63-afk/PS2Recomp | C13, subjects | a second DQ8 effort beside #254 | monthly | 10 ahead, pushed 2026-08-28 [C13] |
| maxigasparini/ReInPS | C13, subjects | interlaced presentation and split GIF IMAGE fixes on our base | monthly | 5 ahead, pushed 2026-09-14 [C13] |
| Arntzen-Software/parallel-gs | the commit `feature/performance-patch-1` pins and its licence file (`COPYING.LGPLv3`) [C7] | if upstream makes it the default GS, the GS our fixes sit beside changes | when the branch merges | pinned `3a66c19` [C7] |
| N64Recomp/N64Recomp and N64Recomp/N64ModernRuntime | `commits/main`; `RSPRecomp/` and `librecomp/src/rsp.cpp` | the method for recompiled co-processor microcode and its exit-reason contract | quarterly | pushed 2026-05-27 and 2026-08-30 [C23] |
| Zelda64Recomp/Zelda64Recomp | `dev`; the microcode `*.toml` configs | the reference for "the game's own sound code, native" | quarterly | pushed 2026-09-25 [C23] |
| hedge-dev/XenonRecomp and hedge-dev/UnleashedRecomp | `commits/main`; the README's Tests section; `apu/` | the emulator-corpus test method; a port that replaced its hardware units | quarterly | pushed 2025-08-04 and 2026-06-29 [C23] |
| GTTeancum `codex/xmen-legends-bringup` (research/63's row, re-read) | its head [C22] | unchanged | as research/63 | 108 ahead, 3 behind, `d885f1b` 2026-09-09 [C22] |

## 6. What this sweep adds that research/63 did not have

1. PR #254 exists and is the deepest single source for Sprint 15: a recorded-then-compiled VU1 path with a
   compiled-against-interpreter differential test, and an LLE IOP that runs a game's own sound IRX modules with the
   IOP clock slaved to the audio device. As it stands it cannot merge (`dirty`), has no review and no upstream CI, and
   its own CI fails on MSVC, on GCC and on one clang test (§3). It touches 50 files we have changed since the
   vendoring (§3).
2. Upstream's own next step is `feature/performance-patch-1`: paraLLEl-GS (LGPL-3.0) as the default GS backend, logs
   off by default, and more work on #244's IOP emulator. `main` itself has not moved since `75d729c`, and
   `feature/iop-emulator` is #244's pre-squash record whose last commit removed an LLE IOP (§1).
3. Of 136 forks, 25 carry work of their own; every single-title fork spends its effort on the IOP RPC boundary
   (CDVD, PADMAN, FILEIO, sound RPCs by number) and on GS presentation, and three recurring fixes are already ours
   (§2). The peers refuse at build time what they cannot translate and keep no run-time interpreter; #254 keeps one
   and tests against it (§4).
