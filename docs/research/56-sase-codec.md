# 56. SASE, SOCOM II's voice codec: what the strings, the call structure and the tables say

Date: 2026-09-24. Sprint 12 research wave, question 11 of the cloud handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`): "what the strings, the call structure and the
data tables say about the codec (frame size, sample rate, bit rate, VAD), without naming a vendor the evidence
does not name; what Q5 (voice chat) would need from it". Read-only; written so that Q5's owner can start here.

**On the vendor, explicitly.** This note names no vendor. The images carry the codec's source-directory names
(`SaseEncVad`, `SaseDec`, `shared`), its unit file names, a 12-character version tag, and one identifier prefix:
the assert expressions spell their null constant `NellyNull` (101 occurrences in 72 strings in the demo and
r0001, 103 in 74 in r0004; `P[1]`). An identifier prefix is not a vendor statement: no copyright, company,
product or licence string accompanies it. Several committed places already say "Nellymoser" (research/23 §3.2 and
§3.4, the Sprint 8 plan's capture-loop step 2, `docs/KNOWN.md`'s "Voice: the headset path" row, and two source
comments: `lgaud.cpp`'s Write case and `ps2_iop_host.cpp:328`); that is a reading of the token, not something a
string in the images says. The codec is called **SASE** here, after its directories.

## How to reproduce every number

All numbers come from one read-only script and its disassembly mode, run from the repo root:

- `P[n]` = `python tools_py/research/symbols/sase_probe.py`, section `[n]` of its output (under ten seconds).
- `D <img> <addr> <len>` = `python tools_py/research/symbols/sase_probe.py --dis <img> <addr> <len>`
  (mnemonics of one span; `<img>` is `demo1`, `demo2`, `r0001` or `r0004`).

Inputs: the Aug 18 2003 demo `game/demo_scus_973_68/SCUS_973.68` ("demo2": stripped, one RWX segment at
0x100000), r0001 `game/disc/socom2_game.elf` with `recomp/socom2_ghidra.csv`, r0004
`game/overlays_r0004/socom2_game_r0004.elf` with `recomp/socom2_ghidra_r0004.csv`, `game/r0004/match.json`,
and the SOCOM 1 demo `game/demo_scus_972_05/SCUS_972.05` ("demo1") as the LPC-10 contrast only. The demo2 has no
function table: its function starts are the `jal`/`j` targets ("the jal/j partition", 9,169 starts, `P[5]`).
Addresses below are r0001's unless a build is named. No table byte, codebook value or instruction word appears in
this note: tables are given by address, length, element width and shape.

## 0. The answer

| Question | Answer | Status |
|---|---|---|
| What is it | A sinusoidal low-rate speech coder in two libraries (encoder with VAD, decoder) plus a shared FFT, 237 functions / 60,208 bytes of code in r0001, all of it recompiled and run as guest code today | size measured (`P[2]`); the kind inferred from the directory and unit names (`EncVad`, `SWSynth`, `SetAmps`, `PtchCand`) |
| Sample rate | **8000 Hz**, mono, 16-bit | measured (`P[3]`) |
| Frame | **160 samples = 20 ms** | 160 measured, 20 ms inferred |
| Bits per frame / rate | **64 bits (8 bytes) per frame, 3200 bit/s**, constant | measured (`P[3]`) |
| Frame format | **17 fields, each at most 8 bits**, packed by a 17 x 16-bit width table | measured (`P[3]`, `P[4]`) |
| VAD | computed inside the encoder's level unit; the game fetches it and **ignores it**; it uses only a gain-trend value to steer the headset's record gain. Transmission is gated by push-to-talk, not VAD | structure measured, meaning inferred |
| On the wire | **32 bytes per 80 ms** (4 frames) per voice message, codec mode 1; the receiver decodes 8 bytes at a time | measured (`D`, §6) |
| Where it plays | decoded PCM goes to the **headset** (lgaud Write, 2 ch 16-bit 8000 Hz, L=R), not to 989snd | measured (§6) |
| LPC-10 in the Aug 18 demo | **code is present**, not only the string: an rt_lpc10 module; three of four 32-byte windows of demo1's LPC-10 decoder data occur in it, next to the `rt_lpc10 version` string; not SOCOM 1's binary; not in the game's voice path | measured + inferred (`P[5]`) |
| Q5's smaller job | **run the recompiled codec as is** (it already runs); a native reimplementation would have to rebuild an unidentified codec bit-exactly plus the tables of a ~21 KB read-only block that are the owner's bytes | inferred from the above |

## 1. The source-path strings and the units

### 1.1 The strings, per image

`P[1]` lists every `../../SaseEncVad/source/*.c`, `../../SaseDec/source/*.c` and `../../shared/*.c` string
by address. Counts: **demo2 and r0001: 25 SASE paths (21 SaseEncVad + 4 SaseDec); r0004: 26 (22 + 4)**; all three
also carry 3 `../../shared/` paths. The r0001 and demo2 addresses differ by a constant 0x158588 (`P[5]`, "rodata
at +0x158588").

| unit | demo2 | r0001 | r0004 | directory |
|---|---|---|---|---|
| `AskToEnvInline.c` | 0x544800 | 0x3ec278 | 0x417468 | SaseDec |
| `BitPackC.c` | 0x53fef0 | 0x3e7968 | 0x412e88 | SaseEncVad |
| `CalcCost.c` | - | - | 0x412ec0 | SaseEncVad |
| `CodePv.c` | 0x540048 | 0x3e7ac0 | 0x413038 | SaseEncVad |
| `Coder.c` | 0x540098 | 0x3e7b10 | 0x413088 | SaseEncVad |
| `DecSC.c` | 0x5449a8 | 0x3ec420 | 0x417610 | SaseDec |
| `DecVcFry.c` | 0x540140 | 0x3e7bb8 | 0x413130 | SaseEncVad |
| `EncSC.c` | 0x5403d0 | 0x3e7e48 | 0x4133c8 | SaseEncVad |
| `fft4CFG.c` | 0x543df0 | 0x3eb868 | 0x416e50 | shared |
| `fftIf.c` | 0x543578 | 0x3eaff0 | 0x4165d8 | shared |
| `LDPDA.c` | 0x5405a0 | 0x3e8018 | 0x413598 | SaseEncVad |
| `libmath.c` | 0x5406e8 | 0x3e8160 | 0x4136e0 | SaseEncVad |
| `libquan.c` | 0x541de0 | 0x3e9858 | 0x414de8 | SaseEncVad |
| `libsigproc.c` | 0x542178 | 0x3e9bf0 | 0x415188 | SaseEncVad |
| `libsnd.c` | 0x542218 | 0x3e9c90 | 0x415228 | SaseEncVad |
| `libspeech.c` | 0x5422c8 | 0x3e9d40 | 0x4152e0 | SaseEncVad |
| `libtran.c` | 0x5424f0 | 0x3e9f68 | 0x415508 | SaseEncVad |
| `libvect.c` | 0x542880 | 0x3ea2f8 | 0x4158b0 | SaseEncVad |
| `PackSC.c` | 0x542948 | 0x3ea3c0 | 0x415980 | SaseEncVad |
| `PostFilt.c` | 0x5429e8 | 0x3ea460 | 0x415a38 | SaseEncVad |
| `PreProc.c` | 0x542a40 | 0x3ea4b8 | 0x415a98 | SaseEncVad |
| `PtchCand.c` | 0x542ab8 | 0x3ea530 | 0x415b10 | SaseEncVad |
| `QP0SC3.c` | 0x542be0 | 0x3ea658 | 0x415c38 | SaseEncVad |
| `RefineC0.c` | 0x542c38 | 0x3ea6b0 | 0x415c90 | SaseEncVad |
| `rFft2G.c` | 0x544318 | 0x3ebd90 | 0x417380 | shared |
| `SetAmps.c` | 0x544ef8 | 0x3ec970 | 0x417b60 | SaseDec |
| `SWSynth.c` | 0x545000 | 0x3eca78 | 0x417c68 | SaseDec |
| `Voicing.c` | 0x543178 | 0x3eabf0 | 0x4161d8 | SaseEncVad |
| `VoicLD.c` | 0x543538 | 0x3eafb0 | 0x416598 | SaseEncVad |

**A correction to the corrected record** (`tools_py/research/symbols/README.md` "Voice codec" and research/44's
addendum, which the controller owns): their unit list has 18 names and says "r0004 adds `CalcCost.c`, `EncSC.c`".
The images carry 25 SASE units in demo2/r0001, including `CodePv.c DecVcFry.c libtran.c libvect.c VoicLD.c
AskToEnvInline.c` and `EncSC.c`; **r0004 adds only `CalcCost.c`**, and `EncSC.c` is in all three (the table).

Other strings that bear on the codec (`P[1]`): the version tag **`BSC.01.01.00`** once in each SOCOM II image
(the decoder's info function copies its 12 bytes into the info struct, §3); **`rt_lpc10 version: 1.00.0002` and
`rt_lpc version: 1.00.0001` in demo2 only**; `rt_audio version: 1.08.0003` (demo2), `1.08.0009` (r0001),
`1.08.0012` (r0004), the DME network library's audio module, whose `$Header` strings name `rt_audio/src/codec.c,v
1.4` in all three.

### 1.2 Function-to-unit attribution

A unit's functions are the ones that form the address of its path string: the argument to `__assert`
(0x191440, 96 call sites in the range, `P[2]`). `P[1]` prints every function per unit for r0001 and for r0004
(by r0004's own path references, independent of `match.json`), and how many of r0001's the current `match.json`
places.

| unit | r0001 fns / bytes | r0004 fns / bytes | r0001 functions |
|---|---|---|---|
| AskToEnvInline.c | 1 / 588 | 1 / 588 | 0x253510 |
| BitPackC.c | 1 / 300 | 1 / 300 | 0x2484a0 |
| CalcCost.c | 0 / 0 | 1 / 516 | (r0004 0x2485d0; the r0001 function at 0x2485d0, 324 B, has no assert) |
| CodePv.c | 1 / 180 | 1 / 180 | 0x2487e8 |
| Coder.c | 1 / 372 | 1 / 372 | 0x2488a0 |
| DecSC.c | 4 / 304 | 4 / 304 | 0x254318 0x254368 0x2543b8 0x254408 |
| DecVcFry.c | 1 / 428 | 1 / 460 | 0x248ad0 |
| EncSC.c | 12 / 1,192 | 12 / 1,192 | 0x249608 0x249660 0x2496d8 0x249750 0x2497a8 0x249810 0x249858 0x249898 0x2498e0 0x249920 0x249968 0x249a38 |
| fft4CFG.c | 1 / 1,048 | 1 / 900 | 0x251c80 |
| fftIf.c | 1 / 320 | 1 / 340 | 0x2518e8 |
| LDPDA.c | 10 / 2,956 | 10 / 3,016 | 0x249fa8 0x24a210 0x24a438 0x24a5a8 0x24a7c0 0x24a840 0x24a8b0 0x24a908 0x24a9f0 0x24aae8 |
| libmath.c | 3 / 728 | 3 / 776 | 0x24ad48 0x24aeb0 0x24af50 |
| libquan.c | 14 / 4,532 | 14 / 4,568 | 0x24b028 0x24b2f8 0x24b560 0x24b720 0x24b7e8 0x24b8b0 0x24b990 0x24ba48 0x24bcf0 0x24be70 0x24bf50 0x24c000 0x24c078 0x24c150 |
| libsigproc.c | 3 / 988 | 2 / 1,016 | 0x24c1f0 0x24c458 0x24c4d8 |
| libsnd.c | 3 / 628 | 3 / 680 | 0x24c648 0x24c6c0 0x24c7d0 |
| libspeech.c | 6 / 2,740 | 5 / 2,200 | 0x24c8e8 0x24cae8 0x24cf10 0x24d370 0x24d498 0x24d560 |
| libtran.c | 10 / 4,584 | 10 / 4,612 | 0x24d8b8 0x24da70 0x24dbb8 0x24dfb8 0x24e408 0x24e5b0 0x24e918 0x24e9c0 0x24ea68 0x24eb60 |
| libvect.c | 5 / 784 | 4 / 560 | 0x24ecf8 0x24edd0 0x24ee38 0x24eea0 0x24ef30 |
| PackSC.c | 1 / 252 | 1 / 252 | 0x24fae8 |
| PostFilt.c | 1 / 592 | 1 / 628 | 0x24fbe8 |
| PreProc.c | 1 / 284 | 1 / 300 | 0x24fe38 |
| PtchCand.c | 6 / 3,036 | 6 / 3,100 | 0x24fff8 0x250320 0x2504f0 0x250708 0x2508f0 0x250a38 |
| QP0SC3.c | 1 / 88 | 1 / 104 | 0x250c68 |
| RefineC0.c | 1 / 648 | 1 / 664 | 0x250cd8 |
| SetAmps.c | 1 / 712 | 1 / 712 | 0x255e68 |
| SWSynth.c | 5 / 2,056 | 5 / 2,056 | 0x256380 0x256420 0x2566d8 0x256ab0 0x256db0 |
| Voicing.c | 1 / 784 | 1 / 792 | 0x250f60 |
| VoicLD.c | 1 / 584 | 1 / 592 | 0x2513f0 |
| **total** | **96** | **94** | of 237 (r0001) / 242 (r0004) functions in the range |

The r0004 column's addresses are in `P[1]`. `rFft2G.c`'s path is referenced by no function in any build
(`P[1]`): its code has no assert. 141 of r0001's 237 functions (60 %) carry no path reference. Within
`SaseEncVad` the path strings and the attributed functions ascend together in case-insensitive name order
(`BitPackC` at 0x2484a0 first; the table above), so an unattributed function has a link-order neighbourhood
between two named units, not a proven unit; `shared` and `SaseDec` follow.

## 2. The call structure

### 2.1 The range, and what calls into it

r0001's SASE code is **0x2484a0-0x256fd0: 237 functions, 60,208 bytes** (`P[2]`); the first function after it,
0x256fd0, is called only from 0x25a120, outside (`P[2]` "end check"). Nothing outside the range calls into it
except **fourteen wrapper functions of the game's voice object at 0x3103d0-0x310830** (`P[2]`, "distinct outside callers"). The
network library never calls SASE; the game does, from two callbacks it hands the network library (§6).

### 2.2 The API, with proposed readable names

Each row: the entry, its caller, and what says so. `D r0001 <addr> <len>` shows the mnemonics.

| r0001 | proposed name | called from | evidence |
|---|---|---|---|
| 0x24f990 | `sase_enc_create` | 0x310830 | allocates 0x30 bytes through the alloc hook (`lw ..-0x7d48($gp)`, `jalr`), writes a 64-bit magic (`ori ..0xface`) and a type byte **0xa** at +0x18, two 64-bit constants (100, 3000), calls the state init 0x249190, bumps the instance count at `-0x7d30($gp)` (`D r0001 0x24f990 0xa0`) |
| 0x24fa30 | `sase_enc_destroy` | 0x3107d0 | checks magic and type 0xa, drops the count, frees through the free hook `-0x7d44($gp)` (`D r0001 0x24fa30 0x90`) |
| 0x24f888 | **`sase_encode_frame`** | 0x310750 | validates an I/O block (PCM pointer, packet pointer, size, byte offset < size, two bit offsets < 8), checks magic/type 0xa, then calls **0x248fb0** (analysis), **0x2488a0** (`Coder.c`, quantize) and **0x24fae8** (`PackSC.c`, pack) in that order (`D r0001 0x24f888 0x108`) |
| 0x24f518 ... 0x24f838 | `sase_enc_set_*` (11) | 0x3104f0-0x310630 | 76-byte shims, each calling one `EncSC.c` setter; 2 of the 11 (0x24f748, 0x24f7e8) have no caller (`P[2]`) |
| 0x24fac0 | `sase_set_vu0_mode` | none | calls 0x251a98, the only writer of the VU0 mode word `-0x7d50($gp)` = 0x1d55a0 (research/23 §3.4) |
| 0x255a68 | **`sase_get_info`** | 0x310830 | fills a struct with the codec's constants (§3) and the `BSC.01.01.00` tag |
| 0x255bd0 | `sase_dec_create` | 0x310830 | as the encoder's create with type byte **0xb** and the state init 0x253a98 (`D r0001 0x255bd0 0x98`) |
| 0x255c68 | `sase_dec_destroy` | 0x3107d0 | magic/type 0xb check, 0x254250, the free hook |
| 0x255b68 | **`sase_decode_frame`** | 0x3106a0 | 24 bytes: sets a third argument to 0 and tail-jumps (`j`) to **0x254ec8**, the decoder core (`D r0001 0x255b68 0x18`) |
| 0x255cf8 | `sase_dec_frame_done` | 0x3106a0 | returns a state byte (+0x40) the caller loops on |
| 0x255b80, 0x255ba8 | `sase_decode_frame_alt*` | none | two further decode entries (to 0x255028 / 0x255490 with extra zeroed arguments): a second decoder path the game never uses (§2.4) |
| 0x256f48, 0x256f68 | `sase_set_alloc_hook`, `sase_set_free_hook` | 0x310830 | store their argument at 0x1d55a8 / 0x1d55ac unless the instance count is non-zero; the game passes 0x310970 (a tail jump to 0x1915c8, which the codec calls as `(1, size)`: calloc-shaped, inferred) and 0x310960 (a tail jump to `free`) (`D r0001 0x310960 0x20`, `D r0001 0x256f48 0x40`) |
| 0x252748, 0x2527f8 | `sase_level_attach`, `sase_level_detach` | 0x310410 | attach allocates 0x20 bytes and calls 0x253420 with **8000.0f and 160** (`P[3]`), hangs it at encoder state +0x4c |
| 0x252880, 0x252920, 0x252ab0, 0x252b50, 0x252a10, 0x252a60 | `sase_level_set_*` | 0x310410, 0x310480 | store halfwords at level-state +0x1a, +0x18, +0x16, +0x14 and set/clear +0x1e; 0x310480 passes 30, 150, 0 and the voice object's +0x10a0 (180 from the constructor) |
| 0x2529c0 | `sase_level_get_decision` | 0x3103d0 | returns level-state +0x1c |
| 0x252ba0 | `sase_level_get_trend` | 0x3103d0 | returns level-state +0x14 |

The game's side, a 0x38-byte "voice codec" object (all in r0001; r0004 counterparts from `match.json` and
`D r0004 0x32d200 0x60`):

| r0001 | r0004 | proposed name | what it does |
|---|---|---|---|
| 0x310830 | 0x32ddd0 | `voice_codec_create` | sets the hooks, reads `sase_get_info` (frame length from info+0x3c, bits from info+0x60, `P[3]`), allocates a PCM buffer of frame x 2 bytes and a packet buffer of ceil(bits/8) + 2 bytes for each direction, creates the decoder then the encoder |
| 0x3107d0 | 0x32dd70 | `voice_codec_destroy` | both destroys, five frees |
| 0x310750 | 0x32dcf0 | **`voice_codec_encode`** | copies **0x140 = 320 bytes** of PCM in, `sase_encode_frame`, copies out the whole bytes the packer completed, carries a partial byte over, returns the byte count (`D r0001 0x310750 0x80`) |
| 0x3106a0 | 0x32dc40 | **`voice_codec_decode`** | copies **8 bytes** of packet in, loops `sase_decode_frame` + copy of frame x 2 bytes of PCM out until `sase_dec_frame_done` (`D r0001 0x3106a0 0xa8`) |
| 0x3103d0 | 0x32d970 | `voice_codec_level_trend` | fetches the level decision (discarded) and the trend (returned) |
| 0x310410, 0x310480, 0x3104f0-0x310630 | | `voice_codec_set_*` | the level unit on/off and settings; the encoder setters |
| 0x30f990 | 0x32cf20 | **`voice_net_fill_cb`** | no direct caller; its address is formed only in 0x30fc70 (`P[2]`). Runs the voice tick 0x30ec10, and in state 3 reads the headset and encodes (§6) |
| 0x30f7e0 | 0x32cda0 | **`voice_net_recv_cb`** | no direct caller; address formed only in 0x30fc70. Decodes and plays (§6) |
| 0x30fc70 | 0x32d200 | `voice_net_describe` | fills the descriptor handed to the network library: +0x2c = the fill callback, +0x34 = the receive callback, +0x14/+0x18/+0x1c record channels/bits/rate, +0x20/+0x24/+0x28 playback channels/bits/rate (`D r0001 0x30fc70 0x60`); called from 0x30d1b0 and 0x30d380, which pass it to network-library functions at 0x6218b8, 0x621950, 0x622fe8, 0x6236c0 and 0x621778 |

### 2.3 Depth and leaves

With `jal` and `j` both followed (the codec tail-calls), `P[2]`: **`sase_encode_frame` reaches 114 functions,
depth 7; `sase_decode_frame` reaches 41, depth 7; 15 are shared** (the FFT and vector helpers); 82 functions
reached from either are leaves. The encoder's chain (callees from `D`, callers re-checked with the probe's
`branch_targets`): 0x24f888 -> 0x248fb0 (analysis: `PreProc.c` 0x24fe38 on 160 samples, `libsnd.c` 0x24c6c0
buffering, the pitch driver 0x2499a8 -> `LDPDA.c` 0x249fa8 -> `PtchCand.c` 0x24fff8, `EncSC.c` 0x249a38, then
0x2492a0 (740 B), which calls `Voicing.c` 0x250f60 -> `RefineC0.c` 0x250cd8, and the level unit 0x2525c0 when
attached) -> `Coder.c` 0x2488a0 (quantization: `libquan.c` 0x24b028 for the spectral envelope, `CodePv.c`
0x2487e8, `QP0SC3.c` 0x250c68 for pitch) -> `PackSC.c` 0x24fae8 -> `BitPackC.c` 0x2484a0. The decoder's: 0x255b68 -> 0x254ec8 ->
0x253df8 (`AskToEnvInline.c` 0x253510 for the envelope with `PostFilt.c` 0x24fbe8, then 0x256190 ->
`SWSynth.c` 0x256420 -> 0x254510, which runs the `fftIf` helpers 0x251af8/0x251b38/0x251c00: the sine-wave
synthesis is FFT-based, `SetAmps.c` 0x255e68 sets the harmonic amplitudes). The leaf DSP routines include the
FFT (`fft4CFG.c` 0x251c80, the rFft2G-region 0x252338/0x252470), the vector primitives (`libvect.c`), and two
bit-manipulating float approximations used everywhere (0x2517d8, 5 callers; 0x251850, 3 callers: mantissa and
exponent masks, `D r0001 0x2517d8 0x74`).

### 2.4 Dead code, and what the codec calls outside itself

- **41 of the 237 functions are reached from no entry point** and named by no data word anywhere in the image
  (`P[2]`): the second decode path (0x255b80/0x255ba8 -> 0x255028/0x255490 -> 0x254020, 0x254730, 0x254a88,
  0x256280, 0x2566d8), the four `DecSC.c` setters and their three shims, the VU0 mode setter pair, two encoder
  setters, several `libtran.c`/`libspeech.c` routines (among them the only `sinf` and `atan2f` callers), and the
  unused hook setters 0x256f88. `recomp/extra_functions.txt` lists 8 of these starts (0x251700 0x252238 0x2528d0
  0x252970 0x252b00 0x254458 0x256130 0x256f88) so the recompiler still emits them
  (`grep -E "^0x0*(24[89a-f]|25[0-6])[0-9a-f]{3}\b" recomp/extra_functions.txt`).
- **Outside callees** (call sites, `P[2]`): `__assert` 96, `fptodp` 4, `ceilf` 2, `dpcmp` 2, `dptofp` 2,
  `expf` 2, `log10f` 2, `memcpy` 2, and one each of `asinf atan2f cosf dpadd dpsub logf pow printf sinf sqrtf`.
  `__assert`, `memcpy`, `printf`, `ceilf`, `cosf`, `sinf` and the soft-double names are `recomp/socom2.toml`'s
  bindings; `pow asinf atan2f expf logf log10f sqrtf` are 20-byte wrappers at 0x1b3898-0x1b3958 that tail-jump
  to the toml's `__ieee754_*` stubs of those names (`D r0001 0x1b3898 0xd8`), named here after their targets. So the recompiled codec's arithmetic depends on the runtime's
  libm and soft-double stubs (research/20; §6).
- **No stub, no override covers the codec**: `grep -ciE "0x0*(24[89a-f]|25[0-6])[0-9a-f]{3}\b" recomp/socom2.toml
  third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` answers 0 and 0. It runs as recompiled
  guest code.
- **The VU0 path is dead** (research/23 §3.4, re-read here): 0x251a28, called at the start of every encoder
  analysis and decoder frame, uploads the VU0 microcode only when the mode word 0x1d55a0 is 1; its only writer
  0x251a98 is reached only from the uncalled 0x24fac0 (`D r0001 0x251a28 0x70`).

## 3. The parameters

| Parameter | Value | Status | Evidence (command) |
|---|---|---|---|
| Sample rate | **8000 Hz** | measured | `sase_get_info` stores `sh 8000` at +0x38 (`P[3]`); `sase_level_attach` passes 8000.0f (`lui 0x45fa`, `P[3]`); the voice constructor stores 8000 for both headset halves at +0x10cc/+0x10d0 (`P[3]`), which 0x30fef0 copies into the lgaud openparam (`D r0001 0x30fef0 0xb0`); the image's other stores at those displacements write a float 100.0 into other objects (`D r0001 0x201fb0 0x60`); `docs/KNOWN.md`'s voice row logged the live open as `rec=1ch/16bit/8000Hz play=2ch/16bit/8000Hz` |
| Sample format | 16-bit, mono in / mono out (played as 2 identical channels) | measured | `sh 16` at +0x3a (`P[3]`); constructor: record channels 1, playback channels 2, bits 16 both (`P[3]`); the L=R duplication in 0x30f5f0 (`D r0001 0x30f5f0 0xf0`) |
| Frame size | **160 samples** | measured | `sh 160` at info+0x3c, read back by `voice_codec_create` as the frame length (`P[3]`); `voice_codec_encode` copies 320 bytes (`P[3]`); the analysis passes 160 to `PreProc.c` and `libsnd.c` (`P[3]`); the level unit is created with 160 (`P[3]`) |
| Frame period | **20 ms** | inferred | 160 / 8000 |
| Bits per frame | **64** (8 bytes), the same value in three fields | measured | `sd 64` at +0x50, +0x58, +0x60 (`P[3]`); `voice_codec_decode` feeds exactly 8 bytes per frame (`P[3]`, `D r0001 0x3106a0 0xa8`); the receive callback steps its input by 8 per decoded frame (`D r0001 0x30f7e0 0x1a8`) |
| Bit rate | **3200 bit/s** | measured | `sd 3200` at +0x48 (`P[3]`) = 64 x 50 frames/s |
| Other info fields | +0x00 = 4 (struct version?), +0x28 = 100, +0x30 = 3000, +0x3e = +0x40 = 1, +0x68/+0x6a computed from `ceilf(0.90625)` | values measured, meanings **unknown** | `P[3]`, `D r0001 0x255a68 0xfc`; 100 and 3000 are also written into both handles at create (`D r0001 0x24f990 0xa0`) |
| Frame layout | **17 fields, each 1-8 bits**, total 64 | measured / sum inferred | `PackSC.c`: a loop of N+1 = 17 iterations (`addiu s1, zero, 16` ... `bgezl`, `P[3]`) reading one 16-bit width per field (`lh`, table 0x3ea398, `P[4]`) and one quantizer index per field; `BitPackC.c` asserts a data width of at most 8 on its argument `cDataWidth` (`slti ..9`, `P[3]`); that the widths sum to 64 follows from the info fields and is not re-added here from the table |
| Packet continuity | a frame's bits are written at a running (byte, bit) offset; a trailing partial byte is carried into the next call | measured | `sase_encode_frame`'s I/O block (byte offset < size, bit offsets < 8) and `voice_codec_encode`'s carry (`D r0001 0x310750 0x80`); with 64-bit frames every frame ends on a byte boundary, so the carry never fires (inferred) |
| Envelope | a **12-coefficient** vector split into **6 two-dimensional sub-vectors**; the first 4 by a structured two-stage VQ, the last 2 by a plain 32-entry VQ; two parameter sets chosen by a float test | measured (structure) / inferred (what the 12 are) | `libquan.c` 0x24b028 asserts the order is 12 (`addiu v0, zero, 0xc` / `beq`), loops 6 times over pairs (`D r0001 0x24b028 0x2d0`); `P[4]` for the tables. The identifiers in the unit's asserts (`iOrder`, `SUB_VECTORS`, `SUB_DIMENSION`, `pfStage1CB`, `pfRotScaleCB`, `pfStage2InCellCB`, `pfStage2OutCellCB`; `iLpcOrder`, `MAX_LPC_ORDER`, `pfPARCOR` in `libspeech.c`) say an LPC-derived envelope |
| Pitch | a scalar index whose width is the macro `BITS_PITCH_SC3` (named in `QP0SC3.c`'s assert) over a candidate search (`PtchCand.c`, `LDPDA.c`, `RefineC0.c`) | structure measured, width **unknown** here | the assert string (`P[1]` lists its unit); the width is one of the 17 table entries |
| Voicing | `Voicing.c` 0x250f60, called from the analysis (0x2492a0), with `RefineC0.c` under it; its assert on `iBaseBand` against `NFFT` reads as a voiced-band decision | chain measured, meaning inferred | §2.3 |
| VAD | the level unit (0x2525c0 per frame, attached by the game) computes a **decision** at level-state +0x1c and a **gain trend** at +0x14. The game fetches both through 0x3103d0 and **returns only the trend**; every fifth capture pass, trend < 0 lowers and > 0 raises the record gain by 5 through lgaud 0x0e SetRecordGain, clamped to 20..100 | structure measured, meaning of +0x1c inferred | `D r0001 0x3103d0 0x40` (the +0x1c result lands in a stack slot nothing reads), `P[3]` (the clamp immediates), `D r0001 0x2529c0 0x50`, `D r0001 0x252ba0 0x50`. **No caller tests a VAD flag to decide whether to send**: the fill callback sends whenever the talk state is 3 (§6) |
| Encoder side delay | `EncSC.c` asserts a length against `ENC_DELAY_SIZE` plus `piWinShift` | value **unknown** | a look-ahead exists; its length is not measured here |

## 4. The data tables

`P[4]` lists every address in the read-only data (0x3d5000-0x408480) that the SASE code forms with a
`lui`/low-half pair, with a length bound (the distance to the next address any SASE function forms, strings
included), the access mnemonics seen through it, and the reading unit (`~addr` = a function without a path
reference, named by address). Lengths marked `=` are measured from a copy or loop bound; `<=` are bounds.

| r0001 address | length | element (access) | shape | reader | consistent with |
|---|---|---|---|---|---|
| 0x3d5980 | = 3,536 B (`memcpy` length end - start, `D r0001 0x252150 0xe4`) | 64-bit words (VU micro) | 442 x 64-bit | ~0x252150 (VU0 upload) | the VU0 FFT microcode; **dead** (mode word 0) |
| 0x3eb088 | = 2,016 B (copy loop to +0x7e0, same command) | copied by `ld`/`sd` to VU0 data 0x11004800 | 126 x 128-bit | ~0x252150 | VU0-side FFT data; **dead** |
| 0x3dcfc8, 0x3dcfe0 | 24 B each | 32-bit pointers | 6 pointers, the first null; targets 16, 32, 48, 64 B apart | `libquan.c` 0x24b028/0x24b2f8 | per-sub-vector prediction matrices: sub-vector i (i = 1..5) predicted from the 2i values before it, 2 x 2i floats; one set per parameter set |
| 0x3e82b8, 0x3e82e8 | = 48 B each (the first ends where the second begins, the second where the first prediction matrix begins, 0x3e8318, `P[4]`) | float | 12 x float | `libquan.c` | the two mean vectors of the 12-coefficient envelope |
| 0x3e84f8-0x3e9658 (five 8-word descriptors at 0x3e8928, 0x3e8d78, 0x3e90d0, 0x3e93a8, 0x3e9638) | 5 pointers per descriptor; the pointed-to blocks are 256, 256, 256, 256 B (two descriptors), 256, 256, 128, 128 B, 256, 256, 64, 64 B and 256, 256, 32, 32 B | float (two-float entries: the sub-vector dimension is 2) | stage-1 codebooks of 32 x 2 floats; stage-2 cell codebooks of 32, 16, 8 and 4 x 2 floats | `libquan.c` (0x24ba48 via the descriptors) | **the envelope (amplitude) codebooks** |
| 0x3e9658 | 32 entries (the count word at 0x1d5548), so 256 B at dimension 2 | float | 32 x 2 float | `libquan.c` (0x24b8b0/0x24b990) | the plain VQ of the last two sub-vectors |
| 0x3e7eb0 | <= 360 B | float (`lwc1`, index x 4) | <= 90 floats; a loop bound of 89 is seen | `LDPDA.c`, `PtchCand.c` | **the pitch-candidate grid** (inferred) |
| 0x3ea398 | = 34 B (17 fields) | 16-bit (`lh`) | 17 x 16-bit | `PackSC.c` | the frame's field-width table |
| 0x3e9eb8 | <= 176 B | float, index x 4, loop bound 44 | 44 floats | `libtran.c` | a cosine/twiddle table (`libtran.c` asserts on `TWIDDLE_PERIOD` and `TWIDDLE_TABLE_SIZE`) |
| 0x3ec1c8 | <= 176 B | float, index x 4, loop bound 44 | 44 floats | ~0x253760 (decoder) | the decoder's table of the same shape |
| 0x3eb688, 0x3eb808 | <= 384 B, <= 96 B | float | | `fft4CFG.c` | FFT tables for the two sizes its assert allows, 256 and 64 |
| 0x3eb8a0, 0x3ebc98 | <= 1,016 B, <= 248 B | float | | ~0x252338, ~0x252470 (rFft2G's code) | real-FFT tables |
| 0x3ec458 | <= 1,284 B | float | | `AskToEnvInline.c` | the decoder's envelope reconstruction |
| 0x3eadf0 | <= 448 B | float, index x 4, loop bound 112 | <= 112 floats | `VoicLD.c` | a window or band weighting (**unknown**) |
| 0x3e7c00 | <= 584 B | passed on as a pointer | | ~0x2499a8 (pitch driver) | **unknown** (an analysis window is one reading) |
| 0x3e79a0, 0x3e7aa0, 0x3e7b88, 0x3e81d0, 0x3e8208, 0x3e99e0, 0x3e9ab8, 0x3e9c18, 0x3ea340, 0x3eb030, 0x3ec2b8, 0x3ec2d8, 0x3ec3d8 | 32-256 B bounds each | mostly float | | the units in `P[4]` | small constant sets; **unknown** |

`P[4]` also prints 0x3d6750 (the end marker of the VU0 image, not a table) and 0x3dcffc (a word array read with
`lw` by 0x254510, live under the synthesis, and by the dead 0x254730/0x254a88; its printed bound runs to the next
formed address and is not a length). **The whole SASE read-only block** from `BitPackC.c`'s path string to
`SWSynth.c`'s last assert is **20,940 bytes in demo2 and r0001, 20,124 in r0004** (`P[5]`).

What the shapes are consistent with, for a sinusoidal coder: **amplitude (envelope) codebooks, yes** (the libquan
block, ~5.5 KB between 0x3e82b8 and the `libquan.c` string at 0x3e9858); **a pitch grid, likely** (0x3e7eb0);
**a sine table, no**: no SASE table has the shape of one, the only `sinf` caller is dead, and the synthesis runs
through the FFT (§2.3). The cosine/twiddle tables are FFT tables.

## 5. The three builds

| | demo2 (Aug 18 2003) | r0001 | r0004 |
|---|---|---|---|
| SASE path strings | 25 | 25 | 26 (+ `CalcCost.c`) (`P[1]`) |
| SASE code | at r0001 + 0x258cc0: the same 237 functions, 233 relinked-identical and 4 (0x24ad48 0x24b2f8 0x253c00 0x256a18) differing only in same-opcode (address) words, 0 opcode mismatches (`P[5]`) | 237 functions, 60,208 B | 242 functions, 61,808 B, 0x2484a0-0x257610; 146 of r0001's 237 have a relinked-identical body there (`P[5]`) |
| codec constants (`sase_get_info`) | = r0001 (`P[5]`) | 8000 / 160 / 64 / 3200 | = r0001 (`P[5]`) |
| field-width table | = r0001, at 0x542920 (`P[5]`) | 17 x 16-bit at 0x3ea398 | = r0001, at 0x415958 (`P[5]`; compared in memory, only the equality is printed) |
| read-only block | 20,940 B | 20,940 B | 20,124 B; 287 of r0001's 323 non-zero 64-byte chunks occur verbatim (`P[5]`) |
| VU0 image | verbatim (`P[5]`) | 0x3d5980 | verbatim (`P[5]`) |
| voice wrappers | present: the same constants (0x500 reads, 4 x 0x140 encodes, 20..100 gain clamp) in one jal/j-partition body at 0x394460 that holds both callbacks (`D demo2 0x394460 0x530`); the mode word +0x1078 set to 1 at 0x394e2c (`D demo2 0x394dc0 0x70`) | §2.2 | exact or relinked matches for every wrapper but the receive callback and the init (`match.json`); the ctor still stores 8000 (`D r0004 0x32d880 0xe8`) |
| `rt_lpc10`/`rt_lpc` | **present** | absent | absent |
| `rt_audio version` | 1.08.0003 | 1.08.0009 | 1.08.0012 |

`match.json` is being regenerated by other Sprint 12 work while this is written: as `P[5]` last read it (summary
resolved 12,136 of 14,879), it placed r0001's 237 SASE functions as exact 109, relinked-body 17, hash+callees 15,
seed+delta 2, unresolved 94. The "146 relinked-identical" count above does not depend on it. So r0004 **rebuilt
the codec's internals** (91 of 237 bodies have no identical counterpart) **without changing its external
parameters**; whether an r0001 and an r0004 console would decode each other's frames is **unknown** (same frame
constants and field widths; 36 differing data chunks; retail players are not mixed across revisions in practice).

**LPC-10 in the Aug 18 demo: code, not just the string.** Measured (`P[5]`):
- demo1's `decode_` (the LPC-10 reference decoder's parameter decode) forms four data addresses; **three of those
  32-byte windows occur in demo2, none in r0001 or r0004**, and in demo2 they sit immediately after the
  `rt_lpc10 version: 1.00.0002` string at 0x53b6f8.
- Four demo2 functions form addresses in the 4 KB after that string: 0x4914c0 (2,216 B), 0x491d68 (864 B),
  0x493b38 (2,368 B), 0x4954b0 (3,800 B), inside a cluster 0x48f1d8-0x496388 of 38 partition functions (29,104 B)
  under a dispatcher 0x487918 (called from 0x4888d0 and 0x4889a0, network-library code).
- The shapes: demo2 0x48f1d8 (1,496 B) has **14 distinct callees, as demo1's `analys_`**; demo2 0x493600 has
  **4, as `synths_`** (`P[5]`). demo1's LPC-10 is 39 functions, 40,300 B.
- **None of demo1's 39 LPC-10 function heads matches a demo2 function** (masked 48-byte heads 0/39, against a
  control of 149 of r0001's 221 SASE functions over 48 bytes matched the same way, `P[5]`): demo2's LPC-10 is a
  separate compilation, not SOCOM 1's `libpttclient` object code, so demo1's names cannot be carried onto it by
  body matching.
- It is not the game's voice path: demo2's voice object calls SASE exactly as r0001's does (the row above). The
  LPC-10 module belongs to the network library's audio layer (`rt_lpc10` next to `rt_audio`'s `codec.c`) and
  whether anything selects it at run time is **unknown**. Retail dropped it.

## 6. What Q5 (voice chat under our runtime) needs from this

### 6.1 The path, end to end (r0001)

**Talking.** research/39's talk routes set the voice object's talk flag +0x4a; the tick 0x30ec10 requests the
floor and, on the grant, starts recording (state 3). The tick is not called by the game directly: its only caller
is `voice_net_fill_cb` 0x30f990 (`P[2]`, the `voice_tick` wrapper line), which nothing in the game calls and whose address goes into the
descriptor handed to the network library, so **the network library calls it** (inferred). It first runs the tick, then in state 3 with codec mode 1 (`sw ..0x1078`
has one writer, 0x310080, `P[3]`, storing 1, `D r0001 0x310080 0xa0`):
1. tops up a 0x500-byte buffer at 0x45b880 with lgaud 0x08 Read on the headset handle (+0x38), no more than
   `0x500 - fill` per call;
2. when it holds **0x500 bytes = 640 samples = 80 ms at 8000 Hz**, encodes it as **4 frames of 0x140 bytes**
   through `voice_codec_encode`, writing **8 bytes per frame (§3), 32 bytes in all**, into the message the library
   passed, and records the length at message +0xc;
3. every fifth such pass, reads the level trend and nudges SetRecordGain (§3, VAD row).
(`D r0001 0x30f990 0x2d8`; `P[3]` for the 0x500, the 4 and the clamp.) **Correction:** the Sprint 8 plan's
capture-loop step 2 computes "640 samples at 11025 Hz, 58.05 ms". The 11025 Hz openparam belongs to the two
other `lgAudOpen` (0x243e40) callers, 0x1e7f98 and 0x23a730 (`addiu ..0x2b11` then `jal 0x243e40`:
`D r0001 0x1e7f98 0x200`, `D r0001 0x23a730 0x200`; research/39 puts the first on the tuner path); the voice object opens at 8000 Hz (§3), so the capture tick is
80 ms. `lgaud.cpp` already serves whatever rate the openparam names, so nothing is broken; its comments and
`host_mic.h`'s "ALWAYS resamples ... down to 11025" describe the tuner path only.

**Hearing.** The network library calls **`voice_net_recv_cb` 0x30f7e0** with a message {+0 type, +4 sender, +8
data, +0xc length}. It drops senders muted in the voice object's 24-entry table at +0x10a4; for type 1 it walks
the data **8 bytes at a time**, each through `voice_codec_decode` into 160 samples (0x140 bytes) at 0x45bd90, and
hands each block to 0x30f5f0, which duplicates every sample to L and R and writes it with **lgaud 0x09 Write**
(0x244200), starting playback with 0x06 (0x244ab8) (`D r0001 0x30f7e0 0x1a8`, `D r0001 0x30f5f0 0x1f0`). A
non-1 type is passed through as raw PCM. **The decoded voice never reaches 989snd or the mixer of research/32**:
it goes to the headset's playback half (2 ch, 16-bit, 8000 Hz). Today `PS2IopHostAdapter::micPlaybackWrite`
only dumps it (`ps2_iop_host.cpp:329-332`); making it audible is the Sprint 8 plan's Task 5, still open.

**The network.** The descriptor `voice_net_describe` builds (§2.2) is the whole contract with the network
library: two callbacks and the two formats. What the library puts around the 32-byte payload on the wire
(headers, sequencing, which peer) is the DME library's and is **not measured here**.

### 6.2 Reuse versus reimplementation

**Running the recompiled codec as is is the smaller job, and it is already the state of the tree.** The
evidence: the codec has no stub and no override (§2.4), its only dependencies are memory, the two hooks the game
sets, and bound libc/libm stubs (§2.4); it is reached only from the game's own wrappers (§2.1); the host's part of
the path is lgaud Read and Write, which Sprint 8 built. A player under our runtime therefore produces and consumes
exactly the frames a PS2 does, and interoperates with a console by construction. The one caveat: the encoder's
arithmetic runs on the runtime's `ceilf`/`log10f`/`logf`/`sqrtf`/`expf`/`pow`/`asinf`/`cosf` and soft-double
stubs; research/20 lists `__ieee754_rem_pio2f` (under `cosf`) as not bit-faithful. That can move a quantizer
decision at a boundary, which changes which valid frame is sent, not the frame format (inferred; unmeasured).

A **native reimplementation** would have to match, bit for bit: 8000 Hz, 160-sample frames, the 17-field 64-bit
layout and its widths, the 12-coefficient split-VQ envelope with its prediction and two parameter sets, the pitch
and voicing quantizers, the FFT-based sine-wave synthesis and post-filter, and the tables of the ~21 KB read-only block (§4), which are the
owner's bytes: a native codec could not ship them and would have to read them from the disc image at run time. Of
the 237 functions, 141 carry no unit name. It is only worth doing for a party that is not running the game: a
server-side mixer, a recorder, a bridge to non-PS2 voice. Even then, calling the recompiled functions directly
(`sase_enc_create`/`sase_encode_frame`/`sase_dec_create`/`sase_decode_frame` with the hooks set, §2.2) is smaller
than a rewrite.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Q5, voice chat: hearing the other player | Decoded voice is written by the game to lgaud 0x09 as 2 ch / 16-bit / 8000 Hz, L=R, 160 samples per 8-byte frame; not 989snd (§6.1) | Q5's audible half is the Sprint 8 plan's Task 5 as written (a separate host stream fed from `micPlaybackWrite`, resampled from 8000 Hz); no codec work, no mixer change |
| Q5, capture | The voice object opens the headset at 8000 Hz; the capture tick is 0x500 bytes = 80 ms = 4 frames; the 11025 Hz openparam is the tuner's (§3, §6.1) | Serve 8000 Hz when the voice object asks (lgaud.cpp already honours the openparam). The Sprint 8 plan's "58.05 ms at 11025 Hz" and the 11025 comments in `lgaud.cpp`/`host_mic.h` need a "tuner path only" note (controller's call; not edited here) |
| Q5, the talk trigger | The game sends only while talk state is 3; the encoder's VAD decision is fetched and discarded; the trend drives SetRecordGain (§3) | A host-side VAD cannot make the game talk; the talk button (research/39's unbound action) remains the trigger. Answer lgaud 0x0e SetRecordGain or the game fights its own AGC |
| Q5, the wire | 32 bytes of payload per 80 ms per talker, type 1; the receiver walks 8-byte frames (§6.1) | Size and pace are known for the netcode side; the DME framing around the payload is the next thing to measure, not the codec |
| Q5, interop with consoles | The recompiled codec is the console's codec (no stub or override in 0x2484a0-0x256fd0) (§2.4, §6.2) | No reimplementation is needed for PC-to-PS2 voice. Watch the libm stubs (research/20's `__ieee754_rem_pio2f`) if a quality comparison ever shows a difference |
| Q5, a native codec (only if a non-game party must speak) | Match 8000 Hz / 160 / 64-bit / 17 fields and the §4 tables read from the disc; or call the recompiled API (§2.2) | Scope it as "call the recompiled API from the host" first; a rewrite is the larger job by every measure here |
| Research/44 addendum, symbols README "Voice codec" | 25 SASE units in demo2/r0001 (list in §1.1), r0004 adds only `CalcCost.c`; `EncSC.c` is in all three | Correct the unit list and the "adds EncSC.c" clause (controller-owned files) |
| research/23, Sprint 8 plan, KNOWN voice row, `lgaud.cpp`, `ps2_iop_host.cpp` comments | "Nellymoser" is a reading of the assert token `NellyNull`; no vendor string exists in the images (preamble) | Say "SASE" (or "the voice codec") where a vendor is asserted, or mark it as a reading of an identifier; this note names no vendor |
| Readable names (Sprint 12 Goal 1) | The API and wrapper names of §2.2 are proposals with their evidence, all r0001 addresses | Candidate sidecar rows for the codec entry points and the voice object's wrappers; the unit attribution of 96 functions (§1.2) is a name source for `sub_*`/`FUN_*` rows (`<unit>_<addr>`), provenance "path-string assert site" |
| Q10 (class inventory) / Goal 3 (vtables) | The voice path is plain C: the wrappers and the codec are not reached through vtables (the callbacks are data pointers in a descriptor) | Naming the voice path does not wait on the RTTI route |
| Demo symbols (Task 7 lineage) | demo2's LPC-10 is a different compilation from demo1's `libpttclient` (0/39 heads), in the network library, absent in retail (§5) | demo1's LPC-10 names cannot be carried onto anything in retail; drop them from any voice-naming plan |
| Frostfire / runtime (research/23 §3.4) | The VU0 microcode upload stays dead in all three builds: the mode setter 0x24fac0 has no caller (§2.4) | The VU0-micro alias bug stays latent for this codec; no change |
