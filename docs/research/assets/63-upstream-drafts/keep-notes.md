# The ten KEEP picks: one note per upstream PR

> Drafts for the owner to post as PR comments on ran-j/PS2Recomp (docs/HUMAN_TASKS.md row O10). Nothing here has been
> posted. Each section's quoted block is the comment. The lines under it are the evidence in our tree and are not
> for upstream.

## What every note rests on

- **The gate.** `python -m tools_py.parity.gate` is the project's three-stage in-game gate (title, transition,
  mission; `docs/DEVELOPING.md:261`). "3/3" means all three stages PASS on SOCOM II (NTSC-U, the r0001 build), with
  the recompiled executable rebuilt with the pick applied. Each pick was also run through the full unit suite
  (Python and `ps2x_tests`, the PR's own cases included). For the GS and VIF picks it was also run through
  `--vram-diff`, which compares the CPU rasteriser's VRAM against the host-draw path on 15 captured VU1 dumps at a
  1.00% tolerance.
- **The record.** `docs/research/42-upstream-cherry-picks.md:162-173` is the per-pick table (base, branch head,
  exe sha256, suite, vram diff, gate). `:202-213` is the combined branch: all ten together, `ps2x_tests` 891/891,
  vram 15/15, `s11_picks_keep_gate` 3/3. `docs/research/64-the-four-menu-captures.md:384-394` replays each stamp
  under the title scorer as amended on 2026-09-25, and every one of the eleven still PASSes.
- **In the tree.** The picks were fast-forwarded into `sprint-11` at `3bb866f4` (`docs/archive/CURRENT_SPRINT-sprints-9-to-11.md`,
  task 6 row) and are ancestors of `sprint-13`. The verdicts are in `6be03dac`.
- **Taken as written.** For each of the twelve upstream commits, the added and removed lines of our cherry-pick are
  identical to upstream's (compared 2026-09-25: `gh api -H "Accept: application/vnd.github.diff"
  repos/ran-j/PS2Recomp/commits/<sha>` against `git show <ours>`, `+`/`-` lines only). Only context moved, because
  our base is `14b1e5c`, before #244. On 2026-09-25 each PR was still open and its head was the commit we took
  (`gh api repos/ran-j/PS2Recomp/pulls/<n>`).
- **What the notes do not claim.** Our base is pre-#244, so none of these was tested on upstream `main`. A gate pass
  says the pick did no visible harm to one game. It does not say which pixel it fixed.

## #231 Correct TEXCLUT addressing for CSM1 and CSM2 (GTTeancum)

> Tested downstream on SOCOM II (a pre-#244 fork of this repo): cherry-picked unchanged, and our three-stage in-game
> gate (title, transition, mission) passed 3/3. The unit suite, including this PR's cases, was green, and our VRAM
> diff of the CPU rasteriser against a second draw path was 15/15 at 1%. Also 3/3 combined with #227, #229, #230,
> #232, #237, #240, #241, #243 and #246. Nothing to change from our side.

Evidence: stamp `s11_pr231_gate`, exe `4949afda…`, branch head `187e8bc` (`research/42:164`). Our commit `895643cf`
(upstream `2e9861201bca`). No adaptation.

## #229 Support GIF IMAGE2 transfers (GTTeancum)

> Tested downstream on SOCOM II (pre-#244 fork): cherry-picked unchanged, and the three-stage in-game gate passed 3/3.
> Unit suite green including this PR's GS and VU1 cases; VRAM diff 15/15. Also 3/3 combined with the other nine PRs
> listed on #231. Nothing to change.

Evidence: `s11_pr229_gate`, exe `e542ef3a…`, head `87a2263` (`research/42:165`). Ours `1bf931b1` (upstream
`101958abbf50`). No adaptation.

## #243 Handle 128-bit writes to GS privileged registers (GTTeancum)

> Tested downstream on SOCOM II (pre-#244 fork): cherry-picked unchanged, and the three-stage in-game gate passed 3/3.
> Unit suite green; VRAM diff 15/15; also 3/3 in the combined set. Nothing to change.

Evidence: `s11_pr243_gate`, exe `b386b914…`, head `d3e0048` (`research/42:166`). Ours `8987b64e` (upstream
`1f8a5876e672`). No adaptation.

## #230 Honor GS COLCLAMP during alpha blending (GTTeancum)

> Tested downstream on SOCOM II (pre-#244 fork): cherry-picked unchanged, and the three-stage in-game gate passed 3/3.
> Unit suite green; VRAM diff 15/15; also 3/3 in the combined set. Nothing to change.

Evidence: `s11_pr230_gate`, exe `07abdf5d…`, head `5bb1eb9` (`research/42:167`). Ours `495d4217` (upstream
`099738ac37eb`). No adaptation.

## #237 Expand VIF UNPACK V2 and V3 lanes (GTTeancum)

> Tested downstream on SOCOM II (pre-#244 fork): all three commits cherry-picked unchanged, and the three-stage in-game
> gate passed 3/3. Unit suite green including the V2/V3 phase cases; VRAM diff 15/15; also 3/3 in the combined set.
> One merge note: this PR and #232 both append their VIF UNPACK test at the same point in
> `ps2xTest/src/ps2_memory_tests.cpp`, so merging one after the other conflicts in that file only. We kept both sets
> of cases.

Evidence: `s11_pr237_gate`, exe `0a2a3a33…`, head `5bb7165` (`research/42:168`). Ours `21d02c2e`, `1279f97f`,
`18a318fa` (upstream `f072ed345b9c`, `2bd95c3037bc`, `6e542cff995a`). The test-file conflict and its resolution:
`research/42:205-208`.

## #232 Expand VIF UNPACK V4-5 channels (GTTeancum)

> Tested downstream on SOCOM II (pre-#244 fork): cherry-picked unchanged, and the three-stage in-game gate passed 3/3.
> Unit suite green; VRAM diff 15/15; also 3/3 in the combined set. We checked for a double scale: the only other
> 5-to-8-bit expansions are the PSMCT16 texel/CLUT decodes in the GS backends, which is a different path. Same
> test-file conflict with #237 as noted there.

Evidence: `s11_pr232_gate`, exe `7a16b2cb…`, head `aeb70a5` (`research/42:169`). Ours `c58dbbc7` (upstream
`79edf0746384`). The double-scale check: `research/42:189-191` (`gs/gs_cpu_backend.cpp:43-45`,
`gs/gs_gl_backend.cpp:142-144`).

## #227 Preserve framebuffer rows in interlaced presentation (GTTeancum)

> Tested downstream on SOCOM II (pre-#244 fork): cherry-picked unchanged, and the three-stage in-game gate passed 3/3.
> Unit suite green; VRAM diff 15/15; also 3/3 in the combined set. For reviewers: this is the one PR of the set that
> removes behaviour (`applyFieldPresentation`), and it does so in the CPU present path. Our shipped backend is GL, so
> the gate shows no harm rather than a visible fix.

Evidence: `s11_pr227_gate`, exe `41a20ce8…`, head `7d9a1c8` (`research/42:170`). Ours `77570a0d` (upstream
`5b4fa3dcd17a`). The caveat: `research/42:217-222`.

## #240 fix(runtime): route SifSetReg and SifGetReg syscalls (hedgeg0d)

> Tested downstream on SOCOM II (pre-#244 fork): cherry-picked unchanged, and the three-stage in-game gate passed 3/3.
> Unit suite green; also 3/3 in the combined set. We could not tell whether this title issues syscalls 0x79/0x7A. The
> counters are only printed under `PS2_IF_AGRESSIVE_LOGS`, and the gate does not set it. So this is "no harm", not
> "exercised".

Evidence: `s11_pr240_gate`, exe `3a17d5b0…`, head `1c6d733` (`research/42:171`; its suite was proven in Step 2,
`research/42:71`). Ours `98e06920` (upstream `80deb9a8654a`). The pre-check that could not be answered:
`research/42:195-198`.

## #241 fix(runtime): complete raw SIF DMA init handshake (hedgeg0d)

> Tested downstream on SOCOM II (pre-#244 fork): cherry-picked unchanged, and the three-stage in-game gate passed 3/3.
> We also booted to an online lobby against our own server. Our fork answers IOP RPCs through its own HLE transport
> on the same raw-DMA path, so the risk was a doubled or shadowed reply. None showed: the same two unhandled-RPC trace
> lines appear with and without the PR, and there were no faults. Our SIF DMA unit cases were green with it. The
> handshake itself could not be counted in a normal run, because the SifSetReg/GetReg counters sit behind
> `PS2_IF_AGRESSIVE_LOGS`.

Evidence: `s11_pr241_gate` 3/3 and `s11_pr241_online` (`LOBBY class=ok`), exe `d78abf93…`, head `7f62e95`
(`research/42:172`, `:177-185`). Ours `a65f6f5a` (upstream `e70cedcbd5cb`). The risk as stated before the gate:
`research/42:37-50` and `:73`. Our server's address, the persona and the login steps are not in the comment.

## #246 Reject depth-failing triangle pixels before texture shading (GTTeancum)

> Tested downstream on SOCOM II (pre-#244 fork): the code was cherry-picked unchanged, and the three-stage in-game gate
> passed 3/3. Unit suite green including this PR's GS cases; VRAM diff 15/15; also 3/3 in the combined set. Two
> things we noticed: `ps2xTest/cmake/CompareGsEarlyDepth.cmake` is not wired into any CMake target. And
> `PS2X_GS_DISABLE_EARLY_DEPTH` is read with `std::getenv`: our fork routes every `PS2X_*` variable through a
> registry, so we added a registry row for it (a local policy, nothing upstream needs).

Evidence: `s11_pr246_gate`, exe `edd649b6…`, head `e5839b4` (`research/42:173`). Ours `ec6d948d` (upstream
`9398dcc76dc8`) plus two fork commits, `30cf9510` (the knob row, read through `ps2x::knob`, presence as upstream's
`!= nullptr`) and `f7a7e206` (`docs/KNOBS.md` regenerated). Why: `tools_py/tests/test_knobs_registry.py` fails a
`PS2X_*` getenv, and that failure had stopped the PR's own tests from running (`research/42:74`). The caveat about
the CPU rasteriser being our VRAM-diff oracle: `research/42:217-222`.
