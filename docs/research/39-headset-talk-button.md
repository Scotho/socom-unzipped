# 39. The headset's own button: the two listing passes, and the stop (Sprint 10, Q5)

> **Superseded in place, 2026-09-25:** `:180`'s "Nellymoser" is wrong. SOCOM II's voice codec is **SASE**
> (`SaseEncVad`/`SaseDec`), verified against all four images (`docs/research/44`'s addendum, `docs/research/56`);
> the earlier name was an inference from the assert macro `NellyNull`, the only Nelly-shaped string in any image,
> and is withdrawn. The finding this note exists for is unaffected.

Date: 2026-09-21. Written by the Q5 agent (worktree `C:\projects\wt-q5`, branch `agent/q5` off `sprint-10` at
`a44eb2d`). The question is the Sprint 9 spec's Goal 4 ("voice: the headset's own button"): Sprint 8 proved that no
pad button talks (`docs/KNOWN.md` row "Voice: the headset path"), and left one hypothesis -- that the Logitech
headset reports a talk button through `lgaud`, in one of three unread spans of its replies: the status word's bits
above bit 1, the device-info block's 0x00-0x61 span, and GetMixer's u16 at reply +0x2c. The spec prescribes two
listing passes and a stop rule. **Both passes were made. Neither found anything that could be a button. This note
files what was read; no mechanism was built** (the brief: "do not invent a mechanism").

Sources, all read-only:
- EE side: `game/analysis/socom2_game.elf.decomp.c` in the main tree (the lgaud client library at :90811-91800,
  the voice object at :210660-211870, the two talk routes at :83886-83930 and :84194-84300, the HUD at
  :85838-85890, the action query at :166915-166931).
- IOP side: `game/disc/RUN/IRX/LGAUD.IRX` (45,925 bytes, "lgAud version 1.08.003, built on Aug 5 2003") and
  `HEADSETO.IRX` (15,728 bytes, "HEADSET Output module v2.0 built with liblgaud 1.08 and SCE 2.8.0"), decompiled
  with the project's Ghidra 12.1.3 headless into the scratchpad (never into the tree). Two things anyone repeating
  this must know: Ghidra's ELF loader picks `MIPS:LE:64:64-32R6addr` for an IRX, under which `jr $ra` (0x03e00008)
  is an invalid instruction and every function is truncated at its first return -- pass `-processor
  MIPS:LE:32:default -cspec default`; and its flow analysis finds 121 of the 149 functions (the USB callbacks and
  the RPC handlers reached through tables are missed) -- a 20-line Python scan for `addiu $sp,$sp,-N` prologues and
  `jal` targets outside known bodies, fed to `ghidra_scripts/MakeFunctions.java` in a second `-process` pass, covers
  33,364 of the 33,856 text bytes; the rest is padding and the import/export stubs. Command shape:

  ```
  analyzeHeadless <dir> lgproj -import LGAUD.IRX HEADSETO.IRX -processor MIPS:LE:32:default -cspec default \
      -scriptPath ghidra_scripts -postScript ExportAll.java <out>
  analyzeHeadless <dir> lgproj -process LGAUD.IRX -scriptPath ghidra_scripts \
      -preScript MakeFunctions.java 0 1458 1920 1994 234 3918 398 3a00 3a34 3c98 3d04 3e30 4114 4288 42f8 \
      4790 483c 484 574 6854 6fd8 7504 76d8 8234 823c 8244 898 d7c -postScript ExportAll.java <out>
  ```

IRX addresses below are offsets into `.text` (the module's link base is 0, so they are what the decompiler prints).

## 1. The answer in one table

| Span the spec named | What the EE reads of it | What the IRX puts in it | Button? |
|---|---|---|---|
| Status word (reply +0x04), bits above bit 1 | Every client call merges it as `word = word & ~2 \| reply` (:90991, :91037, ... 26 sites); the only readers of the merged word are `FUN_00243be8` (:90909, "get and clear if == 1"), called by the voice tick (:211022, compared `== 1` at :211024) and the tuner path (:48402/:48413, `!= 0` means "skip this frame"); and the async EnumHint end function (:91760-91764, `== 1`). No reader masks any bit above bit 1. | `param_2[1] = DAT_00008768; DAT_00008768 = 0;` after every RPC (dispatcher `FUN_00001994`, the common tail). `DAT_00008768` is written 1 on device connect (`FUN_00000574`) and disconnect (`FUN_00000398`), 0 at init and after each report. **It is a one-shot change flag: 0 or 1, nothing else, ever.** | **No.** |
| Device-info block (Enumerate reply +0x20, 0x14c bytes), the 0x00-0x61 span | No caller in the image reads block+0x00..0x61 (Sprint 8's negative, re-confirmed: the four Enumerate callers at :48336, :86588/:86602, :211684, :247060/:247078 read only block+0x62 and the 6-byte entries from block+0x64). | `FUN_00001d8c` builds **four lists**, not a name: `[0x00]` = count of the RECORDING half's format entries (dev+0x10b), 6-byte entries `{channels u8, bits u8, rateLo u16, rateHi u16}` at 0x02+6n (up to 16, from dev+0x11c stride 0x10); `[0x62]` = the PLAYBACK half's format count (dev+0x2b), entries at 0x64+6n (from dev+0x3c); `[0xc4]` = the recording half's feature-unit count (dev+0x10a), 8-byte entries `{u32, u16}` at 0xc8+8n (from dev+0x118 stride 0xa4); `[0x108]` = the playback half's feature-unit count (dev+0x2a), entries at 0x10c+8n (from dev+0x38). 0x10c + 8x8 = 0x14c exactly. USB Audio Class 1.0 capabilities, all of it. | **No.** |
| GetMixer (0x0b), the u16 at reply +0x2c | `FUN_002444f0` (:91212) copies reply+0x2c into the caller's struct +0xc -- and **`FUN_002444f0` has no caller anywhere in the image** (`grep -n FUN_002444f0` finds only its definition; no address literal `2444f0` either). Its twin SetMixer `FUN_00244618` (:91255) likewise has none. | Dispatcher case 10 = `FUN_000032c4`: validates the handle and returns 0 for a valid one, **writing nothing into the struct** (the reply's +0x20..+0x2f echo whatever the EE sent, since the IOP buffer is the send copy). liblgaud 1.08's GetMixer is a stub. Its SetMixer (`FUN_0000331c` -> `FUN_000040a4` -> `FUN_00003f14`) is a USB audio-class SET_CUR to a feature unit. | **No.** |

The rest of every reply, for completeness (the full inventory of `DAT_003dcfb4[...]` reads in :90811-91800):
status +0x00 (the return value), state +0x04 (above), handle +0x0c (Open only, :91036), byteCount +0x20
(Read/Write/0x12/0x13/ARead), PCM at +0x30 (Read), the 0x14c block (Enumerate), and Init's three words in its own
buffer at 0x4149c0 (+0x04 state, +0x08 version 0x108, +0x20 maxstream 0x800: IRX case 0xf, `param_2[2] = 0x108;
param_2[8] = DAT_0000877c`). Nothing else is read, so nothing else could carry a button.

## 2. Pass 1, the EE: what the game polls, and what makes it talk

### 2.1 The lgaud client library and the state word

`FUN_00243840` (lgAudInit, :90813) allocates the one 0x840-byte block `DAT_003dcfb4` and merges the Init reply's
+0x04 into `DAT_003dcfb8` (:90846). Every other client function merges its reply the same way. `FUN_00243be8`
(:90909) is the only "read the state" API: it copies the whole merged word to the caller and zeroes it if it was
exactly 1. The word is therefore `(bit1 as last reported) | (bit0 sticky until read as exactly 1)`, and with the
real module's reply of 0 or 1 it is 0 in the steady state and 1 once after a hot-plug. Our HLE's "2 = steady"
(`lgaud.cpp`, `kStateSteady`) is a value the real module never sends -- it was chosen in Sprint 8 because it is
also harmless under the EE's `== 1` tests, and the s8 rounds proved the tick opens under it. Not changed here.

### 2.2 The voice object and its tick

The voice object is `*DAT_0045b718` (0x10dc bytes; constructor `FUN_003102e0` :211816, init `FUN_00310080`
:211720). The fields that matter, all ESTABLISHED from `FUN_0030ec10` (:210968-211545):

| Field | Meaning | Evidence |
|---|---|---|
| +0x00 (byte) | tick state: 1 idle, 2 floor requested, 3 recording (the HUD's "talking") | :211043-211048 (2 <- 1), :211163-211172 (3 <- 2), :211081 (1 <- 3) |
| +0x24 | channel index (0xb = none) | `FUN_0030e540` :210690 |
| +0x38 | lgaud handle, -1 when closed | :211035, `FUN_0030fef0` :211670 |
| +0x44 | the merged state word as last polled | :211022 (`FUN_00243be8`), :211024 (`== 1` opens) |
| +0x48 (byte) | "recording started" (StartRecording returned 0) | :211163-211172 |
| +0x4a (byte) | **the talk flag** | :211013: when 0, the tick releases the floor (:211016-211034) and decodes/plays the other side (:211044-211080); when non-zero it asks the network object `FUN_00623d00(DAT_0045a1b4, &ready)` (:211084), requests the floor (:211086-211100, request type 1), and on the grant (`+0x70[n] == FUN_0030d5a0(0x45a0c0)`, my client id, :211108-211118) starts recording (:211163-211172) |
| +0x4c (byte) | master gate; 0 = the tick returns at once | :210998-211000 |
| +0x70 + 8n | the floor table: who holds channel n (0x100 = nobody) | `FUN_0030e8e0` :210880-210960 |

**The talk flag +0x4a has exactly three writers** (`grep -n "+ 0x4a) = "` over the voice object's functions):
`FUN_0030e6e0(voice, v)` (:210785, `+0x4a = v` unless the channel is 0xb), `FUN_0030e490` (:210662, clears it on
a channel change) and the constructors/`FUN_0030fef0` (clear). `FUN_0030e6e0` is called from seven places
(:55845, :83913, :83920, :84281, :84430, :126098, :150618); every one but two passes 0. The two that can pass 1 are
the two talk routes below. **Nothing in the voice object, the tick, or the client library writes +0x4a from an
lgaud reply.** The headset module cannot make the game talk; only the two routes can.

### 2.3 The two talk routes, both pad actions

Both read the pad through `FUN_002c64e0(action)` (:166917-166931):

```c
bVar1 = *(byte *)((action & 0xff) + DAT_004415a8 + 0x12);   // the action -> button-slot table
if (bVar1 == 0x10) return 0;                                 // 0x10 = unbound
return *(byte *)(bVar1 + pad + 1);                           // the slot's state byte: 0 up, 2 held, 3 just pressed
```

`DAT_004415a8` is the loaded controller configuration, whose per-action slot table starts at +0x12; it is the disc
resource `data/common/controller.rdr` (KNOWN, Sprint 8). There is no other input into `FUN_002c64e0` -- no
headset, no keyboard, no second table.

- **Route A, `FUN_002359a0` (:84196-84300), action 0xb (zoom/aim).** With `DAT_0045a0c1 != 0` (the online voice
  flag, 1 in a live round), holding the action (`cVar3 == 2`) past the hold timer (`+0xdc8 > DAT_003dcaf8`, 0.3 s)
  with `+0xdcc` set and `DAT_004130a0 == 0` calls `FUN_00236250(player+0x750, 5)` (the talk animation state) and
  `FUN_0030e6e0(voice, 1)` (:84279-84281). With `DAT_0045a0c1 == 0` the same hold is zoom (:84264-84270).
- **Route B, `FUN_002351a0` (:83888-83924), action 10.** Gated on `DAT_0044d4f8` -- which is the options
  menu's **RUN AND TALK: ON/OFF** toggle (:61749-61756, strings 0x3e3c20/0x3e3c40) -- and `DAT_0045a0c1` and the
  player state `+0x750 == 4`, and the 10 s cap `DAT_003dcb00 <= DAT_004130a8`. Held (`cVar3 == 2`): the timer
  `DAT_004130a8` accumulates, `DAT_004130a0 = 1`, `FUN_0030e6e0(voice)` (a1 as left by the caller). Released:
  everything cleared and `FUN_0030e6e0(voice, 0)`.

Sprint 8 held all sixteen pad bits for 3 s each in a live round (`s8_voice_round2`, `round3`, `round4`) and neither
`+0x4a` nor `DAT_004130a8` moved; KNOWN records the reading that action 0xb is unbound in the loaded preset. The
table byte itself was not peeked: **`DAT_004415a8+0x12+0x0b` and `+0x12+0x0a` read live would settle it** (0x10 =
unbound; anything else is the slot that talks). That is a peek, not a mechanism, and it is the one thing this note
leaves for a launch.

### 2.4 How the HUD shows talking

`FUN_00239250` (:85840-85890), the HUD's talk element, draws texture `+0x84` ("talk texture", string 0x3e67a0) when
`FUN_0030e710(voice)` is non-zero, and `+0x80` ("no talk", 0x3e67b0) for a second after someone else took the floor
(`FUN_0030e790`, `DAT_004145f0`). `FUN_0030e710` (:210800) is `voice->state == 3` -- and it mirrors that into the
script variable **`can_talk`** (string 0x3f6988, looked up once at :211764 into `+0x1074`; the u16 at its +0x04
flips and `FUN_003519f0` fires on each change). `hud_talk.tif` (:68613) and `action_talk.tif` (:73551) are the
textures. So "talking" on screen is exactly `+0x00 == 3`: the floor granted and StartRecording answered 0 -- the same
moment `lgaud.cpp` logs `[lgaud] lgAudStartRecording`.

### 2.5 The vendor scan is a sample-rate check, not a Logitech feature

`FUN_0034ba60` (:247047-247081), the only reader of the device-info block, scans the entries at block+0x64+6n for
`{+0 == 1, +1 == 0x10, u16 +2 < 0x5623, u16 +4 > 0x5621}`. With the IRX's layout that is: **a playback format of 1
channel, 16 bits, whose rate range contains 0x5622 = 22050 Hz.** Its callers (:246729, :247098) then open a
22050 Hz stream (`FUN_0033f130(..., 0x5622, ...)`, :246736/:247033) -- game audio into the headset through
`HEADSETO.IRX`, the 989snd plugin ("headset_streamer") that imports lgaud ordinals 5, 6, 8, 13, 14, 15, 16, 22
(Open, Close, Write, Start/Stop/ResumePlayback, SetPlaybackVolume, WriteVag: playback only). The guard
`DAT_0045a0c1 == 0` means this path runs only offline. Sprint 8's R113 ("entryCount 0 = no Logitech vendor
extensions") stands with a better name: our headset reports no 22050 Hz playback format, so the game never routes
989snd into it, which is what we want. The Sprint 8 plan's "0x63 + 6n entry id" is off by one (entries start at
0x64) and "0x00..0x61 = the device name" is wrong (it is the recording half's format list); neither reaches code.

## 3. Pass 2, the IRX: what liblgaud 1.08 is

- **A USB Audio Class 1.0 driver on `usbd` (version 2.4.3 or newer, per its own error string), and nothing else.** The probe `FUN_00000234` knows four
  vendors by id -- Sony 0x054c (with product ranges 0x0100-0x01ff and 0x0154-0x0157 treated differently), Logitech
  0x046d (product bands around 0xcac0-0xcac1), 0x0672 and 0x12ba -- and for everything else walks the interface
  descriptors and accepts only a device with class 1 subclass 1 (AudioControl) AND class 1 subclass 2
  (AudioStreaming). (Which product bands are accepted outright and which fall to the class walk is contorted in the
  decompilation and was not pinned; it does not bear on the question.) On connect, a device from one of the four
  vendors additionally has its iProduct string checked against a per-vendor XOR table (`FUN_00000484`, tables at
  0x8440-0x8470) and is refused (`dev+0x20 = -1`) on a mismatch.
- **Connect** (`FUN_00000574`): SET_CONFIGURATION, SET_INTERFACE x2, GET_DESCRIPTOR(string), the name check, then
  `FUN_000042f8` reads every feature unit's GET_CUR/GET_MIN/GET_MAX (bmRequestType 0xa1, bRequest 0x81/0x82/0x83),
  the device is slotted into `DAT_00009f80[0..7]`, and `DAT_00008768 = 1` (the change flag) plus the local twin
  `DAT_0000876c = (DAT_0000876c & ~2) | 1`. **Disconnect** (`FUN_00000398`) sets the same flag.
- **The descriptor parser (`FUN_000008fc`) DOES notice interrupt-IN endpoints** on any non-audio interface
  (`bmAttributes & 3 == 3 && bEndpointAddress & 0x80`, up to two, stored at dev+0x1e8/+0x1f4 with a count at
  dev+0x200) -- the shape of a HID interface's report pipe, which is where a headset button would live. **And then
  nothing reads them:** `grep` over the whole decompilation for `0x1e8..0x200` and `[0x7a..0x80]` finds only the
  three stores. No pipe is ever opened on them (`sceUsbdOpenPipe` is called for the control pipe and the two
  isochronous streams only), no HID GET_REPORT is ever issued (every control transfer is listed above), no
  HID class request exists in the module. The code that would have carried a button is a stub of a data structure.
- **The RPC dispatcher (`FUN_00001994`)**, IOP case = EE function - 1: 0 Enumerate `FUN_00001d8c`, 1 Open
  `FUN_00002230` (record half from openparam +2/+3/+4, playback half from +8/+9/+10 -- the Sprint 8 ASSUMED order,
  now ESTABLISHED), 2 Close, 3 StartRecording `FUN_00002954` -> `FUN_00002824(h, 0)`, 4 StopRecording (`(h, 1)`),
  5/6/0x10 Start/Stop/ResumePlayback `FUN_000029f4(h, 0/1/2)`, 7 Read `FUN_00002c2c`, 8 Write, 10 GetMixer (stub),
  0xb SetMixer, 0xc SetPlaybackVolume `FUN_000037a4`, 0xd SetRecordGain `FUN_000037d4`, 0xe EnumHint (`*p = 0`),
  0xf Init, 0x11 AvailableRecording (`dev+0x140`), 0x12 RemainingPlayback (`dev+0x60`), 0x13 PrepareForReboot,
  0x14 WriteVag; default 0x80000000. Every case ends with the state tail of section 1.
- **The export table** (0x818c, "lgaud" 1.08, 23 ordinals) exposes the same handlers to other IOP modules plus
  ordinal 18 = `FUN_00001d0c`, an IOP-local "get state and clear if 1" over `DAT_0000876c`. `HEADSETO.IRX` does not
  import it. No IOP-side consumer of a button exists either.

**Verdict of pass 2: liblgaud 1.08 has no button anywhere in its replies, its exports, or its USB traffic.**

## 4. The stop rule, applied

The spec: "two listing passes and two launches without the talk flag moving -> file what was read and stop". The
two listing passes are above and both are negative on every span named; a launch cannot move a flag that no reply
can reach, so no launch was made (this worktree has no `game/`, and the brief keeps launches with the controller).
The retail headset that shipped with SOCOM (Logitech, 0x046d:0xcac0-0xcac1) has an inline mute switch and volume
wheel; whatever they are electrically, this module never asks. **Stopped here.**

What is still true and unchanged: the microphone reaches the game's headset (Sprint 8 Tasks 1-2, `94937ec`,
`79a9e26`); the game opens it when a session starts; the floor protocol, the 0x500-byte reads and the Nellymoser
encode all wait on `+0x4a`. What sets `+0x4a` in a shipped game is a pad slot bound to action 0xb or 10 in
`controller.rdr` -- the loaded preset's bytes were never read live. The one launch this note recommends is that
peek (section 2.3): `DAT_004415a8+0x12+0x0a` and `+0x0b` in a live round, and the controller-configuration screen's
own list of actions, which is the disc's dictionary rendered. If either slot is bound, the pad overlay in
`online_login_ours.py` already knows how to hold it. If both read 0x10, the talk action was never in this build's
preset and the question moves to the disc resource -- a different goal, and the owner's to rank.
