# 989snd RPC protocol as used by SOCOM II (SCUS_972.75)

Sources: `game/analysis/989SND.IRX.decomp.c` (Ghidra export of `RUN/IRX/SOUND/989SND.IRX`,
"989snd (c)2000-2003 SCEA, by Buzz Burrowes, Sep 22 2003, **NO MIDI VERSION** – banks and
streams only"), `game/analysis/socom2_game.elf.decomp.c` (EE client `989snd.c`, functions
`FUN_0033f090..FUN_00340d80`), EE strings at `0x3f73d0..0x3f7640`, reCOM (`src/gamez/zSound`)
for API names, OpenGOAL `game/sound/989snd` for bank-format cross-checks.

Legend: **[C]** confirmed by reading both sides (IRX handler + EE wrapper + a game call
site); **[I]** inferred (name or meaning guessed from behaviour / 989snd public API);
**[U]** unknown / not used by SOCOM II.

## 1. Transport

### 1.1 Servers

The IRX registers two SIF RPC servers (thread `FUN_00001798` / `FUN_00001930`):

| SID        | IRX dispatcher  | Server buffer      | Purpose                                     |
|------------|-----------------|--------------------|---------------------------------------------|
| `0x123456` | `FUN_00001730`  | 0x1000 B (`DAT_0001b060`) | "snd" – all commands, jump table `DAT_0001b070[fno]`, fno 0..103 |
| `0x123457` | `FUN_0000181c`  | `0x1cf44`          | "stream" – bank loads that block on the CD (fno 2,3,4,5,0x57,0x59); result is a single u32 |

EE binds them in `FUN_00340d80` (client data `0x488f70` → `0x123456`, `0x48da50` → `0x123457`).

### 1.2 Reply buffer (SID 0x123456)

The IRX keeps a 0x420-byte reply area (`DAT_0001b064`); `DAT_0001b068` is the *write cursor*.
Every handler that returns a value does `*DAT_0001b068 = value`. For a single call
(`FUN_00001730`): cursor = base+4, handler runs, then `base[2] = 0xFFFFFFFF`; the server
returns `base`, so with `rsize = 0xC` the EE receives:

```
recv[0] = 0xFFFFFFFF   (set once at init, never changed)   "call finished" marker
recv[1] = result       (garbage/previous value if the handler returns nothing)
recv[2] = 0xFFFFFFFF   terminator
```

The EE (`FUN_0033fca0` = `snd_SendIOPCommand`, sync) spins until
`sceSifCheckStatRpc()==0 && recv[0]==-1 && recv[count+1]==-1`, then returns `recv[1]`
(`DAT_00489004`). Sync calls use `send = 0x489040` (args copied there), `recv = 0x489000`,
`rsize = 0xC`, mode = 1 (NOWAIT) – the EE polls.

### 1.3 Batched commands – fno 0x4D (77) **[C]**

`snd_SendIOPCommandNoWait` (`FUN_0033f8b0`) does not call the IOP directly. It appends to
one of two 0x1000-byte command buffers (`0x489180` / `0x48a180`, remaining-space counters
`DAT_003dff90/94` start at 0xFFC) and the pump `FUN_003408f0` (called every frame and while
waiting) flushes a buffer with

```
sceSifCallRpc(0x488f70, fno=0x4D, NOWAIT, send=buf, ssize=0x1000-remaining,
              recv=0x48d180|0x48d5c0, rsize=count*4+8, 0, 0)
```

Send layout:

```
u32 count
repeat count times, 4-byte aligned:
    s16 fno
    s16 argBytes          (raw size given by the wrapper, NOT rounded)
    u8  args[argBytes]    (padded to a multiple of 4)
```

IRX `FUN_00001634` walks it, calls `table[fno](args)` and advances the reply cursor by 4
per command, so the reply is `{-1, result[0..count-1], -1}`. The EE keeps a parallel table
(`0x48b180`/`0x48c180`, 16 B/entry: `{callback fn, pad, u64 user}`) and after the batch
completes calls `callback(result[i], user)` for each entry with a callback (this is how
`snd_PlaySoundVolPanPMPB` returns handles asynchronously). Only one batch is in flight;
`"989snd.c: RPC collision!"` / `"BUFFER %d FULL"` are the EE's guards.

