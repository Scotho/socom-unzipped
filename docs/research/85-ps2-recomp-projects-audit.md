# 85 — The PS2 recomp projects audit: what the other ports already solved, and under which licence (2026-10-03)

The owner's ask, 2026-10-03: "proceed to do another research audit on every relevant ps2recomp project to our issues
... prioritize the repo but also check at least 20ish ps2 recomp projects", with the same day's rule on taking code,
"where applicable, take other commits that share our license ensuring the creators retain credit" (the closing
section). This note is the record of that audit; it replaces the coordinator's report of the same day. Inputs: seven
researcher notes written 2026-10-03 against our tree at `sprint-17` `e9535f7f` (00 our needs, N1-N40; 01 upstream
ran-j/PS2Recomp since 2026-09-26 and 191 non-default fork branches, read through the GitHub API; 02 the other
recompilation and decompilation projects, about 70 repositories; 03 the emulators PCSX2 `81526d4dc7`/v2.8.2, Play!
`83700b2c31`, DobieStation `68dd073e75` for the renderer, the VUs, the FPU and the EE timing; 04 the audio stack:
Ziemas/989snd and dec989snd, PCSX2 `pcsx2/SPU2/`, OpenGOAL `game/sound/`; 05 the network: Horizon `b1a0d03`,
PSHome-MultiServer `8778e985e4`, clank, medius-cpp, PSRewired; 06 recompiler tooling and PCSX2 automation:
N64Recomp, XenonRecomp, ico-recomp, asm-differ, objdiff, PCSX2 v2.8.2's Qt host). Upstream `main` was `c5a9d025`
(2026-09-30). **No hit was built, run or gated on our tree; every verdict below is a reading.** Nothing here comes
from Harry62's table set, `codes.txt` or research/84: this note is about external projects only. Our needs are
named by the ids of note 00 (N1-N40) beside the issue they belong to; the ids are expanded where they first appear.

Markings: **[verified]** a researcher read the cited line, with its URL, hash or `path:line`; **[claimed]** the other
project's own statement (a PR body, a commit message, a README, a findings file) that nobody built, ran or checked
here; **[inferred]** a researcher's reading of what follows from the verified facts; **[unconfirmed]** an in-tree line
this note could not re-find at `e9535f7f`. Every in-tree `path:line` was re-checked against this worktree on
2026-10-03 and corrected where the report had it wrong (the corrections are named inline). In-tree paths are written
from the repository root; the fork's own layout is `third_party/ps2recomp/<ps2xRecomp|ps2xRuntime|ps2xIOP|ps2xLauncher>/`.
The local clone of Ziemas/989snd that `docs/KNOWN.md` cites lives under the git-ignored `/research/` directory and is not
in the tree, so its lines are cited by repository URL and `file:line`. External repositories are cited by URL, never as
tree paths. "Clean" in a verdict means "the same defect is in our file and the patch is small", not "applied without
conflict". "Gate" means a recomp plus the three-stage parity gate under the loop lock.

## 0. Headline

1. **The most valuable single finding sits in our own mixer, not in another repository: the voice volume register is
   read at half scale.** Every reference (the hardware documentation, PCSX2's SPU2 and OpenGOAL's 989snd port) reads a
   voice VOLL/VOLR register as `reg << 1` in Q15, so 0x3FFF is unity gain. Our
   `third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp` divides the same 0..0x3FFF value by 0x7FFE and so plays
   every bank voice and VAG stream **6.02 dB quieter than the console** -- a one-divisor, testable candidate for more than
   half of #91's 11 dB gap (N1, §1.1). The square law our KNOWN row suspected is right; the register scale is wrong.
   **[verified]** on both sides.
2. **PCSX2 fixed coplanar Z-fighting in January 2026 by flooring the interpolated fragment Z to the integer grid before
   the depth test** (PR #13795, then #13851). That is a three-line GLSL port for #104 (N8) onto our existing
   `GL_DEPTH_COMPONENT32F`, and it corrects our own brief: the GS format rule is saturation to the format maximum, not bit
   truncation (§2.1). **[verified]**
3. **Three independent PS2Recomp porters converged in late September on one VU1 architecture**: a static recompiler
   driven by the interpreter's own timing, flag-liveness elision with the 4-cycle visibility window, and a capture/replay
   bit-exactness check. silentsudin's liveness pass ("skip MAC/status flags nothing can observe") is aimed at exactly
   our 71 % FMAC-plus-flag-packing self time (N16, §3.1). PCSX2's microVU, Play! and ico-recomp use the same rule.
   **[claimed]** the fps numbers; **[verified]** the designs.
4. **Upstream moved one README commit, but its new issues and PRs expose six defects still present in our fork** (§4):
   the VCALLMSR out-of-bounds read (#262/#268), the delay-slot resume of an always-taken branch (#260), the DualShock 2
   pressure byte order (#265), the D_ENABLEW->D_ENABLER mirror (#257), the VIF1 DIRECT image continuation (#269) and,
   most worth a check, **async invocation stacks carved from the top of RAM where the main thread's stack lives
   (#258)**. Our allocator has the same numbers. Three ports hit #258 in one week. **[verified]** our lines.
5. **GTTeancum closed all 25 of his open upstream PRs unmerged on 2026-09-27**, #222 (EIE-gated preemption) and the VU
   performance series among them. Upstream is no longer the channel through which VU performance work arrives; the
   frontier is five game ports on fork branches (§4.3).
6. **#72's five unanswered r0004 messages are already modelled in a GPL-3.0 Horizon derivative**
   (GitHubProUser67/PSHome-MultiServer), with the same `RT.Models` shape as our server copy (N32, §6.1). **[verified]**
7. **PSRewired publishes the r0004 DNAS bypass address `0x3953C0`** and warns that the r0001 address `0x2CC670` reboot-loops
   r0004 -- #112's fact, from an unlicensed repository, so a fact and not code (N36, §6.3). PCSX2 2.8.2's `dpatch=`
   gives the conditional pnach. **[verified]**
8. **The Sprint 18 PCSX2 door needs a seeded ini, not just `-batch`**: v2.8.2 runs the setup wizard whenever
   `SetupWizardIncomplete = true`, re-saves every core section when `SettingsVersion` is missing, and never reads DNS2
   from the ini (§7). **[verified]**
9. **The licence picture is simpler than feared.** Upstream and every fork read declare GPL-3.0; PCSX2 is GPL-3.0+;
   OpenGOAL is ISC; ico-recomp, N64Recomp and XenonRecomp are MIT; Play! is BSD-2. The facts-only sources are Ziemas'
   989snd decomps, ps2sdk (AFL-2.0), PSRewired's repositories, reCOM and a few game ports (§10, Licence baseline).
10. **What nobody solves** is the online layer beyond the lobby (peer UDP across two NATs, #34's freeze, the chat receive
    function) and the hardware truths no emulator has measured (GS Z-interpolation precision, macro-mode CFC2 timing,
    FTOI and FPU tables on a console) (§11).

## 1. Audio: one register reading explains about 6 of #91's 11 dB (N1 #91, N2 #42, N3 #28, N4 #94, N5-N7)

### 1.1 A correct square law and a wrong register scale (N1, #91)

Our KNOWN row suspects the square-law `adjustVolToGroup` (`554972e6`) for the mission bed sitting at -51.2 dBFS against
the console's -35..-41. **Two independent sources say the square is correct.** Ziemas' 989SND.IRX decomp computes
`m_vol = gMasterVol[group] * gGroupDuckMult[group] / 0x10000; new_vol = vol * m_vol / 0x400; return (new_vol * new_vol)
/ 0x7ffe * phase` **[verified]** [Ziemas/989snd](https://github.com/Ziemas/989snd) `iop/vol.c:434-455`; the separate
[Ziemas/dec989snd](https://github.com/Ziemas/dec989snd) has the same arithmetic at `src/vol.c:307-332` **[verified]**.
OpenGOAL's ISC-licensed re-implementation carries the identical chain **[verified]**
[vagvoice.cpp#L46-L91](https://github.com/open-goal/jak-project/blob/master/game/sound/989snd/vagvoice.cpp#L46-L91).
The squared value includes the voice volume itself: a half-volume tone comes out at a quarter amplitude, -12.04 dB.
Reverting to linear would be wrong at every volume below full scale.

The defect is one stage later. The IRX writes `snd_AdjustVolToGroup(...) >> 1` to VOLL/VOLR, so the largest register
value is 0x3FFF **[verified]** Ziemas/989snd `iop/blocksnd.c:1267-1271`, `iop/valloc.c:304-306`. **PCSX2 reads that
register as `Value = SignExtend16(src << 1)` and applies `(volume * data) >> 15`**, so 0x3FFF is 0x7FFE/0x8000, or
-0.0005 dB **[verified]** [ADSR.cpp#L110-L117](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/ADSR.cpp#L110-L117),
[Mixer.cpp#L155-L171](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/Mixer.cpp#L155-L171). OpenGOAL does the
same `m_Sweep.bits << 1` **[verified]**
[envelope.cpp#L132-L137](https://github.com/open-goal/jak-project/blob/master/game/sound/common/envelope.cpp#L132-L137).
The hardware documentation says "Voice volume/2 (-4000h..+3FFFh = Volume -8000h..+7FFEh)" **[verified]**
[psx-spx SPU](https://psx-spx.consoledev.net/ps1/spu/soundprocessingunitspu/). Our mixer instead takes the IRX's `>> 1`
(`applyVoiceVolume`, `third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp:1026-1033`, whose comment at `:1030`
records the belief "full volume is half of full scale") and then divides by 0x7FFE: voices at `:2016`
(`g = env.level / 32767.0 / 0x7FFE`) and streams at `:2101-2107` **[verified]** in this worktree (the report's
"1027-1033" is `:1026-1033`; `adjustVolToGroup` itself is `:1020-1024`, under its comment block `:1013-1019`).

That also explains why the menu PCM path matches the console within +0.47 dB. The PCM ring enters as SPU2 core input,
and **BVOL, EVOL and AVOL are not shifted**: their raw register value 0x7FFF is unity **[verified]**
[spu2sys.cpp#L1254-L1275](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/spu2sys.cpp#L1254-L1275). The trial is
therefore one divisor: change the voice and stream divisor from 0x7FFE to 0x4000 in `snd989_mixer.cpp`, leave the PCM
ring alone, and re-score s32-s47 plus a music window. This worktree's re-check supports "leave the ring alone": the PCM
ring's gain at `snd989_mixer.cpp:2465-2466` takes the `>> 1` ("0..0x7ffe ... then the SPU's >> 1: 0..0x3fff"), is
scaled by group 16 at `:2115`, and the mix loop at `:2153-2154` applies it as `(l * gain) / 0x7fff` -- so the ring plays
0x3fff as half scale, which is BVOL's unshifted semantics, consistent with the +0.47 dB parity score **[verified]**. If
the music then reads loud, the console puts the stream on a group whose master the game sets below unity.

Two more contributors sit beside it. First, **our mixer squares the global master (group 16)**:
`groupModifier = masterVol[g] * masterVol[16] / 0x400` at `snd989_mixer.cpp:1007-1011` goes into the square
**[verified]**. The IRX instead applies group 16 linearly through core 1's MVOL as `0x3FFF * vol / 0x400` **[verified]**
Ziemas/989snd `iop/vol.c:97-128`. At master 0x200 that is -12 dB for us against -6 dB on the console. Second, the missing
reverb return (§1.2). One unresolved conflict needs a look before the trial: the IRX decomp's init sets
`gGroupDuckMult[] = 0x1000` **[verified]** `iop/vol.c:12-79,86-95`, while OpenGOAL's duck default is 0x10000
**[verified]** vagvoice.cpp. Under the shared `/ 0x10000` formula those defaults differ by a factor of 16 in `m_vol`, so
whichever value our mixer feeds deserves a check (§8 item 3). **Licence:** OpenGOAL's `vagvoice.cpp` is ISC (headed
"Copyright: 2021 - 2024, Ziemas"), so the same author's arithmetic arrives under a clean licence; take it from there,
not from the unlicensed IRX decomp. PCSX2 is GPL-3.0+. Both are **takeable with credit**.

A free external check exists too. PCSX2 applies `reg << 1`, so a PCSX2 2.8.2 capture of a mission window scored with our
`audio_parity` should reproduce the console's bed if this reading is right. No public project has published a
methodical PS2 loudness match; PCSX2 issue #6802 only reports games "10 to 20db quieter than hardware" with no method
**[verified]** [pcsx2#6802](https://github.com/PCSX2/pcsx2/issues/6802). On that front our own tooling is ahead of the
field.

### 1.2 Reverb, Gaussian and ADPCM all exist under takeable licences (N5)

For N5 (no reverb, although the game requests type 3 and runs 18 AutoReverb ramps a mission), the complete source is
**PCSX2's `V_Core::DoReverb` plus the 39-tap half-band `ReverbResample.cpp`**, GPL-3.0+ **[verified]**
[Reverb.cpp#L48-L161](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/Reverb.cpp#L48-L161),
[ReverbResample.cpp#L9-L74](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/ReverbResample.cpp#L9-L74).
KillzoneRecomp shows the unit can be built stand-alone: its `ext/kzspu2` compiles PCSX2's `Reverb.cpp`, `Mixer.cpp` and
`ADSR.cpp` unmodified **[verified]**
[kzspu2 README](https://github.com/drakolordx7/KillzoneRecomp/blob/master/ext/kzspu2/README.md). The preset values live
in ps2sdk's `effect.c` under AFL-2.0, which makes the code reference-only, but the register values are hardware data and
can be re-typed as facts **[verified]**
[effect.c#L25-L60](https://github.com/ps2dev/ps2sdk/blob/master/iop/sound/libsd/src/effect.c#L25-L60). One cross-check
pins the mapping: 989snd's type-3 work-area size of 18,496 bytes equals libsd's STUDIO_2 `0x484 x 16`, and type 1's 9,920
equals ROOM's `0x26C x 16`, so 989snd numbers its types the way libsd does **[verified]** arithmetic on Ziemas/989snd
`iop/reverb.c:18` and effect.c. A second GPL-3.0 reference is silentsudin's `628a5993`: SPU2 MMIX routing plus combs and
all-passes in sound RAM at 24 kHz, with an impulse unit test, written against #244's LLE IOP **[claimed]**
[silentsudin 628a5993](https://github.com/silentsudin/PS2Recomp/commit/628a5993). The port needs four pieces: DoReverb,
the STUDIO_2 row, a private 18,496-byte work ring, and the VMIXEL/VMIXER wet-send bits from the `TONE_REVERB` flag
**[verified]** Ziemas/989snd `iop/valloc.c:308-313,346-378`. All of it lands in `snd989_mixer.cpp`. **OpenGOAL
implements no reverb** **[verified]**
[vagvoice.cpp#L23-L26](https://github.com/open-goal/jak-project/blob/master/game/sound/989snd/vagvoice.cpp#L23-L26), and
ico-recomp's reverb is explicitly "NOT a model of the SPU2 reverb DSP" **[verified]**
[reverb.cpp:1-13](https://github.com/nathanialf/ico-recomp/blob/main/src/runtime/snd/reverb.cpp).

Gaussian interpolation is a timbre item, not a level lever: the table is normalised to 255/256, about 0.03 dB. Ours is
linear for voices (`snd989_mixer.cpp:2012-2015`) and streams (`:2095-2096`, `frac` at `:2094`) **[verified]** in this
worktree (the report's "2011-2014, 2096-2099"). Both PCSX2's `interpolate_table.h` and OpenGOAL's `interp_table.inc` (256x4, first row
`0x12C7, 0x59B3, 0x1307, -0x0001`) are takeable; OpenGOAL's ISC notice is the lighter burden **[verified]**
[interp_table.inc](https://github.com/open-goal/jak-project/blob/master/game/sound/common/interp_table.inc),
[Mixer.cpp#L280-L298](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/Mixer.cpp#L280-L298). Index it as
`(frac * 4096) >> 4` over a four-sample window. PCSX2's ADPCM decoder adds +32 rounding, which OpenGOAL omits, a ±1 LSB
difference **[verified]** [Mixer.cpp#L34-L72](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/Mixer.cpp#L34-L72),
[voice.cpp#L33-L45](https://github.com/open-goal/jak-project/blob/master/game/sound/common/voice.cpp#L33-L45).

### 1.3 The streamer has a reference, but only as facts (N3 #28, N4 #94, N6, N7)

Two of the notes disagree, and the disagreement matters for #28 and #94. The audio-stack note (04) found Ziemas/989snd's
`iop/stream.c` with 71 of its 77 functions `UNIMPLEMENTED()` and concluded that "no public decomp of the 989snd VAG
streamer exists" **[verified]** Ziemas/989snd `iop/stream.c`. The decomp survey (02) found a **different repository,
Ziemas/dec989snd**, whose `src/stream.c` is 4,231 lines of C with no remaining `INCLUDE_ASM`, covering
`snd_ProcessVAGStreamTick`, `snd_CheckVAGStreamProgress`, `snd_FixVAGStreamSamplesPlayed`,
`snd_RestartInterleavedStream`, `snd_MakeVAGLoop` and the queue functions **[verified]**
[Ziemas/dec989snd](https://github.com/Ziemas/dec989snd) `config/989snd.yaml`, `src/989snd.c:25-26` with
`g989Version = 0x301`. **This note takes the second finding: dec989snd is the streamer reference we lacked; it
supersedes note 04's "none exists" because note 04 searched one repository and note 02 found the other. It has no
licence, so it is facts only** (§8 item 1). Two of its facts already speak to #28's "stems re-fire from identical sector
offsets": `snd_CheckVAGStreamProgress` reads the voice's `SD_VA_NAX` three times under `CpuSuspendIntr` before deciding
progress, and `snd_FixVAGStreamSamplesPlayed` accounts `bytes_played` across the two SPU half-buffers from `last_loc` and
`PlayingBuffer` **[verified]** `src/stream.c` around 1417-1440 and 1569-1589. `snd_PlayVAGStreamByLoc` lives in 989snd
itself: rac1-decomp, bordplate/RC1 and Lombyte all call it **[verified]** GitHub code search. So SOCOM's streams may be
989snd's built-in streamer rather than a separate 989DSTRM, and whether SOCOM's IOP image is v3.01 with built-in
streaming is an open check against our module list.

The best design analogue under a usable licence is OpenGOAL's Jak 2 OVERLORD `spustreams.cpp` (ISC). Per channel it
keeps a 0x4000-byte SPU ring in two 0x2000-byte halves, loop-flags the half ends, refills by polling NAX, and re-syncs a
stereo pair that drifts more than 4 apart by pausing and repointing **[verified]**
[spustreams.cpp#L123-L199, #L293-L316](https://github.com/open-goal/jak-project/blob/master/game/overlord/jak2/spustreams.cpp).
The researchers' working hypothesis for #28 follows from that design **[inferred]**: on the console the SPU consuming
samples at 48 kHz clocks both the refills and the stream's sense of time played, so a stream cannot drift against its
own audio; ours runs streams on the host clock while the game cues them on a guest clock running about 20 % slow (#59),
and the two would separate by about 12 s a minute. This is a mechanism to test (log each `snd_PlayVAGStreamByLoc`
against both clocks), not a finding. The cheapest new fact is free: SOCOM's own `buffer_size` argument to
`snd_InitVAGStreamingEx` already reaches our HLE at
`third_party/ps2recomp/ps2xIOP/src/modules/snd989.cpp:1546-1561` **[verified]** in this worktree (`initVagStreaming`
reads `args.u32(1)`, page-rounds it and floors it at 0x2000). Logging it gives the console's half size and refill period.
A second independent 989snd HLE exists in maxigasparini/ReInPS `c85423df` (+795 lines, Sly Cooper, GPL-3.0)
**[verified]** file list at [ReInPS c85423df](https://github.com/maxigasparini/ReInPS/commit/c85423df); nobody has opened
it yet, so it is a comparison read for N1, N4 and N6, not a pick. For N7 and N4's EE-side framing, sly1's CC0
`src/P2/989snd.c` shows the double-buffered command batches and `snd_SendIOPCommandNoWait` **[verified]**
[sly1](https://github.com/TheOnlyZac/sly1) `src/P2/989snd.c:17-110`.

### 1.4 #42's holes match an overrun that our counters cannot see (N2)

PCSX2's host stream shows the failure shape of #42: 50 ms holes in the endpoint recording, absent from the mixer dump,
with 0 late and 0 dry callbacks. Without time-stretch, **PCSX2 drops an entire incoming chunk when the device ring is
full ("Buffer overrun, chunk dropped")**, and on under-run it plays silence until the ring refills **[verified]**
[AudioStream.cpp#L341-L354, #L230-L262](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Host/AudioStream.cpp).
Neither event leaves a trace in a render-side dump. Our counters track under-runs only. The takeable design (GPL-3.0+)
is an overrun counter plus a device-fill sample at every write into the raylib/miniaudio buffer, in the mixer's output
path. The researchers infer that a ~50 ms hole fits a typical sub-buffer, not PCSX2's 64-frame chunk **[inferred]**;
raylib 5.5's full-buffer policy has not been read. PCSX2 also runs a DC filter on output ("Some games pause voices with
the volume left on") **[verified]** [spu2.cpp#L515-L537](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/SPU2/spu2.cpp#L515-L537),
and brad-richardson's `au18` branch carries an opt-in DC-blocking high-pass **[claimed]**
[au18](https://github.com/brad-richardson/PS2Recomp/tree/au18).

## 2. Renderer: PCSX2 holds the GL-portable answer for five of seven GS needs (N8 #104, N9 #114, N10 #96, N11 #32, N12-N14, N15 #59)

### 2.1 #104's band is unfloored float Z, and the fix is three lines (N8)

Our GL backend writes `gl_FragDepth = vDepth` into `GL_DEPTH_COMPONENT32F` **[verified]** in this worktree:
`third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp:371,2562,2578`. Play!'s GL renderer has exactly that
shape, with no floor and no format clamp, and so shares the likely defect **[verified]**
[GSH_OpenGL_Shader.cpp#L98-L114](https://github.com/jpd002/Play-/blob/83700b2c31/Source/gs/GSH_OpenGL/GSH_OpenGL_Shader.cpp#L98-L114).
PCSX2 fixed it. **PR #13795 floors the interpolated fragment Z, `floor(input_z * exp2(32.0f)) * exp2(-32.0f)`, before
the depth test and write.** Its rationale: "On the PS2 you only have integer depth available, where in hardware, when we
interpolate, we get a sliding scale of decimal values, which can lead to depth tests failing when they shouldn't". It
fixed Haunting Ground and Rayman 3 **[verified]** [pcsx2#13795](https://github.com/PCSX2/pcsx2/pull/13795),
[tfx_fs.glsl#L1194-L1200](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/bin/resources/shaders/opengl/tfx_fs.glsl#L1194-L1200).
PR #13851 narrowed it to interpolated draws that test or write depth, and requires the floor under ZTST_GREATER even
when Z is read-only **[verified]** [pcsx2#13851](https://github.com/PCSX2/pcsx2/pull/13851). The vertex side clamps
`min(i_z, MaxDepth)` with `max_z = 0xFFFFFFFF >> (fmt * 8)` and maps to `float(z) * 2^-32`; the source comment reads "On
the real GS we appear to do clamping on the max z value the format allows. Clamping is done after rasterization"
**[verified]**
[GSRendererHW.cpp#L5628-L5680](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/GS/Renderers/HW/GSRendererHW.cpp#L5628-L5680),
[tfx_vgs.glsl#L78-L92](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/bin/resources/shaders/opengl/tfx_vgs.glsl#L78-L92).

That corrects our brief in one respect: the format rule is **saturation to the format maximum, not bit truncation**,
and DobieStation agrees, doing `z = min(z, 0xFFFFFFU)` for 24-bit formats **[verified]**
[gsthread.cpp#L1501-L1560](https://github.com/PSI-Rockin/DobieStation/blob/68dd073e75/src/core/gsthread.cpp#L1501-L1560).
Under the 2^-32 scale, Z16 and Z24 are exact in float32, so our storage format is fine and the floor is what is missing.
ico-recomp's clean-room GS spec independently writes down both of our suspects: Z "interpolated with a 32.32 fixed-point
DDA" from the clipped bounding-box origin, and "compared and stored at the width of the ZBUF format" **[verified]**
[GS_RENDERER.md](https://github.com/nathanialf/ico-recomp/blob/main/docs/GS_RENDERER.md) around lines 296-303. That
renderer is unverified against its own game, so it is a specification, not proof. One cost on our target: GL 3.3 has no
conservative depth (`layout(depth_less)` needs GL 4.2 or ARB_conservative_depth), so writing `gl_FragDepth` loses early-Z.
The port lands in `gs_gl_backend.cpp`'s depth shader and draw setup. Our retraction history matters here: the Seeding
Chaos shards were VU1 chunk truncation, not depth quantisation (`docs/KNOWN.md` §3), so the floor answers Frostfire's
band, not the water. SOCOM's PCSX2 GameDB entry carries no GS hardware fixes, only `VIF1StallHack` and `InstantDMAHack`
**[verified]**
[GameIndex.yaml#L11770-L11776](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/bin/resources/GameIndex.yaml#L11770-L11776).
**Licence: GPL-3.0+, takeable with credit.**

### 2.2 Read-backs, uploads and the stall each map to one PCSX2 structure (N10 #96, N11 #32, N9 #114)

For #96 (one `gpuRows` window shared by the shadow and the guest read-back; **[verified]** in this worktree at
`gs_gl_backend.cpp:2448,3053-3057,3296-3297,3353-3354`), PCSX2's texture cache keeps **per-target state:
`m_drawn_since_read`, a rect grown by draws and cleared only by a covering read, and `readbacks_since_draw`**.
`InvalidateLocalMem` skips a read whose rect is already covered and zeroes the rect once it is read **[verified]**
[GSTextureCache.cpp#L4948-L5085](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/GS/Renderers/HW/GSTextureCache.cpp#L4948-L5085).
The GL download is a persistent-mapped PBO with a `glFenceSync` **[verified]**
[GSTextureOGL.cpp#L394-L506](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/GS/Renderers/OpenGL/GSTextureOGL.cpp#L394-L406).
Applied to us, the shadow and the guest read-back each get their own rect.

For #32 (7-11k 16x16 tiles a second, with the CPU swizzle at 42 of 59 ms/s), PCSX2 has two mechanisms that beat our
identical-bytes skip, which still swizzles first. `Source::Update` keeps a per-block `m_valid` bitmap, swizzles only
blocks not yet valid, and uploads them in one `Flush`; sources are indexed per GS page, so a write invalidates only the
touched pages **[verified]**
[GSTextureCache.cpp#L7614-L7700, #L8335-L8346](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/GS/Renderers/HW/GSTextureCache.cpp#L7614-L7700).
On top sits an xxHash content cache keyed on TEX0+TEXA+CLUT hash+LOD that reuses a GPU texture with no swizzle at all
**[verified]**
[GSTextureCache.cpp#L7029-L7080](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/GS/Renderers/HW/GSTextureCache.cpp#L7029-L7080).
LightVelox's `sotc-port` has batched CLUT loads and a persistent upload ring, but in an OpenGL 4.6 compute GS that is
above our GL 3.3 target **[claimed]** [LightVelox 6bb975af](https://github.com/LightVelox/PS2Recomp/commit/6bb975af).

For #114 ("stall bound engaged", never released; the messages are at `gs_gl_backend.cpp:739,907,1010` **[verified]**),
our stall code was not read in this pass. PCSX2's MTGS is a **lost-wakeup-safe bounded queue**: an atomic frame count
capped at `VsyncQueueSize` (default 2), a listener flag set before the wait and consumed with `exchange(false)` before
each post, and -- the decisive part -- an extra post whenever the GS thread finds the ring empty, which the source calls
a "Safety valve in case standard signals fail for some reason -- this ensures the EEcore won't sleep the eternity"
**[verified]** [MTGS.cpp#L239-L281, #L585-L599](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/MTGS.cpp#L239-L281).
"Never released" fits a missing wake on the empty path **[inferred]**. ico-recomp's threaded ring adds two invariants
worth auditing: packet bytes are "always copied into the ring, never referenced", and calls that need a value back carry
a sequence number, the producer waiting for `m_reply_seq` to reach its own **[verified]**
[gs_threaded.cpp](https://github.com/nathanialf/ico-recomp/blob/main/src/runtime/gs/gs_threaded.cpp). The audit targets
are `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_stall_coalescer.cpp`, `gs_frame_backpressure.cpp` beside it, and
the stall logic in `gs_gl_backend.cpp`.

### 2.3 Mip chains, deinterlace, the present hold and a menu-frame dump (N12, N13, N14)

For N12 (mipmaps; `docs/LATER.md` row 54), `GSState::GetTex0Layer` builds per-level TEX0s from MIPTBP1/2, and the LOD
block computes `k = (TEX1.K + 8) >> 4`, `mxl = min(MXL, 6)` and constant LOD under LCM=1 **[verified]**
[GSState.cpp#L6796-L6830](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/GS/GSState.cpp#L6796-L6830),
[GSRendererHW.cpp#L3366-L3441](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/GS/Renderers/HW/GSRendererHW.cpp#L3366-L3441).
Uploading each level as a GL mip with `GL_TEXTURE_MAX_LEVEL = mxl` fits GL 3.3. For N13 (rows 53 and 55), blend
deinterlace is `interlace.glsl ps_main2`, about ten lines **[verified]**
[interlace.glsl#L20-L160](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/bin/resources/shaders/opengl/interlace.glsl#L20-L160).
The locked-30 present hold has no emulator reference, because PCSX2 presents on every guest VSync. KillzoneRecomp
measured a related pathology: PCSX2's `Merge`, under a two-read-circuit flicker filter (PMODE=0x8063, circuit 2 one line
lower), blended two frames intermittently, and forcing circuit 2 equal to circuit 1 took bad frames from 20 of 72 to 0 of
72 **[claimed]** [findings.md](https://github.com/drakolordx7/KillzoneRecomp/blob/master/docs/findings.md). For N14 (a
menu-frame GS dump, #41), brad-richardson/ps2xGS offers a `.gscap` capture, replay-and-diff against a CPU backend, and a
feature census, GPL-3.0-or-later **[verified]** [ps2xGS](https://github.com/brad-richardson/ps2xGS); ico-recomp's dump
corpus includes a mip-LOD test triangle. All PCSX2 GS files cited carry `GPL-3.0+`: **takeable with credit**.

### 2.4 #59's frame rate looks like Killzone's staircase (N15)

KillzoneRecomp's measurements describe our SYNCV ~24 fps structure precisely. "Frame time is a staircase. The finished
frame list is kicked at a vblank, so a frame whose EE work ends at 14 ms starts its successor at the next vblank". The EE
spends "10-25 % ... asleep in `EeScheduler::processDueDeadlines`", and "The game kicks the next frame list only when D1
is idle ... a worker that needs more than one vblank period ... gives 2-vblank frames whatever the EE does" **[claimed]**
[findings.md](https://github.com/drakolordx7/KillzoneRecomp/blob/master/docs/findings.md) "EE thread frame budget". The
implied check for us: does SOCOM's next-list kick also wait on the VIF1/VU1 path, so that VU1 cost converts directly
into lost VBlanks? LightVelox's `16deb2a8` adds a matching VU1 timing model, where a D1_CHCR read charges the VU1 cycles
executed since the VIF1 DMA began **[claimed]** [LightVelox 16deb2a8](https://github.com/LightVelox/PS2Recomp/commit/16deb2a8).
Killzone also traced its ~1 M scheduler dispatches a second to tail jumps between `entry_*` fragments and returns after
non-local unwinds, and removed guest control flow from the scheduler in its patch 0023 **[claimed]** same findings.md.
That is a PS2Recomp-wide overhead worth profiling in `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/EeScheduler.cpp`.

## 3. VU1, VU0, FPU and the scheduler: the emulators agree, and three porters converged (N16, N18 #47, N19-N21)

### 3.1 Flag elision is the answer to the 71 %, with three takeable designs (N16)

Our generated VU1 program spends 152 ms/s of self time, 71 % of it in the inlined FMAC op plus MAC/STATUS flag packing,
and four programs stay on the interpreter (research/81). **Every serious implementation computes flags only where a
reader can see them.** PCSX2's microVU models MAC, STATUS and CLIP as four timestamped instances, each readable at
`cycles + 4`; a backward pass keeps only the last four or so producers before a reader or block exit, and `_mVUflagPass`
scans the next block's first four instructions for FSxxx, FMxxx and FCxxx reads **[verified]**
[microVU_Flags.inl#L63-L250](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/x86/microVU_Flags.inl#L63-L75),
[microVU_Analyze.inl#L166-L205](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/x86/microVU_Analyze.inl#L166-L205).
ico-recomp does the same at generation time: "A lower-slot fmand/fsand at bundle i sees the flags committed at bundle
i-4, so the snapshot is taken entering bundle i-3", and outside a read window no flag is materialised **[verified]**
[analyze.rs](https://github.com/nathanialf/ico-recomp/blob/main/tools/recomp/crates/vu-emit/src/analyze.rs),
[emit.rs](https://github.com/nathanialf/ico-recomp/blob/main/tools/recomp/crates/vu-emit/src/emit.rs) around 200-212
and 421-448 (a stale header comment at analyze.rs:24-28 predates the snapshot code). silentsudin's `e56ad7dc` applies
the same rule inside a PS2Recomp-family VU1 recompiler: "skip MAC/status flags nothing can observe (latency-aware
liveness)". **In Road Trip only 5 of 955 pairs keep exact flags, native replay went 3.0 -> 2.3 us/run, and the race went
from ~20-30 to ~35-58 fps** **[claimed]** [silentsudin e56ad7dc](https://github.com/silentsudin/PS2Recomp/commit/e56ad7dc).
Play!'s `QueueInFlagPipeline`/`CheckFlagPipeline` with `LATENCY_MAC = 4` is the simplest model of the ring, under BSD-2
with the notice kept **[verified]**
[VUShared.cpp#L1855-L1930](https://github.com/jpd002/Play-/blob/83700b2c31/Source/ee/VUShared.cpp#L1855-L1930).

Our tier-2 emitter knows the whole 16 KB image at generation time, so the analysis fits it directly. It lands in the
generator that produces `third_party/ps2recomp/ps2xRuntime/src/lib/vu/generated/vu1_d418194495c25213.cpp`. None of
these patches applies to our emitter; each is an analysis to port. One condition comes with it: `vu1_replay` must
tolerate inexact flags where the module declares them dead, as silentsudin's replay does. Two more ideas bear on
coverage. Sinan-Karakaya's `ef8eca6c` records JR/JALR landing targets during a profiling pass, so one pass compiles the
whole chain; DQ8 went from "97% of VU1 work, about 6 FPS" interpreted to "30 FPS with all of VU1 compiled" **[claimed]**
[Sinan ef8eca6c](https://github.com/Sinan-Karakaya/PS2Recomp/commit/ef8eca6c). That may be why four of our programs stay
interpreted, if our coverage depends on a recording **[inferred]**. Separately, microVU keys programs on start PC and
validates only the ranges actually compiled (`mVUcmpProg`), where our FNV-1a over the whole code memory rejects a
program whenever any unrelated word changes **[verified]**
[microVU.cpp#L215-L299](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/x86/microVU.cpp#L215-L299). Range
validation could raise generated-path coverage **[inferred]**; nobody has measured it. One trap is on record: Sinan's
SSE2 fast path fuses product sums only where the interpreter's `acc + fs*ft` does, because FMA contraction breaks
bit-exactness **[claimed]** [Sinan e10dc7fc](https://github.com/Sinan-Karakaya/PS2Recomp/commit/e10dc7fc). The heavier
alternative is KillzoneRecomp's route of linking PCSX2's microVU unmodified as a library; its stated motive matches ours,
PS2Recomp's interpreter at "about 70% of game-thread time" **[verified]**
[kzvu README](https://github.com/drakolordx7/KillzoneRecomp/blob/master/ext/kzvu/README.md). Their build is MSVC-only
and ours is llvm-mingw. On the interpreter tier, smmathews #200 gives both halves of a VU1 pair the pre-pair VF and Q
**[claimed]** [PR #200](https://github.com/ran-j/PS2Recomp/pull/200), not checked in ours, and ico-recomp's audit lists
the same rule plus a non-interlocked Q (7 cycles for div and sqrt, 13 for rsqrt).

### 3.2 VU0 macro flags: both emulators say no latency model is needed (N18, #47)

For #47, **neither PCSX2 nor Play! models flag latency in macro mode**. PCSX2's COP2 recompiler uses a single flag
instance, and its `COP2FlagHackPass` only elides flag computation that no CFC2, VCALLMS, FBRST write or VU0-kicking store
consumes **[verified]**
[microVU_Macro.inl#L36-L100](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/x86/microVU_Macro.inl#L36-L100),
[iR5900Analysis.cpp#L60-L200](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/x86/iR5900Analysis.cpp#L60-L200).
PR #5571 reports 3-10 % gains from that pass **[verified]** [pcsx2#5571](https://github.com/PCSX2/pcsx2/pull/5571).
Play!'s CFC2 flushes the whole pipeline before reading **[verified]**
[COP_VU.cpp#L170-L195](https://github.com/jpd002/Play-/blob/83700b2c31/Source/ee/COP_VU.cpp#L170-L195). The evidence
therefore supports closing #47 as "matches the reference emulators". `COP2FlagHackPass`'s rule set is the takeable
piece, because it lets our recompiled VU0 code skip flag packing where no CFC2 follows. One caution pulls the other way:
KillzoneRecomp found PS2Recomp's interpreter and microVU0 disagreeing in micro mode on program 0xD18, where "`FMAND vi1,
vi3` sees a different MAC flag and the program branches the other way" **[claimed]**
[findings.md](https://github.com/drakolordx7/KillzoneRecomp/blob/master/docs/findings.md) "VU0 micro mode". That is
micro mode, not macro mode, but it is a public instance of flag timing changing a branch.

### 3.3 FTOI, FPU and EIE have consistent rules across three emulators (N19, N20, N21)

For N19, **PCSX2, DobieStation and microVU all saturate by sign for |x| >= 2^31, exponent-255 patterns included**.
PCSX2's `floatToInt` returns 0x80000000 for negatives and 0x7fffffff for positives when
`(bits & 0x7f800000) >= 0x4f000000` **[verified]**
[VUops.cpp#L876-L888](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/VUops.cpp#L876-L888). Dobie maps exponent 255
to ±FLT_MAX before converting **[verified]**
[vu.cpp#L822-L829, #L1151-L1164](https://github.com/PSI-Rockin/DobieStation/blob/68dd073e75/src/core/ee/vu.cpp#L822-L829).
Our rule, from Cucumber, sends NaN to INT_MIN (`docs/KNOWN.md` §2 FTOI row). That is raw x86 `cvttps2dq` behaviour, and
it is wrong for positive exponent-255 inputs. PCSX2 PR #12701 contains a PS2-side program that runs `vftoi0` and
`cvt.w.s` over all 2^32 inputs **[verified]** [pcsx2#12701](https://github.com/PCSX2/pcsx2/pull/12701); it is a ready
hardware oracle if the owner ever runs it on a console, but the PR does not say it was run on hardware **[claimed]** by
implication.

For N20, the fork note found the FPU half already ours: `FPU_ADD_S/SUB_S/MUL_S` saturate, `FPU_DIV_S` gives ±max, and
`FPU_RSQRT_S` is fs/sqrt(|ft|) **[verified]** in this worktree,
`third_party/ps2recomp/ps2xRuntime/include/ps2_runtime_macros.h:878-888`. Upstream PR #272 adds the same rules plus a
per-lane clamp of the VU0 macro `PS2_VADD/VSUB/VMUL` and eight spec-derived tests **[claimed]**
[PR #272](https://github.com/ran-j/PS2Recomp/pull/272); whether our VU0 lanes clamp is unchecked. The comparisons are a
real residual: our `FPU_C_EQ_S/LT_S/LE_S` compare saturated values **[verified]** `ps2_runtime_macros.h:917-929`, so two
different exponent-255 values compare equal, while LightVelox's `c419f26b` fixes EE FPU compares for "extended finite"
values **[claimed]** [LightVelox c419f26b](https://github.com/LightVelox/PS2Recomp/commit/c419f26b). ico-recomp lists the
same point as a registered uncertainty **[verified]**
[recomp_ops.h](https://github.com/nathanialf/ico-recomp/blob/main/include/recomp_ops.h). KillzoneRecomp shows the
failure mode that clamping prevents: 0x7FC00000 x86 NaNs in guest VU0 inputs from level load onward **[claimed]**
findings.md. silentsudin's `164f5eca` also sets D/I flags in FCR31, worth a check against ours **[claimed]**
[silentsudin 164f5eca](https://github.com/silentsudin/PS2Recomp/commit/164f5eca). Bit-exact rounding would need PCSX2's
soft-float PR #12001, open and unmerged since 2024 **[verified]** [pcsx2#12001](https://github.com/PCSX2/pcsx2/pull/12001).

For N21 (`Status.EIE` written by DI/EI and read by nothing), the rule is word-for-word identical in PCSX2 and ps2tek: an
interrupt is taken only when `IE && EIE && !EXL && !ERL` and the IM bit is set **[verified]**
[R5900.cpp#L352-L374](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/R5900.cpp#L352-L374),
[ps2tek](https://psi-rockin.github.io/ps2tek/) "COP0". DI takes effect one instruction late, a change that fixed booting
in Jak X, Namco 50th, SpongeBob and The Incredibles; EI ends the block, and EI, MTC0 to Status and INTC/DMAC mask writes
each schedule a pending-IRQ check 4 cycles out **[verified]**
[iCOP0.cpp#L90-L123](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/x86/iCOP0.cpp#L90-L123),
[COP0.cpp#L666-L686](https://github.com/PCSX2/pcsx2/blob/81526d4dc7/pcsx2/COP0.cpp#L666-L686). **ico-recomp shows that the
scope matters as well as the gate: EIE is per thread.** "The runtime used to keep one global flag, so a thread that
blocked with interrupts disabled held them off for the whole machine and the boot idled after the first read. The flag
is now saved and restored per thread" **[verified]**
[TARGET.md](https://github.com/nathanialf/ico-recomp/blob/main/docs/TARGET.md) "Interrupt enable is per thread".
GTTeancum's #222, which deferred preemption while interrupts were disabled, was **closed unmerged on 2026-09-27**
together with 24 of his other PRs, so that idea now exists only on his branch **[verified]**
[PR #222](https://github.com/ran-j/PS2Recomp/pull/222). The change lands in
`third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/EeScheduler.cpp` and the DI/EI hooks. It needs a gate, because no
console timing oracle exists. smmathews #151's level-triggered INTC pending latch is a nearby design, not yet checked
against ours **[claimed]** [PR #151](https://github.com/ran-j/PS2Recomp/pull/151). dmc-recomp's report of queued
invocations "drained in FIFO order into a per-thread stack that executes LIFO, silently reversing every batch" earns a
one-line audit of `EeScheduler::queueInvocation` (`EeScheduler.cpp:1302` **[verified]**) **[claimed]**
[dmc-recomp](https://github.com/Gui-Tora/dmc-recomp).

## 4. Upstream and its forks: six live defects, one convergence, one closure

### 4.1 Upstream state and what is already ours

Upstream `main` moved once since our last read (research/67, 2026-09-26), to `c5a9d025` on 2026-09-30, a README-only
change (#256, "Document .recomp.json") **[verified]** [c5a9d025](https://github.com/ran-j/PS2Recomp/commit/c5a9d025);
licence GPL-3.0, 142 forks, 88 open issues and PRs. `feature/performance-patch-1` is still `e27a658b` and its verdict is
still owed (`docs/LATER.md` row 32); `feature/iop-emulator` is still `39251a05`. The new material is ten open PRs and
nine issues from three outside porters (drakolordx7, Killzone; penpenlovesrei-dotcom, Ridge Racer V; llesieur99, Ratchet
& Clank), and **most of it is already in our fork**. Already ours **[verified]** in this worktree: #274 (syscalls
0x79/0x7A to `sceSifSetReg`/`sceSifGetReg`,
`third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Syscalls/Dispatcher.cpp:295-299`); #270's unwind tracking in another
form (`dispatchUnwinding()` checked before the `pc == entryPc` heuristic,
`third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp:1550-1562`, commit `ec4b9fbc3`, citing SOCOM `FUN_00315a80`);
#261 (`-msse4.1`, `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt:436-439`, note 01's reading); #272's FPU half (§3.3);
and smmathews #187, #189, #190, #193 and #198. N/A to the product: #266 and #267 (they target #244's LLE IOP, which we do
not have; #266 is a semantics note for the out-of-tree oracle), #263 (`/Qspectre-` under clang-cl; we build with
llvm-mingw). #255/#256 (`.recomp.json` for the recomp.fyi board) bear on none of our needs. No upstream activity since
2026-09-26 on VU0 flag latency, the EIE bit, jump tables or LoadExecPS2 **[verified]** the full `issues?since=` list.

**GTTeancum's mass close changes earlier verdicts.** On 2026-09-27 12:20Z he closed, without merging, #217, #218, #219,
#222, #223, #224, #225, #226, #227, #228, #229, #230, #231, #232, #237, #242, #243, #245, #246, #247, #248, #249, #250,
#251 and #252, with no comment **[verified]** `pulls/222`, `pulls/252`, `issues/222/events`. Our applied picks (#223,
#224, #227, #229-#232, #237, #243, #246, the LWU hunk of #221; research/42, OPEN-PRS) stay ours. #222 (N21), #219
(VCLIP), #217 and #242, all LATER in research/63, and the VU performance series #245, #247-#252 (N16) can now only come
from his `codex/xmen-legends-bringup` branch, readable as design (GPL-3.0). #206 is still open and untouched (§5.1).

### 4.2 Six real defects remain in our tree, all GPL-3.0 and takeable with credit

The highest-value item is a check, not a patch. **Issue #258: the first async invocation stack returns `0x01FFFFF0`,
where the main thread's stack is (`sp=0x1fffff0` in Ridge Racer V), so each interrupt handler overwrote the interrupted
frame's `$ra`.** RRV's loop count went from 0 to 2552 once the region was derived from declared thread stacks
**[claimed]** [issue #258](https://github.com/ran-j/PS2Recomp/issues/258). MunchkinClubber hit the same thing in SSX 3
and moved handler stacks to `0x80000-0x100000` when the ELF loads at or above `0x100000` **[claimed]**
[c97cfaa7](https://github.com/MunchkinClubber/PS2Recomp/commit/c97cfaa7). noahbaxter's `0ed32b59`/`16b29b09` place the
main stack and runtime arena "where the kernel does" **[claimed]** compare listing. **Our allocator has the same
numbers** **[verified]** in this worktree: `m_asyncCallbackStackFloor = 0x01F00000u`, `m_asyncCallbackStackTop =
PS2_RAM_SIZE` (`third_party/ps2recomp/ps2xRuntime/include/ps2_runtime.h:571-572`), reset to the top at
`ps2_runtime.cpp:2013-2016`, returning `top - 0x10u` at `:2239`, 16 KB (`kInvocationStackSize = 0x4000u`) per
invocation at `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/EeScheduler.cpp:1374`; research/63 records that in our
layout "the pool sits above the heap cap (`0x01F00000`) and below the main stack". Three ports in one week raise the
prior. A clobbered `$ra` would read as a random freeze or crash, which is why it bears on #34 if a clobbered frame is
ever found **[inferred]**; our records hold no symptom for it. The check is read-only: SOCOM's `sp` at the first
schedule against the first invocation stack's address. The fix needs porting (a policy choice: derive the region from
thread stacks, or the kernel range); issue #259 (a `GuestThread::stack` that holds a base after CreateThread and a top
after SetupThread **[claimed]** [issue #259](https://github.com/ran-j/PS2Recomp/issues/259)) is a prerequisite and is
unchecked in ours.

Four small ports make one batch. **#268** (fixes issue #262: VCALLMSR reads `ctx->vi[27]` on a `uint16_t vi[16]`, an
out-of-bounds read; the reporter's own correction says the root cause is a VI file sized 16 where hardware has 32).
Ours is identical **[verified]** in this worktree:
`third_party/ps2recomp/ps2xRecomp/src/lib/vu_translation_helpers.cpp:168-181` formats `ctx->vi[{}]` from `inst.rd`, and
`vi` is `uint16_t vi[16]` at `ps2_runtime.h:83`. Take it even if dormant, because it is undefined behaviour
([PR #268](https://github.com/ran-j/PS2Recomp/pull/268)). **#260** (resuming in the delay slot of an always-taken branch
-- `b`, `beq $0,$0`, `bgez $0` -- falls through instead of continuing at the target; RRV: 5 of 343 sampled unconditional
`b` carry a resume entry in the delay slot). Our `emitResumeFromDelaySlotEntry()` always goes to `fallthroughPc()`
**[verified]** `third_party/ps2recomp/ps2xRecomp/src/lib/control_flow_emitter.cpp:152-172`
([issue #260](https://github.com/ran-j/PS2Recomp/issues/260)). **#265** (DualShock 2 pressure bytes 16-19 are L1, R1,
L2, R2). Ours writes L1, L2, R1, R2 **[verified]** `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/Pad.cpp:265-268`
(corrected from the report's "266-269"; `data[16]`..`data[19]`) ([PR #265](https://github.com/ran-j/PS2Recomp/pull/265)).
**#257** (D_ENABLEW `0x1000F590` must mirror into D_ENABLER `0x1000F520`, as PCSX2's `dmacWrite32` does; the game spins
forever otherwise). We have no mirror **[verified]** by grep of `third_party/ps2recomp/ps2xRuntime/src` and `include`
for `F590`/`F520`/`D_ENABLER` ([issue #257](https://github.com/ran-j/PS2Recomp/issues/257)). #268 and #260 change
generated C++ and need a recomp plus the three-stage gate; #265 and #257 are runtime-only. Whether SOCOM II emits
`vcallmsr`, polls D_ENABLER or reads pressure bytes is a one-grep check each over the generated output.

Several more need porting rather than picking. **#269** keeps decoding VIFcodes between a DIRECT tag and its pixel data
and re-wraps only the DIRECT payload while an image is pending, checked "byte for byte against real PCSX2's EE RAM
(through a PINE savestate)" **[claimed]** [PR #269](https://github.com/ran-j/PS2Recomp/pull/269). Ours drains a pending
PATH2 image as raw qwords at the top of the loop **[verified]**
`third_party/ps2recomp/ps2xRuntime/src/lib/ps2_vif1_interpreter.cpp:342-366` (`m_vif1PendingPath2ImageQwc`, set at `:597`),
with no SOCOM symptom known; smmathews #190 moves the continuation the same way. **#271** and MunchkinClubber's
`cc9a3ec5` register resume points for standalone `entry_*` functions, skipping only those inside a real function. Ours
skips all of them **[verified]** `third_party/ps2recomp/ps2xRecomp/src/lib/ps2_recompiler.cpp:1828-1831`
(`isEntryFunctionName` -> `continue` in `discoverAdditionalEntryPoints()`). MunchkinClubber's "deterministic resume slot
owners" is the read for #60 (N26) ([PR #271](https://github.com/ran-j/PS2Recomp/pull/271)). **smmathews #201** discards
VU0-macro writes that name vf0, where we have one `rd == 0` guard **[verified]**
`third_party/ps2recomp/ps2xRecomp/src/lib/vu_translator.cpp:103` ([PR #201](https://github.com/ran-j/PS2Recomp/pull/201)).
LightVelox's **`c4c20e80`** covers a recursive tail jump that leaves pc == entry without an unwind, which our
`dispatchUnwinding()` check does not catch -- an inference-level residual **[inferred]**
([c4c20e80](https://github.com/LightVelox/PS2Recomp/commit/c4c20e80)). Issue #264 (an override registered in the static
library silently discarded by the linker) is a hazard we already avoid by compiling `game_overrides_socom2.cpp` into
`ps2EntryRunner` **[verified]** `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt:450`. Issue #273 (`GSCpuBackend::SampleTexture`
casts unbounded or NaN S,T to int) cites aap/libgpu2 as a GS reference "verified against ... real PS2 hardware" for the
saturating texture-coordinate path; our CPU rasteriser is the GL backend's oracle, so it bears on N8/N12 oracle fidelity,
and aap/libgpu2's licence was not checked.

### 4.3 The branch scan: five late-September game ports carry the new runtime work

The branch scan was new ground: 191 non-default branches across 140 forks, 188 of them ahead of `ran-j:main`, with
Sorachi00/PS2Recomp-Drakengard excluded entirely because its README forbids AI-agent use (nothing from it was read;
its branches were left out). The genuinely new runtime work sits in five late-September game ports: silentsudin
`roadtrip`, LightVelox `sotc-port`, Sinan-Karakaya's #254 follow-ups (head now `40cb3e1c`, 73 commits, still draft),
noahbaxter `ghrecomp` and brad-richardson `ssx3`/`au18`. silentsudin's `roadtrip` also carries test-harness ideas near
#42: deterministic virtual time, per-vblank state hashes, a lockstep control socket, and an `audio` command returning
rms, peak and an exact hash **[claimed]** compare listing, [roadtrip](https://github.com/silentsudin/PS2Recomp/tree/roadtrip).
`au18` vendors "ARMSX2-derived" microVU sources whose licence was **not verified**, and is too large (the 300-file compare
cap) to cherry-pick. MunchkinClubber `ssx3-fixes` (148 ahead) holds `c97cfaa7` (#258 family), `cc9a3ec5` (#271 family)
and `f7f35bc6` (`find_code_pointers.py`, §5.1). maxigasparini/ReInPS `feature/vu1-audit` holds the second snd989 HLE
(§1.3), `address_taken_code.cpp` (§5.1) and VIF1 unpack tests. GTTeancum's `codex/xmen-legends-bringup` was not re-read.

## 5. Recompiler map, jump tables and the matcher: MIT tools already do it (N22 #55, N23 #54, N24 #52, N25 #58, N26 #60, N28)

### 5.1 #55 has a shipped policy, and #206 as written is risky

For #55 (6,640 of 14,657 functions overrun their csv row, 1,112 swallow another, 6,750 are `sub_`), upstream PR #206
(Sinan-Karakaya, `fix/function-map-authority`, opened 2026-08-17) is still open and untouched. It drops every auto-named
carving once the map has parsed, because `IsAutoGeneratedName` matches both `sub_` carvings and Ghidra's `FUN_` names,
so a carving that shares a start with a map row survives the purge and wins the "larger end" tie-break; on an 11,491-row
Metrowerks map 5,613 functions (48.8 %) had inflated bounds and output shrank from 235 MB to 180 MB **[claimed]**
[PR #206](https://github.com/ran-j/PS2Recomp/pull/206). **As written it would also drop JAL-scan `sub_` carvings that
have no map row**, and those would then fail as missing branch targets **[inferred]**, not tested. **N64Recomp's shipped
rule is the safer form: the symbol map is the authority for bounds.** A JAL target inside a symbol becomes a separate
`static_<sec>_<addr>` function that ends at the next known start, and the parent is never shortened; the code is emitted
twice, and the pass runs to a fixed point **[verified]**
[recompilation.cpp:24-75](https://github.com/N64Recomp/N64Recomp/blob/main/src/recompilation.cpp),
[main.cpp:803-870](https://github.com/N64Recomp/N64Recomp/blob/main/src/main.cpp); MIT. Under that model, #54's 1,090
nested forced-entry rows stop being a defect class and become ordinary statics. The open question is our resume-entry
model, which N64Recomp does not have. hedgeg0d's narrower #236 (clamp a same-start carving to the map row's end) was
closed unmerged 2026-08-29, but its branch `fix/ghidra-map-boundaries` survives **[verified]** `pulls/236`. Two tools
cover the opposite half, code the map misses: MunchkinClubber's `find_code_pointers.py` (scans data sections and
`lui/addiu` pairs for code addresses missing from the CSV and emits an `entry_points` block) **[claimed]**
[f7f35bc6](https://github.com/MunchkinClubber/PS2Recomp/commit/f7f35bc6), and ReInPS's `address_taken_code.cpp`
**[verified]** compare, [e529d872](https://github.com/maxigasparini/ReInPS/commit/e529d872). dmc-recomp independently
found the ELF `.symtab` beat the Ghidra CSV for bounds **[claimed]** [dmc-recomp](https://github.com/Gui-Tora/dmc-recomp).
The port lands in `third_party/ps2recomp/ps2xRecomp/src/lib/ps2_recompiler.cpp` (`loadGhidraFunctionMap`), with
`recomp/socom2_ghidra.csv` as input and a three-stage re-gate.

ico-recomp's ingest is the most complete reusable machinery, MIT and in Rust. It has eight named entry proofs, each
paired with an independent positional or structural test, plus hard errors for backward cross-function branches and
delay-slot entries, and an `entry_gaps.txt` sweep of unresolved `lui`/`addiu` pointers **[verified]**
[TARGET.md](https://github.com/nathanialf/ico-recomp/blob/main/docs/TARGET.md) "The translator's inputs". Its "no
backward cross-boundary branch" check can run over our csv as a re-gate check without adopting the tool. Its prologue
window (8 instructions, at most 3 setup words) was measured on GCC code and needs re-measuring on SOCOM's Metrowerks
overlays. The researchers read `scan.rs` through TARGET.md's description, not line by line.

### 5.2 Jump tables and the matcher (N28, N24 #52, N25 #58, N26 #60)

For N28 (no census of tables found against tables missed; `docs/LATER.md` row 15), there are two sizing strategies to
cross. N64Recomp tracks `lui`/`addiu`/`addu`/`lw`/`jr` and reads words until an entry leaves the function or the next
table starts; it ignores the bounds check and fails hard on a zero-entry table **[verified]**
[analysis.cpp:86-346](https://github.com/N64Recomp/N64Recomp/blob/main/src/analysis.cpp). XenonAnalyse takes the count
from the guarding `cmplwi` **[verified]** [XenonRecomp README:33-45](https://github.com/hedge-dev/XenonRecomp/blob/main/README.md),
whose README admits the analyzer "struggles with functions containing jump tables, since they look like tail calls".
ico-recomp recovers 110 tables from `.rodata` before its boundary proofs, strips case labels from candidate entries,
re-recovers on the final ranges, and fails rather than split a function at a case label **[verified]** TARGET.md. The
MIPS census is the tracker walk against an `sltiu`+`beqz` reader, with disagreements marked suspect. The walk depends
on correct bounds, so **#55 comes before the census**. Both tools are MIT and **takeable with credit**. The census lands
in `tools_py/`, as a new script over the r0004 image.

For #52 (the fingerprint zeroes every `addiu`/`ori` immediate, so `exact` is not proof), ico-recomp's correlator differs
in three ways: it keeps branch offsets unmasked as the discriminator, masks load/store displacements and `lui`
immediates too, and accepts an anchor only when "the whole body then reproduces there", with monotonic deltas. "The body
check is the proof, and a wrong hypothesis cannot pass it". It placed 5,533 of 5,855 donor functions **[verified]**
TARGET.md, `ingest/src/correlate.rs`. The decomp ecosystem adds graded confidence: asm-differ (Unlicense) scores with
weighted penalties (regalloc 5, reordering 60, insertion and deletion 100) after folding relocations into the instruction
**[verified]** [diff.py:515-520](https://github.com/simonlindholm/asm-differ/blob/main/diff.py); ghidra-delinker
(Apache-2.0) synthesises relocation tables from a Ghidra database, so the matcher can mask only relocated operands
**[verified]** [ghidra-delinker README](https://github.com/boricj/ghidra-delinker-extension). asm-differ's
insertion/deletion alignment also resolves "repeated windows paired by order"; it is Python and drops into `tools_py/`.
For #58 (BinExport on Ghidra 12.1.3), nothing changed, and no surveyed project uses Ghidra 12.x BinExport; objdiff (MIT or
Apache-2.0, MIPS PS2 listed) or asm-differ could replace the BinDiff cross-check altogether, since neither pins a Ghidra
version **[inferred]**; **[verified]** support list at [objdiff README](https://github.com/encounter/objdiff). For #60, no
peer has a slot-priority rule: both N64Recomp and XenonRecomp key lookup on start address only **[verified]** N64Recomp
README:25, so "stubs win the slot" stays ours to write.

## 6. Network: one ready port, one published address, one unanswered question (N30 #26, N31 #34, N32 #72, N33, N36 #112)

### 6.1 #72's five messages are already modelled in a GPL-3.0 Horizon derivative (N32)

**GitHubProUser67/PSHome-MultiServer (GPL-3.0) has models and MLS `case` handlers for all five ids our r0004 client leaves
unanswered**: VersionServer 0x86, FileListFiles 0xB2, UpdateLadderStats 0xCE, LadderList_ExtraInfo0 0xEF and LobbyExt
GetBuddyInvitations 0x08 **[verified]** `RT.Models/Lobby` and `Servers/Horizon/SERVER/Medius/MLS.cs` lines 1293, 1908,
2369, 2821 and 7819 at `8778e985e4`, [PSHome-MultiServer](https://github.com/GitHubProUser67/PSHome-MultiServer). It
shares Horizon's `RT.Models` shape, so the models port almost verbatim into `server/horizon-server/RT.Models/Lobby`, with
minimal handlers in `server/horizon-server/Server.Medius/Medius/MLS.cs`. Our upstream already declares the ids but has no
models for them **[verified]** in this worktree: `server/horizon-server/RT.Common/Types.cs:708` (0x86), `:752` (0xB2),
`:780` (0xCE), `:813` (0xEF), `:839` (0x08). Our own notes disagree on the count -- four in #72 against five in the status
log; the five-id set (0x86, 0xB2, 0xCE, 0xEF, LobbyExt 0x08) is `docs/archive/STATUS-log-to-2026-09-26.md:2090`
**[verified]**, while `:2123-2125` names a different five (0xB2, 0xEC, 0xEF, 0x08, 0x86): that list predates the 0xEC
model (`ChannelList_ExtraInfo0`, handled at `server/horizon-server/Server.Medius/Medius/MLS.cs:3373`) and lacks 0xCE.
**This note takes `:2090`'s five as the open set**, because the log names each id and #72's "four" is
`MediusVersionServer` plus three (§8 item 4). Two
checks come before the port: which class the 0xEF response must use, and the 0xB2 field layout against the 1.50
client's request size (MultiServer notes the `StartPosition` of `MediusLadderListRequest` as "Socom: 8, Others 4"
**[verified]** `RT.Models/Lobby/MediusLadderListRequest.cs:19`). Adding GPL-3.0 files to our MIT `server/` copy makes the
server combination GPL-3.0; that is compatible, but it belongs in `server/README.md`. clank (MIT, Java) has VersionServer
and GetBuddyInvitations handlers as a second reference **[verified]** [clank](https://github.com/hashsploit/clank).
medius-cpp is AGPL-3.0, and its network clause would bind a hosted server, so treat it as reference unless the owner
accepts that clause. MultiServer's NAT service answers three times and maps IPv6 senders to IPv4 **[verified]**
`Servers/Horizon/NAT/NAT.cs` lines ~25-58; that small hardening for lossy paths bears on N33. MultiServer also lists
"Socom II November Beta" under app id 10540 where PSRewired's site labels 10540 "SOCOM II PAL BETA" -- the two sources
conflict on what 10540 is (§8 item 6).

Horizon upstream merged #37 (.NET 10, `9c0b23f`, merge `6375a09`) and #38 (`e9aeb4b` "Cryptography + DME improvements",
merge `b1a0d03`) on 2026-10-01 **[verified]** [horizon-server](https://github.com/Horizon-Private-Server/horizon-server).
#38 makes `CipherService`'s map a `ConcurrentDictionary` and shares one static `MultithreadEventLoopGroup` across DME UDP
clients (+9/-33 over three files). That is a cheap MIT cherry-pick from `e9aeb4b`, once the `World.cs` hunk is checked
against `World.Clients` being keyed by DmeId **[verified]** `server/horizon-server/Server.Dme/Models/World.cs:96`. The
`nzo-server-tick-fixes` branch's `68357b0` (aggregation drift, stopwatch tick; PR #36 merged into that branch, not master)
is server hygiene, not the likely #34 cause, because round traffic does not ride DME TCP **[verified]**
`docs/research/18-online-round-start.md:81-99`. PR #35, graceful disconnect, closed unmerged.

### 6.2 #26: a watch target, no public answer (N30)

No public source names SOCOM II's chat receive function. reCOM, a SOCOM 1 decomp with no licence, names `CZNetGame`'s
`m_uiv_ChatList` registered as `"BCHATLISTVAR"` **[verified]**
[zNetGame.cpp:36-38](https://github.com/NotEnoughPhotons/reCOM/blob/5b05af1d0d/src/gamez/zNetwork/zNetGame.cpp), and
our research/11 already matched SOCOM II's `FUN_002a76d0` (`CZNetGame::Initialize`) creating the same variable
**[verified]** `docs/research/11-recom-applicability.md:41`. A write watch on that variable while player B receives a
line is the cleanest target. Horizon's DME dispatches only `APP_*` records and has no chat handling **[verified]** in this
worktree: the message switch at `server/horizon-server/Server.Dme/TcpServer.cs:451-517`, the `RT_MSG_CLIENT_APP_BROADCAST`,
`APP_LIST` and `APP_SINGLE` cases at `:502-516`; and the libmedius `MediusChatFwdMessage` callback never fires. So the
line almost certainly rides a game-defined DME APP opcode, and an opcode histogram diff over the chat window would
discriminate **[inferred]** from our own notes, not a public write-up.

### 6.3 #112: the published address, and the conditional pnach (N36)

**PSRewired's Game-Information publishes the r0004 DNAS bypass at `0x3953C0`, and warns that the r0001 code at
`0x2CC670` "if left on will cause the game to go into a reboot loop"** **[verified]** Game-Information commits
`1b40265`/`8188e02`, [PSRewired/Game-Information](https://github.com/PSRewired/Game-Information). The repository has no
licence, so the address is a fact, not code, and our r0004 map should confirm `0x3953C0` is DNASAuthenticate before use.
PCSX2 2.8.2's `dpatch=` applies a patch only where memory matches a pattern **[verified]**
[Patch.cpp:1004-1031](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/Patch.cpp), so a pattern guard on
`FUN_002cc670`'s original words gives the conditional pnach; its match semantics have not been read. PSRewired's server
source is not public, and any contact is by the owner's hand (R293).

## 7. The PCSX2 door facts for Sprint 18: a seeded ini, not just `-batch`

The Sprint 18 launcher toggle runs straight into one fact: **`pcsx2-qt.exe -batch <iso>` boots directly but does not
suppress the setup wizard**, which runs before the main window whenever `[UI] SetupWizardIncomplete = true`
**[verified]** [QtHost.cpp:1421-1422, 2487-2560](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2-qt/QtHost.cpp). An
existing `PCSX2.ini` without `[UI] SettingsVersion = 1` is worse: PCSX2 asks a modal Yes/No question, re-saves every core
section from defaults (wiping `[DEV9/Eth]`), and then runs the wizard **[verified]** QtHost.cpp:1358-1395,
[VMManager.cpp:549-604](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/VMManager.cpp). The seed is therefore
`[UI] SettingsVersion = 1`, `SetupWizardIncomplete = false`, and `[DEV9/Eth] EthEnable = true`, `EthApi = Sockets`,
`EthDevice = Auto`, `ModeDNS1 = Manual`, `DNS1 = <the box's address>`. Alternatively, run `-testconfig` once and patch the
result. **v2.8.2 never loads DNS2 from the ini**: the load path calls `LoadIPHelper(DNS1, ...)` twice, and master has the
same lines **[verified]** [Pcsx2Config.cpp:1351-1352](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/Pcsx2Config.cpp).
An empty, BOM-less `portable.txt` beside the exe keeps `inis/`, `bios/`, `memcards/` and `patches/` under the extracted
folder. A missing card is auto-created as 8 MB of 0xFF, unformatted, and a non-empty card is never overwritten
**[verified]** [MemoryCardFile.cpp:286-294](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/SIO/Memcard/MemoryCardFile.cpp).
This host's `tar.exe` is bsdtar 3.8.8 with liblzma, so it should extract the `.7z`, but older System32 builds lack LZMA
("LZMA codec is unsupported", "compiled without liblzma") -- a fallback is prudent **[verified]** locally; the failure
report is **[claimed]** at [DLSS5-Autopilot#93](https://github.com/Kizzuwatnaa/DLSS5-Autopilot/issues/93) (§8 item 5).
This lands in `third_party/ps2recomp/ps2xLauncher/src`. The facts are PCSX2 behaviour, not code to copy.

## 8. Where the notes disagreed, and which side this note takes

1. **The 989snd streamer source.** Note 04: none exists (Ziemas/989snd `iop/stream.c` is 71 of 77 `UNIMPLEMENTED()`).
   Note 02: Ziemas/dec989snd `src/stream.c` is complete (4,231 lines). **Note 02 wins**: it found a second repository
   note 04 did not search; both are right about their own repository. dec989snd is unlicensed, so facts only (§1.3).
2. **The GS Z format rule.** Our brief (#104) said truncation to the ZBUF width; PCSX2 and DobieStation both saturate to
   the format maximum. **The emulators win** (two independent implementations, one with a hardware comment) (§2.1).
3. **The duck default.** Ziemas/989snd's init sets `gGroupDuckMult[] = 0x1000`; OpenGOAL's default is 0x10000, under
   the same `/ 0x10000` formula. **Unresolved**: a factor of 16 in `m_vol`; whichever value our mixer feeds is checked
   before the divisor trial, because the two cannot both be the console's (§1.1).
4. **#72's message count.** The issue says four; the status log says five, and the log holds two five-id lists:
   `STATUS-log-to-2026-09-26.md:2090` (0x86, 0xB2, 0xCE, 0xEF, LobbyExt 0x08) and `:2123-2125` (0xB2, 0xEC, 0xEF, 0x08,
   0x86), the second written before 0xEC was modelled (`MLS.cs:3373`). **The `:2090` five**: 0xEC is handled, 0xCE is
   not, and #72's "four" is `MediusVersionServer` plus three others, the same set counted differently (§6.1).
5. **Windows `tar.exe` and `.7z`.** One report says a 25H2 build extracted a 7z; another says the System32 build has no
   LZMA. **Both are taken as true of different builds** **[inferred]**; this host's is 3.8.8 with liblzma, and the
   launcher keeps a fallback (§7).
6. **App id 10540.** MultiServer calls it "Socom II November Beta"; PSRewired's site "SOCOM II PAL BETA". **Neither side
   is taken**; the id is not one we serve (10472), so it is recorded and left (§6.1).
7. **The vol.c line numbers.** The report cited the IRX arithmetic at both `vol.c:434-455` (Ziemas/989snd) and
   `src/vol.c:307-332` (dec989snd). **Both are right**: they are two repositories with the same function (§1.1).

## 9. Prioritised adoption list

Ordered by confidence first, then cost. "Lands in" names the in-tree file (the fork's root is `third_party/ps2recomp/`).
Each row's `docs/LATER.md` home is named so the register and this note agree.

| # | Item | Need | Source and licence | Lands in | Cost | Confidence | LATER |
|---|---|---|---|---|---|---|---|
| 1 | Voice/stream register as `reg << 1` Q15 (divisor 0x7FFE -> 0x4000), PCM ring untouched; group 16 linear via MVOL; the duck default checked | N1 #91 | PCSX2 ADSR.cpp/Mixer.cpp (GPL-3.0+); OpenGOAL vagvoice.cpp (ISC) | `ps2xRuntime/src/lib/snd989_mixer.cpp:1007-1033,2016,2101-2107` | one-line trial plus re-score | high: hardware doc and two implementations agree | row 67 |
| 2 | Read-only #258 check: SOCOM `sp` at the first schedule against the first invocation stack | stability, N31 #34 | issue #258; MunchkinClubber c97cfaa7 (GPL-3.0) | `ps2xRuntime/include/ps2_runtime.h:571-572`, `ps2xRuntime/src/lib/ps2_runtime.cpp:2013-2016,2239` | minutes | high on mechanism; symptom unknown | row 82 |
| 3 | Batch: #268, #260, #265, #257 | VU0, resume, pad, DMAC | upstream (GPL-3.0) | `vu_translation_helpers.cpp`, `control_flow_emitter.cpp`, `Kernel/Stubs/Pad.cpp`, `PS2Memory::Store32` | small; one gate for the two codegen fixes | high: same code verified in ours | row 83 |
| 4 | Z floor plus format clamp in the GL depth path | N8 #104 | PCSX2 #13795/#13851, EmulateZbuffer (GPL-3.0+) | `ps2xRuntime/src/lib/gs/gs_gl_backend.cpp:371` shader and draw setup | ~3 GLSL lines plus a CPU branch | high: fixed the same class in PCSX2 | row 84 |
| 5 | Port the five Medius models and minimal handlers; Horizon #38 cherry-pick | N32 #72 | PSHome-MultiServer (GPL-3.0); Horizon e9aeb4b (MIT) | `server/horizon-server/RT.Models/Lobby`, `Server.Medius/Medius/MLS.cs`; `Server.Dme` | a day; minutes | high | rows 85, 86 |
| 6 | Seeded ini, portable.txt, dpatch-guarded pnach at the verified address | N36 #112, Sprint 18 door | PCSX2 v2.8.2 facts; PSRewired address (facts only) | `ps2xLauncher/src` | small | high | row 87 |
| 7 | Per-consumer read-back rects | N10 #96 | PCSX2 InvalidateLocalMem (GPL-3.0+) | `gs/gs_gl_backend.cpp` (`gpuRows`) | moderate | high (latent bug) | row 47 |
| 8 | Overrun counter and device-fill sample at the device write | N2 #42 | PCSX2 AudioStream.cpp design (GPL-3.0+) | the mixer's output path | small, instrumentation | medium: hypothesis to test | row 88 |
| 9 | FTOI saturate-by-sign; EE FPU extended-finite compares; VU0 lane clamp check | N19, N20 | PCSX2 floatToInt; LightVelox c419f26b; PR #272 (GPL-3.0) | `ps2xRuntime/include/ps2_runtime_macros.h:917-929`, VU0 helpers | small, gate | medium-high | row 89 (rows 11, 12) |
| 10 | Generation-time VU1 flag liveness (4-cycle window), replay tolerant of dead flags | N16, N15 | silentsudin e56ad7dc (GPL-3.0); ico-recomp (MIT); microVU (GPL-3.0+); Play! (BSD-2) | the VU1 generator for `ps2xRuntime/src/lib/vu/generated/` | weeks | medium: claims unverified here, design consistent | row 90 (row 5) |
| 11 | Recorded JR/JALR targets; range-validated program identity | N16 | Sinan ef8eca6c (GPL-3.0); microVU mVUcmpProg | `ps2xRuntime/src/lib/vu/` program selection | moderate | medium (applies only if coverage is recording-driven) | row 91 |
| 12 | Reverb (DoReverb, resampler, STUDIO_2 row, VMIXEL/R); Gaussian table | N5 | PCSX2 (GPL-3.0+); OpenGOAL interp_table.inc (ISC); libsd presets as facts | `snd989_mixer.cpp` | moderate | high on correctness, low urgency | row 92 |
| 13 | Per-thread EIE, IRQ gate `IE&&EIE&&!EXL&&!ERL`, DI one late, EI re-check; FIFO/LIFO audit | N21 | PCSX2 R5900/COP0; ico-recomp TARGET.md (MIT) | `ps2xRuntime/src/lib/Kernel/EeScheduler.cpp`, DI/EI hooks | moderate, gate | medium (no console oracle) | row 93 (row 10) |
| 14 | Block-valid bitmaps, page-indexed invalidation, hash cache | N11 #32 | PCSX2 GSTextureCache (GPL-3.0+) | `gs/gs_gl_backend.cpp` upload path | large | high on design | row 94 |
| 15 | Map authority with N64Recomp-style statics plus pointer-scan backfill, then the jump-table census | N22 #55, N23 #54, N28 | N64Recomp, XenonAnalyse (MIT); MunchkinClubber/ReInPS tools (GPL-3.0) | `ps2xRecomp/src/lib/ps2_recompiler.cpp`, `tools_py/` | large, full re-gate | medium (resume-entry interaction untested) | rows 17, 16, 15 |
| 16 | Relocation-masked matcher with whole-body proof and asm-differ scoring | N24 #52, N25 #58 | ico-recomp correlate.rs (MIT); asm-differ (Unlicense); ghidra-delinker (Apache-2.0) | `tools_py/` matcher | moderate | medium | rows 20, 21 |
| 17 | Mip chain and LOD; blend deinterlace | N12, N13 | PCSX2 GetTex0Layer, interlace.glsl (GPL-3.0+) | `gs/gs_gl_backend.cpp` | moderate | high on design | rows 54, 55 |
| 18 | MTGS-style empty-ring wake audit | N9 #114 | PCSX2 MTGS; ico-recomp ring (MIT) | `gs/gs_stall_coalescer.cpp`, `gs/gs_frame_backpressure.cpp` | audit first | medium (our code not read) | row 58 |
| 19 | Port as ideas: #269, #271/cc9a3ec5, #201, #200, c4c20e80 | VIF, N26 #60, N18 | GPL-3.0 forks | the VIF1 interpreter, the recompiler, the VU translators | small each, gates | medium | row 95 (row 14) |

## 10. Every project surveyed, with licence and verdict

The licence comes from the GitHub API or the LICENSE file as the notes record it. **TAKEABLE WITH CREDIT** means a
cherry-pick `-x` or a `Co-authored-by` with the source URL and hash, the notice kept, a README credits row (the Licence
baseline below). **FACTS ONLY** means the code is not copied; what it proves may be re-derived and cited. **LICENCE
UNCONFIRMED** means check before use. AGPL is combinable under GPLv3 section 13, but its network clause would bind our
hosted server, so AGPL sources are reference only unless the owner accepts that clause (the Licence baseline).

| Project | Licence | Verdict | What it offers us |
|---|---|---|---|
| ran-j/PS2Recomp (upstream, `c5a9d025`) | GPL-3.0 | TAKEABLE WITH CREDIT | #258, #260, #265, #257, #268-#272, #206 |
| silentsudin/PS2Recomp `roadtrip` | GPL-3.0 | TAKEABLE WITH CREDIT | VU1 recompiler, flag liveness, SPU2 reverb, harness |
| LightVelox/PS2Recomp `sotc-port` | GPL-3.0 | TAKEABLE WITH CREDIT | VU1 AOT, D1_CHCR timing, tail-jump fix, FPU compares, GL 4.6 GS |
| Sinan-Karakaya/PS2Recomp (#254) | GPL-3.0 | TAKEABLE WITH CREDIT | recorded JR targets, SSE2 path, LLE oracle |
| noahbaxter/PS2Recomp `ghrecomp` | GPL-3.0 | TAKEABLE WITH CREDIT | stack/heap placement (#258 family), COP0 Count |
| brad-richardson/PS2Recomp `au18`/`ssx3` | GPL-3.0 (ARMSX2 parts unverified) | LICENCE UNCONFIRMED for the ARMSX2 parts; the rest TAKEABLE WITH CREDIT | microVU bridge, DC blocker; design only |
| drakolordx7 `killzone` branch | GPL-3.0 | TAKEABLE WITH CREDIT | source of #265-#272 |
| MunchkinClubber/PS2Recomp `ssx3-fixes` | GPL-3.0 | TAKEABLE WITH CREDIT | c97cfaa7, cc9a3ec5, find_code_pointers.py |
| maxigasparini/ReInPS `feature/vu1-audit` | GPL-3.0 | TAKEABLE WITH CREDIT | second snd989 HLE, address-taken discovery, VIF1 unpack tests |
| smmathews/PS2Recomp (#137-#201) | GPL-3.0 | TAKEABLE WITH CREDIT | #200, #201, #151; most already ours |
| hedgeg0d/PS2Recomp | GPL-3.0 | TAKEABLE WITH CREDIT | #236 branch |
| 0xjjjjjj/PS2Recomp | GPL-3.0 | TAKEABLE WITH CREDIT | superseded VU1 session |
| GTTeancum `codex/xmen-legends-bringup` | GPL-3.0 | TAKEABLE WITH CREDIT (design) | #222, VU perf series, now branch-only |
| Sorachi00/PS2Recomp-Drakengard | README forbids AI use | FACTS ONLY; not opened | none |
| nathanialf/ico-recomp | MIT (paraLLEl-GS LGPL-3.0) | TAKEABLE WITH CREDIT | VU1 latency audit, GS spec, threaded ring, per-thread EIE, ingest, correlator |
| mirou1611/AstraRecomp | MIT | TAKEABLE WITH CREDIT | corroborates delayed VI branch |
| InconspicuousCactus/SotCStaticRecompilation | none | FACTS ONLY | dead |
| drakolordx7/KillzoneRecomp | GPL-3.0 | TAKEABLE WITH CREDIT | PCSX2 units as libraries, staircase and flicker measurements |
| Gui-Tora/dmc-recomp | GPL-3.0 | TAKEABLE WITH CREDIT | symtab bounds, FIFO/LIFO scheduler bug |
| nicolasserpa/shadow-the-hedgehog-recomp | GPL-3.0 | TAKEABLE WITH CREDIT | none |
| LabronFox/vulcan4 | GPL-3.0 | TAKEABLE WITH CREDIT | VU1 prior-art survey |
| noahbaxter/ghpc | GPL-3.0 | TAKEABLE WITH CREDIT | not diffed |
| z3xox/BT3-Recomp | GPL-3.0 | TAKEABLE WITH CREDIT | not diffed |
| Red-tv141/DC2-PS2RECOMP | AGPL-3.0 | reference only unless the owner accepts the AGPL clause | not diffed |
| GTTeancum/Timesplitters | none | FACTS ONLY | not read |
| BlackLineInteractive/SHO-GTA-VCS-PS2Recomp | GPL-3.0 | TAKEABLE WITH CREDIT | not read |
| brad-richardson/ps2xGS | GPL-3.0-or-later | TAKEABLE WITH CREDIT | `.gscap` capture/replay/census (N14) |
| open-goal/jak-project | ISC | TAKEABLE WITH CREDIT | volume law, Gaussian table, stream double buffer |
| theclub654/ProjectCane | none | FACTS ONLY | low |
| Mikompilation/MikuPan | AGPL-3.0 | reference only unless the owner accepts the AGPL clause | low |
| Pedroj-64/DownHill-Port-PC | GPL-3.0 | TAKEABLE WITH CREDIT | low |
| nathanialf/ico-pc | NOASSERTION (README says MIT) | LICENCE UNCONFIRMED | future library decomps |
| Ziemas/dec989snd | none | FACTS ONLY | complete VAG streamer, vol/reverb/autovol |
| Ziemas/989snd | none | FACTS ONLY | volume chain, reverb sizes |
| Ziemas/overlord | none | FACTS ONLY | low |
| TheOnlyZac/sly1 | CC0-1.0 | TAKEABLE WITH CREDIT | EE-side 989snd client |
| parappadev/parappa2 | none | FACTS ONLY | IOP BGM streamer design |
| ethteck/kh1 | none | FACTS ONLY | none |
| Fantaskink/SOTC | MIT | TAKEABLE WITH CREDIT | none |
| crowded-street/3s-decomp | AGPL-3.0 | reference only unless the owner accepts the AGPL clause | none |
| AshfordFamily/recvx-decomp | MIT | TAKEABLE WITH CREDIT | none |
| Lynder063/rac1-decomp; mateuszklysz/Lombyte; bordplate/RC1; ProjectRYNO | NOASSERTION; MIT; none; none | FACTS ONLY except Lombyte (TAKEABLE WITH CREDIT) | confirm `snd_PlayVAGStreamByLoc` is 989snd |
| Other matching decomps (god-hand, mh1j, Bullseye, Himuro, dds, P3/P4, Chronicle, ICO-decomp) | MIT, CC0 or none | per licence | nothing for the runtime |
| Hat-Kid/989snd-player; ahigerd/989snd-clef | ISC; NOASSERTION (README MIT+ISC) | TAKEABLE WITH CREDIT; LICENCE UNCONFIRMED | format players on OpenGOAL code |
| PCSX2/pcsx2 (`81526d4dc7`, v2.8.2) | GPL-3.0+ | TAKEABLE WITH CREDIT | depth, read-back, MTGS, texture cache, mips, deinterlace, microVU, FPU, EIE, SPU2, door facts |
| jpd002/Play- | BSD-2 | TAKEABLE WITH CREDIT (keep the notice) | simplest flag-pipeline model |
| PSI-Rockin/DobieStation | GPL-3.0 | TAKEABLE WITH CREDIT | Z clamp and FTOI corroboration |
| ps2tek | none (docs) | FACTS ONLY | float and COP0 rules |
| ps2dev/ps2sdk | AFL-2.0 | FACTS ONLY | reverb presets as data |
| psx-spx | docs | FACTS ONLY | SPU register formats |
| aap/libgpu2 | not checked | LICENCE UNCONFIRMED | GS texture-coordinate saturation |
| N64Recomp/N64Recomp | MIT | TAKEABLE WITH CREDIT | map authority, statics, jump-table tracker |
| hedge-dev/XenonRecomp | MIT | TAKEABLE WITH CREDIT | bounds-check table count |
| simonlindholm/asm-differ | Unlicense | TAKEABLE WITH CREDIT | match scoring |
| splat; spimdisasm | MIT | TAKEABLE WITH CREDIT | R5900 disassembly and symbols |
| matt-kempster/m2c | GPL-3.0 | TAKEABLE WITH CREDIT | switch coalescing (decompiler) |
| decompme/decomp.me | MIT | TAKEABLE WITH CREDIT | scoring idea |
| encounter/objdiff | MIT or Apache-2.0 | TAKEABLE WITH CREDIT | BinDiff alternative |
| boricj/ghidra-delinker-extension | Apache-2.0 | TAKEABLE WITH CREDIT | relocation synthesis (12.1.3 compatibility unverified) |
| ghidra-emotionengine-reloaded | Apache-2.0 | already in use | none new |
| Horizon-Private-Server/horizon-server | MIT | TAKEABLE WITH CREDIT | #38, tick fixes |
| GitHubProUser67/PSHome-MultiServer | GPL-3.0 | TAKEABLE WITH CREDIT | the five r0004 message models, NAT x3 |
| hashsploit/clank | MIT | TAKEABLE WITH CREDIT | VersionServer and BuddyInvitations handlers |
| Jump-Suit/horizon-server-public-extended | MIT | TAKEABLE WITH CREDIT | Killzone only |
| MrChip53/medius-cpp | AGPL-3.0 | reference unless the owner accepts AGPL | message declarations |
| Speedy11CZ/clank | none | FACTS ONLY | none read |
| PSRewired/Memdusa, Game-Information, RetroDNS | none | FACTS ONLY | threat model; `0x3953C0` and the reboot-loop warning; DNS approach |
| NotEnoughPhotons/reCOM | none | FACTS ONLY | `BCHATLISTVAR` |
| cripfoun159/EyeToy-Chat-online-server- | none | FACTS ONLY | none |

## 11. What no project solves

The online layer beyond the lobby is unsolved everywhere. **No Medius implementation relays peer UDP or traverses NAT
beyond the 4-byte address echo**; Horizon's DME relays only `APP_*` records, never SOCOM's raw 3658/3660 channel
**[verified]** `server/horizon-server/Server.NAT/NAT.cs`, research/18. So a round across two networks (N33) works only if
both NATs are endpoint-independent. Whether SOCOM's `0x18` record carries the NAT-learned external address at all is
unmeasured. If symmetric NAT fails, the fallback is ours to build: tunnel the peer channel through DME `APP_SINGLE` in
the libnetb HLE (`socom2_libnetb.cpp`), or run a TURN-like relay. Nothing external addresses #34's 3-17 s freezes under
host load. The chat receive function (#26) has a public watch target but no public answer. **No project models two
universes by revision** (#72's first bar), because SCEA and PSRewired alike force every client to r0004 through the
in-game patch; our r0001 native players are a situation only we have.

Several hardware truths have no oracle anywhere. No source documents how the GS interpolates Z internally (fixed-point
width, rounding); PCSX2's own comment says "we appear to" clamp, and ico-recomp's 32.32 DDA is unverified, so N8's
second suspect stays open after the floor. No emulator or document gives a measured macro-mode CFC2 latency (N18); both
emulators assume none, and ps2tek says only that macro instructions interlock. No project holds hardware-verified FTOI
or FPU tables; PCSX2's 2^32 program exists, but nobody says it ran on a console. No project has an
interpreter-against-hardware VU oracle: every porter's "bit-exact" means against their own interpreter, which is our own
gap (`docs/LATER.md` row 5). And no EE timing oracle exists for the EIE change.

Some of our own areas have no external counterpart. Nobody has a SOCOM-specific function map, so the 1,090 nested rows
and the stub-over-resume slot conflict (#60) need our own policy. No project models the ZAR V2 shared-node persona
layout (#111), or an in-process LoadExecPS2 restart (already done by us). No project documents a locked-30 present hold
(N13's second half), an identical-tile skip, or a GPU swizzle in a GL 3.3 renderer; PCSX2's hash cache is the nearest.
Nothing covers #132's launcher font-reload segfault, #105's unfocused pad, the Linux real-GPU suites (N39), HDD `pfs0:`
HLE (N40), or a native port of the DNAS self-decrypt (N37). Above all, **no public 989snd streamer source exists under
any usable licence**: dec989snd is facts only, and the real refill trigger (SPU IRQ at the half address, or NAX polling)
is observable for us only through the out-of-tree LLE oracle running the real IRX (research/70).

The audit changes where to look more than what to build. The two largest audio and renderer defects on our list (#91's
level and #104's band) are each one well-understood rule that every reference implementation already applies -- the
voice register's `<< 1` and the integer Z floor -- and both read as fidelity mysteries only because our code encodes a
plausible but wrong belief, one of them stated outright in a mixer comment. Before treating a parity gap as a modelling
problem, diff each constant and scale in the affected path against PCSX2 and OpenGOAL. The fork scene has also shifted:
with GTTeancum's closures, upstream is no longer the channel through which VU performance work arrives; the real
frontier is five game ports that independently built what N16 asks for and published fps numbers nobody has reproduced.
The remaining hard problems (peer NAT, revision universes, Z and CFC2 hardware timing) need a second network, a console,
or the owner.

## Licence baseline

Our repository is GPLv3 (the root `LICENSE`). The owner's rule of 2026-10-03, "where applicable, take other commits that
share our license ensuring the creators retain credit", is applied as follows. **Takeable with credit:** GPL-3.0 (and
GPL-3.0-or-later), GPL-2.0-or-later, LGPL, and the permissive licences MIT, BSD, ISC, Apache-2.0, zlib and CC0. Credit
means: a `git cherry-pick -x` where the commit applies, or a `Co-authored-by:` trailer plus the source URL and commit
hash in the commit body where it is re-typed or ported; the original copyright and licence notice kept in the file
header; a row in `README.md` "License and credits"; and the licence text copied into `LICENSES/` when that licence is
new to the tree. AGPL-3.0 is combinable under GPLv3 section 13 but its network clause would bind our hosted server, so
AGPL sources are reference only unless the owner accepts that clause for the server. **Facts only:** unlicensed
repositories (Ziemas/989snd and dec989snd, PSRewired's repositories, reCOM, ps2tek, the unlicensed game ports), GPL-2.0-only,
AFL-2.0 (ps2sdk: the code is reference-only, hardware register values are data), and any repository whose README forbids
the use (Sorachi00/PS2Recomp-Drakengard, not opened). A fact from such a source is re-derived in our own words and cited
by URL; no line of its code enters the tree. `docs/UPSTREAM.md` §0 carries the two-sentence form of this rule.
