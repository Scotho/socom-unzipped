# Open PRs watched: what each would bring, our read of it -- research, not a report

Written 2026-09-26 (owner's scope, the same day). **Three kinds, three places:** bugs in a vendor's `main` are
`docs/UPSTREAM.md`; feedback that is not a bug is `NOT-UPSTREAM.md` beside this file; research on what waiting
upstream PRs would bring -- this file. Nothing here is for sending. It points at the notes that hold the reading
rather than repeating them: the verdicts and the watch table are `docs/research/63-upstream-triage-2026-09-25.md`
§0-§2, the ten picks' record is `docs/research/42-upstream-cherry-picks.md`, and the 2026-09-26 sweep (upstream's
branches, the forks, #254, the watch rows to add) is `docs/research/67-external-sweep.md` §1, §3 and §5.

All on `ran-j/PS2Recomp`, whose `main` is `75d729c` (2026-09-26). Local status is checked against this tree's
`git log` on 2026-09-26; "our read" is the verdict of the note named.

| PR / branch | what it would bring (one line) | our read | local status | confidence |
|---|---|---|---|---|
| #227, #229, #230, #231, #232, #237, #240, #241, #243, #246 | GS, VIF and SIF fixes (the titles are in `NOT-UPSTREAM.md` §1.1) | KEEP, research/42 | applied in our tree (commits in `NOT-UPSTREAM.md` §1.1) | high: each gated 3/3 on SOCOM II |
| #221 | a ps2autotests harness, plus MOVZ/MOVN and LWU emit fixes | TAKE the LWU hunk only, research/63 §1 | LWU applied at `53d0d50b`; MOVZ/MOVN ours already; the harness not applied (not ours) | high |
| #223 | a zero-QWC END tag completes its DMA chain | TAKE, research/63 §1 | applied at `f5028386` | high |
| #224 | bit 31 of MADR/TADR/tag ADDR selects the scratchpad | TAKE the MADR/TADR half, research/63 §1 | applied at `c7414c2b`; the tag half ours already (`51529462`) | medium: latent for SOCOM II |
| #239 | translated PS2 paths cannot leave their root | TAKE the class, research/63 §1 | our own code at `4eb07b45`, not the PR's | high |
| #253 | generated files declare only the functions they call | TAKE, research/63 §1 | our own implementation at `5d00f29d` (issue #57) | high |
| #206 | an explicit function map overrides the JAL-target scan | TAKE, research/63 §1 | **not applied**: no commit carries it | medium: measured on the recompiler's output, never built |
| #222 | defer EE time-slice preemption while interrupts are disabled | LATER, research/63 §1 (our tree has a wider form of the defect: nothing reads `Status.EIE`; the PR's premise is untrue of upstream's base too) | not applied (a scheduler-semantics change with a deadlock risk) | medium |
| #254 (Sinan-Karakaya, draft) | recorded-then-compiled VU1 programs with a compiled-against-interpreter test, and an LLE IOP running a game's own sound IRX with SPU2 | no verdict (research/67 gives none; Sprint 15's register decides) | not applied: draft, `dirty`, its fork's CI red on three jobs, 50 of its files changed on our side since the vendoring (research/67 §3) | low: read through the API only, never built Sprint 15 X1's read: research/69 (the sound drivers' imports; a note for its author in NOT-UPSTREAM §1.3). *Superseded 2026-09-27 (Sprint 15 close): decided 2026-09-26 -- its LLE IOP is adopted as an out-of-tree oracle for the audio model, never the product (the owner's word, Sprint 15 T1; research/70, `docs/research/assets/70-lle-oracle/`); the VU1 half has no verdict (`docs/LATER.md` row 5).* |
| `feature/performance-patch-1` (a branch, no PR) | paraLLEl-GS as the default GS backend, logs off by default, IOP and VU1 work | no verdict (research/67 §1) | not applicable to our tree (not proposed upstream yet) | low: one WIP commit |

The rest of research/63's 27 rows (ALREADY OURS, NOT OURS, LATER) and research/42's #226-#252 are in those notes and
are not repeated here. New rows come from the watch rows of research/67 §5 as they are read.

## Upstream issues and PRs read 2026-10-03 (research/85 §4)

Upstream `main` = `c5a9d025` (2026-09-30, a README-only change). These are upstream's own issues and PRs, filed by
other porters (drakolordx7, penpenlovesrei-dotcom, llesieur99), so nothing here is ours to file and `docs/UPSTREAM.md`'s
rows are unchanged. Local status was checked against this tree at `e9535f7f` on 2026-10-03 (the lines re-found in the
worktree); the reading is `docs/research/85-ps2-recomp-projects-audit.md` §4.2, the candidate rows `docs/LATER.md` 82,
83 and 95. Paths are the fork's, under `third_party/ps2recomp/`.

| issue / PR | what it brings (one line) | local status | confidence |
|---|---|---|---|
| #257 (issue) | D_ENABLEW `0x1000F590` writes mirror into D_ENABLER `0x1000F520`, as PCSX2's `dmacWrite32` does | **not applied**: no mirror in ours (grep of `ps2xRuntime/src`); clean, runtime-only; whether SOCOM II polls D_ENABLER is unchecked | medium: latent for SOCOM II |
| #258 (issue) + #259 | async invocation stacks carved from the top of RAM alias the main thread's stack; `GuestThread::stack` base/top confusion | **not applied**: ours has the same layout (`ps2xRuntime/include/ps2_runtime.h:571-572`, `ps2xRuntime/src/lib/ps2_runtime.cpp:2013-2016,2239`); the read-only `sp` check comes first (LATER row 82); the fix is a policy port with no patch on offer | high on mechanism; no SOCOM symptom |
| #260 (issue) | a resume entry in the delay slot of an always-taken branch continues at the target, not the fall-through | **not applied**: `ps2xRecomp/src/lib/control_flow_emitter.cpp:152-172` always falls through; clean, codegen (recomp + gate) | high |
| #262 (issue) / #268 (PR) | VCALLMSR reads `ctx->vu0_cmsar0`, not `ctx->vi[27]` on a `uint16_t vi[16]` | **not applied**: the identical out-of-bounds read at `ps2xRecomp/src/lib/vu_translation_helpers.cpp:168-181`; clean, codegen; UB, so taken even if SOCOM II never emits `vcallmsr` (unchecked) | high |
| #265 (PR) | DualShock 2 pressure bytes 16-19 are L1, R1, L2, R2 | **not applied**: ours writes L1, L2, R1, R2 (`ps2xRuntime/src/lib/Kernel/Stubs/Pad.cpp:265-268`); clean, runtime-only; matters only if the game reads pressure bytes (unchecked) | high |
| #269 (PR) | VIFcodes keep decoding between a DIRECT tag and its image data; only the DIRECT payload is re-wrapped | **not applied**: ours drains the pending PATH2 image as raw qwords (`ps2xRuntime/src/lib/ps2_vif1_interpreter.cpp:342-366`); needs porting; no SOCOM symptom known | medium |
| #271 (PR) | resume points registered for standalone `entry_*` functions (skip only those inside a real function) | **not applied**: ours skips every `entry_*` (`ps2xRecomp/src/lib/ps2_recompiler.cpp:1828-1831`); needs porting; MunchkinClubber `cc9a3ec5` is the same fix and #60's read | medium |
| #270 (PR), #274 (PR), #261 (issue), #272 (PR, the FPU half) | explicit unwind tracking; syscalls 0x79/0x7A; `-msse4.1`; FPU clamps | **already ours**, in our own form: `ps2_runtime.cpp:1550-1562` (`ec4b9fbc3`); `Kernel/Syscalls/Dispatcher.cpp:295-299`; `ps2xRuntime/CMakeLists.txt:436-439`; `ps2xRuntime/include/ps2_runtime_macros.h:878-888` (#272's VU0 lane clamp is unchecked, LATER row 89) | high |
| #266, #267 (PRs), #263 (issue) | #244 IOP kernel and CDVD fixes; `/Qspectre-` under clang-cl | not applicable to our tree (no #244 IOP in the product; llvm-mingw, not clang-cl) | high |
| #264, #273 (issues) | a static-library override silently discarded; `GSCpuBackend::SampleTexture` casts NaN S,T to int | #264 avoided by design (`ps2xRuntime/CMakeLists.txt:450`); #273 a hazard note for the CPU rasteriser oracle (its aap/libgpu2 reference's licence unchecked) | medium |
| GTTeancum's 25 PRs (#217-#219, #222-#232, #237, #242-#243, #245-#252) | closed unmerged by their author on 2026-09-27, no comment | the applied picks stay ours; #222 (N21) and the VU performance series are now branch-only designs on `codex/xmen-legends-bringup` | high |