A no-arg command issued while nothing is queued (e.g. `snd_StopAllSounds`) is sent as a
plain call with `send=0, rsize=0xC`.

### 1.4 Stream SID (0x123457) calls

Only two are used, both sync-polled on `0x48dac0`:

| fno | EE wrapper       | send (`0x48db00`/`0x489080`)             | name **[C]**                   |
|-----|------------------|-------------------------------------------|--------------------------------|
| 2   | `FUN_00340760`   | `{u32 fileOffset; char path[]}` (strlen+5) | `snd_BankLoadEx(path, offset)` → bank ptr |
| 3   | `FUN_00340570`   | `{u32 sector; u32 byteOffsetInSector}` (8) | `snd_BankLoadByLoc(sector, off)` → bank ptr |

Reply: single u32 = IOP bank pointer (0 on failure; the EE stores `0x106` in
`DAT_00488fa8` = last load error when the RPC itself fails). Not used: 4 (`FUN_00008b54`,
second-chunk load by name), 5 (`FUN_00008d18`, by loc), 0x57 (`snd_BankLoadFromIOP`, from
IOP memory) and 0x59 (`FUN_000088c8`, bank image already in IOP memory).

### 1.5 EE status block (fno 0) **[C]**

`FUN_00340d80` sends fno 0 with `{u32 eeStatusBlock = 0x48da00; u32 flags}`. The IRX stores
the address (`DAT_0001c3ac`) and later SIF-DMAs into it (`FUN_00009d90`):

```
0x48da00 +0x00  u32 busy       (1 while a stream-safe CD read is running)
0x48da10 +0x10  u32 lastError  (sceCdGetError result of that read; 0 = ok)
```

The EE reads it after `InvalidateDCache(0x48da00,0x48da3f)` (`FUN_001a4558`).

## 2. Command table (SID 0x123456)

`fno → IRX handler → internal function`; EE wrapper column is the main ELF function.
"sync"/"nowait" = which EE send primitive the wrapper uses. Arguments are consecutive u32
words unless noted. `handle` = 989snd sound handle: `bits 24..28 type` (4 = VAG stream,
5 = bank sound), `bits 16..23 slot`, `bits 0..15 uid`; 0 = none, `-1` = "last".

### 2.1 Used by SOCOM II

