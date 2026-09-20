# Sprint 9, Q0 — the mission music, investigated before it is fixed

Opened 2026-09-20 by the controller after the owner failed `playtest-1` at step 6: "the music cues still failing
awfully during the first mission. All the same issues mentioned earlier which should have been resolved on this
sprint." The owner's instruction: "a deep investigation, and ensure we really are confident we know the issue." Their
two questions: do we need to validate against PCSX2, and how do we validate music is playing accurately at all.

This file is the record. Every claim carries what it rests on; every hypothesis says what would kill it. Nothing is
"fixed" until an instrument reproduces the defect on our build AND a reference says what right sounds like.

## 1. The symptom, in the owner's words

First mission, X through the dialog, walking toward the first two targets: "the music sounded like it was getting
louder and quieter and jumping between different tracks. It was not coherent. Glitched between different samples."
"Skips and almost plays two different spliced segments." Voice and sound effects fine. Also between menus and once on
entering a lobby. Reported 2026-09-18, 2026-09-19, 2026-09-20 -- three builds, one description.

## 2. Why three sprints of fixes changed nothing (established)

Goal 10's spec named two stream-path bugs as the root cause (R169 queue, R170 ramp ownership) plus two universal ones
(R171 loop flags, R172 concurrency cap -- declined). The spec's own "cheapest discriminating experiment" was to trace
`parentHandle`/`reused` through a driven mission: "if `reused == true` appears during mission music, 1 and 2 are
confirmed together." It was run (`logs/parity/s9_p1_m51_audio2`, 2026-09-19 20:05) and came back **negative**:
`parentHandle` is 0 on all 55 stream plays, `reused` never true, zero `QUEUED`/`REPLACED`/`seam` lines. **R169-R171
are protocol-correct and dead code on the mission path.** The fixes were committed on the strength of a code reading,
not on that test's result, and the sprint file said "the owner hears this every session" over a fix nothing had heard.

## 3. What the existing capture actually contains (read 2026-09-20, never read against the timeline before)

`logs/parity/s9_p1_m51_audio2/mission.game.log` + `mission_audio_playable.wav` (559.6 s, the mission HUD from ~t=340).

- **The music is ~4-second stems.** Group 1 is the music group. The cues it played, read off the VPK headers at the
  logged sectors of `game/SOCOM II - U.S. Navy SEALs (USA).iso`: `0x11e17d` 4.3 s, `0x11e0e2` 4.0 s, `0x11ec92` 3.9 s,
  `0x11ed2d` 4.3 s, `0x11f0d0` 2.6 s, `0x11f1da` 4.2 s, `0x1240d8` 4.3 s; and four long ones (`0x1159a2` 29 s,
  `0x11f50a` 18 s, `0x11dc7b` 9.5 s, `0x1319ce` 30.3 s -- the last is the pre-mission music). Stereo, 32 kHz, VPK.
- **The game chains stems by polling.** `snd_SoundIsStillPlaying` is called 6,261 times in the run (~11/s). For every
  music stem, the game's first "0" answer is followed by the NEXT music play **3 to 13 log lines later**. One
  exception: handle `0x04000496` was faded (`snd_AutoVol [h, 0, 0x1e0, 2]`, 2 s to zero) 107 lines after it started
  and the next stem started 163 lines after that -- a crossfade rather than a wait. Three AutoVol calls in the run, all
  on music, all 2 s fades to zero.
- **So every ~4 s the music crosses a boundary through our whole start-latency chain:** last sample -> `done` (set in
  the render call where the data ran out, `snd989_mixer.cpp` render) -> the game's next poll (up to ~90 ms) -> RPC ->
  `Mixer::playStream` opens the ISO, seeks and reads the 0x30-byte header **on the EE thread** -> push -> the worker
  wakes (10 ms cadence) and decodes the first chunk pair -> the next 10 ms callback picks it up. Tens of milliseconds of
  silence, in the music, every four seconds. That is "skips" literally. On the console the 989snd IRX owns the CD
  streamer and its own timing; whether IT leaves a hole is section 5's experiment.
