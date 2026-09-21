# Sprint 10 Q1b — The gate states what it measured: plan and record

**Goal (from `docs/CURRENT_SPRINT.md` row Q1b, KNOWN §4 "The gate records WHICH BINARY it ran and nothing else").**
`summary.txt` pinned one thing, the EXE line. Everything else a score depends on could drift with no record: the
reference images, the memory card the run boots from, the drive scripts, the harness revision, the `PS2X_*`
environment. A silently-changed reference image moves every score with nothing saying anything moved — the sibling
of HANDOFF trap 4 (the pipeline cannot see a defect present in every run; it cannot see a change in its own standard
either). Q3b (the keyboard mapping hash) needs the same refusal, so it is built once here.

**Branch / tree:** `agent/gatepin` in the worktree `C:\projects\wt-gatepin`, off `sprint-10` at `48f8e12`. Pure
Python; no C++ build, no game run. The one proving launch is the controller's, after the merge (§5).

## 1. The exact set of pinned inputs (read from the code, not guessed)

| stage | drive script | references the script names (`untilref`/`ifref`, resolved like `drive.ref_for_target("ours")`) | files the scorer / drive-side checks read |
|---|---|---|---|
| title | `scripts/parity/title_menu.txt` | `ref_main_menu_ours.png` | `gate.TITLE_REF` (the same file) |
| transition | `scripts/parity/transition_probe.txt` | `ref_save_prompt_ours.png` | `gate.BRIEFING_REF` = `ref_briefing_ours.png` (`black_rows.py` is code → harness) |
| mission | `scripts/parity/gameplay_probe.txt` | `ref_save_prompt_ours.png`, `ref_hud_ours.png` | `ifpopup` → `sp_death_probe.PROMPT_REF` = `ref_popup_prompt_ours.png`; `console_compare.CONSOLE_REF` = `refs/console_spawn_slot8.png` (print-only, R78, but on every summary); `mission_fail.BANNER_REF` = `refs/mission_failure_banner.png`; `guest_probe_console.json` (the probe's tolerances AND the source of `PS2X_PEEK`) |

Plus three non-file inputs: **card** — the directory the launch boots from (`PS2X_MC_DIR` when the operator set it,
else `game/disc/mc0_parity`, which `run_gate` copies per stamp), pinned by CONTENTS as a sorted manifest hash;
**env** — the `PS2X_*` variables the mission stage (the widest) is launched with, `launch_env()`, minus
`PS2X_MC_DIR` (the card's path is not an input; its contents are, and that is the card pin); **harness** — the
manifest hash of the tracked files under `tools_py/parity` + `scripts/parity` (content read from disk, so an
uncommitted edit moves it), with the git revision and clean/dirty for the record. And the hook: **mapping** — the
first `[socom2] input mapping sha256=<hex>` line in the stages' `*.game.log`, absent until Q3b's runtime prints it.

`scripts/parity/refs/*.png` other than the two above are the ONLINE harness's references (login, lobby, the map
list); the three gate stages never read them, so they are not pinned here. `pinned_files()` is derived from the
scripts and `STAGE_INPUTS` rather than listed, so a script that starts naming another reference pins it without a
code change, and a `<stem>.ours.png` sibling that appeared would be pinned under its own name (the file the drive
would actually read) — an "unpinned input", refused.

## 2. Design

- **`tools_py/parity/pins.py`** — the mechanism, gate-agnostic: `Pin(name, sha256, detail)`; `file_pin`,
  `tree_pin` (manifest: `<relpath>\0<sha256>\n` per file, sorted), `env_pin`, `harness_pin`, `mapping_pin`;
  `compare(current, expected) -> [Drift(name, actual, expected)]` naming changed values, missing inputs and
  unpinned inputs; `lines()` (the `PIN ...` summary lines); `write_expected`/`load_expected` (the standard);
  `write_record`/`load_record` (a run's `pins.json`). `RECORD_ONLY = ("harness",)`.
- **`gate.collect_pins(base, game_logs)`** names the gate's set; `check_pins` compares it to the standard and,
  with `--accept-pins`, rewrites the standard; `baseline_pins` does the `--baseline` checks.
- **The standard: `scripts/parity/pins.json`** — `{"_about", "accepted", "pins": {name: sha256}, "detail":
  {card, env}}`. JSON, flat name → hex, because it is the same shape the run writes beside its summary (so
  `--accept-pins` is literally "the run's pins become the file", and a diff of the two is readable), because the
  gate already reads JSON (`guest_probe_console.json`), and because `detail` can carry what a hash alone does not
  say (the env's lines, the card's source). File names are their own pin names (repo-relative, forward slashes);
  the non-file pins are `card`, `env`, `harness`, `mapping`.
- **Flow of a launch.** disk check → make `out_root` → EXE line → `collect_pins` → compare. Drift and no
  `--accept-pins`: write `summary.txt` (EXE + PIN lines + `PINS DRIFTED: ...`) and `pins.json`, print
  `GATE REFUSED (pins drifted: <names>) -> <out_root>`, **exit 7, before the lock and before any launch** (no run
  is paid for). Otherwise take the lock, run the stages, then read the mapping line off `<stage>.game.log` and
  compare it too; the summary gets the stage lines, the EXE line, every PIN line and the PINS verdict; `pins.json`
  the same as JSON plus the verdict and what drifted. A late mapping drift keeps the stage lines (they were
  measured) but the verdict is REFUSED and the exit code 7.
- **`--baseline <stamp>`** compares the stamp's recorded `pins.json` to the standard (every pin it recorded — a
  changed env or card in the record is a refusal: the run was not made under the standard), then today's pinned
  FILES to the standard (the re-score reads today's reference images; today's card and shell boot nothing and are
  not asked). A stamp without `pins.json` (every run before this commit) prints `PINS unrecorded (...)` and scores.
  `--accept-pins` with `--baseline` is an argparse error: a re-score compares the record, it does not set the standard.
- **`--pins`** — the lock-free dry check (exit 0/7); `--pins --accept-pins` rewrites the standard from the tree.
  This is how the committed file was generated.
- **Exit code 7** — distinct from 1 (a stage FAIL), 2 (lock busy), 3 (disk), 4 (baseline: nothing to score); the
  online ladder already uses 7 for "pin failed", so the number reads the same across both tools.

## 3. What was done

- `tools_py/tests/test_gate_pins.py` (34 cases, written first; RED: `ImportError: cannot import name 'pins'`):
  the manifest hash (order-independent, moves on a byte/a name), the env pin (PS2X_* only, not the card path; the
  gate's own launch environment), the exact pinned-file set, `script_refs` (with the `.ours.png` sibling case),
  the card pin (the operator's `PS2X_MC_DIR` or the pristine card), the mapping hook (present / absent / two stages
  disagreeing), `compare` (changed, missing, unpinned; record-only and absent never drift; mapping compared once it
  is in the file), the summary lines, the standard file round trip, **the committed standard matches the tree**
  (a CI-side guard: a reference changed without `--accept-pins` fails the suite before any gate), and the launch
  cases with the launch mocked: a matching launch scores and states every pin; a drifted reference refuses with its
  name (no lock taken, no stage run); a refusal is not a stage failure (7 vs 1); a touched card refuses; an
  operator's `PS2X_GS_STATS=1` refuses; `--accept-pins` records and passes and the next launch matches; a mapping
  line present is refused as a new pinned input, accepted with the flag, then compared; absent is recorded, not
  refused; `--pins` writes no stamp; the four `--baseline` cases.
- `tools_py/parity/pins.py` (new), `gate.py` (`launch_env`/`card_source` split out of `run_gate` so the pin hashes
  exactly what a launch gets; `STAGE_INPUTS`, `script_refs`, `pinned_files`, `collect_pins`, `check_pins`,
  `baseline_pins`, `pins_verdict`; `--pins`, `--accept-pins`; the summary), `drive.ref_for_target(..., root=)`.
- `scripts/parity/pins.json` generated from the real tree at `48f8e12` by `gate --pins --accept-pins`, the card
  read (read-only) from the owner's `game/disc/mc0_parity` through `PS2X_MC_DIR` (the worktree has no `game/`);
  its `detail.card` then set to the canonical description rather than my absolute path. 13 pins: 11 files, card
  `682ad80b…`, env `9c1c9635…` (`PS2X_HOST_GAMEPAD=0 PS2X_PC_SAMPLER=1 PS2X_PEEK=<the six chains of
  guest_probe_console.json>`).
- `test_gate.py`'s `test_proceeds_above_default_threshold` now mocks `check_pins`: on a checkout without the
  git-ignored card the pins check (which sits between the disk check and the lock) would answer 7 first.
- `docs/parity/NOTES.md`: how a summary with PIN lines is read.

## 4. Proposed rulings (for the controller to number in CURRENT_SPRINT; next free is R184)

- **R184 — any drift refuses, whatever `--only` asked for.** The standard describes the gate as a whole; a
  `--only title` run with a drifted mission reference is still a gate whose standard moved, and `--accept-pins`
  is one flag away. Cost if wrong: an unnecessary refusal on a partial run. Overturn: scope `compare` to the
  requested stages' inputs (the per-stage lists are already in `pinned_files`' construction).
- **R185 — the harness is recorded, never compared.** The file cannot name the revision of the tree that holds it,
  and the inputs the score depends on are pinned individually; every commit to the harness is itself the record.
  The expected-pins file is excluded from the harness hash so accepting a standard does not move the harness it
  was accepted under.
- **R186 — an operator's extra `PS2X_*` variable is a drift.** The gate is defined as a boot with exactly its own
  knobs; `PS2X_GS_STATS=1` or a wider `PS2X_PEEK` changes what the runtime does and is refused unless accepted.
  `PS2X_MC_DIR` is exempt from the env pin because the card pin covers what it points at: an operator's copy of
  the pristine card matches; a touched one does not.
- **R187 — the first run that prints a mapping hash is refused until accepted.** The task said "pin it as
  mapping"; a pin the standard does not hold is an unpinned input like any other. Q3b's proving gate therefore
  runs with `--accept-pins` once, and the file gains `mapping`. An absent line is recorded as absent and never
  refused (as briefed).
- **A stamp without `pins.json` re-scores with a line saying so** (every run before this commit has none; the
  alternative is making `--baseline` useless for its whole history).

## 5. The proving launch (the controller's, after the merge, main tree, under the lock)

    python -m tools_py.parity.gate --pins                      # lock-free first: must end "PINS MATCH scripts/parity/pins.json (13 compared)", exit 0
    bash scripts/loop_lock.sh run gate --purpose "Q1b proving gate" -- python -m tools_py.parity.gate --stamp s10_q1b_pins_gate

`logs/parity/gate/s10_q1b_pins_gate/summary.txt` must show the three stage lines (3/3 is the runtime's business,
not this change's), the `EXE dist/socom2.exe bytes=... sha256=...` line, thirteen `PIN ... ok` lines (the eleven
files, `PIN card sha256=682ad80b... ok; game/disc/mc0_parity, 12 files`, `PIN env sha256=9c1c9635... ok; PS2X_HOST_GAMEPAD=0
PS2X_PC_SAMPLER=1 PS2X_PEEK=...`), `PIN harness sha256=... recorded (git <merge rev>, clean; ...; not compared)`,
`PIN mapping absent (not compared)`, and `PINS MATCH scripts/parity/pins.json (13 compared)`; stdout ends
`GATE PASS (3/3) -> logs/parity/gate/s10_q1b_pins_gate`, exit 0; `pins.json` beside it with `"verdict": "MATCH"`.
Then the negative control, no launch needed: `python -m tools_py.parity.gate --baseline s10_q1b_pins_gate` must print
`PINS MATCH` and re-score; and `PS2X_GS_STATS=1 python -m tools_py.parity.gate --pins` must print
`PIN env ... DRIFTED (expected 9c1c9635...)` and `PINS DRIFTED: env ...`, exit 7.

If the card hash on the controller's machine is not `682ad80b…`, `game/disc/mc0_parity` has been touched since
2026-09-21 01:00 (it was hashed from the main tree then) — that is the finding, not a defect in the check.

## 6. Unverified

- No gate was launched (pure-Python task); the launch path is proven with `run_gate` mocked. The one thing a
  mock cannot show is `run_gate`'s card copy after the `launch_env` split — the call is unchanged in substance
  (`copytree` then `PS2X_MC_DIR=<abs copy>`), and `test_mission_stage_launches_with_the_probe_peek_spec` (skipped
  here, runs on the main tree where the card exists) asserts the copy's contents.
- The `harness` pin's git call was exercised in a worktree (`git ls-files` in a linked worktree lists the same
  tracked set); on a checkout without git it walks the trees instead (untested path beyond its shape).