| fno  | EE wrapper     | send args                                                    | IRX handler → fn                   | Name / semantics                                                                                       | Reply | Conf. |
|------|----------------|--------------------------------------------------------------|------------------------------------|--------------------------------------------------------------------------------------------------------|-------|-------|
| 0x00 | `FUN_00340d80` (sync) | `{u32 eeStatusAddr, u32 flags}`                        | `FUN_00000250` → `FUN_00006ec8`    | `snd_StartSoundSystem(flags)` + register EE status block. flags: bit0 !verbose?, bit1 quiet, bit2 skip SPU core setup, bits3/4 S/PDIF mode. Sets all group volumes to 0x400. | –     | C |
| 0x01 | `FUN_003408c0` (sync) | –                                                     | `FUN_0000027c` → `FUN_000072b0`    | `snd_StopSoundSystem()`                                                                                | –     | C |
| 0x06 | `FUN_00340520` (nowait) | `{u32 bank}`                                        | `FUN_000003cc` → `FUN_00008928`    | `snd_UnloadBank(bank)` (checks `"SBlk"` magic; frees IOP + SPU RAM)                                    | 0     | C |
| 0x08 | `FUN_00340550` (nowait) | –                                                   | `FUN_0000041c` → `FUN_0000976c`    | `snd_ResolveBankXREFS()` – resolves cross-bank child references                                        | –     | C |
| 0x09 | `FUN_003404e0` (nowait) | `{u32 group, s32 vol}`                              | `FUN_0000043c` → `FUN_000190fc`    | `snd_SetMasterVolume(group, vol)`; group 0..14 or 16 = overall (SPU MVOL); vol clamped 0..0x400; group 15 rejected | – | C |
| 0x0A | `FUN_003404b0` (sync) | `{u32 group}`                                         | `FUN_00000468` → `FUN_0001921c`    | `snd_GetMasterVolume(group)`                                                                           | vol   | C |
| 0x0B | `FUN_00340480` (nowait) | `{s32 mode}`                                        | `FUN_00000494` → `FUN_00019238`    | `snd_SetPlaybackMode(mode)` 0/1/2 – a global s16 used by pan/volume math (`FUN_00019254/…`)           | –     | I |
| 0x0C | `FUN_00340470` (sync) | –                                                     | `FUN_000004b8` → `FUN_00019244`    | `snd_GetPlaybackMode()`                                                                                | mode  | I |
| 0x0E | `FUN_0033f2a0` (nowait) | `{u32 coreMask, s32 type}`                          | `FUN_00000560` → `FUN_0000cad0`    | `snd_SetReverbType(coreMask, type)` (game: `(2, 3)` = core 1, STUDIO_B). delay/feedback = 0           | –     | I |
| 0x10 | `FUN_0033f220` (nowait) | `{u32 coreMask, s32 depth, s32 ticks, s32 how}`     | `FUN_000005bc` → `FUN_0000350c`    | `snd_AutoReverb(coreMask, depth, time, how)` – ramp reverb depth (game: `(2, d, 0xF0, 3)`)             | –     | C (name from reCOM) |
| 0x11 | `FUN_00340360` (nowait+cb) | `{u32 bank, u32 sound, s32 vol, s32 pan, s16 pm(+pad), s16 pb(+pad)}` (0x18) | `FUN_000005f0` → `FUN_0000ba5c` | `snd_PlaySoundVolPanPMPB(bank, sound, vol, pan, pitchMod, pitchBend)`; bank −1 = last loaded; returns handle via batch callback | handle | C |
| 0x12 | `FUN_003403b0` (nowait) | same 0x18 bytes                                     | `FUN_00000638` → `FUN_0000ba5c`    | same, no return ("…NoReturn")                                                                          | –     | C |
| 0x13 | `FUN_003402c0` (nowait) | `{u32 handle}`                                      | `FUN_000006a0` → `FUN_0000c28c`    | `snd_PauseSound(handle)`                                                                               | –     | C |
| 0x14 | `FUN_00340290` (nowait) | `{u32 handle}`                                      | `FUN_000006c4` → `FUN_0000c32c`    | `snd_ContinueSound(handle)`                                                                            | –     | C |
| 0x15 | `FUN_00340330` (nowait) | `{u32 handle}`                                      | `FUN_000006e8` → `FUN_0000bab8`    | `snd_StopSound(handle)`                                                                                | –     | C |
| 0x16 | `FUN_00340240` (nowait) | `{u32 groupMask}`                                   | `FUN_0000070c` → `FUN_0000d900`    | `snd_PauseAllSoundsInGroup(mask)` (game passes −1)                                                     | –     | C |
| 0x17 | `FUN_00340210` (nowait) | `{u32 groupMask}`                                   | `FUN_00000730` → `FUN_0000da6c`    | `snd_ContinueAllSoundsInGroup(mask)`                                                                   | –     | C |
| 0x18 | `FUN_00340270` (nowait) | –                                                   | `FUN_00000754` → `FUN_0000db38`    | `snd_StopAllSounds()` (IRX waits until its active list is empty)                                       | –     | C |
| 0x19 | `FUN_003401e0` (nowait+cb) | `{u32 handle}`                                   | `FUN_00000798` → `FUN_0000bb04`    | `snd_SoundIsStillPlaying(handle)` → handle if alive, 0 if not, −1 for −1                              | u32   | C |
| 0x1B | `FUN_003401a0` (nowait) | `{u32 handle, s32 vol, s32 pan}`                    | `FUN_000007f8` → `FUN_0000bc28`    | `snd_SetSoundVolPan(handle, vol, pan)`; `vol=0x7FFFFFFF` / `pan=-2` = unchanged                         | –     | C |
| 0x1E | `FUN_00340160` (nowait) | `{u32 handle, s32 value}`                           | `FUN_00000888` → `FUN_0000bf74`    | bank sounds only: stores value as 7-bit coarse/fine pair at sound+0x2C/0x2D then re-evaluates the voice (`FUN_00006500`). Probably `snd_SetSoundPitchBend`-style 14-bit param | – | I |
| 0x21 | `FUN_00340110` (nowait+cb) | `{u32 handle, u32 mask, s32 vol, s32 pan, s16 pm, s16 pb}` (0x18) | `FUN_0000090c` → `FUN_0000bcbc` | `snd_SetSoundParams(handle, mask, vol, pan, pm, pb)`; mask bit0 vol, bit1 pan, bit2 auto-pan to `pan` over 30 ticks, bit3 pitchMod, bit4 pitchBend. Returns handle (or 0 if dead) | handle | C |
| 0x22 | `FUN_003400d0` (nowait) | `{u32 handle, s32 vol, s32 ticks, s32 how}`         | `FUN_00000954` → `FUN_000038b4`    | `snd_AutoVol(handle, vol, time, how)` – fade; `vol=-4` = fade out & stop                               | –     | I |
| 0x2A | `FUN_0033f720` (sync) | `{s32 numStreams, s32 bufBytes, u32 p3, u32 p4}`      | `FUN_00000a8c` → `FUN_0000ef1c`    | `snd_InitVAGStreamingEx(n, bufSize, ?, allocReadBuffer)` (game: `(6,0xB000,0,1)`, `(4,0xB000,0)`); bufSize rounded to 4 KiB, min 0x2000; creates 4 threads, allocs n×0x50 stream slots + SPU RAM | 1/0 | C |
| 0x2C | `FUN_0033f580` (nowait+cb) | `{u32 sector1, u32 sector2, u16 off1 \| u16 vol<<16, u16 off2 \| u16 pan<<16, u32 group, u32 parentHandle, u32 priority, u32 flags}` (0x20) | `FUN_00000b68` → `FUN_0000f7e0` | `snd_PlayVAGStreamByLoc(...)`: start a VAG stream (stereo pair if sector2≠0) from CD sector+byte offset. If `parentHandle`≠0 the stream is *queued* after that stream instead. flags: bit0 loop?, bit1/bit2 stream flags, bit3 "no auto free", bit6 use vol/pan, bit5 "double voice". Returns stream handle | handle | C (layout) / I (flag meaning) |
| 0x34 | `FUN_0033f700` (nowait) | –                                                   | `FUN_00000d24` → `FUN_000104d0`    | `snd_StopAllVAGStreams()`                                                                              | –     | C |
| 0x35 | `FUN_0033f5f0` (sync) | –                                                     | `FUN_00000d44` → `FUN_00016284`    | `snd_ShutdownVAGStreaming()` (EE first drains pending reads)                                           | –     | C |
| 0x36 | `FUN_0033f550` (sync) | `{s32 block}`                                         | `FUN_00000d64` → `FUN_00016334`    | wait until no stream CD read / data read is pending, then `sceCdCallback(0)`; returns 1 idle, 0 busy (non-blocking). Used before the EE takes the CD (`snd_StreamSafeCdSync`-family) | 1/0 | I |
| 0x38 | `FUN_0033f420` (nowait) | `{u32 sector, u32 sectors, u32 eeDest}`             | `FUN_00000db8` → `FUN_00012038`    | `snd_StreamSafeCdRead(lbn, n, dest[, mode])` – the EE's `sceCdRead` replacement while streaming is active (see §4). EE sets status.busy=1 before sending; IOP reads through its buffer, DMAs to EE, then writes `{busy=0, err}` | 1/0 (queued) | C |
| 0x3B | `FUN_0033f1e0` (sync) | `{u32 bytes, u32 p2, s32 vol, u32 p4, u32 p5, u32 mode}` | `FUN_00000e4c` → `FUN_0000a318` | PCM stream open: allocates an IOP buffer (`bytes`), claims a SPU DMA channel; mode 3 = 2 SPU voices, else SPU block-transfer path (game: `(size,0,0x366,0,2,2)`). Returns IOP buffer address | ptr | I ("snd_OpenPCMStream"?) |
| 0x3C | `FUN_0033f1c0` (sync) | –                                                     | `FUN_00000e94` → `FUN_0000a780`    | PCM stream close/free                                                                                  | –     | I |
| 0x3D | `FUN_0033f1d0` (sync) | –                                                     | `FUN_00000eb4` → `FUN_0000a864`    | PCM stream stop                                                                                        | –     | I |
| 0x3E | `FUN_0033f180` (sync) | `{u32 buf, u32 size, u32 end, s32 freq, s32 channels}` | `FUN_00000ed4` → `FUN_0000a9ac`  | PCM stream start (`sceSdBlockTrans(ch, 0x13, buf, size, ..)`)                                          | –     | I |
| 0x40 | `FUN_0033f170` (sync) | –                                                     | `FUN_00000fb4` → `FUN_0000b268`    | PCM stream position (`sceSdBlockTransStatus`)                                                          | u32   | I |
| 0x4C | `FUN_0033f130` (sync) / `FUN_0033f090`,`FUN_0033f0e0` (nowait[+cb]) | `{u32 moduleId, u32 fn, u32 a0..a4}` (0x1C) | `FUN_000012cc` → `FUN_0000018c` | `snd_CallExtension(moduleId, fn, a0..a4)` – dispatches into a table registered by another IRX (`FUN_00000148` list). SOCOM uses id `0x12C4E67A` = **989DSTRM.IRX**: fn 0 init `(0xF000,0x400,0x5622,prio<<16\|0x10)`, fn 1 play `(sector, off, vol, group=2, 0)`, fn 2, fn 4/5/6/7 stop/pause/… Returns 0 if the module is missing (error 3) | u32 | C (mechanism) / I (fns) |
| 0x4D | (pump)         | batch, §1.3                                                  | `FUN_00001634`                     | batch dispatcher                                                                                       | n×u32 | C |
| 0x4E | `FUN_00340430` (nowait) | `{u32 group, s32 first, s32 last}`                  | `FUN_00000530` → `FUN_000173a8`    | `snd_SetGroupVoiceRange(group, first, last)` (game: `(g, 0x18, 0x2F)` → core-1 voices only for groups 1,2,4,6,14) | – | C |
| 0x50 | `FUN_0033f260` (nowait) | `{u32 coreMask, s32 type, s32 depth, s32 delay, s32 feedback}` | `FUN_0000131c` → `FUN_0000ca2c` | `snd_SetReverb(mask, type, depth, delay, feedback)` (game: `(2,0,0,0,0)` = off)                        | –     | I |
| 0x64 | `FUN_00340400` (nowait) | `{s32 enable}`                                      | `FUN_0000050c` → `FUN_0000c7f4`    | core-1 `SD_P_MMIX` bits 0..1 (SINER/SINEL) on/off = route external input into core-1 effects (game: 1) | –     | I |
| 0x67 | `FUN_003402f0` (nowait) | `{u32 index(1..32), s8 value}`                      | `FUN_00001580` → `FUN_000042b8`    | `snd_SetGlobalReg(index, value)` – byte table read by grains (game: `(2, x)`)                          | –     | I |

