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

## 7. Stop rules

- No mixer behaviour changes (latency, headroom, caps) until the PCSX2 reference and the instrument agree on what is
  wrong. The pan fix is exempt: it is a protocol bug with a certain reading, not a sound-shaping choice.
- The owner's ear closes this, not a number. If the instrument says clean and the ear says not, say so.
- Q0 outranks Sprint 10 while it is open.
