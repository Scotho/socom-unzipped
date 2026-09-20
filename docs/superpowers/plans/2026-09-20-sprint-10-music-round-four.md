# Sprint 10 — the mission music, round four: validate the track, not the mix

Opened 2026-09-20 ~20:10 UTC after the owner's third listen on the child-sound build: "ambiance is good. cutscene
music sounds good. Started mission and walked a few meters forward. The music issues of jumping up and down in
volume or skipping persists for a few moments before stopping all together ... Music started playing again when an
enemy was engaged, couldn't tell if it was correct because it cut off again within a few seconds." Also on the
mission briefing screen. Their question: "are we approaching the problem, the fix, or our validation methods wrong?"

## What was wrong, honestly

1. **The instrument scored the mix, not the music.** `audio_parity` scores 8 s windows of everything the game
   outputs for level, silence, oscillation, splices. With the ambience bed missing it flagged the mission windows; with
   the bed back (R178) it covers the music: a stem can drop out, jump, or stop for ten seconds under a continuous bed
   and the window still reads "no silence, level within 6 dB". 10/48 -> 31/48 with the music no better.
2. **Every reference run stood still; the owner walks and engages.** The score is adaptive -- stems chosen by
   intensity (movement, proximity, contact) and re-scored through exactly the transitions the owner triggers. The
   scripted runs exercised one long stem at rest.
3. **Five layers fixed, each proved on its own layer, none proved on the track:** the device buffer (R177), the pan
   sign, SetSoundParams reaching streams, the pre-fill, the conductor grains (R178). All real. None was a test of "the
   mission music on ours matches the console's through a walk and an engagement".
4. **"Not establishable" taken at face value once:** `snd_AutoVol`'s `how` was recorded as unknown while the IRX's
   disassembly sat in `game/analysis/`. Read tonight (below).

## What the IRX says (read 2026-09-20, `game/analysis/989SND.IRX.decomp.c`)

- **`snd_AutoVol` (`FUN_000038b4`):** target = `vol * sound.vol >> 10` capped at 127 (relative to the sound's OWN
  volume, as play is); `vol == -4` = fade to 0 then stop (the ramp end callback `FUN_00003b90` stops the sound when
  its marker is 0xfffc); `ticks == 0` = set at once; an existing type-2 ramp on the sound is cancelled and restarted
  from the current volume unless `how == 3` (then re-timed from the existing ramp's target). The game always passes
  2. Our `Mixer::autoVol` matches this shape (a new ramp replaces the running one from where it is; -4 stops at the
  end) -- **AutoVol is not the "stops, then restarts" mechanism** by reading. Struck as a suspect.
- **`snd_SoundIsStillPlaying` (`FUN_0000bb04`) -- CORRECTED 2026-09-20 ~19:30 UTC by the real decompilation
  (`research/989snd-ziemas/`, git-ignored; audit in `docs/research/36-989snd-decomp-audit.md`):** the lookup
  (`FUN_0000d6b4` = `snd_CheckHandlerStillActive`, sndhand.c:270) compares the slot's WHOLE handle word, and the
  handle the EE holds carries bit 31 (set by activation, sndhand.c:148). The streamer's free path
  (`FUN_0000d4a4` = `snd_DeactivateHandler`, sndhand.c:237) leaves the word but CLEARS bit 31 -- the reading of
  ~20:40 UTC missed the `& 0x7fffffff`. So a played-out stream answers 0 on the first tick after its last buffer's
  voice ends (`FUN_0001107c`, the tick, deactivates when nothing is queued at handler+0x44). The EE's music manager
  (`FUN_0034afd0`) polls 0x19 every frame and starts the next stem FRESH through 0x2c with queue = 0 (its only
  0x2c caller, `FUN_00342240`, never passes a parent) -- so "parentHandle 0 on all 55 plays" was the console's
  own behaviour, not a symptom. `e39a8dc` (StreamSlot::ended answering the handle) is WRONG and inverted the
  symptom: the manager never sees 0, stays in "playing" after one stem, and only an enemy-contact cue restarts
  the music -- the owner's third listen exactly. Reverted by the fix agent (see the audit's diff list: the
  0x21 SetSoundParams answer for live streams, the squared volume curve of vol.c:434, the AutoVol step schedule).
- **What the decompilation is:** Ziemas' function-by-function C of 989snd.irx v3.01 (the OpenGOAL author's).
  sndhand.c, playsnd.c, blocksnd.c, autovol.c, vol.c, loader.c and the RPC dispatcher are real code;
  stream.c (71 of 77 functions) and moviesnd.c are signatures only, so the streamer is still read from our own
  IRX's disassembly. The 0x12c4e67a extension (`FUN_0033f090`) is 989DSTRM's Logitech-headset music route;
  without a headset both PCSX2 and ours take the plain 0x2c path.

