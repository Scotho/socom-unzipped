# 32 — The audio path: what SOCOM II asks 989snd to play, and what the host has to do to make it audible (Task 6c Step 1, 2026-09-17)

The host audio device is up (raylib/miniaudio) and the 989snd IOP service (`ps2xIOP/src/modules/snd989.cpp`,
research/06) answers every RPC, loads the banks and models the voice and stream slots — and `PS2AudioBackend::
onSoundCommand` understands only the libsd SID, so nothing SOCOM plays reaches a speaker. This note pins the
bank format on the disc (read, not inferred), the play-call arguments as the game sends them, and the playback
arithmetic (from the 989snd public API as re-implemented in OpenGOAL's `game/sound/989snd`, cross-checked against
the IRX decomp), so that Steps 2–3 are a build, not a search.

## 1. The banks on the disc [verified: bytes read from the ISO]

Bank handles the game uses: `0x00a00000` (sector 2010461, "HUDUI", 24 sounds), `0x00a10000` (2025764+384,
8 sounds), `0x00a20000` (2025428+1152, 187 sounds), `0x00a30000` (2024946+1792); a bank load line in every
run log gives sector, byte offset, block and VAG sizes. Each is a FileAttributes header (type 3 = bank + MIDI
chunk, 2 chunks read) followed by chunk 0 (the "SBlk" block, **version 3**) and chunk 1 (the VAG sample data,
raw ADPCM, no "VAGp" header).

Block header (offsets from the block start; the `snd989.cpp` first cut read NumSounds at 0x14 and logged
"sounds 0" for every bank — the fields sit two bytes on):

| offset | field | HUDUI value |
|---|---|---|
| 0x00 | `DataID` "SBlk" | `6b6c4253` |
| 0x04 | `Version` | 3 |
| 0x08 | `Flags` | 0x104 |
| 0x0C | `BankID` | 'UNEM' |
| 0x10 | `BankNum` (s8 + pad) | 5 |
| **0x16** | `NumSounds` s16 | 24 |
| 0x18 | `NumGrains` s16 | 78 |
| 0x1A | `NumVAGs` s16 | 19 |
| 0x1C | `FirstSound` | 0x40 |
| 0x20 | `FirstGrain` | 0x160 |
| 0x24 | `VagsInSR` | 0x5040 (SPU address after upload) |
| 0x28 | `VagDataSize` | 60928 = chunk 1's size |
| 0x2C | SRAM alloc | 60928 |
| 0x30 | `NextBlock` | 0 |
| 0x34 | `GrainData` | 0x3d0 — the per-grain parameter pool |
| 0x38 | `BlockNames` | 0x898 — "HUDUI" then a name/index table |

**Sound record, 12 bytes** at `FirstSound + i*12`: `s8 Vol, s8 VolGroup, s16 Pan, s8 NumGrains, s8 InstanceLimit,
u16 Flags, s32 FirstSFXGrain` (a byte offset into the grain array; -8 for a sound with no grains). HUDUI sound 0:
vol 98, group 14, pan 0, 4 grains at 0; sound 8: vol 115, 1 grain at 0x60; sound 16: vol 90, 5 grains at 0x140.

**Grain record, 8 bytes** (the compact form: `u32 Opcode` = `type << 24 | arg24`, `s32 Delay` in ticks) at
`FirstGrain + FirstSFXGrain + g*8`. Types seen: 1 TONE, 4 LFO_SETTINGS, 26 RAND_DELAY (delay 444), 41
KEY_OFF_VOICES; the full enum is OpenGOAL `sfxgrain.h` (TONE 1, TONE2 9, XREF 2/3, LFO 4, START/STOPCHILDSOUND
5/6, PLUGIN 7, BRANCH 8, CONTROL 20, LOOP_START/END/CONTINUE 21/22/23, STOP 24, RAND_PLAY 25, RAND_DELAY 26,
RAND_PB 27, PB 28, ADD_PB 29, registers 30–34/40/44, MARKER 35–37, WAIT_FOR_ALL_VOICES 38, PLAY_CYCLE 39,
KEY_OFF_VOICES 41, KILL_VOICES 42, ON_STOP_MARKER 43).

