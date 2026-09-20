# 36. 989snd IOP model audited against the 989snd.irx decompilation

Date: 2026-09-20. Read-only audit; no code changed. Sources: Ziemas' decompilation of 989snd v3.01
(`research/989snd-ziemas/`, git-ignored, reference only), Ghidra's disassembly of SOCOM II's own
`989SND.IRX` ("Sep 22 2003", `game/analysis/989SND.IRX.decomp.c`), the game's EE code
(`game/analysis/socom2_game.elf.decomp.c`), and our model: `third_party/ps2recomp/ps2xIOP/src/modules/snd989.cpp`
(the IOP module), `third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp` (the host mixer),
`third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`.

## Caveats on the sources (read first)

- **SOCOM's IRX is an older build than v3.01.** Its generic handler header is 0x30 bytes (parent at +0x24,
  first_child at +0x28: `FUN_0000d5f0`, `FUN_0000d4a4` recursing on `param_1[10]`) where v3.01's is 0x34
  (`types.h:611-628`); its VAG stream handler is 0x50 bytes (`FUN_0000d6b4`: `uVar3 * 0x50 + DAT_0001ccdc`)
  where v3.01's is 0x58 (`types.h:664-672`), and the queued-stream pointer sits at +0x44 (`FUN_00016568`)
  instead of v3.01's `qued_stream` at +0x4c. The LOGIC matches line for line everywhere both sources have it;
  only offsets differ. Citations below give v3.01 for logic and the IRX for offsets.
- **stream.c is unimplemented in v3.01** (`stream.c:79` PlayVAGStreamByLocEx, `:176` ProcessVAGStreamTick,
  `:196` CheckVAGStreamProgress, `:546-551` FixVol/FixPan, `:559` SetVAGStreamVolPan are all `UNIMPLEMENTED()`;
  only signatures and locals). Everything said here about the streamer comes from the IRX disassembly alone.
- **989DSTRM.IRX** (`game/disc/RUN/IRX/SOUND/989DSTRM.IRX`) is not decompiled. What its functions do is
  inferred from the EE call sites and research/06.
- The EE's RPC completion callback the music poll uses (`0x346300`) is not emitted as a function by Ghidra;
  its effect is inferred from the poll's `-1` sentinel and the liveness test that reads the same word.

## Q1. When does a played-out VAG stream's handle stop answering?

**Verdict: on the first 240 Hz tick after the SPU voice's envelope reaches zero on the final buffer -- and
the handle answers 0 from that tick on. Commit 77d5522's premise ("the IRX leaves the handle word in the
slot, so the handle keeps answering until the slot is retaken") is wrong: the IRX leaves the handle word
but CLEARS BIT 31 of it, and the handle the EE holds has bit 31 SET, so the equality test fails.**

The handler model (v3.01, identical in the IRX):

- `snd_ActivateHandler` sets bit 31: `snd->OwnerID |= 0x80000000` (`research/989snd-ziemas/iop/sndhand.c:148`);
  IRX `FUN_0000d428` line 8311 `*param_1 = *param_1 | 0x80000000`.
- The play call returns the OwnerID read AFTER activation: IRX `FUN_0000f7e0` (the PlayVAGStreamByLoc
  worker) ends `FUN_0000d428(puVar4); ... return *puVar4;`. So every stream handle the EE ever sees has
  bit 31 set (e.g. our `0x84xxxxxx`-class handles; type 4 in bits 24-28, index in bits 16-23, a use
  counter in bits 0-15: `sndhand.c:56`, IRX `FUN_000163f4`).
- `snd_DeactivateHandler` sets `snd->Sound = NULL` and clears bit 31: `snd->OwnerID &= ~0x80000000`
  (`sndhand.c:236-237`); IRX `FUN_0000d4a4` lines 8343-8344 `param_1[1] = 0; *param_1 = *param_1 & 0x7fffffff`.
- `snd_CheckHandlerStillActive` compares the WHOLE word: `gVAGStreamHandler[i].SH.OwnerID == handle`
  (`sndhand.c:302-310`); IRX `FUN_0000d6b4`: `if (*puVar1 == param_1) return puVar1; return 0`.
  After deactivation the slot holds `handle & 0x7fffffff`, the EE holds `handle` with bit 31 -- they differ.