### 2.2 Present in the IRX but not called by SOCOM II **[U]**

| fno | handler → fn | note |
|-----|--------------|------|
| 0x02..0x05, 0x57, 0x59 | bank loads (same functions as the stream SID) | SOCOM uses the stream SID |
| 0x07 | `FUN_000003f8`→`FUN_00008d5c(x)` | unload second-chunk data |
| 0x0D | `FUN_000004e0`→`FUN_00017310(mode, fx)` | sets all 16 group voice ranges (mode 1 → 0x18..0x2F) + fno 0x64 |
| 0x0F | `FUN_0000058c`→`FUN_0000cebc(mask, depthL, depthR)` | `snd_SetReverbDepth` |
| 0x1A | `FUN_000007c4`→`FUN_0000bb50(h, x)` | returns u32 (`snd_GetSoundUserData`?) |
| 0x1C | `FUN_00000828`→`FUN_0000bdc4(h, x)` | returns |
| 0x1D | `FUN_0000085c`→`FUN_0000be60(h)` | returns |
| 0x1F | `FUN_000008b4`→`FUN_0000bfd4(h, s16)` | `snd_SetSoundPitchBend` |
| 0x20 | `FUN_000008e0`→`FUN_0000c038(h, s16)` | `snd_SetSoundPitchModifier` |
| 0x23 | `FUN_00000988`→`FUN_000029e0(h,a,b,c,d)` | auto-pan |
| 0x24, 0x25 | `FUN_000031dc`, `FUN_00002eac` (h,a,b,c) | auto-pitch / auto-… |
| 0x26 | `FUN_00000a28`→`FUN_0000c4d4()` | returns (`snd_GetTick`?) |
| 0x27 | `FUN_00000a50`→`FUN_0000c4b0(x)` | |
| 0x28, 0x29 | `0xa74`, `0xa84` | tiny stubs |
| 0x2B | error 0x6C, returns 0 | MIDI function removed in this build |
| 0x2D..0x2F | `FUN_000106d8/0001092c/00010c64(h)` | pause/continue/stop VAG stream |
| 0x30..0x33, 0x4F | `FUN_0000ff48/0001198c/00011a68/00011aec/00011ba0(h)` | stream queries (returns) |
| 0x37 | `FUN_00011fe0()` | returns 1; flags stream data read |
| 0x39, 0x3A | IOP `AllocSysMemory(x,7,0)` / `FreeSysMemory` via `PTR_FUN_0001c3a4/a8` | `snd_IOPMemAlloc/Free` |
| 0x3F | `FUN_0000b290()` | returns |
| 0x41 | `FUN_0000ef00()` | returns (streaming initialised?) |
| 0x42 | `FUN_00001004(core)` | 24-bit voice-busy mask (`snd_GetVoiceStatus`) |
| 0x43..0x46 | `FUN_000173dc(0,0x12345678)`, `FUN_000174e4(a,b)`, `FUN_00017588(x)`, `FUN_000174b0()` | `snd_LockVoiceAllocator`, `snd_ExternVoiceAlloc`, `snd_ExternVoiceFree`, `snd_UnlockVoiceAllocator` |
| 0x47..0x4B | `FUN_0000e26c(size)`, `FUN_0000e5d4(addr,size)`, `FUN_0000e464(addr,size)`, `FUN_0000e948()`, `FUN_0000e988()` | `snd_SRAMMalloc`, `snd_SRAMMarkUsed`, `snd_SRAMFree`, SRAM stats (interrupts disabled) |
| 0x51 | `FUN_0000c84c(a,b)` | |
| 0x52 | `FUN_000079f0()` | returns (`snd_GetLastLoadError`?) |
| 0x53 | `FUN_0000b57c(x)` | |
| 0x54, 0x55 | `0x13cc`, `0x13dc` | tiny stubs |
| 0x56 | `FUN_000013e4` → `FUN_0000b5dc(a, args+8, b, args+16, …)` + SIF DMA thread | `snd_BankLoadFromEE`-style |
| 0x58, 0x5A, 0x5B, 0x5C | `FUN_0000b038(a,b)`, `FUN_0000a64c(a,b)`, `FUN_0000a69c()`, `FUN_0000b8ac()` | PCM-stream helpers |
| 0x5D..0x60 | `FUN_0000c0b8(h,x)`, `FUN_0000c12c(h,x,s8)`, `FUN_0000c1a0(h, args+4)`, `FUN_0001a0a0(h, args+4 or 0)` | sound regs / user data |
| 0x61 | `FUN_0000d9cc(mask)` | `snd_StopAllSoundsInGroup` |
| 0x62, 0x63 | `FUN_0000f5b8(a,b,c)`, `FUN_000166b0(a,b,c,d)` | stream helpers |
| 0x65 | `FUN_0001a778()` | returns (`sceCdGetDiskType`?) |
| 0x66 | `FUN_0000428c(index)` | `snd_GetGlobalReg` |