**Tone parameters, 24 bytes** at `GrainData + arg24` for a TONE grain: `s8 Priority, s8 Vol, s8 CenterNote,
s8 CenterFine, s16 Pan, s8 MapLow, s8 MapHigh, s8 PBLow, s8 PBHigh, u16 ADSR1, u16 ADSR2, u16 Flags,
u32 SampleOffset (into chunk 1), u32 reserved`. HUDUI sound 0 grain 0: prio 99, vol 90, note -58, fine 66,
pan 0, ADSR1 0x80ff, ADSR2 0x9fe8, sample 0x3940; sound 16's two tones: notes -99 / -106, PB 12/12, sample
0x6950 (the same sample at two pitches). A negative CenterNote is the "PS1 note" flag (§3).

## 2. What the game sends [verified: run logs]

`snd_PlaySoundVolPanPMPBNoReturn(bank, sound, vol, pan, pitchMod, pitchBend)` (fno 0x12, batched through 0x4D)
is the workhorse — 515 calls in a Frostfire match. Typical: `[0x00a00000, 8, 0x400, -1, 0, 0]` (HUD click at
full volume, pan -1 = PAN_RESET → the sound's own pan), `[0x00a20000, 0x61, 0x400, 2, ...]`, and the weapon
bank `[0x00a30000, 6, 0x3e4..0x400, 0x167 / 0x166 / 0..4, ...]` with pan 0..359 degrees. `vol` is 0..0x400
(1024 = unity; the handler does `(sfx.Vol * vol) >> 10`, clamped to 127). Handles come back as
`(5 << 24) | (slot << 16) | uid`; `snd_SoundIsStillPlaying`, `SetSoundVolPan`, `SetSoundParams`, `AutoVol`,
`PauseSound`/`ContinueSound`/`StopSound` address them (research/06 §2.1).

Streams: `snd_PlayVAGStreamByLoc` (fno 0x2c: `{sector, sector2, off|vol<<16, off2|pan<<16, group, parent,
priority, flags}`) 43 times per match — music and voice, read through the stream-safe CD reads the module
already serves; `snd_SetGlobalReg(2, x)` runs every frame in the mission (11,225 calls) and drives grain
register tests, not audio output.

## 3. The playback arithmetic (989snd, as OpenGOAL re-implements it)

- **Volume.** Handler: `play_vol = min(127, (sfx.Vol * vol) >> 10)` where `vol` is the call's 0..0x400.
  Voice: `MakeVolume(127, 0, play_vol, play_pan, tone.Vol, tone.Pan)`: `v = 127 * 258; v = v * play_vol / 127;
  v = v * tone.Vol / 127`; pan = the sum of the pans normalised to 0..359; `left = panTable[p].left * v / 0x3fff`,
  `right = panTable[p].right * v / 0x3fff` (the table is a 181-entry quarter-wave cos/sin pair ×0x3fff, mirrored
  past 180); mono mode returns `{v, v}`. Group: `modifier = masterVol[group] * duck[group] / 0x10000;
  volume = volume * modifier / 0x400` — `snd_SetMasterVolume(group, vol)` (fno 0x09) sets `masterVol`,
  group 16 = overall. The SPU voice gets `left >> 1, right >> 1` (0..0x3fff → 0..0x1fff).
- **Pitch.** `PitchBend(tone, pb, pm, start_note, start_fine)`: `v = (start_note << 7) + start_fine + pm;
  v += pb >= 0 ? tone.PBHigh * (pb << 7) / 0x7fff : tone.PBLow * (pb << 7) / 0x8000; note = v / 128, fine = v % 128`.
  `PS1Note2Pitch(center_note, center_fine, note, fine)`: a negative `center_note` is negated and the result is
  used as is; a non-negative one scales the result by `44100/48000`. `sceSdNote2Pitch` = `NotePitchTable[semitone]
  * NotePitchTable[12 + fine] / 0x10000` with an octave shift — the table is 12 semitone ratios (`0x8000 * 2^(i/12)`:
  0x8000, 0x879C, 0x8FAC, 0x9837, 0xA145, 0xAADC, 0xB504, 0xBFC8, 0xCB2F, 0xD744, 0xE411, 0xF1A1) and 128 fine
  ratios (`0x8000 * 2^(i/1536)`: 0x8000, 0x800E … 0x878C). SPU pitch 0x1000 = 44.1 kHz playback of the ADPCM
  stream; the host resamples by `pitch / 0x1000`. The play call's `pitchMod` is in 1/128 semitone units,
  `pitchBend` is -0x8000..0x7fff over the tone's PBLow/PBHigh semitones.
- **Envelope.** `ADSR1`/`ADSR2` are the SPU's register words (attack rate/mode, decay, sustain level; sustain
  rate/mode, release). KEY_OFF_VOICES (grain 41) and `snd_StopSound` key off → release; `KILL_VOICES` zeroes the
  volume. A host envelope needs the SPU's rate table (exponential/linear modes, 0x7f rates); for a first cut,
  attack/decay/sustain-level/release from the register fields at the SPU's nominal rate constants.