- `snd_SoundIsStillPlaying` = `CheckHandlerStillActive(handle) ? handle : 0` (`playsnd.c:228-242`;
  IRX `FUN_0000bb04`).
- `snd_FindFreeHandler`/`FUN_000163f4` test `Sound == NULL` (`sndhand.c:55`; IRX `puVar3[1] == 0`) and
  bump the low 16 bits, so the next allocation of the slot produces a DIFFERENT handle anyway.

When the streamer deactivates (IRX `FUN_0001107c` = the per-tick stream update, called from
`snd_UpdateHandlers` for every active VAG handler, `sndhand.c:555-557`):

1. It walks the handler's stream list calling `FUN_000113c8` (CheckVAGStreamProgress). That returns **-1**
   in exactly two places: (a) the stream's "final buffer loaded" flag (`*param_1 & 0x40`) is set and the SPU
   voice's ENVX reads zero (`FUN_0001a6cc(voice | 0x500) == 0` -> `local_34 = -1`), i.e. the VAG end block
   keyed the voice off and the envelope has decayed; (b) the "NAX ran off the buffer" error path
   (`FUN_00001f0c(0x35, ...)`, `return -1`).
2. On -1, with the "loop the file" flag (`*puVar8 & 0x400`) clear:
   - **no queued stream (`param_1[0x11]`, handler+0x44, is NULL):** every stream's voice is freed
     (`FUN_00018e54`), the doubling voice too, the active-stream count decremented, and
     `FUN_0000d4a4(param_1, 0)` deactivates the handler. From this tick `snd_SoundIsStillPlaying` answers 0.
   - **a queued stream exists:** it is swapped in on the SAME handler (`param_1[1] = queued`), the voices
     are handed over (`puVar7[0x1f] = voice`), its flags are cleared of the "queued" bit, and it is started
     with `FUN_000152fc(stream, 1)` if any queued stream carried the pre-buffer bit 0x80, else
     `FUN_0001092c(*param_1)` (the continue/start on the handle). The handler is NOT deactivated, so the
     handle keeps answering, and the queued segment plays under the parent's handle.
3. A handler with the STOPPING flag (`+0x16 & 4`, set by `snd_StopHandlerPtr` -> `snd_StopVAGStream`,
   `sndhand.c:449,464-466`) takes the else branch instead: it waits until neither a load
   (`FUN_00010d20`) nor a DMA (`FUN_00010cd8`) is in flight, then `FUN_00010d84(handle, 1)` kills the
   stream (which deactivates). So an explicit stop may lag by a few ticks while I/O drains, and the handle
   answers during that lag.

**What ours should do instead** (`snd989.cpp`):

- `soundIsStillPlaying` (line 1276-1310): when the host says the stream is not playing, answer **0** and
  mark the slot free. Delete the `ended` branch (1292-1296) and `StreamSlot::ended` (278), and
  `reapEndedStreams` (1545-1560) should free (`active = false`), not mark ended. The pre-77d5522 behaviour
  ("0 at the last rendered sample") was right to within one 240 Hz tick (<= 4.2 ms).
- `playVagStream` (1562-1625): the parent lookup must fail for a finished stream (as `FUN_0000d6b4` does),
  and the IRX's behaviour on that failure is: if `flags & 0x10` return 0, else `param_8 = 0` and start a
  FRESH stream (`FUN_0000f7e0`, the `if ((param_10 & 0x10) != 0) return 0; param_8 = 0;` fall-through).
  Ours instead chains onto the ended slot ("a play queued behind an ended handle is accepted", 77d5522).
- The tests that pin 77d5522 (`socom2_audio_tests.cpp:1970-2030`, `2074-2120`) assert the wrong answer and
  must be rewritten to assert 0 after the end.
- Also (moot for SOCOM, see Q2, but the model claims otherwise): a QUEUED play returns **1**, not the parent's
  handle (`FUN_0000f7e0`, `LAB_0000faec: return 1`). Ours returns `target->handle`
  (`snd989.cpp:1625`; test `:2146` "the queued segment keeps the parent's handle").

## Q2. How the EE starts the next music stem

**Verdict: it polls `snd_SoundIsStillPlaying` (fno 0x19, batched, one per frame per live entry) and starts
the next stem FRESH with fno 0x2c, `queue = 0`. It never queues. The console is not gapless between stems:
there is a gap of roughly two to three EE frames plus the disc read/prebuffer of the new stream.**

