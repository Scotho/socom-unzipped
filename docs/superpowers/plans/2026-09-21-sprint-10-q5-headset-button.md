# Sprint 10, Q5 — Goal 4: voice, the headset's own button (stopped on the spec's rule)

Written 2026-09-21 by the Q5 agent (worktree `C:\projects\wt-q5`, branch `agent/q5` off `sprint-10` at `a44eb2d`).
The item is `docs/CURRENT_SPRINT.md` row Q5; the design is the Sprint 9 spec's "Goal 4 — voice: the headset's own
button", unchanged, including its stop rule. This file is the record: what was read, the finding, the rulings
proposed (numbered from R218, for the controller to confirm), and what the controller could still launch. The
reading itself is `docs/research/39-headset-talk-button.md`.

**Scope:** documents only. No runtime, launcher, test or registry file was touched: the brief's second half (a
launcher-bound push-to-talk that drives a headset report) is conditional on the first half finding a report, and it
found none. No game was run: this worktree has no `game/`, and the launches are the controller's.

---

## What the brief asked, and what was done

1. **Two listing passes** over what `lgaud` can report, in the three unread spans the spec named -- the status
   word's bits above bit 1, the device-info block's 0x00-0x61 span, GetMixer's u16 at reply +0x2c -- with what the
   game polls and when. Done, on both sides of the SIF:
   - the EE client library, the voice object and its tick, both talk routes, and the HUD's talk element, in
     `socom2_game.elf.decomp.c` (addresses in the note);
   - `LGAUD.IRX` itself, decompiled headless into the scratchpad (149 functions, 33,364 of 33,856 text bytes) -- the
     first time this project has read the module rather than inferred it from its client.
2. **The finding: nothing in any span is, or could be, a button.**
   - The status word at reply +0x04 is `DAT_00008768`, a one-shot flag the IRX sets to 1 on USB connect/disconnect
     and clears after reporting: 0 or 1, never any higher bit. The EE's only readers test it `== 1` or `!= 0`.
   - The device-info block is four USB-audio capability lists (record formats, playback formats, record feature
     units, playback feature units), 0x14c bytes to the byte. The "name" span 0x00-0x61 is the recording half's
     format list. The only EE reader scans the playback formats for 22050 Hz (the `0x5622` literal is a sample
     rate, not a Logitech feature) to route game audio into the headset through `HEADSETO.IRX`, offline only.
   - GetMixer (0x0b) is a stub in liblgaud 1.08 (validates the handle, writes nothing) and has no caller in the
     game anyway; neither has SetMixer.
   - The IRX's descriptor parser records interrupt-IN endpoints of non-audio interfaces -- the shape of a HID
     report pipe -- and no code ever opens or reads them. No HID request exists in the module.
   - On the EE, the talk flag `voice+0x4a` has three writers, none fed by an lgaud reply; the two that can set it
     are pad actions 0xb (hold past 0.3 s, online) and 10 (RUN AND TALK), both through the controller
     configuration's action-to-slot table at `DAT_004415a8+0x12`, which is the disc's `controller.rdr`.
3. **The stop rule applied**: "two listing passes and two launches without the talk flag moving -> file what was
   read and stop". Both passes negative on every span; a launch cannot move a flag no reply reaches. Filed, stopped,
   no mechanism invented.

## What the tests say

Nothing was built. `./build.sh test --no-runner` was not run: no source under `third_party/ps2recomp/`, `recomp/`,
`tools_py/` or `launcher/` changed, so its counts would be the branch point's (1661/757 at `a44eb2d`, per the
sprint log) and the host is load-sensitive. The controller can run it on the merge if a green count is wanted on
record; the docs-only diff cannot change it.

## Proposed rulings (numbered from R218; the controller confirms)

- **R218 -- Goal 4 is closed on its own stop rule, without a launch.** The spec allowed two launches after the two
  passes; none was spent, because both passes proved there is no report for a launch to watch (the IRX's reply
  word is 0/1 by construction; the block and the mixer struct carry audio-class capabilities and nothing). Cost:
  none. Overturnable: the controller may still run one driven match with `PS2X_MIC_GAMEREAD_DUMP` to see the
  negative live, but the note says why it will be silent.
