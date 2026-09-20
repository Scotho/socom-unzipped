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
      **Run 9b (`s10_r4j`, ~22:50 UTC; ours rebuilt at 15:44 local from `25a8cd5` = the three model commits; the game's
      per-app session held at 1.0):** 77/177 within tolerance. (a) was Windows: `socom2.exe session first seen: vol 0.03`
      on the endpoint -- the capture now holds it (`app_volume`), and the residual is ~6 dB on both routes (title ring
      -3.9 dB median, options page -6.5, mission stems -5.9). (b) the stems now chain: 11 group-1 stems, 8 of 11
      boundaries within 2.3 s (0, 0, 0.2, 0.8 s ...); three gaps of 11.1, 9.6 and 22.1 s remain (ours at -99.7 dB for
      ~35 s over s129-s132 while the console plays through). The console's own silences (s134-s138, s148-s149,
      s164-s176, 182 s in the late mission vs ours' 90 s) are its score's decisions after a different walk -- the runs
      are not synchronised, so the trace, not the window alignment, judges ours. Handed to the fix agent as items 6
      (the gaps: what the EE did between a stem's end and the next 0x2c) and 7 (the 6 dB: the `>> 1`, the pan table at
      pan -1, the PCM ring's chain). Run 9's PCSX2 re-pin was abandoned (the emulator's window went empty at the
      mission load -- a black screen with the loading bar, then nothing); the run 8 reference stands.
      The owner's fourth listen is in HUMAN_TASKS.
      **The fix agent's answers (~23:20 UTC):** item 6, the gaps are the GAME's: around each gap the stem played its
      full VPK length (28.96 / 2.16 / 3.89 / 3.89 s on the disc, ours 29.00 / 2.18 / 3.92 / 3.92), the first 0x19 after
      the end answered 0, no 0x2c failed, no stop, no -1 left pending; inside the gaps the EE only ducked group 1, wrote
      the ambience register (2 -> 3|5) and played SFX -- the music manager (`FUN_0034afd0`) sat in state 3 with an empty
      cue queue, which only mission/AI logic fills (`FUN_0034b6c0` via the generic play-sound API). Not ours to fix; the
      console does the same on its own walk. Item 7, the 6 dB on the stems: a stereo stream on the console is a VOICE
      PAIR -- the main voice forced to pan 270 (`FUN_000152fc`) = table[0] = (32766, 0) and the doubling voice on the
      right -- while ours centre-panned one voice (table[90] = 23167, squared: exactly 0.5). `8a43b09`: a two-channel
      stream's main voice at pan+270 and the pair mixed L/R. The title ring's -4..-6.5 dB is NOT explained (the agent's
      arithmetic predicts ours 1.5 dB louder) and stays open. Run 10 = `s10_r4k` (ours only on `8a43b09`):
      **126/177** (6 -> 77 -> 126 over the day).
      **The owner's own recordings (2026-09-20 ~23:10-23:30 UTC, five phone clips of run 10 playing on the speakers;
      envelope cross-correlation places each in the loopback at corr 0.90-1.00):** the dips they hear are in OURS'
      output -- 173.9 s (150 ms, -14 dB) and 176.0 s on the AUDIO OPTIONS page, 419.7 s (100 ms) and 420.1 s (450 ms,
      -25 dB) in the contact music -- and the "trailing silence" in three clips was the game going silent: 148.1 s
      (3.2 s after the sliders), 249.0 s (10.9 s on the briefing), 358.6 s (17.9 s at the mission start). Their
      question, "do we have an honest lead?": every choppy place is STREAMED audio (the PCM ring, the VAG stems), every
      clean one is in memory (SFX, the ambience conductor, the cutscene music) -- the unifying hypothesis is stream
      feed pacing (emulated time) against real-time consumption. The per-window score cannot see a 150 ms dip; the
      gate is now a combined trace (dump + endpoint + per-stream buffer occupancy + the guest clock) with every dip
      classified DEVICE / STARVATION / COMMAND / UNEXPLAINED (the fix agent, item 9 widened), and a decision-level
      poll of the EE music manager's state on both machines (a second agent: PINE on the console, the runtime's peek
      on ours) for the stops.
      **The console stops too:** run 8's loopback has digital silences of 33.6 s after the OPTIONS return (219 s),
      73.5 s over the briefing/loading (275 s) and 68 s from 411 s (60 s after its HUD; cut by the recorder's end, so
      >= 68 s). Ours' are shorter and more frequent (3.2, 1.6, 3.1, 10.7, 1.8, 10.9, 12.6, 17.9, 9.7, 16.2, 2.0, 33.6 s
      over the same span). Whether a given stop is the game's decision or ours' is what the state poll answers.
      The recorder's 480 s cap (fixed to 620, `5daf39b`) made run 8's late reference windows silent; re-pin = `s10_r4l`.
      **THE LEAD (2026-09-20 ~23:55 UTC, after the owner's "it doesn't even sound like music"): ours plays the two
      channels of every stereo VAG music stream OUT OF SYNC.** Content analysis of the loopback captures (L against R,
      decimated to 4 kHz, lag search +/-2 s, 25-30 s windows): the console's mission music correlates at lag 0
      (+0.26, +0.27, +0.59; the briefing +0.47); ours reads +0.05 / -0.06 at lag 0 with the best match at an OFFSET --
      +61 ms on the first mission stem in all three of today's builds (run 8 before any fix, 9b, 10), -561 ms on the
      briefing music and on later mission stems, +136 / +674 / +109 ms on others; side/mid energy ~0 dB vs the
      console's -2 dB. Per-file, deterministic first offsets (one interleave block?) that then drift: the two channel
      cursors start apart and do not advance together. The title loop (the PCM ring) is aligned on both (+0.37 vs
      +0.42). Before `8a43b09` the desynced pair was centre-mixed -- the phasey "choppy, jumping" smear of the earlier
      listens; after it, hard-panned and still desynced. Level, modulation (3-5 Hz music rhythm on both), spectral
      flatness (tonal on both), clicks (none) and spectral peaks (coincident) all read the same on both machines --
      which is why every level instrument passed it. Handed to the fix agent as item 10 (test first: a two-channel
      VPK with identical L/R renders sample-aligned across chunks, the pre-fill and an underrun); a third agent adds
      `lr_corr0 / lr_lag_ms / lr_best / side_mid_db` per window to the parity scorer with a stereo-desync compare rule.
      **THE CAUSE (`ce6ed95`, 2026-09-21 ~00:40 UTC):** a two-channel VPK is interleaved per STREAMING BUFFER, not per
      0x800 chunk. Every SOCOM stem has header word 2 = 0x800, word 3 = 0xb000, 2 channels; the IRX's stream open
      (`FUN_00013334`) requires word 3 to equal the streaming buffer the game passed to InitVAGStreamingEx (0xb000)
      and splits each buffer per channel (`>> 1`): 0x5800 bytes of LEFT then 0x5800 of RIGHT per 0xb000 of file, the
      last partial buffer split in halves. Ours read alternate 0x800 chunks as L/R -- so the right channel played a
      different part of the song, an offset that depends on the position in the buffer (the +561 / +61 / +674 ms
      lags), and every listen since the mission music first played was two copies of the score out of step. The
      scorer now flags it (`005b454`; run 10 against the 620 s reference: 118/177 with six stereo-desync windows:
      s127/s139/s140 at +560 ms, s141 -21, s147 -90, s158 -102 ms). The fix agent's instrumented run on the fixed exe
      (buffer occupancy + starvation events `a486c6d`, the dip classifier `tools_py/parity/audio_dips.py`) is next.
      **The instrumented run (`s10_r4l_music_ours`, exe 16:58 = `ce6ed95`+`a486c6d`, ~01:00 UTC 2026-09-21):**
      123/177 against the 620 s reference; the stereo rule now trips on ONE window (s156: +610 ms during a 5.8 s
      silence -- a stem boundary; item 12) instead of six. Item 8 answered: all 11 cue pushes were QUEUED (free 20,
      enable 1, none refused); every push comes from the play-sound API caller `ra 0x3432d8` (FUN_00343140); the
      gaps are stretches with NO push (a stem done at frame 17156160, the next push 47 s later) -- the game's own
      logic, next probe `PS2X_CALL_TRACE=0x343140` for its callers, and the console's manager polled over PINE for
      the same walk (music_state_poll, wired into the re-pin chain). Item 9's table (endpoint = dump + 3.9 s, corr
      0.95): COMMAND 24 (stem ends, StopSound, AutoVol, the script's own slider moves), STARVATION 5 -- ALL on the
      PCM ring (29.8, 33.4, 56.5, 209.8, 220.8 s): the EE's feed is a steady 19456 B / 100 ms then `written=0` for
      300-400 ms and a 24576 burst against a 128 ms ring, with the EE clock normal -- a feed STALL, not drift (item
      11: instrument the cdvd read behind the feeder); DEVICE 2; UNEXPLAINED 3 (22 dB dips of 1.5-3.3 s on the PCM
      route, probably the material). ZERO VAG stream underruns in the whole run. Route note: the title/options
      music is the VAG loop 0x1303f8; the PCM ring carries the intro and the briefing.
      **Run 13 (`s10_r4n`, ours, exe 17:21, the manager peeked at 20 Hz) and the console run `s10_r4o` (the manager
      polled over PINE at 5 Hz; its first run at 20 Hz took PCSX2 down at 119 s -- cause unproven):** ours 136/177
      against the run 11 reference, NO stereo-desync window. **The decision-level comparison, aligned on the HUD:**
      the first three cues line up almost to the second on both machines -- cue 0xff at HUD-12.6 s (ours 12.2 s
      long, console 11.2), cue 0xff again at +1.9 / +0.6 (7.8 / 8.2 s), cue 4 at +19.8 / +18.6 -- then they diverge:
      on OURS cue 4's stem ENDS after 9.3 s (played out, `done detail=0`; the manager idles; 14 plays of 0.05-12 s with
      idle gaps over the next 100 s, several stopped by the game 50-80 ms after their start), on the CONSOLE cue 4
      stays in state 1 on the same handle for the rest of the poll, >= 120 s. **The stem loops on the console and
      plays out once on ours** -- item 13 with the fix agent. **Its answer (~02:50 UTC):** wrong on three counts.
      `+1408` is a byte offset, not a length; cue 4 on ours is `M51_048`, a 9.15 s MONO voice line (group 2, routed
      through this sequencer by its def's music bit) and ours played all 9.14 s of it; no VPK stem carries a loop
      flag and the stems longer than a buffer play their full length (the 28.96 s stem: 28.9 s). **The polled
      manager is the mission's VOICE cue sequencer, not the music scheduler:** none of run 13's group-1 stem plays
      coincides with its transitions; the music stems reach 0x2c through FUN_00342240's two other callers
      (:242150, :242232 in the generic play-sound API FUN_00342aa0 / FUN_00343140) -- next probe `PS2X_CALL_TRACE`
      on those. Still unexplained: the console holding cue 4 in state 1 for >= 120 s with its audio silent from
      ~70 s after the HUD (a different file for that name, or a played-out handle still answered -- item 1's model
      again); the state poll is being extended to dump the sound entry and def (name, sector, handle) on every
      change to settle it. Item 12: NOT a desync -- s156 holds a wide-by-nature stem (its own channels 0.08 at lag 0
      from the disc). Item 11 so far: the PCM ring's feeder in the intro/briefing is the game's PSS demux thread,
      which the runtime parks in `sceMpegGetPicture` until a picture's presentation tick -- the one place a 300-400
      ms hole can come from with the EE clock normal (`4e446cc` traces the parks; the correlation run is in flight);
      the console's ring is the same 0x6000 bytes, so a ~400 ms delay line on the PCM route is the fallback.
      **Item 11 answered (`s10_r4m_music_ours`, ~03:20 UTC):** the feeder waits on NOTHING modelled -- 11958 stamped
      stream reads, zero cd-stream parks, zero mpeg parks, `[clock]` normal -- and around each PCM starvation the
      demux thread's reads simply stop for 0.42-0.70 s (26-41 VSync ticks pass) then resume: the calling thread is
      absent. The MPEG HLE decodes pictures with ffmpeg ON THE CALLING THREAD (MPEG.cpp:320-350, no worker); a slow
      decode burst under load starves the 128 ms ring. Item 14: a decode-ahead worker filling `decodedFrames` so
      `sceMpegGetPicture` only pops (the delay line as fallback). Item 15: `PS2X_CALL_TRACE` on the play-sound API's
      callers to attribute every group-1 stem play and read the condition that fires the next one.
      **The console's cue 4 riddle, answered by the extended poll (`0ffbf27`; run `s10_r4q`, 132/177 for ours run
      13 against its re-pin):** the console plays the same file, `M51_048` (9.15 s, group 2). Its sound ENTRY's
      handle word alternates -1 (a 0x19 poll in flight) and 0x84000006 (the IOP's answer: type 4, bit 31 set) from
      351.5 s to 367.0 s, then reads -1 for the rest of the run (to 470 s) with no further change: the console's
      poll callback never came back, so its sequencer sits in state 1 on cue 4 believing the line still plays, and
      fires no voice cue after that. A lost RPC completion on the console's side -- its own behaviour, not a model
      difference; item 1's model (a played-out stream answers 0) stands, and ours' sequencer, which does get its
      answers, simply moves on. The mission MUSIC is not this sequencer's (item 15 is where the pauses live).
      **Item 14 (`ac53a9d`, ~04:30 UTC): the MPEG decode-ahead worker is in and correct (a 300 ms fake decode
      returns in < 5 ms; 698 C++ green) and it did NOT clear the bar** -- run `s10_r4p_music_ours` (134/177) has the
      same four PCM starvations and the same 0.2-0.7 s stream-read gaps (12 totalling 4.8 s over 304 s of movie),
      VSync ticks advancing at the host rate across each: the demux GUEST THREAD is absent, not parked, not
      decoding, not reading. Ruled out: the drive, picture waits, the decode, the screenshot exports. Next: a
      per-guest-thread run trace from the EE scheduler across a gap (which thread ran, in which stub, how long) --
      a fresh agent (item 16); the mixer-side delay line (~400 ms FIFO on the PCM route, lip-sync cost on the
      briefing's speaker) stays the fallback, not taken. **Item 15, first link:** the 8 mission stems all come
      from `ra 0x343590` (FUN_00343550+0x40, a play-def-at-1.0 wrapper via the def's vtable), the title loop and
      the briefing music from `ra 0x265cd8` (FUN_002659c0+0x318, a scripted sound-command executor); both are
      virtual-dispatched, so the firing condition sits one link up -- the next run traces those.
      **Item 15 read to the source (runs `s10_r4p/q/r`, ~05:40 UTC):** the title loop and the briefing music are
      fired by the menu/briefing SCRIPT runner (FUN_00269da0 -> the command stepper FUN_0026a6e0 -> the "play sound"
      handler FUN_002659c0) on the script's own sequence. The 8 mission stems come from the mission-music state
      machine (decomp :245347-246077; `DAT_0048e090` current level -1/0-3, `DAT_0048e080` the single stem,
      `DAT_0048e088` a playlist with a cursor at +0xc, `DAT_0048e0a0` the alert level from the AI's threat float via
      FUN_00348ce0, `DAT_0048e0a8` level-changed): the per-frame tick FUN_003492b0, when nothing plays (the entry's
      handle word = our 0x19 answer), sets level -1 and re-dispatches FUN_00348dc0: levels 3/1 play a single stem,
      levels 2/0 roll a playlist (FUN_00348b20, the game's LCG PRNG against a per-level weight table) that
      FUN_00349db0 advances entry by entry as each stem ends. **No timer, no rest in the reading** -- so the 10-27 s
      gaps on ours are not yet explained by the logic as read; candidates: a rest field in the playlist entries,
      the idle test on the entry's handle word (item 1's answer), the dispatch failing on ours. The state poll gets
      a `--what music` mode for both machines to compare level / stem / playlist cursor / alert on the same walk.
      **The playlist entries DO carry a rest (`1e310d6`, ~06:20 UTC):** each 0x10-byte entry is {def (0 = REST),
      sound entry, PAUSETIME s, elapsed s}, filled from the mission's `.rdr` node's SNDNAME/PAUSETIME
      (FUN_00349e90 :246077); FUN_00349b90 (:245922) counts a rest entry done when elapsed > PAUSETIME, a stem
      entry done when its handle is dead; FUN_00349db0 plays the next at once; a finished list re-rolls the same
      tick. Four lists per mission (STEALTH, FIGHT, MED_FIGHT, HEAVY_FIGHT) with weights. So a 10-27 s gap on
      ours may be the mission's own `rest N s` entry -- the console's capture had silences of the same order --
      or a dispatch/idle-test difference; the music-state rows (every entry, the rest's elapsed, the cursor)
      separate the two. Runs `s10_r4s` (ours) and `s10_r4t` (console) carry the music-state poll.
      **ITEM 15 CLOSED (~07:20 UTC): the mission's pauses are the mission's own design, identical on both
      machines.** Both polls read the same STEALTH playlists from the mission's `.rdr`: `[rest 9.0 s | MGEN0014 |
      rest 8.5 s | MGEN0009 | rest 9.5 s | MGEN0012]` and `[rest 11.5 s | MGEN0039 | rest 9.0 s | MGEN0032 |
      rest 11.5 s | MGEN0010 | rest 10.0 s | ...]` -- at stealth level the music is a 3 s stinger, ~10 s of
      silence, a stinger; only the fight levels (alert 2/3 from the AI's threat) play a continuous stem
      (ours: fight-list MGEN0045 at HUD+86.5 s on contact, single-forced MGEN0004 at +89.9, back to stealth at
      +117.4 as the alert fell). Ours' cursor advanced through every rest and stem in order; the console's list
      started during its flyover (before its HUD), a timing difference in the level-0 dispatch, not a mechanism
      difference. Scores: ours run 14 (`s10_r4s`) 131/177 against run 12c, 137/177 against run 12d (`s10_r4t`).
      **Nothing in the mission music's decisions differs between the machines any more; what remains is
      item 16 (the PCM ring's 300-700 ms feed stalls on the intro and briefing: the demux guest thread's absence)
      and the owner's ear on the stereo fix (the fifth listen).**

## The owner's part -- ANSWERED 2026-09-20 ~21:00 UTC

"psx2 sounds expected, so validating against it is ideal once we establish trust in those tests." And ours, by ear,
in the mission and on the briefing screen: "plays for a while incorrectly and then abruptly stops each time it kicks
in ... choppy in a way that could be volume changes, segments interrupting each other, or abrupt pauses and starts."
So the reference stands, the music-only capture is the test to trust, and its three measures (level trace, splices,
silences) are what separate the owner's three candidates.
