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
  and is NOT yet read. Ours answers "done" when the last decoded sample leaves render(). If the IRX answers "done"
  earlier (at the last DISC read, while the SPU still holds ~100 ms+ of chunks), the game on the console starts the
  next stem BEFORE the current one ends -- overlapped, seamless -- and on ours only after a gap. **This is the next
  reading, and it fits "skipping".**

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

- [ ] 1. Map AUDIO OPTIONS (rows, slider step) -- running.
- [ ] 2. `music_only` step prefix for both targets; the moving capture script; the PCSX2 reference; ours' capture.
- [ ] 3. Read the IRX streamer: when a stream slot is freed (the "done" moment) -- `DAT_0001ccdc` slot writers.
- [ ] 4. Compare the stem timelines; fix what differs; re-capture; the owner listens.

## The owner's part

On PCSX2: the mission, walk a few meters, engage the first enemy -- does the console's music ever stop or jump? Every
plan above assumes it is continuous, and nobody has listened to it.