Call sites:

- fno 0x2c has ONE packer, `FUN_0033f580` (`socom2_game.elf.decomp.c:240112-240134`), and ONE caller,
  `FUN_00342240` at `:241895`: `FUN_0033f580(sector1, sector2, off1, off2, vol, pan, group, 0)`. Word
  layout (`:240122-240134`): `[0]=loc1 [1]=loc2 [2]=vol<<16|off1 [3]=pan<<16|off2 [4]=vol_group
  [5]=queue(parent handle) [6]=sub_group [7]=flags` -- matching `stream.h:14`
  (`loc1, loc2, offset1, offset2, vol, pan, vol_group, queue, sub_group, flags`). So in our log line
  `[0x001319ce, 0, 0x04000000, 0xffff0000, 1, 0, 0, 4]`: sector 0x1319ce, vol 0x400, pan -1 (default),
  group 1, **queue 0**, flags 4. Word 5 is the queue word (our `args.u32(5)`, `snd989.cpp:1573`) and the
  EE's only caller passes 0 -- "parentHandle 0 on all 55 plays" is not a symptom, it is the game.
- fno 0x4c with magic 0x12c4e67a: `FUN_0033f130` (sync, `:239849-239870`), `FUN_0033f0e0` (nowait,
  `:239824-239846`), `FUN_0033f090` (nowait + callback, `:239798-239820`). Call sites: fn 0 init
  `(0xf000, 0x400, 0x5622, prio<<16|0x10, deviceIndex)` at `:246736` and `:247033`; fn 1 play
  `(sector, offset, vol, group 7, 0)` at `:246672` (in `FUN_0034ad00`) and `(sector, offset, vol, group 2, 0)`
  at `:246798` (in `FUN_0034afd0`), both with callback `0x34b4e0`; fn 2 at `:246626`; fn 4 / fn 5 at
  `:246422` / `:246410` (pause / continue); fn 6 at `:243221`, `:246439`, `:246630` (stop); fn 7 at `:246843`
  (shutdown, then `DAT_0049e150 = 2`).

The music manager (`FUN_0034afd0`, `:246683-246850`, entry `+9` = state: 4 reset, 3 idle, 1 playing,
0 extension-started, 2 extension fn 2 pending):

1. **State 1 (playing):** if the cue entry `+0xd` exists and `FUN_00346d70(entry)` (`:244263-244272`:
   alive iff `entry[0] != 0`, or flag bit 6) says dead, `FUN_00347810(entry)` frees it and state -> 3.
   If the interrupt flag `+10` is set (a type-1/2 cue arrived while playing, `FUN_0034aac0`
   `:246560-246607`), `FUN_00347610` (fno 0x15 StopSound via `FUN_00340330`) then free, state -> 3.
   That interrupt is the legitimate "restarts on enemy contact".
2. **State 3 (idle), on the NEXT call:** `FUN_0034b510` (`:246856-246900`) pops the next cue; with no
   headset (`cVar2 == 0`, below) `FUN_00347960` allocates a sound entry and `FUN_00342240` resolves the
   stem's name to a VAGSTORE sector/offset (`FUN_0034d480`) and issues 0x2c; state -> 1.
3. **The poll** (`FUN_00347120` `:244400+`, every frame, inside a `FUN_0033f8a0`/`FUN_0033f890` batch
   = fno 0x4d): `FUN_00346ea0` (`:244313-244400`) sets `entry[0] = -1` (pending) and issues 0x19
   (`FUN_003401e0`, nowait + callback `0x346300`, `:240540-240549`) -- or, for a positioned entry (flag bit
   0), 0x21 SetSoundParams with the same callback (`FUN_00340110`, `:240485-240504`), whose return is the
   handle or 0 (`playsnd.c:304-306, 340`; IRX `FUN_0000bcbc`). The callback stores the answer in `entry[0]`.
   Also here: the fade timer `entry[8]`, set by `FUN_00346dd0` (`:244290-244306`), which calls
   `snd_AutoVol(handle, 0, seconds * 240, 2)` and, when the timer runs out, StopSound.