## The validation that replaces the old one

1. **Music alone.** The game's AUDIO OPTIONS page has the sliders; a step script zeroes SFX and voice on both targets
   (`scripts/parity/audio_options_explore.txt` maps the page first), so `audio_parity` scores the music track.
2. **A moving, engaging script** for the capture: the mission, X through the flyover, walk forward toward the first
   enemies, fire on contact -- the owner's path (`gameplay_damage_audio.txt` has the moves; the capture needs them
   after the sliders).
3. **The stem timeline on both machines:** ours from the stream trace (`stream_events.py`); the console's music-state
   from PINE at the addresses our runtime peeks (the adaptive score's state, the current stem). Decisions compared, not
   only sound.
4. **Bar:** the music-only parity windows through the walk and the contact within tolerance, AND the owner's ear.

## Tasks

- [x] 1. AUDIO OPTIONS mapped (`logs/parity/s10_audio_options`): MUSIC / SOUND / DIALOG / HEADSET VOLUME sliders of
      ~13 notches, one per LEFT; SOUND stereo/mono; DEFAULT SETTINGS; RETURN.
- [x] 2. `scripts/parity/music_only_mission.txt` (both targets: PCSX2's keys map takes ours' stick names). Run 1
      (`logs/parity/s10_r4_music_*`, 2026-09-20 ~22:10 UTC) was INVALID: the boot's counted CROSS presses overshot
      the main menu on both targets (ours ended at MISSION BRIEFING, PCSX2 at MAPS/INTEL when the "sliders as set"
      frame was taken), so no slider was moved and ours' -99.7 dB windows were a muted game, not a verdict. Fixed
      (`d8e10ef`): the main menu is reached by `untilref` on the logo band (proven in `options_explore.txt`), the
      SOUND and DIALOG rows by `until(box)` on their teal highlight. Runs 2-6 (`s10_r4b`..`s10_r4f`, all on
      PCSX2, each killed at its first invalid frame) taught the page one fact each: the rows sit 44 px apart
      (the first boxes straddled a gap); a slow PCSX2 boot outruns untilref's count of 12 (the chain now sets
      `SOCOM_DRIVE_SLOW_HOST=1`, the paced budget); the sliders are FINE, ~5 px of 290 per press, so 60 LEFTs
      not 16; TRIANGLE off the AUDIO page asks to CLEAR the changes, so the exit is each page's RETURN row;
      RETURN off OPTIONS asks to save to the memory card (answered NO, so the zeroed sliders never persist on
      the card). Run 7 = `s10_r4g`: the reference re-pinned, ours compared. Chain: `logs/s10_music_round4_captures.sh`.
- [x] 3. The IRX streamer read (above): the slot is freed at the voices' end, the handle word stays, the lookup answers it.
- [ ] 4. Compare the stem timelines; fix what differs; re-capture; the owner listens.
      **First valid reading, run 8 (`s10_r4h`, 2026-09-20 ~20:50 UTC; ours on the 13:40 exe = the e39a8dc model,
      before the fix agent's commits):** 6/177 windows within tolerance. Two facts, both new:
      (a) **ours' music track is ~31 dB low everywhere** -- median ours-minus-PCSX2 rms: title/menu (the PCM
      ring) -31.1 dB, AUDIO OPTIONS -31.2, briefing -24.4, mission (VAG stems) -30.1 -- while SFX/dialog matched
      within 6 dB in the whole-mix captures on the same loopback path. A factor of ~32 on the music path alone
      (handed to the fix agent as item 5; the group-1 master is 0x2f5 in the trace, the plays carry vol 0x400).
      (b) **the stems stop:** 53 streams, 7 group-1 stems, gaps of 70.5 s, 74.9 s, 59.0 s and 24.2 s between
      consecutive stems on ours; ours' windows s128-s176 carry 4-21 s of silence each where the console has none
      (the e39a8dc still-playing answer kept the EE's manager waiting -- item 1, `a0e0d0b`, is the fix to measure).
      Next: `logs/s10_music_round4_ours_only.sh <stamp>` after the agent's commits (runtime rebuilt, ours captured,
      compared against the same pinned reference).

## The owner's part -- ANSWERED 2026-09-20 ~21:00 UTC

"psx2 sounds expected, so validating against it is ideal once we establish trust in those tests." And ours, by ear,
in the mission and on the briefing screen: "plays for a while incorrectly and then abruptly stops each time it kicks
in ... choppy in a way that could be volume changes, segments interrupting each other, or abrupt pauses and starts."
So the reference stands, the music-only capture is the test to trust, and its three measures (level trace, splices,
silences) are what separate the owner's three candidates.