- **R219 -- Sprint 8's R113 stands with its meaning corrected, and the HLE is not changed for it.** "entryCount 0
  = no Logitech vendor extensions" is really "no 22050 Hz playback format, so the game never routes 989snd into the
  headset". That is the answer we want (host audio is the mixer's). `lgaud.cpp` still writes a name string into
  block 0x00-0x61 and 0 at 0x62; the string is misdescribed in its comments and harmless in fact (no reader of
  0x00-0x61 exists). A comment-only correction is owed when someone next edits the file, not a rebuild now.
  Cost: none. Overturnable.
- **R220 -- the HLE's state word stays at "1 once, then 2".** The real module answers 0 or 1 (never 2) and the EE
  would be equally content with "1 once, then 0"; the s8 rounds proved the open under the current values, and
  changing a proven reply for fidelity's sake costs a runtime rebuild and a gate. Recorded so nobody reads the 2 as
  the module's. Cost: none. Overturnable, cheaply, whenever the runtime is next rebuilt for another reason.
- **R221 -- the one launch worth making is a peek, not a proof, and it is queued behind the sprint's ranked
  items.** Read `DAT_004415a8+0x12+0x0a` and `+0x12+0x0b` in a live online round (the action-to-slot bytes for
  the two talk actions; 0x10 = unbound). If either is bound, the talk button exists and the harness's pad overlay
  (`online_login_ours.py`, `SOCOM_PAD_OVERLAY`) already knows how to hold it; if both read 0x10, the talk action is
  not in this build's loaded preset and the question moves to the disc resource `data/common/controller.rdr` -- a
  different goal, and the owner's to rank against the sweep and the holes. Cost: one round, later. Overturnable.

## What the controller could run after the merge (none is owed by this record)

The spec's bar, for the record, in case R218 is overturned and a launch is wanted:

1. A driven match with the mic instruments in the operator's environment (the Sprint 8 plan's `_mic_env(side)`
   helper was never written; the s8 rounds set the knobs by hand, and `{title}` in a dump path expands to the
   instance's window tag so one exported value serves both -- `79a9e26`, `docs/KNOBS.md:120-123`):
   `PS2X_MIC_FAKE=<the reference WAV from scripts/parity/refs/make_voice_ref.py>`,
   `PS2X_MIC_GAMEREAD_DUMP=logs/parity/<out>/{title}_gameread.wav`,
   `PS2X_MIC_DUMP_PLAYBACK=logs/parity/<out>/{title}_playback.wav`, then the two-instance round through
   `online_match_ours.py` as `s8_voice_round4` was run. Expected under the finding: `[lgaud] lgAudOpen mode=3
   rec=1ch/16bit/8000Hz ...` in both logs, **no** `[lgaud] lgAudStartRecording`, the game-read WAVs absent or
   empty, the playback WAVs silent -- because nothing sets `+0x4a`.
2. The R221 peek in the same round: the two bytes above, once the lobby has loaded the preset; the controller's
   peek tooling from `s8_voice_round3` reads them.
3. Only if a slot is bound: the overlay holding it for the round, then `audio_corr --ref-wav` on `A_gameread.wav`
   against the fake source (>= 0.95 while held, silent otherwise), then `B_playback.wav` carrying A's voice.

## Unverified, plainly

- The IRX decompilation lives in the scratchpad, not the tree (game bytes). The command shape to regenerate it is in
  the note; the function-address list for the second pass is there too. Nobody else has read it yet.
- The exact vendor/product acceptance bands in the IRX's probe are contorted in the decompilation and were not
  pinned; they do not bear on the question.
- The loaded preset's slot bytes (R221) were never read live, here or in Sprint 8.
- `FUN_002c64e0`'s second argument (the pad state block) is not visible in the decompilation at the two talk-route
  call sites (`FUN_002c64e0(0xb)`, `FUN_002c64e0(10)`); which pad's state they test is assumed to be the player's.
  Sprint 8's sixteen-bit sweep is the empirical side of that assumption.