Timing on the console between two stems, from these mechanisms: the SPU plays the last sample; within one
tick (<= 4.2 ms) the IRX deactivates the handler; the next frame's batched 0x19 is answered 0 by the IOP
and stored by the callback; the following frame `FUN_0034afd0` frees the entry (state 3); the frame after
that it pops the next cue and issues 0x2c; the IRX allocates, seeks and reads the first buffers from
VAGSTORE.ZAR, DMAs them and keys the voice on. Roughly **2-3 frames (33-50 ms at 60 Hz) plus the read and
prebuffer (tens of ms on PCSX2)** -- a short, audible seam, not a crossfade and not gapless. The EE relies
on `snd_SoundIsStillPlaying` turning 0 promptly; with 77d5522 in place it never does, so the manager stays
in state 1 forever and only an interrupting cue (a type-1/2 event: enemy contact) breaks it. That is the
owner's "plays a while, abruptly stops, restarts on enemy contact", made worse rather than better by 77d5522.

Ours must reproduce: 0 from the first poll after the last sample; a fresh 0x2c starting within a frame or
two; and no reuse of the dead handle.

## Q3. `snd_CallExtension` 0x12c4e67a

**Verdict: the extension is 989DSTRM.IRX, and in this game it is the USB-HEADSET music route. The console
takes it only when a Logitech headset advertising feature 0x5622 is enumerated; otherwise (PCSX2, and ours)
the 0x2c path above is the music path. Our stub is adequate for the path the game actually takes.**

- The IRX's 0x4c handler (`snd_CMD_SL_EXTERNCALL`, `989snd.c:741-744`, IRX `FUN_000012cc` ->
  `FUN_0000018c` per research/06) dispatches into a table another IRX registers; 989SND itself contains
  no code for it (the magic does not occur in `989SND.IRX.decomp.c`). The module on the disc is
  `game/disc/RUN/IRX/SOUND/989DSTRM.IRX`, loaded right after 989SND (research/05 line 63). Not decompiled.
- Which path the game takes: `FUN_0034bb80` (`:247090+`) and `FUN_0034afd0` call `FUN_0034ba60`
  (`:247045-247081`), which enumerates devices through RPC server 0x414980 (`'BLIP'` at `:90825`, the
  Logitech USB audio module) looking for an entry with class 0x10 whose feature range contains 0x5622.
  Found -> fn 0 init and `DAT_0049e150 = 1` (the `FUN_0034ad00` state machine: fn 1 with group 7);
  not found -> `DAT_0049e150 = 2` (`FUN_0034afd0`: 0x2c). `FUN_0034b410` (`:246830+`): if the fn 1
  callback reports 0, fn 7 and fall back to `DAT_0049e150 = 2`. Sprint 8's headset work reports
  `entryCount = 0` (R113), so ours never enumerates 0x5622 -- same branch as a console without that headset.
- Modes, from the EE: **0** init `(0xf000 buffer, 0x400, 0x5622, prio<<16|0x10, device)`; **1** play
  `(sector, offset, vol, group, 0)` -- group 7 in the headset machine, group 2 in the fallback machine
  (a play through DSTRM to the headset while the speakers get the 0x2c stream is the intent);
  **2** (after a play, with callback; likely "is buffered / started"); **4/5** pause/continue; **6** stop;
  **7** shutdown. Research/06 line 147 already has this.
- Ours (`snd989.cpp:1737-1760`): fn 0 marks initialised and returns 1, fn 1 forwards to the host
  (`audioCommand(kSndSid, 0x4c)`) and returns 1, everything else returns 1. Missing: nothing that matters
  for the speaker path. If the headset emulation ever advertises 0x5622 the game would expect fn 1 to play
  a stream to the headset device and fn 2's callback to answer; then a real implementation would be needed.
  Sprint 9 Q0's "fn 1 absent from every log" is therefore expected, not a symptom.

## Q4. The 0x30-0x33 gap in our fno table

**Verdict: 0x30 GetVAGStreamQueueCount, 0x31 GetVAGStreamLoc, 0x32 GetVAGStreamTimeRemaining,
0x33 GetVAGStreamTotalTime (and 0x4f IsVAGStreamBuffered). The EE never issues any of them.**