## 3. Banks

### 3.1 How a bank reaches the IOP **[C]**

Banks never pass through EE memory. `FUN_00343dd0` (EE bank manager) either resolves the
bank inside the game's ZAR/archive to a **disc sector + byte offset** and calls
`snd_BankLoadByLoc(sector, off)` (stream SID fno 3), or calls `snd_BankLoadEx(path, 0)`
(stream SID fno 2). On the IOP (`FUN_00007fe8`, reader `FUN_00007b54`):

* by-loc: `sceCdRead`-style sector reads (`FUN_000084d0(sector, byteOff, len)`), the
  byte offset within the first sector is honoured;
* by-name: `ioman open/lseek/read` on the path.

The IRX reads the 0x20-byte **FileAttributes** header, allocates IOP memory for chunk 0
(the bank block, `AllocSysMemory(size,1)`), reads it, relocates the two/three internal
offsets, then reads chunk 1 (VAG sample data) in pieces into a temp buffer and uploads
each piece to SPU RAM (`FUN_00008e2c` → `sceSdVoiceTrans`), allocating SPU RAM with
`snd_SRAMMalloc(VagDataSize)` (or `snd_SRAMMarkUsed` if the bank fixes its address).
Type-3 files (with a third chunk) go through `FUN_00008c3c` (MIDI data, not supported here).
On success the bank pointer is appended to the bank list (`FUN_00009260`, head
`DAT_0001c3b0`, last = `DAT_0001c3b4`) and a load callback (`DAT_0001b040`, registered by
extension modules) is fired. **The returned value – the IOP address of the bank block – is
the bank handle** the EE later passes to play/unload.

