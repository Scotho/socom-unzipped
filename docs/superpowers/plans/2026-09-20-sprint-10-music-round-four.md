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
- **`snd_SoundIsStillPlaying` (`FUN_0000bb04`):** alive iff the handle still resolves to its slot (`FUN_0000d6b4`:
  type 4 = a stream slot of 0x50 bytes at `DAT_0001ccdc`, the slot's first word equal to the handle). When the IRX
  clears a stream slot -- at the last block read, at the SPU voice's end, or later -- is the streamer thread's business
  -- READ, ~20:40 UTC: the streamer frees a played-out stream's slot (`FUN_0001107c` -> `FUN_0000d4a4`: slot+4 =
  0) and LEAVES THE HANDLE WORD in it; the lookup never checks slot+4; and `FUN_000163f4` allocates the first slot
  with slot+4 == 0. **So on the console a stem that has played out still answers "playing" until another stream
  takes its slot.** The EE's music manager (`FUN_0034afd0`, entries polled by `FUN_00346ea0`) keeps its cue entry
  on that answer, schedules the next stem on its own clock and passes the live handle as parentHandle -- the IRX
  queues it, gapless. Ours answered 0 at the last rendered sample: the manager read the cue as dead, dropped the
  entry, and every next stem began fresh (parentHandle 0 on all 55 plays of `s9_p1_m51_audio2`), late, or not
  until the next intensity event -- the owner's skips, stops and "restarts when an enemy is engaged". **Fixed in
  the IOP model** (`StreamSlot::ended`, `e39a8dc`): a played-out slot is allocatable and still answers its handle;
  a fresh play retakes it and only that turns the old answer to 0. Not yet measured on the track.

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
      SOUND and DIALOG rows by `until(box)` on their teal highlight. Run 2 = `logs/s10_music_round4_captures.sh
      s10_r4b` (the PCSX2 reference re-pinned over the invalid one, ours compared).
- [x] 3. The IRX streamer read (above): the slot is freed at the voices' end, the handle word stays, the lookup answers it.
- [ ] 4. Compare the stem timelines; fix what differs; re-capture; the owner listens.

## The owner's part -- ANSWERED 2026-09-20 ~21:00 UTC

"psx2 sounds expected, so validating against it is ideal once we establish trust in those tests." And ours, by ear,
in the mission and on the briefing screen: "plays for a while incorrectly and then abruptly stops each time it kicks
in ... choppy in a way that could be volume changes, segments interrupting each other, or abrupt pauses and starts."
So the reference stands, the music-only capture is the test to trust, and its three measures (level trace, splices,
silences) are what separate the owner's three candidates.