Counting the dispatcher enum (`989snd.c:50-154`): `..., 0x2a INITVAGSTREAMINGEX, 0x2b PLAYVAGSTREAMBYNAME,
0x2c PLAYVAGSTREAMBYLOC, 0x2d PAUSEVAGSTREAM, 0x2e CONTINUEVAGSTREAM, 0x2f STOPVAGSTREAM,
0x30 GETVAGSTREAMQUEUECOUNT (line 98), 0x31 GETVAGSTREAMLOC (99), 0x32 GETVAGSTREAMTIMEREMAINING (100),
0x33 GETVAGSTREAMTOTALTIME (101), 0x34 STOPALLVAGSTREAMS, 0x35 CLOSEVAGSTREAMING, 0x36 STREAMSAFECHECKCDIDLE,
0x37 STREAMSAFECDBREAK, 0x38 STREAMSAFECDREAD, ..., 0x4c EXTERNCALL, 0x4d COMMAND_BATCH,
0x4e SETGROUPVOICERANGE, 0x4f ISVAGSTREAMBUFFERED, 0x50 SETREVERBEX, ...`. This agrees with our table
(`snd989.cpp:36-95`) and research/06 line 174 (IRX `FUN_0000ff48/0001198c/00011a68/00011aec/00011ba0`).

A census of every RPC packer in the EE (`grep -o "FUN_0033f[0-9a-f]*(0x[0-9a-f]*"`): via `FUN_0033f8b0`
0x0b 0x0e 0x10-0x19 0x1b 0x1e 0x21 0x22 0x2c 0x34 0x38 0x4c 0x4e 0x50 0x67; via `FUN_0033fca0` 0x0c 0x2a 0x35
0x36 0x3b-0x3e 0x40 0x4c. **No 0x30-0x33, no 0x4f -- and no 0x2d/0x2e/0x2f either**: the game pauses,
continues and stops streams through the generic 0x13/0x14/0x15 (`FUN_003402c0`, `FUN_00340290`,
`FUN_00340330`), which reach the stream through `snd_StopSound` -> `snd_StopHandlerPtr` -> `snd_StopVAGStream`
(`playsnd.c:217-226`, `sndhand.c:464-466`). Nothing to implement; the gap can be documented as
"defined, unused".

Two table notes while here: our 0x57 is named `kBankLoadFromIop` but v3.01 has 0x57 BANKLOADFROMEE and
0x59 BANKLOADFROMIOP; our 0x64 `kSetExternalInputMix` is v3.01's SETREVERBMODE (research/06 line 151 reads
the SOCOM IRX as the core-1 external-input mix, so the SOCOM build may differ here; unverified).

## Q5. AutoVol and the stream volume/pan model

**Verdict: the shape matches; the arithmetic does not. Three concrete differences: the console's ramps run
in integer 7-bit steps and finish EARLY; the target is relative to the play-time (original) volume, not the
current one; and every volume below full is SQUARED by the group stage (Q6), which makes fades and quiet
stems markedly quieter on the console than on ours.**

`snd_AutoVol` (`autovol.c:10-110`; IRX `FUN_000038b4` at 2579-2700, identical):

- `vol == -4` -> target 0 and `stopit` (`:24-26`); otherwise `target = (Original_Vol * vol) >> 10`, capped
  127 (`:28-31`) -- the 0..0x400 argument scales the ORIGINAL 7-bit volume (`+0xc`), not the current one.
- `delta_time == 0` -> immediate: `snd_StopSound` or `snd_SetSoundVolPan(handle, -target, -2)` (`:34-44`).
- `volchange = target - Current_Vol`; 0 -> remove the effect and return (`:46-51`).
- An existing type-2 effect is re-used; only `delta_from == 3` re-times it against the OLD target
  (`:53-69`). The game always passes 2 (both 0x22 call sites: `:244232` `(handle, 0, 0x168, 2)` and
  `:244304` `(handle, 0, seconds*240, 2)`), so `how` never matters. Our `(void)how` is correct.
- **Fast ramp** (`|volchange| >= ticks`): `delta_value = 32 * volchange / ticks`, per tick
  `newMvol = (32 * Current_Vol + delta_value) >> 5` (`:82-85`, `:121-125`) -- an arithmetic shift of an
  integer, i.e. `Current_Vol + floor(delta_value / 32)`: a negative ramp rounds each step DOWN.