### 3.2 On-disc layout (IRX reading, cross-checked with OpenGOAL) **[C]**

```
FileAttributes (0x20 read):
  +0x00 u32 type          1 = sound bank, 3 = bank + MIDI chunk (rejected otherwise, err 0x54)
  +0x04 u32 numChunks
  +0x08 { u32 offset; u32 size; } chunk[3]   (only 3 read)
Chunk 0 = bank block ("SBlk", version <= 1, or "SBv2"):
  +0x00 u32 DataID   'SBlk' = 0x6B6C4253
  +0x04 u32 Version
  +0x08 u32 Flags    (IRX sets bit0 "relocated", bit2 "SRAM fixed", bit3 "has MIDI chunk")
  +0x0C u32 BankID
  +0x14 s16 NumSounds
  +0x1C s32 FirstSound  → pointer after load (relocated by +block)
  +0x20 s32 FirstGrain  → pointer
  +0x24 s32 VagsInSR    (SBv2: relocated; SBlk: SPU address filled after upload)
  +0x28 u32 VagDataSize (SBv2: +0x2C)
  +0x2C u32 SRAM size used by the upload
  +0x30 s32 NextBank    (list link)
Sound entry (0x1C bytes, at FirstSound + i*0x1C):
  +0x00 s32 Type   (4/5 = reference to a child sound by name → resolved by snd_ResolveBankXREFS into +0x18)
  +0x04 s32 Bank   (back pointer, filled by ResolveBankXREFS)
  +0x0C name/ref
Chunk 1 = concatenated VAG sample data, uploaded to SPU RAM.
```

