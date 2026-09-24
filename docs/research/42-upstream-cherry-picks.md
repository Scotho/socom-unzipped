# 42. The cherry-pickable upstream PRs: what each one is, whether it still applies, what the suite says

Date: 2026-09-24. Sprint 11 Task 6 (milestone U item 2), Steps 1 and 2. Step 1 fetched the open `ran-j/PS2Recomp`
PRs listed in `docs/research/40-upstream-divergence.md` §5 and cherry-picked the ones that apply onto a branch of
their own; Step 2 (this note) rebased each surviving branch onto the moving `sprint-11` and ran
`./build.sh runtime --no-runner && ./build.sh test --no-runner` under the loop lock, once per branch.

The **verdict column is deliberately empty.** KEEP/DROP is the controller's Step 3 decision, taken on the
`s11_pr<N>_gate` 3/3 runs and, for the GS/VIF picks, `--vram-diff` 15/15. Nothing here is merged to `sprint-11`,
nothing is pushed, and no game was launched by this step.

Worktree: `C:\projects\wt-cherry` (a worktree of this repository; `C:\projects\socom_pc`'s working tree was not
touched). Branches: `agent/pr<N>`, one to three commits each on top of `sprint-11`.

## 1. Why ten picks and not twenty-seven

Upstream's open PRs #226-#252 are all branches on `origin/main` = `75d729c` ("Feature/iop emulator (#244)"),
i.e. on the **post-#244** tree, while our base is `14b1e5c`, the commit before it (research/40 §1). A pick is
viable only where its hunks land in files #244 did not rewrite. Step 1's outcome, restated from the branches:

- **Ten picks landed:** #227, #229, #230, #231, #232, #237 (three commits), #240, #241, #243, #246.
- **`agent/pr226` carries no commit.** The branch exists and points at the Step 1 base with nothing on it: the
  coalesced GIF DMA interrupt change lands in the DMAC path #244 rewrote.