- **Slow ramp** (`|volchange| < ticks`): `delta_time = |ticks / volchange|` (INTEGER division), a +-1 step
  every `delta_time` ticks (`:86-95`, `:138-140`). The fade therefore takes `|volchange| * floor(ticks /
  |volchange|)` ticks: the game's 1.5 s fade (360 ticks) from 127 runs 127 x 2 = 254 ticks = 1.06 s; the
  2 s fade (480) runs 127 x 3 = 381 ticks = 1.59 s. Ours (`snd989_mixer.cpp:733-752`) interpolates
  `from -> to` linearly over exactly `ticks`.
- Each step calls `snd_SetSoundVolPan(OwnerID, -newMvol, -2)` (`:132`): the **negative volume is the
  "absolute 7-bit" convention** -- for streams `snd_FixVol` (IRX `FUN_0001661c`, 13424-13437):
  `vol < 0 -> -vol; vol == 0x7fffffff -> unchanged; else vol * 0x7f >> 10`, capped 0x7f. (For block sounds
  `blocksnd.c:1198-1203` maps a negative to `App_Vol = -1024 * vol / 127`, i.e. the same 7-bit value re-expressed
  against the original.) `pan -2` = unchanged, `-1` = 0, else wrapped to 0..359 (`FUN_00016660`).
- The ramp is REMOVED when it lands (`:133-136`) and `Current_Vol` stays at the target; `stopit` makes
  `snd_UpdateHandlers` stop the handler at that tick (`sndhand.c:567-574`). Ours: `stopAtEnd` -> `stopHandle`
  at the last tick, scale kept at the target. Same.