- **VAG stream underruns are not counted anywhere.** `underruns` exists only for the PCM (movie/menu) ring. A starved
  music stream plays silence and resumes from the same position (`render`: `haveSamples = false`, `pos` unchanged) --
  a stretch, not a skip -- and leaves no trace. The run's "clean" event counts are blind to this class.
- **The PCM ring underran 384 times in 50 s before the mission** (t=220-270, the briefing/loadout screens, ~8/s), then
  0 through the mission. The one instrument that could see, saw a defect on a screen the owner also names.

## 4. Ruled out by reading (each with the reason, so nobody re-derives it)

| Hypothesis | Verdict | Why |
|---|---|---|
| The mixer tells the game a stem finished early (so the next starts on top of it) | **Out** | `snd_SoundIsStillPlaying` -> `Mixer::isPlaying` -> `!done`; `done` is the CONSUMER flag set when the last sample plays, not the producer's `ended` (`snd989_mixer.cpp` `isPlaying`, `render`, `soundIsStillPlaying` in `snd989.cpp`) |
| A stream underrun causes the "jump" | **Out as the jump** | An underrun is silence-then-resume from the same `pos`: a stutter/stretch, not a jump. Still a live suspect for "skips" |
| The game's own `snd_SetMasterVolume` writes are the "louder and quieter" | **Out for the mission** | 140 group-1 writes, but in the mission window they are ONE smooth 5 s fade-in ramp at load (0x1d3->0x2f5, t=340-345, every group at once) and a single write at t=425. The jagged interleaving the pipeline map saw is in the briefing screens |
| The R169/R170 mechanisms | **Out** | Section 2 |
| The mix going to digital zero for 30 s at a time mid-mission (Q1's scorer: 56 gaps, 143 s after the mission start, 36.8 s at 7:56, 34.3 s at 8:45) is the music defect | **Out** | The game's 989snd RPC rate drops to ZERO in exactly those windows (t=475-505, 525-555 wall) and the frames are the HELP pop-up ("press SELECT to open the TACMAP ... PRESS X TO CONTINUE"): the game is PAUSED, every sound stops, and the driven script's late `wait+15` steps never dismiss it. Legitimate, and a human dismisses it in a second. Consequence for the instrument: score the mission portion with the pop-up windows excluded, and the harness must `ifpopup` on every mission step, not only the early ones |

## 5. Open, ranked, each with the experiment that settles it

1. **Stem-boundary holes** (section 3). *Settles it:* the PCSX2 reference (`logs/pcsx2_mission_audio_ref.sh`, the
   real IRX standing still at mission start). **PCSX2 2.8.1's SPU2 wave log is a dev-build feature -- the release read
   the patched keys, opened SPU2 and wrote nothing -- so the emulator's output is recorded at the endpoint by WASAPI
   loopback instead (`tools_py/parity/loopback_record.py`, pyaudiowpatch) scored by the Q1 envelope/splice/silence
   instrument beside our WAV. If PCSX2's music has no holes at stem boundaries and ours does, this is confirmed and the
   fix is start-latency (pre-open and pre-decode the first chunk at play time; never a disk read on the RPC thread).
2. **Stream starvation on a loaded machine** (the owner's 2x window, real GPU, real pad, a real session). *Settles it:*
   the stream event trace on the output-frame clock (section 6), run in the owner's conditions; the owner's third
   observation (scale 1 vs 2) is the cheap version.
3. **The pan sign loss** -- FOUND, certain, constant. `snd989.cpp` `playVagStream` splits the vol|off and pan|off words
   with `>> 16` and no sign; the game passes pan `0xffff` (-1, "default") on every music cue; the host gets 65535 and
   the pan table wraps it to 105 degrees. ~2.3 dB right on all music. Not the oscillation; part of "not coherent". Fix
   test-first (RED written in `socom2_audio_tests.cpp`).
4. **`vol` applied when flags bit 6 is clear.** research/06 marks bit 6 "use vol/pan" as inferred; the capture never
   sets it, and 14 of 55 streams ask for vol 0x0000 -- which we play silent. All music is 0x400 so music is unaffected;
   the layer under it may be. *Settles it:* audible in the PCSX2 reference or not.
5. **The host device endpoint -- FOUND to differ, 2026-09-20 ~02:30.** The harness negotiated 48 kHz/10 ms
   (`frames/call=480`). **This machine's default output device is "Speakers (JBL Flip 6)", a Bluetooth speaker at
   44.1 kHz** (`pyaudiowpatch` WASAPI enumeration; the wired Realtek and NVIDIA endpoints are 48 kHz). When the JBL is
   connected, raylib's 48k->44.1k linear converter runs, `render` is called with ragged counts, and Windows' Bluetooth
   audio stack adds its own buffering -- none of it exercised by any capture, all of it on the path the owner listens
   on. **The owner confirmed at ~04:05: every listen was through the JBL.** So no ear has ever heard this game on the
   path the instruments measured, and no instrument has ever measured the path the ear heard. *Settles it:* the owner
   plays through a wired output (HUMAN_TASKS item 0); and our build captured BOTH by
   `PS2X_AUDIO_DUMP` (pre-device) and by loopback at the JBL endpoint in one run -- the difference is the device path.
6. **The PCM-ring interleave contradiction** (research/32 section 7 says sample-interleaved, measured; the mixer
   implements 512-byte L/R blocks and says the doc's reading was wrong). The title path correlates 1.000 with the code
   as it is, so the CODE is right for the title stream and the DOC is stale -- but it wants writing down. Menu path only.

## 5b. What Q1's scorer found on the existing capture (2026-09-20 ~03:00; `tools_py/parity/audio_envelope.py`)

Whole file: 78 silences totalling 292 s (51.7% digital zero), 174 splices (13 sample-steps, all after the mission start, clustered 4:10-4:24 and 7:03-7:54; 161 spectral-flux events, 86 of them within 0.5 s of a gap edge, i.e. audio resuming). Oscillation 7.5-12.8 per minute, but the peak is in the menus and is the gaps punching the envelope to the floor; on the longest GAPLESS spans it reads 3.2-5.3 dB against 4.24 for an injected +/-6 dB wobble -- so a real wobble exists independent of the dropouts, with the caveat that gunfire moves a mix several dB in that band and only the PCSX2 difference is a verdict. The long mid-mission gaps are the HELP pop-ups (section 4).

**Correction to the clock (03:50):** the `[audio-trace] t=` value IS the WAV clock (rendered frames / 48000), so on it the mission's fade-in is at 340-345 s and the first music stem at 355 s -- not "3:35". Re-scored like for like, pop-ups excluded: **the first minute of mission music (WAV 345-405) has 20 silences below -60 dB** -- ten of them 60-400 ms holes at 358.0, 364.6, 365.1, 367.2, 367.6, 368.0, 373.9, 379.0, 379.6, 380.3 s (median spacing 2.0 s), the rest 0.8-5 s stretches and the 11.4 s pop-up at 386. Sub-second holes every couple of seconds in the middle of the score is the owner's "skips" as a list of timestamps. Whether the real game has them is the PCSX2 window 241-300 s of `pcsx2_mission_loopback.wav`.

## 5c. THE REFERENCE (2026-09-20 04:20) -- `logs/parity/pcsx2_mission_audio_ref/pcsx2_mission_loopback.wav`

PCSX2 2.8.1, the real 989snd IRX, the same ISO, standing still at the mission start, recorded at the same JBL endpoint the owner listens on (44.1 kHz WASAPI loopback; PCSX2's per-app routing override had to be removed for it to reach any endpoint -- section 6b). Like for like, the first minute after the mission fade-in:

| | silences (< -60 dB, >= 50 ms) | sub-second holes | median hole |
|---|---|---|---|
| PCSX2, 273-333 s | **0** | **0** | -- |
| ours, 345-405 s | **20** | **12** | **128 ms** |

After its first minute the real game settles to a continuous bed at -39 dB (oscillation 0.35, no splices, no silences, for two minutes). Ours between stems is digital zero. **Two facts are now established by measurement, not reading:** (1) the real game has no hole at a stem boundary, so ours' ~4 s cadence of 60-400 ms holes is a defect of ours; (2) the real game has a continuous bed under the music that ours does not produce at all, so a boundary that would be masked on the console is a hole of silence on ours. Which of the two the owner's ear reports as "skips" and which as "louder and quieter" no longer matters: both must go. The trace run (section 6) says whether each hole is a boundary or an underrun; the bed's identity is the next read.

**Also found in the same pass:** `Mixer::setVolPan` looks up only bank handlers -- a `snd_SetSoundParams` on a STREAM handle is dropped. The game starts its positioned voice streams at vol 0 (flags 2, a pan in degrees) and raises them with that very call (4 such calls in the first 30 s, one per vol-0 stream). Those lines are silent on ours. Certain from reading; a RED test is owed.

7. **REVERB -- the leading identity for the console's bed (04:35).** The game calls `snd_SetReverbType(core 2, type 3)` and then `snd_AutoReverb(core 2, 0, 0xf0, 3)` repeatedly (a 1 s depth ramp on the music/effects core); `snd989.cpp` stores type and depth in `m_model.reverbType/Depth` and forwards NOTHING -- the mixer has no reverb path at all. A studio reverb over the ~4 s stems and the 134 bank sounds fired in the mission's first 30 s is exactly a continuous midrange bed at -39 dB, and its tail is what bridges a stem boundary on the console while ours drops to digital zero. It would also account for "louder and quieter" (dry stems arriving and leaving abruptly against nothing) and "not coherent". Spectral shape is consistent (the bed peaks near the music's own centre) but that is not proof. *Settles it:* a PCSX2 capture with the reverb call disabled by pnach (the harness already patches PCSX2: `scripts/parity/pcsx2/0F6FC6CF.pnach`; `snd_SetReverbType`'s EE stub returning early) beside the reverb-on capture from tonight. If the bed thins to the dry stems and the boundaries show, the bed is reverb and the fix is a reverb in the mixer (the SPU's algorithm is documented; the open 989snd reimplementation and PCSX2's SPU2 both carry one) -- a feature, not a patch, and a Sprint 9 Q item of its own.

## 5d. THE TRACED RUN (05:15) -- `logs/parity/s9_q0_m51_trace/` (dump + JBL endpoint loopback + stream events)

**Device path, measured.** Same mission minute (WAV 340-400 s): the pre-device dump has 5 silences, 2 sub-second; what Windows sent to the JBL has **45 silences, 41 sub-second (55-350 ms)**. Forty-one dropouts a minute appear between `render()` and the speaker. The dump is written per callback and cannot see a late callback; the endpoint can. PCSX2 on the same endpoint with the same recorder: 0 in three minutes. Mechanism: raylib opens the device with miniaudio's low-latency defaults -- 10 ms periods x 3, a 30 ms WASAPI buffer (`raudio.c:474`, `MA_DEFAULT_PERIOD_SIZE_IN_MILLISECONDS_LOW_LATENCY 10`, `MA_DEFAULT_PERIODS 3`) -- and under gameplay load the device thread misses its 10 ms deadline ~40 times a minute. PCSX2 runs 20 ms plus time-stretch. **This is the owner's "skips", on the path only the owner ever heard.** Bar for the fix: endpoint dropouts per mission minute, 41 -> ~0, on this same driven run.

**Music on ours is sparse, not chained.** Mission stems start at 340, 348, 355, 379, 390, 410 s, each 3-4 s (one 17.9 s), and the game fades and stops them itself (`AutoVol` 2 s, then `snd_StopSound`, e.g. handle `04040486` at ~351 and ~355 s). Between stems ours is digital zero for 6-15 s where the console holds a bed. The stems carry NO VAG loop flags on disc (every block's flag byte is 0), so looping is ruled out; the bed is something else (reverb: the A/B; or a layer we never hear -- next). Correction: the "zero-length stem" reading of `11f275` was the instrument's gap -- a game-side stop set `done` without an event; `closeStream` now emits Done(0xFFFFFFFF).

**Stem-boundary holes did not reproduce** in this run's dump (2 sub-second silences in the minute, vs 12 in `s9_p1_m51_audio2`), and the trace shows the stems are not chained back-to-back here, so that first-run reading was not deterministic boundary latency. Underruns: three stems starved 480 frames (10 ms) each at their first callback -- the worker's first fill -- and nothing else.

## 5e. RETRACTIONS AND THE A/B (05:45) -- what measurement took back

- **Reverb is OUT.** The pnach applied (`emulog.txt`: "6 game patches are active"), and the console with `snd_SetReverbType`/`snd_AutoReverb` patched out is indistinguishable from the console with them: first music minute -26.5 dB / osc 1.90 vs -26.5 / 1.93; the settled bed -39.3 / 0.37 vs -39.4 / 0.38; identical band shares. Hypothesis 7 is dead by measurement, and so is the idea that ours needs a reverb to close this.
- **"Digital zero between stems" is retracted for the traced run.** Sections 5c/5d read the first run's silence list (`s9_p1_m51_audio2`: 20 silences in the music minute) as ours having no bed. In the traced run (`s9_q0_m51_trace`) the dump between stems is -28 to -30 dB with 0.1-0.4% zero samples -- a bed, louder than the console's -39 dB (ours was walking and shooting; the console stood still). The first run's holes did not recur in the second run's dump (12 -> 2 sub-second), so they were run-specific, not the mixer's steady behaviour. What DID recur, and is reproducible on the path the owner hears: the endpoint dropouts (5d).
- **What stands, measured:** (1) the device path drops out ~41 times a minute at the speaker under gameplay load, the console 0 -- fix in flight (`mix_device.h`, the runtime's own 20 ms x 4 device); (2) `setVolPan` never reached a stream, so every positioned voice line the game raises from vol 0 stayed silent -- fix in flight; (3) the pan sign -- fixed and gated; (4) three stems starve 10 ms at their first callback (the worker's first fill) -- small, real, now visible. The owner's ear judges the rest.

## 6. The instrument (being built test-first, `socom2_audio_tests.cpp`, RED written)

`snd989::StreamEvent` {Start, Done, Underrun} with `frame` = the mixer's output-frame clock (`Mixer::renderedFrames`),
which is the clock `PS2X_AUDIO_DUMP`'s WAV is written on (`ps2_audio.cpp` writes every rendered buffer from the first
callback) -- so an event's frame IS a WAV offset. Emitted to stderr as `[audio] 989snd stream <h> start|done|UNDERRUN
frame=N ...` and to a test sink. Tests: start/done stamped within one render call of the truth; a starved stream
reports every underrun with its frame, is NOT done, and stretches by exactly the starved frames. Then a Python reader
that pairs done(N) -> start(N+1) into boundary holes in ms, and a driven M51 run with it on.

**State of the code at 04:50:** the event clock and the pan-sign fix are built into `dist/socom2.exe` and under the gate (`s9_q0_trace_gate`); `Mixer::setVolPan` reaching stream handles is written, RED watched ("audible once the game raises it (peak 0)"), syntax-clean, not yet built -- it takes the next test+runtime+gate cycle. The stream-event reader (`tools_py/parity/stream_events.py`, 4 tests) and the envelope/splice/silence scorer (`tools_py/parity/audio_envelope.py`, 12 tests) are green.

## 6b. Host-side changes made for the reference capture (to undo)

- The per-app audio routing override for `tools/pcsx2/pcsx2-qt.exe` was REMOVED from `HKCU\Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\PropertyStore` (backed up to the scratchpad as `pcsx2_audio_override_backup.txt`, key|value). PCSX2 A was silent at every endpoint with it in force; instance B's override is untouched. Restore by re-picking the device in Windows Settings, or by recreating the key.
- `pyaudiowpatch` was pip-installed for the WASAPI loopback recorder.

## 6c. THE FIX MEASURED (07:00)

`s9_q0_m51_trace2`, the same driven mission on the runtime that opens its own device (20 ms x 4, `mix_device.h`): endpoint dropouts in the mission minute **42 -> 2**, the endpoint now mirroring the dump (3 silences / 4 at the speaker, against 5 / 46 before). The mix-open line names the device, the period and the engine rate from now on. Gate `s9_q0_device_gate` 3/3, suite 682/682. Still open and small: every stem starves its first callback (10-20 ms) while the worker's first fill lands -- pre-fill one chunk pair at play time.

## 6d. THE AUDIO PARITY CHECK (08:30) -- the owner's ask, built

`scripts/parity/audio_parity.sh capture|compare` + `tools_py/parity/audio_parity.py` (7 tests): the same step script on PCSX2 and ours, each recorded at the endpoint, cut into per-step windows by the drive's step times, scored, and ours compared to the console's pinned JSON with tolerances (holes: ref + 2 + 50% -- 41 against 0 fails at once; splices, silences, oscillation likewise; rms within 6 dB). Reference pinned from tonight's console capture. It is the visual gate's shape applied to sound, and it measures the path the owner hears rather than the mixer's output.

**The owner's second listen (08:10), same words as asked:** better, not fixed -- "stuttering, skipping a bit" walking to the first enemies; "two segments playing at once and then both stopped abruptly" on the briefing; a stop at the HELP pop-up (the game pauses there; PCSX2 stood still and never opened one -- unmeasured). His log carried the trace: the device line is right, and **every stream's first callback starved -- 21 underruns, one per stream start, 20 ms each** (the worker fills on its own 10 ms cadence; with a 20 ms period the hole doubled). Fixed: `playStream` decodes the first chunk pair itself before the push (RED: "the first 20 ms render already carries the stream (peak 0)"). The briefing's two-at-once: his log shows the 29 s briefing cue `1159a2` under two voice lines, the second starting 0.4 s before the game stopped the first (`done detail=0xFFFFFFFF`) -- the game's own interrupt, or our `SoundIsStillPlaying` answering early; the parity check's briefing windows will say which.

## 6e. THE FIRST AUDIO PARITY VERDICT (09:55) -- `logs/parity/s9_q1_parity_ours/audio_parity.txt`

`launch_to_mission_xl` on ours, recorded at the JBL, 50 windows scored against the console's 48: **FAIL, 10/48.** Two readings. (1) A harness bug: `drive.py --seconds` defaults to 400 and killed our game while the script and the recorder ran on, so s33-s47 are digital silence (-99.7 dB) on ours -- fixed in `audio_parity.sh` (`--seconds 600`), re-run queued. (2) The real finding, in the windows that are honest: **menus and settings PASS** (s06, s08, s10, s12, s14, s15 -- holes 0/0, levels within a dB or two), **the cinematic PASSES** (s20, s22, s23, s25), and **the mission windows FAIL on content**: standing still after the flyover, ours reads -34/-36/-39/-30 dB where the console reads -22/-23/-28/-24 (s24, s26, s27, s31), with 3-6 s of silence per 8 s window (s24 5.5 s, s31 4.1 s, s32 6.1 s) where the console has none, and oscillation 14-25 against 1-5. **The console plays something continuously at the mission start that ours does not play at all.** Not a timing defect of the mixer -- a request or a subsystem: either the game on ours does not ask for it, or we drop what it asks for. Leading suspect: 989DSTRM, the second streaming engine the game initialises through `snd_CallExtension` (fn 0) and, on ours, never asks to play (fn 1 absent from every log; only fn 6 stops) -- the shape of a game that was told the engine failed to init. Next: what fn 0 returns on ours, against research/06 and the IRX.

## 6f. THE MISSING BED, FOUND AND MODELLED (07:30-08:10 UTC) -- the ambience is a CONDUCTOR sound our mixer never ran

What the verdict's honest windows said, taken window by window with each target's own step times (the first
spectral pass used ours' times for the console and read a loading screen -- retracted before it was written up):

| window | console | ours | what ours had playing (stream trace, `logs/run_20260920_041306.log`) |
|---|---|---|---|
| s22-s25 (radio lines) | -22..-26 dB, 0% silent | -25..-26 dB, 0% silent, same band shape | the group-6 / group-2 dialogue streams, full length, right level -- **these PASS** |
| s24 | -22 dB, 0% silent | -34 dB, **69% silent** | M51_071 ended at 175.8 s, the next line at 181.2 s: a 5.4 s gap the console does not have |
| s26-s27 (one music stem) | -25 dB, 0% silent, energy up to 8 kHz | -37 dB, dark (3-8 kHz 17 dB lower) | stem 04010311 alone, 29.0 s = its disc length exactly |
| s31-s32 | -27 dB, 0% silent | -33 dB, **64% silent** | stems + lines with gaps between |

Every stream the game asked for plays its full on-disc length (eight checked against the VAGp / VPK headers,
all within 0.1 s) at the level the menu music calibrated. So the console's continuous floor is not a stream at
all. It is **bank M51_AM sound 0x31** -- `05120309` in the trace, played once at mission load at vol 0x400, polled
by the game every frame and never restarted because we always answered "still playing". Parsed from the disc
(fixture `tests/fixtures/audio/m51_am_block.bin`): 33 grains, and they are START_CHILD_SOUND x9,
STOP_CHILD_SOUND x9, TEST_REGISTER on **global register 2** (which the game writes every frame:
`snd_SetGlobalReg(2, 6)`, 632 calls), GOTO_MARKER, MARKER, LOOP. A conductor. Its children are the bed and the
wildlife: sounds 0x32..0x38 and 0x52 on one branch (looping tones, RAND_DELAY chirps, register-driven
volumes), 0x52 and 0x73 on the other. Our grain interpreter had `default: break; // ... children ... not
modelled` -- so the conductor looped forever in silence, alive, and the game was satisfied.

**Modelled** (`snd989_mixer.cpp`, from the open 989snd reimplementation's `sfxgrain.cpp` /
`blocksound_handler.cpp`, fetched and read whole, not summarised): START/STOP_CHILD_SOUND (a child is a
Handler with `parent`; its volume the spec's scaled by the parent's app volume, `app * orig / 127`, as the
reference's MakeHandler computes it; it keeps the parent alive; stop/pause/setVolPan reach it),
TEST/SET/SET_RAND/INC/DEC/ADD/COPY_REGISTER (four handler registers, 32 globals; a grain's register -N is
global N-1, which the IRX confirms: `snd_SetGlobalReg(index 1..32)` stores at `table[index-1]`, FUN_000042b8),
MARKER / GOTO_MARKER / GOTO_RANDOM_MARKER, RAND_PLAY / PLAY_CYCLE (the skip bookkeeping), WAIT_FOR_ALL_VOICES,
ON_STOP_MARKER, BRANCH, the tone Vol/Pan sentinels (-1..-4 a register, -5 random, -6.. a global -- the
chirps' tones are `vol -2 pan -3`, silent before as a negative volume), LOOP_END landing on LOOP_START itself
so its delay paces every pass (the conductor's is 120 ticks), RAND_DELAY as `arg + 1`. `snd_SetGlobalReg`
now reaches the mixer (IOP forward, backend 0x67). Three tests: a hand-built conductor block on HUDUI's
samples (both branches, the sentinel, stop reaching the children), the real M51_AM block with no samples
(global 2 = 6 -> the eight children 0x32..0x38, 0x52; 40 -> 0x52, 0x73), the backend route.

**Not the whole of it.** Two more things the same pass measured: (a) **the movie audio is ~20 dB under the
console** on the logo movies (s02: -50 vs -28 dB) and the cinematic (s19: -47 vs -26, the same band shape),
the only PCM-ring content in the script; the ring's gain arithmetic gives x0.425 for its vol 0x366, so the
deficit is in what the EE writes or in stale blocks -- a PCM dump run (`PS2X_AUDIO_PCM_DUMP`) is queued in
the chain to read the ring's level and fill rate. (b) **the 5 s dialogue gaps** (s24, s31) are the game's own
schedule on ours; whether the console's differs is masked by its bed. Re-measure after the bed is back.

(c) The five positioned emitters the game starts after the flyover (sound 0x42, two looping tones each,
handles `0500030b..0504030f`) get `snd_SetSoundParams(mask 5, vol 0, pan 313..318)` from the EE every frame:
the EE's own attenuation (`FUN_00342670` behind `FUN_00346ea0`) says they are out of range at the spawn. The
same code runs on the console; whether it says the same there is unmeasured (a listener-position divergence
would show as exactly this). Not chased tonight -- the conductor's bed is the measured gap.

**Verdicts (08:50 UTC, the chain `logs/s9_final_chain.sh`):** C++ suite 686/686 (three times over with the Python
suite, `PS2X_TEST_REPEAT=3`, exit 0); gate `s9_q0_children_gate` PASS 3/3 on `dist/socom2.exe` sha256
`b3abebd5...`; CI green at `3e93b51` (its first run caught a test whose sink vector died before the mixer -- a
Linux double free, fixed in the test). **Audio parity `s9_q1_parity_ours2`: 31/48 windows within tolerance,
from 10/48.** Not one mission window reports silence any more (s24 was 69% silent, s31 64%): the bed is
there. What remains is LEVEL: s24 -28.9 vs -22.1 dB, s26 -34.4 vs -23.1, s30 -28.2 vs -21.6, s31 -38.4 vs
-23.7, s32 -41.7 vs -35.3, the 3-8 kHz band (the chirps) 11 dB under the console's in s26-s27 -- our bed
plays about 7-12 dB quieter than the console's. The candidate is the child volume chain: the reference's
`params.vol = app * orig / 127` then `play_vol = (spec vol * params.vol) >> 10` (a child of the 0x31 conductor
at vol 0x400 lands at 53/127 before its own tone volume and group 5's master) may not be what the IRX does;
the IRX's own START_CHILD_SOUND handler is the authority and is the next reading (`game/analysis/989SND.IRX.decomp.c`,
the grain dispatcher was not located tonight). s27-s29 PASS outright.

**The movie audio, measured at the ring (`logs/parity/s9_pcm_dump/`, `tools_py/parity/pcm_dump.py`):** the EE
keeps the ring 100% full at every second (no starvation), and what it writes for the logo movies is
**-38 dBFS** (peak -26) against **-20 dBFS** (peak -7) for the title loop that follows on the same ring at the same
vol 0x366 -- and the title matched the console while the logos are 22 dB under it. The deficit is in the samples
the EE produces for the movies, not in the ring or its gain: ~18 dB is x1/8, three bits, the shape of a shift in
the recompiled movie-audio path. Sprint 10 work, recorded in KNOWN section 4.

**Q0b, second bursts (`logs/parity/q0b_arrow2_*`):** the PCSX2 burst covers the first 180 s of gameplay with the
script standing still -- no arrow appears; the HELP pop-up arrives at ~110 s and stays. The blue spikes the
scorer found are the compass icon. The cue is presumably tied to approaching the first enemies, which no
script does yet. Our burst captured 720 WHITE frames while the driver's own step screenshots of the same run
are fine: `frame_burst` on ours found a window whose PrintWindow came back blank this time (the first bursts
worked) -- a harness defect to fix before the next try (KNOWN section 4). Q0b stays open, tracked.


**Q0b, the blue arrow:** both bursts ran out at the cinematic's end (`launch_to_mission.txt` reaches only
the flyover; ours 87 s, PCSX2 144 s of 220), so neither saw gameplay. The pixel scorer is calibrated on
the sky (12,400 "blue" pixels at the title). Next: burst the first 60 s of gameplay from
`launch_to_mission_xl` on both, then look, not count.

## 7. Stop rules

- No mixer behaviour changes (latency, headroom, caps) until the PCSX2 reference and the instrument agree on what is
  wrong. The pan fix is exempt: it is a protocol bug with a certain reading, not a sound-shaping choice.
- The owner's ear closes this, not a number. If the instrument says clean and the ear says not, say so.
- Q0 outranks Sprint 10 while it is open.