- **`agent/pr245` and `agent/pr247` … `agent/pr252` carry no commit** for the same reason. The VU performance
  series (#245-#252) is written against upstream's post-#244 `ps2xRuntime/src/lib/vu/`, and our `vu/native/` +
  `vu/generated/` work has moved that subsystem a long way (research/40 §2).

Consequence for Step 3: **there is no VU performance pick on the table.** Every row below is GS, VIF, EE memory
or SIF. The `[vu1-stats]` half of the brief's performance evidence has nothing to measure.

## 2. The ps2xIOP / SIF contact rule (research/40 §1)

- **No pick touches `third_party/ps2recomp/ps2xIOP/` at all.** Nothing goes near `snd989.cpp`, `lgaud.cpp`,
  `eznetcnf.cpp`, `dbcman.cpp`, `module_factories.h` or the profile ABI.
- **#241 is the one deep SIF contact.** It rewrites `sceSifSetDma`'s tail in `Kernel/Stubs/SIF.cpp` and adds
  `EeScheduler::dispatchIrqNow`. Three behaviours ride with it:
  1. a raw SIF DMA descriptor whose `dest` is 0 is no longer copied to EE address 0 but treated as the IOP
     sifcmd receive endpoint;
  2. an `SIF_CMD_INIT_CMD` (`0x80000002`) packet with `opt == 1` gets a synthesised 24-byte SET_SREG reply
     written into the EE receive buffer recorded from the matching `opt == 0` packet;
  3. the DMAC channel-5 interrupt goes through `eeScheduler().dispatchIrq` / `dispatchIrqNow` instead of
     `ps2_syscalls::dispatchDmacHandlersForCause`.

  Our `ps2_iop_transport.h` and `ps2_iop_host.cpp` consume that same raw-DMA path, so (1) and (2) can shadow or
  double an answer our transport already gives. Evidence in its favour: with #241 applied, our own SOCOM-specific
  raw-DMA tests still pass — `sceSifSetDma applies SJX DTX payloads into the emulated SJRMT data ring`,
  `… acknowledges DTX work-buffer transfers by advancing the EE footer ticket`, `… recognizes SJX DTX payloads
  from rotated EE work buffers`, and the 989snd reset-semantics tests. That is a unit-level result, not a boot;
  **gate #241 on a title run and the boot handshake, not on pixels.**
- **#240 is SIF-adjacent but shallow:** two `case` labels in `Kernel/Syscalls/Dispatcher.cpp` routing EE syscalls
  `0x79`/`0x7A` to the `ps2_stubs::sceSifSetReg` / `sceSifGetReg` that already exist in our tree (they already
  carry `g_sifSetRegLogCount` / `g_sifGetRegLogCount`). No SIF state shape changes.
- The other eight touch GS front/back end, the VIF1 interpreter or `ps2_memory.cpp` only.

## 3. The table

`base` is the `sprint-11` commit the branch sits on. `sprint-11` moved by about twenty commits while this step
ran (the controller was merging), so the bases differ between rows; each row's suite is green against its own
base. Every pick brings its own tests, so "all pass" includes the PR's own cases.

| PR | What it does | Files (besides its tests) | Rebased | Suite | ps2xIOP / SIF contact | Verdict (Step 3) |
|---|---|---|---|---|---|---|
| **#231** TEXCLUT by CLUT storage mode | CSM1 ignores COU/COV/CBW and reads from block 0; CSM2 shifts COU left by 4. Before: COU/COV/CBW were applied in both modes. | `gs/gs_cpu_backend.cpp` (+8/−3) | yes, onto `38161fd` (`0340bc4`) | **all pass** — Python 2268 OK (106 skipped); `ps2x_tests` 868/868, 0 failed; vram diff 15/15 checked at 1.00% tolerance; 8 field compares 0 mismatching | none | |
| **#229** GIF IMAGE2 (FLG=3) | `GIF_FMT_DISABLED` becomes `GIF_FMT_IMAGE2` and is decoded as an image transfer in the GIF frontend, the native image-upload fast paths and the VU1 XGKICK tag walk. | `gs/gs_types.h`, `gs/gs_frontend.cpp`, `ps2_memory.cpp`, `vu/ps2_vu1_core.cpp`, `ps2_debug_panel.cpp` | yes, onto `0bf1a5d` (`704931d`) | **all pass** — Python 2268 OK; `ps2x_tests` 864/864; vram diff 15/15; field compares clean | none | |
| **#243** GS privileged 128-bit SQ writes | `PS2Memory::write128` to a GS privileged register writes only the low 64 bits instead of spilling the upper lane into the next bus slot. | `ps2_memory.cpp` (+9) | yes, onto `1b47be2` (`a439d7d`) | **all pass** — Python 2268 OK; `ps2x_tests` 870/870; vram diff 15/15; field compares clean | none | |
| **#230** COLCLAMP during alpha blending | The blend result is clamped only when `COLCLAMP.CLAMP` is set; otherwise it wraps to 8 bits, which is what the hardware does. | `gs/gs_cpu_backend.cpp` (+9/−3) | yes, onto `38161fd` (`553f539`) | **all pass** — Python 2268 OK; `ps2x_tests` 868/868; vram diff 15/15; field compares clean | none | |
| **#237** VIF UNPACK V2 and V3 lanes | Three commits: V2 expands to XYXY; V3's W lane follows a hardware phase derived from `vl`, the packet's start alignment and the unpack iteration; V3 quadword boundary behaviour. | `ps2_vif1_interpreter.cpp` (+69) | yes, onto `1b47be2` (`c5bea70`, 3 commits) | **all pass** — Python 2268 OK; `ps2x_tests` 873/873; vram diff 15/15; field compares clean | none | |
| **#232** VIF UNPACK V4-5 channels | The 5/5/5/1 packed value is expanded into the high bits of each lane (`<<3`, `>>2`, `>>7`, `>>8`) instead of being delivered as raw 5-bit values. | `ps2_vif1_interpreter.cpp` (+5/−5) | yes, onto `1b47be2` (`9e88966`) | **all pass** — Python 2268 OK; `ps2x_tests` 870/870; vram diff 15/15; field compares clean | none | |
| **#240** SifSetReg / SifGetReg syscalls | Routes EE syscalls `0x79` and `0x7A` to the existing SIF register stubs. | `Kernel/Syscalls/Dispatcher.cpp` (+6) | yes, onto `1b47be2` (`60c8262`) | **all pass** — Python 2268 OK; `ps2x_tests` 870/870; vram diff 15/15; field compares clean | **SIF-adjacent**, shallow: two dispatch cases, no state change | |
| **#227** interlaced presentation | Removes `applyFieldPresentation` and the SMODE2 decode from `PresentFromLocalMemory`: field mode no longer duplicates rows from the odd/even source line. A removal, not an addition. | `gs/gs_cpu_backend.cpp` (−34) | yes, onto `c1a06d1` (`4184d5f`) | **all pass** — Python 2268 OK; `ps2x_tests` 862/862; vram diff 15/15; field compares clean | none | |
| **#241** raw SIF DMA init handshake | See §2. `sceSifSetDma` synthesises the IOP's sifcmd/sifrpc boot reply; `EeScheduler::dispatchIrqNow` invokes DMAC ch5 handlers inline. | `Kernel/Stubs/SIF.cpp` (+82/−4), `Kernel/EeScheduler.cpp` (+51), `runtime/ee_scheduler.h` (+1) | yes, onto `1b47be2` (`387131a`) | **all pass** — Python 2268 OK; `ps2x_tests` 870/870 including our SJX/DTX raw-DMA and 989snd reset cases; vram diff 15/15; field compares clean | **yes — the one real SIF contact.** No `ps2xIOP/` file touched, but it changes the path our IOP transport reads | |
| **#246** reject depth-failing triangles before shading | `DrawTriangle` reads the Z buffer and skips a pixel whose depth test fails before it shades, instead of letting `WritePixel` decide. CPU rasteriser only. Adds a standalone `CompareGsEarlyDepth.cmake` comparison script (not wired into any CMake target). | `gs/gs_cpu_backend.cpp` (+18/−1), `ps2xTest/cmake/CompareGsEarlyDepth.cmake` (new) | yes, onto `1b47be2` (`0ef03be`) | **FAILED, then not rebuilt (yielded).** First run: `tools_py.tests.test_knobs_registry.SourceAgainstRegistryTest.test_no_problem_in_the_tree` — the pick reads `PS2X_GS_DISABLE_EARLY_DEPTH` with `std::getenv`, which our registry forbids; that one failure aborted the step before `ps2x_tests` ran at all, so **the PR's own 149 lines of GS tests have never been executed here.** Fixed on the branch by two fork-policy commits (`07cc25d` registers the knob and reads it with `ps2x::knob`; `7065f1b` regenerates `docs/KNOBS.md`); `python -m unittest tools_py.tests.test_knobs_registry` is 11/11 green with them. The full suite rerun was cut short by the controller's yield of the loop lock to the r0004 critical path | none | |

**Sizes.** With `--no-runner` the build produces `third_party/ps2recomp/build-clang/ps2xRuntime/libps2_runtime.a`
and `dist/socom_unzipped_launcher.exe`. The launcher is **3,682,304 bytes on every branch** (no pick touches
`ps2xLauncher/`). The library: #227 6,185,618 · #229 6,186,436 · #230 6,191,932 · #231 6,191,886 · #232 6,192,954
· #237 6,193,406 · #240 6,193,166 · #241 6,207,104 · #243 6,192,960 · #246 6,193,664. These are **not comparable
between rows** — each was built on a different `sprint-11`, and the tree grew by more than the picks did over the
same hours. The only within-row reading worth having is that #241 is the largest jump (+14 KB over its
neighbours on the same base), which matches its +134 lines of scheduler and SIF code.