Ours (`snd989_mixer.cpp:1626-1660`): `to = vol / 1024` as a SCALE on the current `base` (which
`setVolPan` rewrites, `:1558-1580`), `from = rampScale(handle)` (1.0 when no ramp), linear over `ticks`,
`-4` -> 0 then stop. Differences: (1) integer step schedule vs linear (fades complete 20-30 % early on the
console); (2) target relative to the original vs the current volume (only differs after a SetSoundVolPan
changed the level; the game's fades all target 0, so no audible difference for them); (3) the square law of
Q6 under everything; (4) our IOP-model `kAutoVol` (`snd989.cpp:867-884`) deactivates a bank-sound slot
IMMEDIATELY on -4, the IRX at the ramp's end -- harmless because the host's answer takes precedence in
`soundIsStillPlaying`.

Stream play volume: `param_5 * 0x7f >> 10` into both `+0xc` (Original) and `+0x10` (Current)
(`FUN_0000f7e0`); ours `min(127, 127 * vol >> 10)` (`snd989_mixer.cpp:1940`). Same. Per-voice volume for a
stream (`FUN_00016898`): `work = ((((Current_Vol * 0x102 * 0x7f) / 0x7f) * stream_vol) / 0x7f) *
subgroup_vol / 0x7f` (`FUN_00019578`, 15059-15075; = `snd_MakeVolumes`' `snd_vol * 258` at `vol.c:147`),
then the pan table, then `FUN_00019b7c` (the group stage), `>> 1`, `sceSdSetParam VOLL/VOLR`. Ours:
`makeVolume(127, 0, playVol, playPan, 127, 0)` then `base * groupModifier * volScale / 0x400 / 0x400 >> 1`
(`:1745-1747`) -- the same chain minus the square.

`Mixer::setVolPan` (`:1558-1585`) clamps `vol` to `0..0x400`: a negative (absolute 7-bit) volume would be
read as 0 = silence. No EE packer sends one (the convention is internal to the IRX's ramps), so it is
latent, not live.

## Q6. Other contradictions in the implemented files

1. **The group/master volume is a SQUARE law, ours is linear.** `snd_AdjustVolToGroup`
   (`vol.c:434-455`): `m = MasterVol[g] * Duck[g] / 0x10000; v = vol14 * m / 0x400; return (v * v) / 0x7ffe`
   (with sign); IRX `FUN_00019b7c` (15274-15300) is the same, `((iVar2 * iVar2) / 0x7ffe) * sign`. It is
   applied to every voice -- block sounds (`blocksnd.c:1267-1268`), streams (`FUN_00016898`), and on every
   master-volume change (`snd_AdjustAllChannelsMasterVolume`, `vol.c:457-483`). At full (0x7ffe) it is the
   identity; at half amplitude it is a quarter: **the MUSIC/SOUND sliders at 50 % are -12 dB on the console
   and -6 dB on ours; a stem played at vol 0x200 likewise; and a linear 7-bit fade is a quadratic loudness
   curve on the console.** Ours: `groupModifier(g) * volScale / 0x400` then `base * modifier / 0x400 >> 1`
   (`snd989_mixer.cpp:770-783`, `:1745-1747`), and the PCM ring's `0x7ffe * vol / 0x400 >> 1` (`:2131`).
   This is the most likely explanation of level mismatches in the music-only parity windows once the
   liveness bug is out of the way.
2. **The tick rate is 240 Hz, from the source, not inferred.** `init.c:114-118`
   (`USec2SysClock(1000000) / 0x0f0` as the hard-timer compare) and `init.c:165-167`
   (`snd_GetTickRate() { return 240; }`). `docs/research/32-audio-path.md:95` can drop "inferred";
   `kTickHz = 240.0` (`snd989_mixer.cpp:509`) stands.
3. **`snd_StopHandlerPtr(snd, and_child, silence, vlimit_stop)`** (`sndhand.c:437-494`): `silence = 1`
   mutes at once (`snd_SilenceVoicesEx`), 0 keys off and lets the ADSR release ring (`:479-483`).
   `snd_StopSound` passes 0 (`playsnd.c:223`); `snd_StopAllSounds` and the instance-limit steal pass 1
   (`sndhand.c:128, 423`); a second stop on an already-stopping handler forces a hard kill (`:445-448`).
   For VAG streams none of this applies: the type switch hands off to `snd_StopVAGStream` and skips the
   voice/deactivate step (`:464-466, 477`); the IRX then kills the stream on a later tick once I/O is idle
   (Q1 item 3). Ours: `Mixer::stop` keys off (`:876-881`) -- right for 0x15; `kStopVagStream`/`kStopSound`
   free the model slot at once (`snd989.cpp:756, 908`), a few ticks early -- harmless.
4. **`snd_SetSoundParams` (0x21) answers the handle for ANY live handler, or 0** (`playsnd.c:304-306, 340`;
   IRX `FUN_0000bcbc`). Ours answers `slot->handle` only for a BANK slot and **0 for every stream handle**
   (`snd989.cpp:812-838`: `findSound` only; `value` defaults to 0 in `execute`). The EE polls positioned
   entries with 0x21 instead of 0x19 (`FUN_00346ea0` `:244360-244380`: flag bit 0 -> `FUN_00340110(handle, 5,
   vol, pan, ..., cb)`), so every positioned stream (the Sprint 9 Q0 voice lines, any positioned music cue)
   is read as dead on its first poll. Same class of bug as Q1, in the other direction.
5. **A queued play behind a dead or unknown handle** (`FUN_0000f7e0`): `flags & 0x10` -> return 0; otherwise
   the request degrades to a fresh play (`param_8 = 0`). Ours accepts the chain onto an ended slot
   (77d5522). Moot for SOCOM's EE (never queues) but the model and tests state the opposite of the IRX.
6. **`snd_UpdateHandlers` order** (`sndhand.c:540-575`): the type-specific tick first, then the effect chain
   (`snd_UpdateEffect`, only when not paused), then a stop if either asked. So a fade-to-stop on a stream
   ends it through `snd_StopHandlerPtr` -> `snd_StopVAGStream` (the deferred kill), not through the
   streamer's own end -- and `snd_SoundIsStillPlaying` answers the handle for those few extra ticks.
7. `pantable.c`: 181-entry quarter-wave tables (`gPanTable1`, `:6-...`; `snd_SetPanMode` `:374-380` picks
   table 2 for mode 1). Ours synthesises cos/sin at 0x3fff (`snd989_mixer.cpp:131-142`); the shipped
   table is not exactly cos/sin (16383, 16382, 16380, 16377, ... vs cos) but within rounding; not a
   contributor to anything audible. Pan table 2 (mode 1) is not modelled; the game's 0x53 SetPanMode is not
   in the EE packer census, so it is never selected.
8. `snd_CMD_SL_AUTOVOL_A` in v3.01 unpacks `{handle, s16 vol | s16 time, ...}` (`989snd.c:427-430`) while
   SOCOM's EE packs `{u32 handle, s32 vol, s32 ticks, s32 how}` (`FUN_003400d0`, `:240466-240478`) and the
   IRX's `FUN_000038b4` takes four full words -- a wire-format difference between the builds; ours follows
   the SOCOM format, correctly.

## Diff list (ordered by likely impact on the mission music's choppiness)

1. **`snd989.cpp` `soundIsStillPlaying` / `StreamSlot::ended` / `reapEndedStreams` -- revert 77d5522.**
   A stream the host has finished answers **0** on the next 0x19 and its slot is free (`active = false`);
   delete `ended`. This is what lets the EE's manager leave state 1 and start the next stem; with `ended`
   the music stops after one stem until an enemy-contact cue interrupts. Rewrite the two tests that pin the
   opposite (`socom2_audio_tests.cpp:1970-2030`, `:2074-2120`). Also fix the sprint-10 plan's
   "What the IRX says" paragraph (`docs/superpowers/plans/2026-09-20-sprint-10-music-round-four.md:32-44`).
2. **`snd989.cpp` `kSetSoundParams` (0x21):** answer the handle for a live STREAM slot too (a `findStream`
   beside `findSound`, both gated on the host's `audioIsPlaying`), 0 otherwise -- the IRX's `FUN_0000bcbc`.
   Positioned streams are polled through 0x21 and currently read as dead on the first poll.
3. **`snd989_mixer.cpp` group stage -- the square law.** After the master/duck multiply and before the
   SPU `>> 1`, apply `v = v * v / 0x7ffe` on each channel (`applyVoiceVolume` `:776-783`, the stream mix
   `:1745-1747`, `pcmStreamStart` `:2131`). Every level below full is currently 2x too loud in amplitude
   terms on ours; it shifts the whole music-only level trace and every fade's shape.
4. **`snd989_mixer.cpp` `autoVol` / `tickVolRamps`:** step in integer 7-bit units on the IRX's schedule --
   fast branch `cur += floor(32 * dv / ticks / 32)` per tick, slow branch +-1 every `floor(ticks / |dv|)`
   ticks -- so a 360-tick fade from 127 lands in 254 ticks as on the console; compute the target as
   `(Original_Vol * vol) >> 10` against the play-time volume. Lower priority than 3 because every game
   fade targets 0.
5. **`snd989.cpp` `playVagStream` queue semantics** (moot for SOCOM, but the model documents the reverse):
   a parent that no longer resolves -> `flags & 0x10 ? 0 : fresh play`; a real queue returns 1, not the
   parent's handle; never chain onto a freed slot. Update the comment at `:1584-1590` and test `:2123-2150`.
6. **Stop timing (low):** a stream's stop may lag a few ticks while a load/DMA is in flight, and the handle
   answers meanwhile; a fade-to-stop ends through the deferred kill. Not worth modelling unless a parity
   window shows an early cut.
7. **Docs only:** `docs/research/32-audio-path.md:95` -- 240 Hz is read from `init.c`, not inferred;
   research/06 -- add the 0x30-0x33/0x4f names and the fact that the EE issues none of 0x2d-0x33;
   note the 0x57/0x59 naming and the 0x64 question (Q4).
8. **`callExtension` (no change):** the DSTRM route is the Logitech-headset music path; the console
   without that headset uses 0x2c exactly as ours does. Leave the stub; if the headset emulation ever
   advertises feature 0x5622, fn 1/fn 2 need a real implementation.

## What could not be determined

- The exact SPU parameter code behind `FUN_0001a6cc(voice | 0x500)` is read as ENVX from the libsd
  numbering (VOLL 0x000, VOLR 0x100, PITCH 0x200, ADSR1 0x300, ADSR2 0x400, ENVX 0x500); if it is another
  register the trigger of the -1 still sits at the voice's end, only its exact tick may differ.
- What 989DSTRM's fn 2 answers, and the disc-read latency PCSX2 adds to the seam between stems (it decides
  how long the console's gap is; measure it from the PCSX2 music-only capture's silences rather than model it).
- Whether `snd_SetVAGStreamSubGroupVolPan` (0x63) and the 16 per-handler sub-group volumes matter: the EE
  never issues 0x63, so the sub-group volumes stay at 0x7f (`FUN_0000f7e0` fills `+0x34..+0x43` with 0x7f).