Bank sound instances (`FUN_0000d6b4`): 64 slots × 0x11C at IOP `0x1D914`; VAG streams
`numStreams × 0x50` at `DAT_0001ccdc`.

## 4. VAG streaming and the CD **[C]**

* `snd_InitVAGStreamingEx(n, bufBytes, ?, allocReadBuf)` creates the stream slots, four
  threads (tick, CD reader `FUN_00011be0`, data mover `FUN_00013334`, feeder) and one IOP
  read buffer of `bufBytes/2` per stream plus SPU RAM ring buffers. From then on **the IOP
  owns the CD drive** (`sceCdCallback` installed); the EE therefore must not use `sceCdRead`
  itself.
* The EE side honours that: while `DAT_00488fb0` (streaming initialised) is set, the game's
  CD read/sync/get-error wrappers (`FUN_0033f420/320/2e0`) route through fno 0x38 and the
  status block; otherwise they call the normal CDVD RPC (`FUN_0018f178` etc.). `FUN_0033f420`
  is signature-compatible with `sceCdRead(lbn, sectors, buf, mode)`.
  Sequence: EE sets `status.busy=1`, `status.err=0`, sends fno 0x38; IRX reader thread
  reads `sectors` into its buffer (`DAT_0001ccfc`) in `bufBytes/2/0x800`-sector pieces and
  DMAs them to `eeDest` (advancing dest by 0x800/sector); when done `FUN_00009d90(0, err)`
  SIF-DMAs `busy=0` then `err`. The EE polls `busy` (`snd_StreamSafeCdSync`), then fires the
  user callback `DAT_00488fb8(1)`.