### What Step 2 cannot measure

`--no-runner` builds the runtime library, the launcher and the tests; it does **not** build `dist/socom2.exe`,
because no generated game code is in this worktree. So for every row:

- **exe size: not measured.** There is no `socom2.exe` to weigh; the library and launcher figures above are the
  only size evidence this step can give.
- **`[gs-gl stats]` and `[vu1-stats]`: not measured.** Those lines come from a game run, which is the
  controller's gate. No game was launched.

## 4. Recommended gate order

Ordered by expected value to SOCOM II, GS/VIF correctness first, with the SIF pick last because it is the one
that can change boot rather than pixels. (The brief's "VU performance last" rule has nothing to order: §1, no VU
performance pick survived.)

1. **#231 TEXCLUT by CLUT storage mode.** The highest-value row. Every paletted texture in the game goes through
   `LookupCLUT`; today CSM1 applies COU/COV/CBW it must ignore, so any non-zero TEXCLUT silently reads the wrong
   palette entries. This is the pick most likely to move a visible defect (research/31's flat grey geometry,
   research/34's CLUT serials). Gate with `--vram-diff` 15/15.
2. **#229 GIF IMAGE2.** `FLG=3` was decoded as "disabled", so an IMAGE2 upload was dropped entirely and, worse,
   the VU1 XGKICK tag walk mis-measured the packet and desynchronised everything after it. Small, mechanical,
   and it fixes a dropped-data class rather than an off-by-one. `--vram-diff`.
3. **#243 GS privileged SQ writes.** Cheap and contained (9 lines), and what it protects is the display register
   pair — a 128-bit store to DISPFB/DISPLAY currently spills its upper lane into the next register slot. Anything
   the game sets that way is being corrupted now.
4. **#230 COLCLAMP.** Correct hardware behaviour for a bit we already decode; visible as wrong bright or dark
   pixels wherever a blend overflows with CLAMP off. `--vram-diff`.
5. **#237 VIF UNPACK V2/V3 lanes.** Real geometry correctness, but the largest behaviour change of the VIF pair:
   the V3 W-lane phase is a heuristic over packet alignment and iteration count, and a wrong phase writes garbage
   into a vertex lane. Gate it on its own, `--vram-diff` 15/15, and watch the 3/3 for geometry that moved.
6. **#232 VIF UNPACK V4-5.** Small and self-contained. Before merging, confirm nothing downstream in our tree
   already scales the 5-bit channels — this pick moves the scaling into the unpack, and a second scale would
   double it.
7. **#227 interlaced presentation.** Last of the GS picks deliberately: it *removes* behaviour from the CPU
   backend's present path, our shipped backend is GL, and the CPU present is what the VRAM-diff oracle reads. Low
   upside, and it changes the oracle. Gate it after the picks that add correctness, not before.
8. **#240 SifSetReg / SifGetReg.** Two dispatch cases. Only meaningful if the game issues those syscalls at all;
   the cheap pre-check is whether `g_sifSetRegLogCount` / `g_sifGetRegLogCount` ever move in a title run. If they
   do not, this is a no-op and can be kept or dropped on taste.
9. **#241 raw SIF DMA init handshake.** **Gate last, and differently.** Its risk is not pixels: it intercepts the
   raw-DMA path our IOP transport owns and synthesises an IOP reply the transport may already be producing. The
   gate that means something is a boot to the title screen with the IOP transport trace on, checking that the
   handshake happens once and that DMAC ch5 handlers are not invoked twice. A green `--vram-diff` would say
   nothing about it.
10. **#246 early depth reject.** Not yet suite-green here (see the table): its own tests have never run in our
    tree. Re-run `./build.sh test --no-runner` on `agent/pr246` (the two fork-policy commits are already on the
    branch) before gating. Even then the payoff is bounded — the change is in the CPU rasteriser, which is not
    the shipped backend — so it is a correctness/perf improvement to the VRAM-diff oracle itself, which is a
    reason to be careful rather than eager: it moves the reference the other GS picks are judged against.

## 5. Provenance and how to re-derive any row

Each branch carries its upstream commit hash in the commit subject, e.g.
`(cherry picked from ran-j/PS2Recomp#231 2e9861201bca)`.

    git log --oneline sprint-11..agent/pr<N>      # the pick
    git diff  sprint-11...agent/pr<N>             # the pick against our tree

The suite each row reports is exactly:

    export LOOP_LOCK_WAIT_SEC=5
    bash scripts/loop_lock.sh run agent-cherry --purpose "T6 pr<N> suite" --wait 2400 \
      -- bash -c './build.sh runtime --no-runner && ./build.sh test --no-runner'