- **Grain sequencing.** `countdown = grains[0].Delay; while (countdown <= 0 && !done) DoGrain();` then per
  tick `countdown--`; the tick rate is 240 Hz in OpenGOAL's handler (inferred for this IRX, not read from it: RAND_DELAY 444 would be ≈ 1.85 s). RAND_DELAY returns `rand() %
  Amount`; RAND_PB / PB / ADD_PB set the handler's pitch bend; LOOP_START/END/CONTINUE walk the grain list;
  STOP ends the handler; an instance limit evicts the weakest instance (by volume or start tick).
- **ADPCM.** PS2 VAG: 16-byte blocks — `shift|filter<<4`, flags (bit0 loop end, bit1 loop repeat, bit2 loop
  start), 14 bytes = 28 nibbles; `s = nibble << 12 >> shift; s += prev1 * f1[filter] + prev2 * f2[filter]` with
  the five filter pairs (0,0), (60,0), (115,-52), (98,-55), (122,-60) over 64. The runtime has the decoder
  (`ps2_vag::decode`, `ps2_audio_vag.cpp`) for "VAGp"-headed files; the bank samples are headerless, so a raw
  block-range entry point is Step 2, with the loop flags honoured (flag 1 with bit1 clear ends the sample; a
  sample whose block carries bit2 then bit1|bit0 loops).

## 4. Where the host stands, and the shape of Steps 2–3

- `snd989.cpp` parses the FileAttributes and the block header (with the NumSounds offset wrong, §1), keeps
  `Bank{handle, sector, offset, blockBytes, vagDataBytes}` and a 64-slot `SoundSlot` model, and forwards every
  play/stop/volume command to `IopHost::audioCommand(0x123456, fno, args)`, where `PS2AudioBackend::onSoundCommand`
  drops it (`sid != 0x80000701`).
- **Step 2 (test-first):** `ps2_vag::decodeBlocks(data, bytes, loopStart*, pcm)` for headerless data with the
  loop flags; a bank reader (`socom2_bank.h`: header, sound, grain, tone as in §1) with a test on HUDUI's bytes
  (24 sounds, sound 0 has 4 TONE grains at sample 0x3940 …) — the test fixture is the 3472-byte block plus
  the first 4 KiB of VAG data cut from the ISO at build time or checked in (small).
- **Step 3:** the backend keeps the loaded banks' block + VAG bytes (the module reads them from the ISO already);
  on fno 0x11/0x12 it runs the grain list of `bank.sounds[sound]` (TONE → a voice: decode the sample from
  `SampleOffset` to its loop end, resample by the pitch of §3, apply the volume pair and a simple ADSR; RAND_DELAY
  / LOOP / STOP / KEY_OFF as in §3), mixes voices into one raylib `AudioStream` (44.1 kHz stereo s16, 20 ms
  buffers) from the audio callback, and honours stop/pause/vol-pan/params/AutoVol by handle. Streams (0x2c):
  the module's stream-safe reads deliver the sectors; a stream voice decodes them as they arrive. The gate-side
  bar: `PS2X_AUDIO_DUMP=<wav>` writes the mix; a title-screen run's RMS above a floor.

## 5. Steps 2–3, first cut (2026-09-17)

- **Step 2** (`734afcc`): `socom2_bank::parse` (the layout of §1, with the NumSounds offset the module had wrong) and
  `ps2_vag::decodeBlocks` (headerless blocks to the end flag, loop flags reported), test-first on HUDUI's chunks
  checked in as fixtures.
- **Step 3, bank sounds** (this commit): `snd989::Mixer` — the grain sequencer at 240 ticks/s (TONE, RAND_DELAY,
  RAND_PB / PB / ADD_PB, LOOP_*, STOP, KEY_OFF/KILL_VOICES; LFO, registers, markers, children, plugins not
  modelled), voices with the §3 pitch (`note2Pitch`, a transliteration of sceSdNote2Pitch; the center fine is
  *added* to the played fine), MakeVolume's pan table and group master volumes, the SPU ADSR (psx-spx rates: the
  shift/step/exponential rules), linear-interpolated resampling, mixed to 48 kHz stereo. The IOP module now reads
  each bank's block and VAG chunks and hands them to the host (`IopHost::audioBank`), and reports the play family in
  host words with its own handle first (`IopHost::audioNotify`), so stop / pause / vol-pan / params / AutoVol / master
  volume / unload address the same sounds the game does. `PS2AudioBackend` runs the mix on one raylib
  `AudioStream` (`SetAudioStreamCallback`, 1024-frame buffers) opened when the audio device is ready;
  `PS2X_AUDIO_DUMP=<wav>` writes the mix as it is rendered (the harness kills the process, so incrementally; a killed
  run's header keeps zero sizes and the file length is the truth).
- **Measured**: ps2x_tests 480/480 (mixer: a HUDUI click plays to its end and goes quiet, stop keys it off, vol 0 and
  master 0 are silence, pan 270/90 hard left/right and 359 just left, SetVolPan moves a playing sound, a four-tone
  sound starts four voices, +12 semitones halves the frames, unloadBank silences; the backend routes a bank and the
  play family under the module's handle). Title stage with the dump (`s6_audio_title`, 163 s): the eleven HUD clicks
  the walk presses are in the mix (five one-second windows with RMS 259–594, peak 13544); everything else is
  silence, because the title music and the mission voice-overs are VAG **streams** (fno 0x2c), not yet played.
- **Next**: streams (`snd_PlayVAGStreamByLoc`: sector + offset → the stream-safe CD reads the module already serves,
  decoded as a looping voice with the stream's own vol/pan), `snd_SoundIsStillPlaying` answered from the mixer instead
  of the module's 2.5 s lifetime, PauseAll/ContinueAll, the LFO grain (vibrato on weapon loops), and the owner's
  listening test in free play.

## 6. Streams (2026-09-17, later)

- **Measured** (`s6_audio_gate5`, gate 3/3, spawn 23.8): the mission's eleven streams open and play (the briefing voice-overs, then the
  mission music at RMS 3000–4500 through the round); the dump peaks at 18572 after the SPU's half-scale voice volume
  (`left >> 1, right >> 1`) was added — the first cut summed at full scale and clipped at 32768.

- **Two file shapes on the disc.** The music streams are VPK files: the magic is the little-endian word `"VPK "`, so the bytes
  read `" KPV"` (0x20 4B 50 56); then data size, interleave (0x800), header size (0xB0), sample rate (32000), channels (2), all
  little-endian; the data is 0x800-byte ADPCM chunks alternating L, R. The mission voice-overs are plain `VAGp` files
  (48-byte big-endian header: data size at 0x0c, rate at 0x10 — 22050 Hz, mono; the name at 0x20: `M51_140`…). Both
  read straight from the disc image at `sector * 2048 + offset` as they play (`Mixer::playStream`, resampled to 48 kHz;
  the image is over 2 GB, so the seeks are 64-bit — a 32-bit `fseek` failed silently on every mission stream first).
- **Wiring.** The module reports `snd_PlayVAGStreamByLoc` with its handle first (`{handle, sector1, sector2, off1, vol,
  off2, pan, group, flags}`); `snd_SoundIsStillPlaying` is answered by the mixer for handles it knows
  (`IopHost::audioIsPlaying`), so the game's own polling sees the real end of a sound.
- **What is still silent.** The title-screen music is a **PCM stream** (fno 0x3B open 0x6000 bytes / 0x3E start / 0x40
  position): the EE decodes it itself from a CD stream (`sceCdStStart` at LBN 0xcdade) and SIF-DMAs PCM into an IOP
  buffer the module hands out (`0x900000`, a fake address the copies land on in EE RAM). The host needs the buffer in
  the IOP heap window (`allocateGuest`), the module's `onSifTransfer` hook to see the writes, and a ring voice in the
  mixer with a position the module can report. Next.
- **Tests.** 484/484: the VPK stream (interleaved channels left and right, its own rate, ends after its data, pan,
  stop, stopAllStreams), the VAGp stream, the backend routing a stream by sector and answering the playing query. The
  runner gained `PS2X_TEST_SUITE=<substring>` and `PS2X_TEST_SKIP=<substrings>` filters and unbuffered stdout, which
  found the one-in-six crash of the day: the routing test rendering 4096 frames into a 2048-frame buffer.