* `snd_PlayVAGStreamByLoc` starts reading at `sector*0x800 + off`; the VAG data on disc is a
  standard 48-byte-header VAG (interleaved L/R files for a stereo pair given as sector2).
  The IRX feeds SPU RAM via `sceSdVoiceTrans` and plays it on allocated voices with the
  group's volume; a parent handle queues the stream after the parent (gapless playlists).
* `snd_StopAllVAGStreams` retries five times to bring all slots idle; `snd_ShutdownVAGStreaming`
  releases the CD (`sceCdCallback(0)`), threads and SPU RAM.

## 5. Host mapping (first version, `ps2xIOP/src/modules/snd989.cpp`)

| Protocol piece | Host behaviour |
|----------------|----------------|
| Sync call reply | write `{-1, result, -1}` straight into the EE receive buffer, `resultAddress = receive` |
| Batch 0x4D | walk the send buffer, run each command, write `{-1, results…, -1}` (rsize words) |
| Bank loads (stream SID 2/3, snd 2/3) | read FileAttributes + chunk 0 from the CD image (`HostPathKind::CdImage`, 2048-byte sectors) or the translated path; parse `SBlk` header; keep `{name/sector, numSounds, vagDataSize}`; return a fake IOP pointer `0x00A00000 + slot*0x10000` (unique, non-zero, passes the EE's checks) |
| Master volume / group ranges / reverb / mode | stored in the model, logged |
| Play (0x11/0x12) | allocate a sound slot, synthesise a handle `(5<<24)\|(slot<<16)\|uid`, forward to `IopHost::audioCommand(0x123456, fno, args, {})`, return the handle |
| Pause/Continue/Stop/SetVolPan/SetParams/AutoVol/IsStillPlaying | update the slot; forward to `audioCommand`; IsStillPlaying returns the handle for `kSoundLifetime` (2.5 s wall clock, paused sounds excluded) then 0 so one-shots complete |
| VAG streaming init/play/stop/shutdown | model of `n` stream slots; handles `(4<<24)\|(slot<<16)\|uid`; play forwarded to `audioCommand` |
| Stream-safe CD read (0x38) | synchronous: read `sectors*2048` from the CD image at `lbn*2048`, `writeGuest(eeDest)`, then write `busy=0`, `err=0/err` into the registered status block (0x48da00) |
| PCM stream (0x3B..0x40) | return a fake buffer pointer / 0 position |
| Extension 0x4C | 989DSTRM: fn 0 (init) → 1, fn 1 (play) → 1, others → 1; logged |

`PS2AudioBackend::onSoundCommand` currently only understands the libsd SID; the forwarded
989snd commands are no-ops there until a bank/VAG-aware backend is added (the forwarded
arg buffer is the guest command's own argument words, so a backend can decode
`{bank, sound, vol, pan}` / stream sectors directly).
