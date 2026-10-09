# The macOS port to main, experimental (2026-10-09)

The owner, 2026-10-09 ~03:30Z, on the 2026-10-08 report (Grswld's macOS port taken onto `sprint-17` by cherry-pick,
`docs/MACOS.md`): "ill contact him. off by default it stays in, stay experimental. get it on main with as much stable
work as you can". This plan holds the two rulings that answer it and the log of the topic branch that carries the
work to `main`.

## Rulings

- **R349 (2026-10-09, the owner's word) — mouse look stays in, off by default.** Grswld's mouse look (direct yaw and
  pitch writes, left-click fire, right-click aim-hold, raw GCMouse deltas on macOS) is taken with `PS2X_MOUSE`
  defaulting to 0, where his fork defaults to 1; `PS2X_MOUSE=1` (a Dev knob: `PS2X_DEV=1` or dev mode) turns it on.
  Off, `socom2MouseApply` returns before it reads or writes anything; the test "Menus scope or PS2X_MOUSE=0" now
  also applies the mouse in Full scope with the knob unset and asserts the pad byte for byte. Contacting him is the
  owner's.
- **R350 (2026-10-09, the owner's word) — the macOS work goes to `main` as experimental, ahead of a chain.** The
  topic branch `feat/macos-experimental` off `main` carries the phase-1 port and the fork's default-off, diagnostic
  and Mac-only work; it merges on the required checks (`build`, `build-windows`, `leakcheck`) and the Python suite,
  without the merged chain a sprint slice needs (GIT_STRATEGY section 2), because everything in it is behind
  `__APPLE__`, `USE_SSE2NEON` or a default-off knob except what `docs/MACOS.md` section 4 lists. Left out as not
  stable: anything that changes a Windows code path by default -- batch-by-value's default flip, the FPCR skip, the
  guest-heap rewrite, the readback lock change -- and the VU1 worker thread (`docs/MACOS.md` section 5, LATER 105).

## Log

- **2026-10-09** -- `agent/macos-main` off `origin/main` (a519c9bf, the tree the fork's later branches sit on): 46
  fork commits by `cherry-pick -x` (the phase-1 port; the GS flush-reason counter, frame stats, batch-by-value behind
  its unset-off knob, the P-key recording; mouse look; the game-thread QoS; the bench's no-display refusal;
  `PS2X_VBLANK_NTSC`), then R349's default and the probe note renumbered 87 (the fork's 86 is upstream's macOS sizing).
  Conflicts, each kept both sides or narrowed to the picked commit: `.gitignore`, `vu1_ops_tests.cpp`'s includes, the
  test lists in `ps2xTest/CMakeLists.txt` and `main.cpp`, `ps2_runtime.cpp`'s includes, `EeScheduler.cpp` (the NTSC
  include only, not the VU1 worker's), `docs/KNOBS.md` regenerated.
- **2026-10-09** -- the docs: research/86 and LATER 102/103 (`ef16241d`), `docs/MACOS.md`, README's status note and
  Contributors, the review's fixes, by `cherry-pick -x` from `sprint-17` (README without sprint-17's "Ported with
  credit" paragraph, whose ports are not on `main`; LATER 102, ~~103~~ and 105 only). Then his VPK music fix
  (`56f4adce`, `b4ef5156`): `main` had no fix for the three errors, and sprint-17's own (`bc6984da`, gated) is kept
  wherever the two meet at the merge back. `docs/MACOS.md` rewritten for what `main` carries.
- **2026-10-09** -- the fresh review (FAIL on one item): the `PS2X_MOUSE` description was 122 characters, over
  `test_knobs_registry`'s 110 (now 92); the `[mouse] raw deltas unavailable` line printed with the mouse off (now
  only on); the Full-scope off case pinned by a test. His VPK fix reads mono files in 0xB000 chunks where upstream
  keeps 0x800, so the branch was rebuilt (unpushed) without his two VPK commits and takes upstream's gated
  `bc6984da`/`bd336f9d` instead; his finding stays credited.
