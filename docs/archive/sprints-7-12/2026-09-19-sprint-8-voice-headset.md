# Sprint 8 Goal 3 — Voice: Serve the Headset from the Host Microphone: Implementation Plan

> **ARCHIVED 2026-09-25 -- a Sprint 8 plan; the sprint is closed and this is its record.**
> Moved here from `docs/superpowers/plans/` in Sprint 13 (Task R1, with the rest of Sprints 7-10's specs and
> plans); nothing below it was edited except citations that pointed at a path that has since moved. It is a
> record, not an instruction.

> **Superseded in place, 2026-09-25, on two points.** (1) The codec named at `:810` and `:934` is not Nellymoser:
> SOCOM II's voice codec is **SASE** (`SaseEncVad`/`SaseDec`), verified against all four images
> (`docs/research/44`'s addendum, `docs/research/56`); SOCOM 1's demo speaks LPC-10 and GSM appears nowhere. No
> image carries the string `Nellymoser` — only the assert macro `NellyNull` — so the name was an inference from
> that macro and is withdrawn. (2) `:168`'s "0x500 = 1280 bytes — 640 samples at **11025 Hz** mono s16,
> **58.05 ms**" belongs to two *other* `lgaud` callers, not to the voice object: **the voice object opens at 8000 Hz
> and reads every 80 ms** (research/56 §3, §6). `docs/KNOWN.md` §2's voice row carries the corrected record and wins
> on any disagreement.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SOCOM II's own USB-headset module real, served from the PC's microphone, so that a player who picks a capture device in the launcher is heard by the other machine. Today `lgaud.cpp` answers `0x80000001` = "no device" to everything but its version query, and the game polls `0x01 Enumerate` 3,749 times and `0x0f EnumHint` 5,316 times in a single run against that answer (`docs/KNOWN.md:101`). The bar for the autonomous half is a WAV of **what the game actually read through `0x08`** correlating at **>= 0.95** with the WAV fed in through a fake microphone, plus voice packets leaving instance A on the wire; the two-machine "can you hear me" is the owner's.

**Architecture:** The IOP module is a state machine over a message block whose layout is **already recovered, field by field, from the game's own decompiled client library** (`game/analysis/socom2_game.elf.decomp.c:90811-91800`) — see "The recovered message block" below and Task 2. Nothing is guessed at the RPC boundary. The host side follows the shape `snd989.cpp` already uses: the module never touches a device, it asks `IopHost` (`iop_host.h:56-123`), `PS2IopHostAdapter` (`ps2_iop_host.cpp:242-288`) forwards to the runtime, and the runtime owns `HostMic`. All new arithmetic — the rate conversion, the byte accounting, the WAV parsing — lives in a **header-only, device-free** header (`runtime/mic_format.h`) next to `host_mic.h`, exactly as `runtime/gs/gs_gl_target_extent.h` is header-only so `ps2xTest` can check it without a GL context; here it is so `ps2x_tests` can check it without a microphone. Proof without a second human comes from three files: a fake source (`PS2X_MIC_FAKE`) puts a known WAV where a device would be, a game-read dump (`PS2X_MIC_GAMEREAD_DUMP`) records exactly the bytes handed to `0x08`, and a playback dump (`PS2X_MIC_DUMP_PLAYBACK`) records what instance B's headset was asked to play. Correlating file 1 with file 2 proves the capture path; correlating file 1 with file 3 proves A-mic -> network -> B-headset end to end.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh` on the host; system clang + Ninja in the VM and on `ubuntu-24.04`), CMake >= 3.20, MiniTest (`ps2x_tests`, no filter, runs every case), miniaudio as compiled into raylib's `raudio.c` (**`MA_NO_WAV` at `raudio.c:167`** — there is no WAV decoder in the binary, so this plan hand-writes its reader the way `hostMicWavHeader` hand-writes the header), Python 3 `unittest` (**not** pytest, see Global Constraints), the online harness (`tools_py/parity/online_match_ours.py`, `tools_py/parity/online_login_ours.py`, `tools_py/parity/audio_corr.py`, `tools_py/parity/gate.py`), `scripts/run_detached.sh` + `scripts/loop_lock.sh` for every host launch.

**Spec:** `docs/archive/sprints-7-12/2026-09-18-sprint-8-linux-and-finish-design.md` — **Goal 3 only** (§2 "Goal 3 — voice: serve the headset (autonomous up to the two-machine check)": *"Enumerate answers one device when `PS2X_MIC_DEVICE` is set, Open succeeds, Read serves HostMic's ring; a WAV of what the game read is the proof; then the owner's 'can you hear me' on two machines"*, and §3's budget: *"Goal 3's dump (one)"* launch on Windows). **Required reading for every dispatch:** this plan's Handoff notes, Global Constraints, the recovered message block and the File map; `docs/KNOWN.md:101` (the Task 9c spike row — the function table and what the game polls); `docs/CURRENT_SPRINT.md:151-154` (Sprint 8 block item 2); `docs/HUMAN_TASKS.md:93-110` (the two open microphone items, both of which this goal rewrites); for the game side `game/analysis/socom2_game.elf.decomp.c:90811-91800` (the whole lgaud client library) and `:211455-211545` (the capture loop that actually calls `0x08`); for the code `third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp` (all 102 lines), `third_party/ps2recomp/ps2xIOP/include/ps2x/iop/iop_host.h:69-99` (the audio seams to copy), `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.cpp:242-288`, `third_party/ps2recomp/ps2xRuntime/include/runtime/host_mic.h` and `third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp`, and `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp:106-256` (`Snd989TestHost` / `Snd989HarnessT`, the harness shape this plan copies).

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; a fresh implementer per task; a task review after each that re-derives at least one number independently (for Task 2 that means re-reading one struct offset out of the decomp listing, not trusting this plan's table); the controller merges. Ledger at `.superpowers/sdd/2026-09-19-sprint-8-voice-headset/progress.md`. Decisions on the owner's behalf are `Ruling: ... — why — cost if wrong`, numbered from **R111** (R109 and R110 are taken by the hosted-server plan and the menu-render-cost plan's tail, both written 2026-09-19). *(2026-09-25: taken twice -- the menu-render-cost plan's are R109 and R110, the hosted-server plan's are cited as R109b and R110b.)*
- **Read this before Task 2, because the brief this plan was written from is wrong about four things, and the tree plus the decomp say otherwise.** Each is re-derivable with the command given; put the re-derivation in the ledger.
  1. **The format is 11025 Hz, not 16 kHz.** `host_mic.h:5-7` carries a `FORMAT ASSUMPTION: 16 kHz, mono, signed 16-bit` and says Task 9c's spike is what settles it. The spike is now settled the other way: the game's own `lgAudOpen` callers build an openparam of `{Mode=2, channels=1, bits=0x10, rate=0x2b11, latency=500}` — `0x2b11` is **11025** (`game/analysis/socom2_game.elf.decomp.c:48338-48342`, and byte-identically at `:86590-86594`). Re-derive with `sed -n '48336,48346p' game/analysis/socom2_game.elf.decomp.c`. So a linear resample from the ring's 16 kHz down to 11025 Hz is **always** needed, never conditionally.
  2. **The game never calls `0x12 GetAvailableRecordingBytes`.** `grep -n "FUN_00244820(" game/analysis/socom2_game.elf.decomp.c` finds the definition (`:91320`) and **no caller**. The capture loop (`:211478-211489`) calls `0x08 Read` directly for `0x500 - fill` bytes and reads the *actual* count back out of the reply. The brief's "GetAvailableRecordingBytes answers from HostMic's ring fill" is still implemented (Task 2 Step 7), because it is cheap and it is in the table, but **it is not on the path the proof runs through**: `0x08` must itself return short, correctly, when the ring is not full.
  3. **`0x08`'s payload does not go to a separate EE buffer — it goes into the RPC receive buffer at `+0x30`.** The brief says "Read copies that many bytes into the EE buffer the RPC names (through the SIF transfer path the module already uses for replies)". There is no such named EE buffer in the send block: `FUN_00244088` calls with `recvsize = ((count + 0x3f) >> 4) << 4` and then does `memcpy(dest, DAT_003dcfb4 + 0x30, reply[0x20])` on the EE side (`:91102`, `:91106`). The async `lgAudARead` is the same, with the EE destination kept in the EE's own `DAT_00414b30` (`:91631`), never sent to us. So `IopHost::writeGuest(request.receive.address + 0x30, ...)` — a wider version of the one call `lgaud.cpp:80` already makes — is the whole transfer path. Nothing new is needed, and the async variants need no IOP-side callback at all.
  4. **The send and receive buffers are the same address.** Every lgaud call passes `DAT_003dcfb4` as both (`:90956`, `:91033`, `:91102`, `:91330`, ...). **The module must read the entire send block before it writes one byte of reply**, or it will overwrite the handle and the byte count it is about to use. This is R112, and Task 2 Step 2's case fails if it is violated.
- **One more tree fact that will bite: `PS2X_MIC_DUMP`'s thread is the ring's only consumer.** `host_mic.cpp:163-165` says so in its own comment and `:189-196` drains the ring every 20 ms. If the game starts reading while that thread runs, the two split the audio between them and both files are wrong. Task 1 Step 6 turns the dump into a tee off the capture callback instead of a second reader; until it does, do not run a launch with both a device and `PS2X_MIC_DUMP` set.
- **`docs/KNOWN.md` has one writer: the controller.** The row at `:101` explicitly lists "the openparam block's fields — the rate, the channel count and `Mode` — are undecoded" as what keeps the spike out of Proven. Task 2 settles all three and Task 6 rewrites the row; the `16 kHz` sentence in `host_mic.h`'s header comment is retracted in Task 1, in the same commit that adds the resampler.
- **Autonomy (owner 2026-09-17, standing).** Proceed autonomously; no waiting for a window the owner names. **One host launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a host launch runs**: no `./build.sh test`, no `python -m unittest`, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers).
- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. A brief names the files to touch, the exact edit, the command that proves it and the expected output. A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, and never starts a launch. In this plan the natural subagent jobs are Task 2 Step 1's offset re-derivation from the decomp listing and Task 4 Step 5's per-length histogram of two runs' `udp send` lines.
- **Commit conventions.** `git commit -m "..." -- <paths>` with an explicit pathspec; never `git add -A`; `server/config/simulated.db` stays unstaged (it is modified in the working tree right now and must stay that way); `ONBOARDING.md` stays untracked; `vm/` is gitignored and nothing under it is ever staged. Push after each commit. Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Line numbers.** Every line number in this plan is the number at the `sprint-8` tip when it was written (2026-09-19, after `a44ef5e`). Goals 1, 2, 9 and 12 are landing in the same checkout; before starting a task, `git diff -- <the task's files>` and reconcile, saying so in the ledger rather than writing a step twice. This goal touches `gs_gl_backend.cpp` not at all and `launcher_config.cpp` only to read it, so a collision with Goal 2 or Goal 9 is unlikely; `tools_py/parity/online_login_ours.py` (Task 4) is shared with Goal 12's harness work and is the one file to check first.
- **Test binary.** `ps2x_tests` takes no filter and runs every case. Windows: `third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe`. Linux: `third_party/ps2recomp/build-linux/ps2xTest/ps2x_tests`.
- **The launch budget.** Spec §3 allows Goal 3 **one** dump launch. This plan spends **three**, and says why: `s8_voice_read` (Task 2's single-instance proof that the game reaches `0x02`/`0x04`/`0x08` at all — the cheapest possible check and the one that de-risks the two-instance run), `s8_voice_round` (Task 4, the two-instance round that is the actual bar), and one gate run (`s8_g3_gate`), because Task 2 changes `dist/socom2.exe`. If the budget is enforced strictly, `s8_voice_read` is the one to drop and Task 4 absorbs it.

### The command set (use these verbatim)

```bash
# --- build and suite (Windows host) ---
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "<what>" -- ./build.sh test

# --- the runner, for a launch ---
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/build_runtime.marker
scripts/run_detached.sh --owner gate  --purpose launch logs/<name>.sh           logs/<name>.marker
cat logs/<name>.marker 2>/dev/null || echo running     # poll the marker, never the tool call
bash scripts/check_quiet_gate.sh                       # answers whether a suite may run

# --- the gate (3/3) ---
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g3_<what>

# --- reading a voice run ---
grep -n "\[lgaud\]" logs/run_A_<stamp>.log | head -40
grep -c "\[lgaud:stub\]" logs/run_A_<stamp>.log          # 0 once Task 2 lands with a device set
grep -n "udp send #" logs/run_A_<stamp>.log | tail -40
python -m tools_py.parity.audio_corr logs/parity/<name>/A_gameread.wav \
    --ref-wav scripts/parity/refs/voice_ref.wav --rate 11025 --window-s 2 --bar 0.95
```

A host launch script is a file under `logs/`, in the shape of `logs/s7_audio_online.sh` (the online instrument set comes from `scripts/parity/env.sh`, which is **sourced, never executed**):

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:$HOME/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
. scripts/parity/env.sh
<the exports this run needs>
python -m tools_py.parity.online_match_ours --hold <s> --out logs/parity/<name>
rc=$?
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/<name>.done
exit $rc
```

## Global Constraints

- Branch `sprint-8`. Branch in the main checkout, never a worktree.
- **Everything is off unless `PS2X_MIC_DEVICE` or `PS2X_MIC_FAKE` is set.** With neither set, `lgaud.cpp` answers exactly what it answers today, byte for byte: `0x80000001` to every function but `0x10`, and the same `[lgaud:stub]` line for the first 32. The gate runs with neither set (`scripts/parity/env.sh` exports no mic knob), so **the gate must be unaffected**, and Task 2 Step 9's case asserts the off-path reply words are unchanged.
- **Every runtime change under a RED test first.** Each step that changes `lgaud.cpp`, `host_mic.cpp` or `ps2_iop_host.cpp` names the case that fails before it and passes after, and the exact failure text. A step that cannot state its RED says so in one sentence and names the launch or the dump that verifies it instead.
- **The arithmetic lives in a header, the device lives in the .cpp.** New logic goes into `third_party/ps2recomp/ps2xRuntime/include/runtime/mic_format.h` — header-only, `<cstdint>`/`<vector>`/`<string>`-grade dependencies, **no miniaudio, no raylib, no thread**, exactly as `runtime/gs/gs_gl_target_extent.h` is free of GL. That is what lets the resampler's and the WAV reader's cases run in CI, in the VM and on a machine with no microphone at all.
- **No `#ifdef _WIN32` is added by this goal.** `host_mic.cpp` has none today and Goal 1's Linux port must not need one because of this goal. If a change cannot be written without one, it stops and becomes a ruling.
- **Nothing in the IOP module reads the environment.** `lgaud.cpp` has no `getenv` and gains none: whether a microphone exists is a question it asks `IopHost` (`micAvailable()`), exactly as `snd989.cpp` asks `audioIsPlaying` (`snd989.cpp:1271`). This keeps the module testable with `Snd989TestHost`'s successor and keeps the knob in one place.
- **A missing microphone is never fatal.** `host_mic.cpp:250-256` already refuses to stop the game when the device will not open; a malformed `PS2X_MIC_FAKE` WAV, a rate the resampler will not accept and an `0x02 Open` for a device index the host does not have all take the same road: a line on stderr and "no device" to the game.
- `./build.sh test` exit 0 on the Windows host before any commit touching `third_party/ps2recomp/`, `tools_py/` or `scripts/`. **The three-stage gate PASS (3/3) before any commit touching `third_party/ps2recomp/ps2xRuntime/src/` or `third_party/ps2recomp/ps2xIOP/src/`** — which is Tasks 1, 2 and 5.
- Explicit pathspecs on every commit, never `git add -A`. `server/config/simulated.db` is **never** staged. `vm/` is never staged.
- Commit trailer, every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- LF line endings in every new file. New shell scripts are `chmod +x` and committed with the mode bit.
- **Python tests are `unittest`, never pytest.** `tools_py/tests/test_test_hygiene.py` fails the suite on a `test_*.py` outside `tools_py/tests/`, on any `import pytest`, and on a module-level `def test_`.
- **Reference WAVs are generated, never recorded.** `scripts/parity/refs/voice_ref.wav` is written by a committed generator (Task 1 Step 5) from a deterministic formula, so CI and the VM produce the same bytes and no one's recorded voice is committed to the repository.

---

## The recovered message block (this is the contract; do not re-derive it by guessing)

All lgaud calls share one 0x840-byte buffer, `DAT_003dcfb4`, passed as **both** send and receive (`game/analysis/socom2_game.elf.decomp.c:90871-90878` allocates it; `:90956` and every other call site pass it twice). Offsets are bytes from the start of that buffer.

| Offset | Width | Name | Direction | Verdict |
|---|---|---|---|---|
| 0x00 | 4 | `status` — returned verbatim as the client API's return value; 0 = success | reply | **ESTABLISHED** `:91035`, `:91105`, `:91333` |
| 0x04 | 4 | `state` — merged after *every* call as `DAT_003dcfb8 = (DAT_003dcfb8 & ~2) \| reply[0x04]`; bit1 = device present, bit0 = a latched "changed" event the game clears on read | reply | **ESTABLISHED** `:91037`, `:91108`, `:91755-91762` |
| 0x08 | 4 | `deviceIndex` (functions 0x01 and 0x02 only) | send | **ESTABLISHED** `:90955`, `:91027` |
| 0x0c | 4 | `handle` — send on every per-device function; **reply** on 0x02 | both | **ESTABLISHED** `:91063`, `:91036`, `:91357` |
| 0x10 | 1 | mixer channel byte (0x0d / 0x0e) | send | **ESTABLISHED** `:91491` |
| 0x11 | 1 | mixer level byte (0x0d / 0x0e) | send | **ESTABLISHED** `:91493` |
| 0x12 | 1 | flag byte, `param_2` of Read/Write/WriteVag; the live capture path always passes **1** | send | **ESTABLISHED** `:91100`, `:91626`, `:211484` |
| 0x20 | 4 | `byteCount` — requested on 0x08/0x09/0x15, returned on 0x08/0x09/0x12/0x13/0x15 | both | **ESTABLISHED** `:91101`, `:91107`, `:91334` |
| 0x20 | 0x14C | the device-info block (function 0x01 only) | reply | **ESTABLISHED** `:90959-90978` |
| 0x30 | n | PCM payload | reply on Read, send on Write | **ESTABLISHED** `:91106`, `:91145` |

Payload cap: `DAT_003dcfac = 0x800 - 0x30 = 0x7d0` (2000 bytes); every Read and Write refuses a larger count on the EE side (`:90880` sets it, `:91095` and `:91139` check it). **ESTABLISHED.**

### Per function

| Fn | Name | send size | recv size | mode | End fn | Verdict |
|---|---|---|---|---|---|---|
| 0x01 | Enumerate | 0x20 | 0x170 | sync | — | **ESTABLISHED** `:90956` |
| 0x02 | Open | 0x30 | 0x20 | sync | — | **ESTABLISHED** `:91033` |
| 0x03 | Close | 0x20 | 0x20 | sync | — | **ESTABLISHED** `:91063` |
| 0x04 | StartRecording | 0x20 | 0x20 | sync | — | **ESTABLISHED** `:91358` |
| 0x05 | unknown (shares StartRecording's error string) | 0x20 | 0x20 | sync | — | shape **ESTABLISHED** `:91384`; "StopRecording" **ASSUMED** |
| 0x06 / 0x07 / 0x11 | Start / Stop / ResumePlayback | 0x20 | 0x20 | sync | — | **ESTABLISHED** `:91411`, `:91438`, `:91465` |
| 0x08 | Read | **0x30** | `((n + 0x3f) >> 4) << 4` | sync | — | **ESTABLISHED** `:91102` |
| 0x08 | ARead | 0x30 | same | async | 0x245080 | **ESTABLISHED** `:91633` |
| 0x09 / 0x15 | Write / WriteVag | `((n + 0x3f) >> 4) << 4` | 0x30 | sync | — | **ESTABLISHED** `:91146`, `:91189` |
| 0x0b / 0x0c | Get / SetMixer (a 16-byte struct at +0x20; Get reads a u16 back at reply +0x2c) | 0x30 | 0x30 | sync | — | **ESTABLISHED** `:91234`, `:91274`, `:91240` |
| 0x0d / 0x0e | SetPlaybackVolume / SetRecordGain `(handle, u8 channel, u8 level)` | 0x20 | 0x20 | sync | — | shape **ESTABLISHED** `:91495`, `:91524`; names **ASSUMED** from their callers |
| 0x0f | AEnumHint | 0x20 | 0x20 | **async** | 0x245568 | **ESTABLISHED** `:91788` |
| 0x10 | Init | 0x20 | 0x30 | sync | — | **ESTABLISHED** `docs/KNOWN.md:101` |
| 0x12 / 0x13 | Get Available Recording / Remaining Playback Bytes | 0x20 | **0x30** | sync | — | **ESTABLISHED** `:91330`, `:91302` |
| 0x14 | PrepareForReboot (handle = -1) | 0x20 | 0x20 | sync | — | **ESTABLISHED** `:91552` |

### 0x01's device-info block (reply +0x20, 0x14C bytes)

| Offset in block | Width | Read as | Verdict |
|---|---|---|---|
| 0x00 .. 0x61 | 98 | **never read by any caller in the image** — the device name string | offsets **ESTABLISHED** as a negative (no reader exists anywhere); "name" **ASSUMED** |
| 0x62 | 1 | `entryCount`, the bound of the vendor-extension scan | **ESTABLISHED** `:247063`, `:247072` |
| 0x63 + 6n | 1 | entry id, handed back to the caller as the chosen value | **ESTABLISHED** `:247070` |
| 0x64 + 6n | 1 | must equal 1 | **ESTABLISHED** `:247069` |
| 0x65 + 6n | 1 | must equal 0x10 | **ESTABLISHED** `:247066` |
| 0x66 + 6n | 2 | range low, must be < 0x5623 | **ESTABLISHED** `:247066` |
| 0x68 + 6n | 2 | range high, must be > 0x5621 | **ESTABLISHED** `:247067` |
| — | — | the entry **stride of 6** against 7 bytes of fields is how Ghidra renders it | **ASSUMED** |

Only `FUN_0034ba60` (`:247050-247081`) reads any of it, and only to ask "does this device support Logitech feature 0x5622" (the same literal as the vendor call at `:247039`). `entryCount = 0` is a complete, valid answer meaning "no vendor extensions" (**R113**).

**How "one device" is expressed — ESTABLISHED.** Four callers walk the index upward and stop on a non-zero status: `FUN_001e7f98` (`:48334-48346`), `FUN_0023a730` (`:86588-86603`), `FUN_0034ba60` (`:247060-247078`), `FUN_0030fef0` (`:211684`, index 0 only). So "one device" = **status 0 for index 0 and 0x80000001 for every index >= 1**.

### 0x02's openparam (send +0x20, 14 bytes)

| openparam off | send off | Width | Name | Value the game sends | Verdict |
|---|---|---|---|---|---|
| 0x00 | 0x20 | 1 | `Mode` — the EE refuses to call at all if it is 0 | **2** (capture), **3** (capture + playback) | offset and guard **ESTABLISHED** `:91022`, `:91030`; the meaning of 2 vs 3 **ASSUMED** from which caller sends which |
| 0x01 | 0x21 | 1 | pad — no caller writes it | — | **ESTABLISHED** negative |
| 0x02 | 0x22 | 1 | record channels | **1** | offset **ESTABLISHED** `:48339`; name **ASSUMED** |
| 0x03 | 0x23 | 1 | record bits per sample | **0x10** | offset **ESTABLISHED** `:48340`; name **ASSUMED** |
| 0x04 | 0x24 | 2 | record sample rate | **0x2b11 = 11025** | offset **ESTABLISHED** `:48341`; name **ASSUMED** (it is the only 16-bit field whose value reads as a rate) |
| 0x06 | 0x26 | 2 | record buffer / latency | **500** | offset **ESTABLISHED** `:48342`; meaning **ASSUMED** |
| 0x08 | 0x28 | 1 | playback channels | from config `+0x10c8` | offset **ESTABLISHED** `:91031`, `:211690`; name **ASSUMED** |
| 0x09 | 0x29 | 1 | playback bits | from config `+0x10cc` | as above |
| 0x0a | 0x2a | 2 | playback sample rate | from config `+0x10d0` | as above |
| 0x0c | 0x2c | 2 | playback buffer / latency | from config `+0x10d8` | offset **ESTABLISHED** `:91032`; meaning **ASSUMED** |

The record/playback pairing of 0x02..0x07 against 0x08..0x0d is **ESTABLISHED** by the parallel config offsets `FUN_0030fef0` copies them from (`:211686-211694`); *which* half is record is **ASSUMED** from the capture-only callers filling the first half and leaving the second at zero.

Reply: `status` at 0x00, `state` at 0x04, **`handle` at 0x0c** (`*param_3 = DAT_003dcfb4[3]`, `:91036`). **ESTABLISHED.**

### The capture loop that is the whole proof (`:211455-211545`)

Per tick, when the state byte `*DAT_0045b718 == 3`:

1. If `DAT_0045b878 < 0x500`, the handle is not -1 and the "recording started" byte `DAT_0045b718[0x48]` is non-zero, call `0x08 Read(handle, 1, &DAT_0045b880 + fill, &count)` with `count = 0x500 - fill` going in and the **actual** count coming out; `fill += count`. (`:211478-211489`) **ESTABLISHED.**
2. When `fill` reaches **0x500 = 1280 bytes** — 640 samples at 11025 Hz mono s16, **58.05 ms** — it encodes **four** 0x140-byte (320-byte, 160-sample) blocks through `FUN_00310750` and resets `fill` to 0. (`:211492-211501`) **ESTABLISHED.** The codec is Nellymoser (`docs/research/23-frostfire-ground-probe.md:318,355,433-435`; its VU0 fast path is dead — the mode word at 0x1d55a0 is 0 in the ELF and in all 18 RDRAM images — so it runs scalar).
3. Every fifth pass it asks `FUN_003103d0` whether the level ran low or high and nudges the record gain with **`0x0e SetRecordGain(handle, 0, level)`**, clamped to 0x14..100, in steps of 5. (`:211504-211527`) **ESTABLISHED.** A module that refuses 0x0e leaves the game fighting its own AGC.
4. `DAT_0045b718[0x48]` is set to 1 only after `0x04 StartRecording` returns 0, and only when it was not already 1 (`:211163-211172`). **ESTABLISHED.** The condition that reaches that code (`bVar4` at `LAB_0030ee70`) is the push-to-talk question Task 3 answers.

**Consequences for the module:** the largest Read the live path ever asks for is **0x500**, comfortably inside the 0x7d0 payload cap; it asks about **17.2 times a second**; and it copes with a short return by simply not advancing. A module that returns 0 bytes when the ring is empty is correct, not a failure.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/include/runtime/mic_format.h` (new), `third_party/ps2recomp/ps2xRuntime/include/runtime/host_mic.h` (:5-7 the retracted assumption, :70-92 `HostMic`, :100-102 the env entry points), `third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp` (:160-235 the dump thread, :238-258 `startHostMicFromEnvironment`), `third_party/ps2recomp/ps2xIOP/include/ps2x/iop/iop_host.h` (:69-99, beside the audio seams), `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.h` (:47-52), `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.cpp` (:265-288), `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp` (:1228-1245 the `MicRing` case, :1405-1430 the WAV header cases), `scripts/parity/refs/make_voice_ref.py` (new) | **Task 1**: `IopHost::micAvailable()` / `micRead()`, the pure format header, `PS2X_MIC_FAKE`, `PS2X_MIC_GAMEREAD_DUMP`, and the dump thread turned into a tee |
| `third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp` (rewritten), `third_party/ps2recomp/ps2xIOP/src/builtin_profiles.cpp` (:121, read only), `third_party/ps2recomp/ps2xTest/src/socom2_lgaud_tests.cpp` (new), `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (:65, the source list), `logs/s8_voice_read.sh` (new) | **Task 2**: the service state machine against the block above — Enumerate / EnumHint / Open / StartRecording / Available / Read / Mixer / Close — and one single-instance launch that proves the game reaches 0x08 |
| `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp` (:345, read only), `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp` (:344-347, the two existing mic cases), `docs/research/35-voice-path.md` (new) | **Task 3**: the launcher wiring check, and the push-to-talk answer out of `:211140-211175` | <!-- docmaint: future -->
| `tools_py/parity/audio_corr.py` (:47 `read_wav`, :159 `correlate_arrays`, :304-330 the argument parser), `tools_py/parity/online_login_ours.py` (:57-66 `INSTANCES`), `tools_py/tests/test_audio_corr.py` (new), `logs/s8_voice_round.sh` (new), `logs/parity/s8_voice_round/` | **Task 4**: the driven two-instance round and the three dumps; `--ref-wav`; the >= 0.95 bar and the packets leaving A |
| `third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp` (the playback half), `third_party/ps2recomp/ps2xIOP/include/ps2x/iop/iop_host.h` (`micPlaybackWrite`), `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_audio.cpp`, `third_party/ps2recomp/ps2xTest/src/socom2_lgaud_tests.cpp` | **Task 5**: the other player heard through the PC's speakers — Write PCM into the 989snd mixer as an extra source |
| `docs/KNOWN.md` (:101), `docs/STATUS.md`, `docs/CURRENT_SPRINT.md` (:151-154), `docs/HUMAN_TASKS.md` (:93-110), this plan | **Task 6**: Goal 3 close-out |

---

## Task 1 — The host seam: `IopHost::micRead`, the pure format header, and a microphone that is a file (spec Goal 3: "Read serves HostMic's ring")

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/mic_format.h`, `scripts/parity/refs/make_voice_ref.py`
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/host_mic.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp`, `third_party/ps2recomp/ps2xIOP/include/ps2x/iop/iop_host.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.cpp`, `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`
- Read only, to confirm and record: `third_party/ps2recomp/ps2xIOP/src/modules/snd989.cpp:405,948,1271` (the three shapes of host call this copies), `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_target_extent.h` (the header-only precedent), `third_party/ps2recomp/build-clang/_deps/raylib-src/src/raudio.c:166-173` (`MA_NO_WAV`)
- Test: new MiniTest cases in `socom2_audio_tests.cpp`, all device-free

**Interfaces:**
- `MicFormat { uint32_t rate; uint8_t channels; uint8_t bits; }` and `MicFormat::bytesPerFrame() -> size_t` (`channels * bits / 8`), `MicFormat::supported() -> bool` (**channels == 1, bits == 16, 4000 <= rate <= 48000**; anything else is refused at Open, R114).
- `micResampleLinear(const int16_t *in, size_t inFrames, uint32_t inRate, int16_t *out, size_t outFrames, uint32_t outRate, double &phase) -> size_t` — mono linear interpolation with a carried fractional phase so consecutive calls do not click at the seam; returns frames written. Pure, header-only, no allocation.
- `micFramesNeeded(size_t outFrames, uint32_t inRate, uint32_t outRate, double phase) -> size_t` — how many input frames the above will consume. The inverse arithmetic lives beside it so `HostMic::read` is asked for exactly the right number and never over-drains the ring.
- `micWavRead(const std::string &path, std::vector<int16_t> &samples, MicFormat &format, std::string &error) -> bool` — a 44-byte-header PCM WAV reader that accepts the exact shape `hostMicWavHeader` writes, tolerates the `0xFFFFFFFF` "unknown size" both fields carry on a killed run (`host_mic.h:94-98`) by reading to end of file, and refuses anything that is not 16-bit PCM with a reason in `error`.
- `micWavWrite`-side: unchanged; `hostMicWavHeader` is reused for every dump this goal writes.
- `HostMic::startFromFile(const std::string &wavPath)` — the fake source: reads the WAV once into memory through `micWavRead`, resamples it to `kSampleRate` once, and feeds the ring from a thread at real time (1024 frames every 64 ms), looping. `running()` is true exactly as for a device, and `read()` is the same call.
- `HostMic *hostMic()` — a free function in `host_mic.cpp` returning the process's `HostMic` or `nullptr`. **This does not exist today**: `g_hostMic` is a file-static at `host_mic.cpp:161` with no accessor, so nothing outside the file can reach the ring. It is the missing link between the runtime and the module.
- `IopHost::micAvailable() const -> bool` and `IopHost::micRead(int16_t *out, size_t frames) -> size_t`, both `virtual` with a no-op default, added beside `audioPcmPosition`/`audioIsPlaying` at `iop_host.h:85-98` and overridden in `PS2IopHostAdapter`.
- Knobs: `PS2X_MIC_FAKE=<path.wav>` (a microphone that is a file; takes precedence over `PS2X_MIC_DEVICE`, and works with `PS2X_MIC_DEVICE` unset so CI and the VM need no hardware), `PS2X_MIC_GAMEREAD_DUMP=<path.wav>` (Task 2 writes it), `PS2X_MIC_DUMP` (unchanged name, new mechanism).

**Steps:**

- [ ] **Step 1: RED — the format arithmetic, before the header exists.** Add to `socom2_audio_tests.cpp`, in the audio suite next to the `MicRing` case at `:1228`:

```cpp
        tc.Run("micResampleLinear carries its phase across calls and never clicks at the seam", [](TestCase &t)
        {
            // A 16 kHz ramp resampled to 11025 Hz: the game's rate (decomp :48341, 0x2b11).
            std::vector<int16_t> in(1600);
            for (size_t i = 0; i < in.size(); ++i)
                in[i] = static_cast<int16_t>(i * 10);
            MicFormat fmt{11025u, 1u, 16u};
            t.IsTrue(fmt.supported(), "11025 Hz mono 16-bit is what the game asks for");
            t.Equals(fmt.bytesPerFrame(), size_t{2}, "mono 16-bit is two bytes a frame");

            std::vector<int16_t> out(1102);
            double phase = 0.0;
            const size_t firstHalf = micResampleLinear(in.data(), 800u, 16000u, out.data(), 551u, 11025u, phase);
            t.Equals(firstHalf, size_t{551}, "the first half fills");
            t.IsTrue(phase > 0.0, "the fractional position is carried, not dropped");
            const size_t consumed = micFramesNeeded(551u, 16000u, 11025u, 0.0);
            t.IsTrue(consumed <= 800u, "the arithmetic never asks for more input than it was given");

            const size_t secondHalf = micResampleLinear(in.data() + consumed, 800u - consumed + 800u, 16000u,
                                                        out.data() + 551u, 551u, 11025u, phase);
            t.Equals(secondHalf, size_t{551}, "the second half fills");
            // A ramp stays a ramp: every step is positive and within one input step of the last.
            for (size_t i = 1; i < out.size(); ++i)
                t.IsTrue(out[i] > out[i - 1], "the resampled ramp is still monotonic across the seam");
        });

        tc.Run("MicFormat refuses what we cannot serve", [](TestCase &t)
        {
            t.IsTrue(!MicFormat{11025u, 2u, 16u}.supported(), "stereo capture is refused");
            t.IsTrue(!MicFormat{11025u, 1u, 8u}.supported(), "8-bit capture is refused");
            t.IsTrue(!MicFormat{96000u, 1u, 16u}.supported(), "a rate outside 4000..48000 is refused");
            t.IsTrue(MicFormat{16000u, 1u, 16u}.supported(), "the ring's own rate is of course supported");
        });
```

  Run: `cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8`
  Expected failure: `error: unknown type name 'MicFormat'` and `error: use of undeclared identifier 'micResampleLinear'` from `socom2_audio_tests.cpp`. **The build must fail before Step 2 is written.**

- [ ] **Step 2: GREEN — `runtime/mic_format.h`.** Header-only, no miniaudio, no thread, no allocation in the hot function:

```cpp
#pragma once
// Sprint 8 Goal 3 Task 1: the microphone arithmetic, kept free of any device so ps2x_tests can check it in
// CI, in the VM and on a machine with no microphone -- the same rule runtime/gs/gs_gl_target_extent.h follows
// for GL. RETRACTS host_mic.h's "16 kHz" FORMAT ASSUMPTION: the game asks lgAudOpen for 11025 Hz mono 16-bit
// (game/analysis/socom2_game.elf.decomp.c:48341, openparam+0x04 = 0x2b11), so a resample is always needed.
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

struct MicFormat
{
    uint32_t rate = 11025u;
    uint8_t channels = 1u;
    uint8_t bits = 16u;

    [[nodiscard]] size_t bytesPerFrame() const { return static_cast<size_t>(channels) * bits / 8u; }
    [[nodiscard]] bool supported() const
    {
        return channels == 1u && bits == 16u && rate >= 4000u && rate <= 48000u;
    }
};

// Mono linear interpolation with a carried fractional phase, so back-to-back calls join without a step.
// Returns frames written. `phase` is the position, in input frames, of the next output sample.
inline size_t micResampleLinear(const int16_t *in, size_t inFrames, uint32_t inRate,
                                int16_t *out, size_t outFrames, uint32_t outRate, double &phase)
{
    if (in == nullptr || out == nullptr || inFrames == 0u || outFrames == 0u || inRate == 0u || outRate == 0u)
        return 0u;
    if (inRate == outRate)
    {
        const size_t n = inFrames < outFrames ? inFrames : outFrames;
        for (size_t i = 0; i < n; ++i)
            out[i] = in[i];
        return n;
    }
    const double step = static_cast<double>(inRate) / static_cast<double>(outRate);
    size_t written = 0u;
    while (written < outFrames)
    {
        const double pos = phase;
        const size_t i0 = static_cast<size_t>(pos);
        if (i0 + 1u >= inFrames)
            break;
        const double frac = pos - static_cast<double>(i0);
        const double v = static_cast<double>(in[i0]) * (1.0 - frac) + static_cast<double>(in[i0 + 1u]) * frac;
        out[written++] = static_cast<int16_t>(v < -32768.0 ? -32768.0 : (v > 32767.0 ? 32767.0 : v));
        phase += step;
    }
    phase -= static_cast<double>(static_cast<size_t>(phase));   // keep only the fraction; the caller drops the frames
    return written;
}

// How many input frames micResampleLinear will consume to produce `outFrames`, starting at `phase`.
// One extra frame is added because the interpolation reads in[i0 + 1].
inline size_t micFramesNeeded(size_t outFrames, uint32_t inRate, uint32_t outRate, double phase)
{
    if (outFrames == 0u || inRate == 0u || outRate == 0u)
        return 0u;
    const double step = static_cast<double>(inRate) / static_cast<double>(outRate);
    const double end = phase + step * static_cast<double>(outFrames);
    return static_cast<size_t>(end) + 2u;
}

// The 44-byte PCM WAV hostMicWavHeader writes, read back. dataSize == 0xFFFFFFFF means "read to the end of the
// file" (host_mic.h:94-98: a killed run leaves the two size fields unpatched). 16-bit PCM only.
bool micWavRead(const std::string &path, std::vector<int16_t> &samples, MicFormat &format, std::string &error);
```

  `micWavRead` is declared here and defined in `host_mic.cpp` (it touches `<cstdio>`, which the header stays free of).
  Run: `cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"`
  Expected: both new cases pass; `[  FAILED  ] 0`.

- [ ] **Step 3: RED then GREEN — the WAV reader, round-tripped against our own writer.** Case, next to the existing `hostMicWavHeader` case at `socom2_audio_tests.cpp:1405`:

```cpp
        tc.Run("micWavRead reads back what hostMicWavHeader wrote, patched sizes or not", [](TestCase &t)
        {
            const std::string path = std::string(testTempDir()) + "/mic_roundtrip.wav";
            std::vector<int16_t> written(4410);
            for (size_t i = 0; i < written.size(); ++i)
                written[i] = static_cast<int16_t>((i % 128) * 200 - 12800);
            {
                uint8_t header[44] = {};
                hostMicWavHeader(header, static_cast<uint32_t>(written.size() * 2u), 11025u);
                std::FILE *f = std::fopen(path.c_str(), "wb");
                t.IsTrue(f != nullptr, "the temp WAV opens for writing");
                std::fwrite(header, 1, 44, f);
                std::fwrite(written.data(), 2, written.size(), f);
                std::fclose(f);
            }
            std::vector<int16_t> read;
            MicFormat fmt{};
            std::string error;
            t.IsTrue(micWavRead(path, read, fmt, error), "a well-formed 16-bit mono WAV reads: " + error);
            t.Equals(fmt.rate, 11025u, "the rate comes out of the header, not out of a default");
            t.Equals(read.size(), written.size(), "every sample comes back");
            t.Equals(read[100], written[100], "and they are the same samples");

            std::vector<int16_t> nothing;
            MicFormat bad{};
            std::string reason;
            t.IsTrue(!micWavRead(path + ".missing", nothing, bad, reason), "a missing file is refused");
            t.IsTrue(!reason.empty(), "and it says why, because that string reaches the player on stderr");
        });
```

  Expected failure before the implementation: `error: use of undeclared identifier 'micWavRead'`. Implement it in `host_mic.cpp` beside `hostMicWavHeader`: check `RIFF`/`WAVE`/`fmt `/`data`, require `audioFormat == 1` and `bits == 16`, take `channels` and `rate` from the header, and when the `data` size is `0` or `0xFFFFFFFF` read to end of file.

- [ ] **Step 4: `PS2X_MIC_FAKE` — a microphone that is a file.** In `host_mic.h`, beside `start`:

```cpp
    // PS2X_MIC_FAKE=<file.wav>: the capture device replaced by a WAV, looped in real time. This is what gives
    // CI, the Linux VM and the driven harness a "microphone" with a KNOWN signal, so the game-read dump can be
    // correlated against it without a human speaking (Sprint 8 Goal 3 Task 1).
    bool startFromFile(const std::string &wavPath);
```

  In `host_mic.cpp`: read the file once through `micWavRead`, resample it to `kSampleRate` once with `micResampleLinear` (phase carried across the whole file), then run a feeder thread that writes 1024 frames into the ring every 64 ms and wraps at the end. `m_running` is set exactly as `start()` sets it; `stop()` joins the feeder. In `startHostMicFromEnvironment()` (`host_mic.cpp:238`), `PS2X_MIC_FAKE` is checked **first** and, when it is set, `PS2X_MIC_DEVICE` is not read at all:

```cpp
void startHostMicFromEnvironment()
{
    const char *fake = std::getenv("PS2X_MIC_FAKE");
    const char *name = std::getenv("PS2X_MIC_DEVICE");
    if ((fake == nullptr || fake[0] == 0) && (name == nullptr || name[0] == 0))
        return;   // the default, and what the gate runs with: no capture source of any kind
    if (g_hostMic != nullptr)
        return;
    g_hostMic = new HostMic();
    const bool ok = (fake != nullptr && fake[0] != 0) ? g_hostMic->startFromFile(fake) : g_hostMic->start(name);
    if (!ok)
    {
        // Never fatal: a missing microphone must not stop the game starting.
        std::cerr << "[mic] " << (fake ? "PS2X_MIC_FAKE" : "PS2X_MIC_DEVICE") << ": " << g_hostMic->error()
                  << " (" << (fake ? fake : name) << ")" << std::endl;
        delete g_hostMic;
        g_hostMic = nullptr;
        return;
    }
    std::cout << "[mic] capturing \"" << (fake ? fake : name) << "\" at " << HostMic::kSampleRate << " Hz mono"
              << (fake ? " (fake source)" : "") << std::endl;
    ...
}
```

  **Ruling R115: `PS2X_MIC_FAKE` beats `PS2X_MIC_DEVICE` when both are set** — because every driven run sets the fake one deliberately and a stale device name in the environment must not silently win. Cost if wrong: an operator who wanted the real device with a leftover `PS2X_MIC_FAKE` gets the file, and the `[mic] ... (fake source)` line says so on the first line of the log.
  RED: a case that calls `startFromFile` on the Step 3 round-trip WAV, sleeps 200 ms, and asserts `read()` returns frames. Expected failure: `error: no member named 'startFromFile' in 'HostMic'`.

- [ ] **Step 5: the reference WAV and its generator.** `scripts/parity/refs/make_voice_ref.py` writes `scripts/parity/refs/voice_ref.wav`: **20 seconds, 11025 Hz, mono, 16-bit**, a deterministic signal built to be easy to correlate and hard to match by accident — a 300 Hz carrier amplitude-modulated by a 3 Hz envelope, plus a pseudo-random binary sequence at 40 Hz seeded from a constant, scaled to peak 0.6. No `numpy` beyond what `tools_py` already requires; header written by the same 44-byte layout `hostMicWavHeader` uses, so `micWavRead` reads it.

```bash
python scripts/parity/refs/make_voice_ref.py --out scripts/parity/refs/voice_ref.wav
python -c "import wave; w=wave.open('scripts/parity/refs/voice_ref.wav'); print(w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes())"
```
  Expected: `11025 1 2 220500`. Commit the generator **and** the WAV (441 KB), so a machine with no Python numpy can still run the proof.

- [ ] **Step 6: fix the dump thread — it must tee, not consume.** `host_mic.cpp:163-165` states that the `PS2X_MIC_DUMP` thread is the ring's only consumer, and `:189-196` drains it. Once the game reads, that is a race that silently halves both files. Change the mechanism, not the knob: the dump gets its **own** `MicRing`, written from `micDataCallback` (`host_mic.cpp:57-66`) alongside the main ring, and its thread drains only that. RED, in `socom2_audio_tests.cpp`:

```cpp
        tc.Run("the PS2X_MIC_DUMP tee does not steal frames from the game's ring", [](TestCase &t)
        {
            HostMic mic;
            t.IsTrue(mic.startFromFile(std::string(testTempDir()) + "/mic_roundtrip.wav"), mic.error());
            mic.startDumpTee(std::string(testTempDir()) + "/mic_tee.wav");
            std::this_thread::sleep_for(std::chrono::milliseconds(300));
            std::vector<int16_t> block(4096);
            const size_t got = mic.read(block.data(), block.size());
            t.IsTrue(got > 1000u, "the game's read still gets the frames the dump also wrote");
            mic.stop();
        });
```
  Expected failure: `error: no member named 'startDumpTee' in 'HostMic'`. Then implement the second ring and move `startDump`'s body onto it.

- [ ] **Step 7: the `IopHost` seam.** In `iop_host.h`, immediately after `audioNotify` (`:95-98`), with the same comment discipline as its neighbours:

```cpp
        // Sprint 8 Goal 3: the USB headset's capture side. lgaud.cpp asks these two questions and nothing
        // else -- it never opens a device and never reads the environment, exactly as snd989.cpp asks
        // audioIsPlaying rather than owning a mixer. micRead() returns frames of 16 kHz mono s16 from
        // HostMic's ring; the module resamples to whatever rate lgAudOpen asked for.
        [[nodiscard]] virtual bool micAvailable() const { return false; }
        virtual size_t micRead(int16_t *out, size_t frames)
        {
            (void)out; (void)frames;
            return 0u;
        }
```

  In `ps2_iop_host.h` (beside the `audioPcmPosition` override at `:51`) and `ps2_iop_host.cpp` (beside `audioPcmPosition` at `:285`):

```cpp
bool PS2IopHostAdapter::micAvailable() const
{
    const HostMic *mic = hostMic();
    return mic != nullptr && mic->running();
}

size_t PS2IopHostAdapter::micRead(int16_t *out, size_t frames)
{
    HostMic *mic = hostMic();
    return mic == nullptr ? 0u : mic->read(out, frames);
}
```

  and add the accessor to `host_mic.h` / `host_mic.cpp`:

```cpp
// The process's capture source, or nullptr when none was started. g_hostMic is a file static with no accessor
// today, which is why nothing outside host_mic.cpp can reach the ring (Sprint 8 Goal 3 Task 1).
HostMic *hostMic();
```

  RED: a case that constructs a `Snd989TestHost` (which now inherits the two defaults) and asserts `micAvailable()` is false and `micRead` returns 0, so the **off** path is pinned before the on path exists. Expected failure: `error: no member named 'micAvailable' in 'ps2x::iop::IopHost'`.

- [ ] **Step 8: full suite, then commit.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "goal 3 task 1 suite" -- ./build.sh test
git commit -m "feat(mic): the host seam for the headset -- IopHost::micAvailable/micRead, a pure format header (11025 Hz is what the game asks for, retracting the 16 kHz assumption), PS2X_MIC_FAKE so CI and the VM have a microphone, and PS2X_MIC_DUMP teed instead of consuming (Sprint 8 Goal 3 Task 1)" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/mic_format.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/host_mic.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp \
  third_party/ps2recomp/ps2xIOP/include/ps2x/iop/iop_host.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.cpp \
  third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp \
  scripts/parity/refs/make_voice_ref.py scripts/parity/refs/voice_ref.wav
git push
```
  The message's first clause is the retraction; the trailer is `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

**STOP RULE (from the brief).** If the argument structs for Read (0x08) and Available (0x12) cannot be recovered with confidence — they *are* recovered above, with file:line for every field, so this fires only if the reviewer's independent re-derivation in Task 2 Step 1 **disagrees** — stop after this task, file the listing of what the game asked for in `docs/KNOWN.md` and `docs/research/35-voice-path.md`, and do not write a state machine against a guess. <!-- docmaint: future -->

---

## Task 2 — The lgaud service, against the recovered block (spec Goal 3: "Enumerate answers one device ... Open succeeds ... Read serves HostMic's ring")

**Files:**
- Create: `third_party/ps2recomp/ps2xTest/src/socom2_lgaud_tests.cpp`, `logs/s8_voice_read.sh`
- Modify: `third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp` (rewritten), `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (:65, add the new source)
- Read only, to confirm and record: `game/analysis/socom2_game.elf.decomp.c:90811-91800` and `:211455-211545`, `third_party/ps2recomp/ps2xIOP/src/modules/snd989.cpp:600-640` (how a service zeroes a receive buffer before replying), `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp:222-256` (`Snd989HarnessT`)
- Test: `socom2_lgaud_tests.cpp`, every case device-free through a fake `IopHost`

**Interfaces:**
- `LgAudService` keeps: `bool m_open`, `uint32_t m_handle`, `MicFormat m_format`, `bool m_recording`, `uint64_t m_bytesRead`, `bool m_hintSent`, `std::array<uint8_t, 4> m_gain`, `std::array<uint8_t, 16> m_mixer`, `double m_phase`, `std::vector<int16_t> m_scratch`.
- Constants, all named after the table above: `kMsgStatus = 0x00`, `kMsgState = 0x04`, `kMsgDeviceIndex = 0x08`, `kMsgHandle = 0x0c`, `kMsgMixerChannel = 0x10`, `kMsgMixerLevel = 0x11`, `kMsgFlag = 0x12`, `kMsgByteCount = 0x20`, `kMsgOpenParam = 0x20`, `kMsgPayload = 0x30`, `kMaxPayload = 0x7d0`, `kEnumBlock = 0x20`, `kEnumBlockBytes = 0x14c`, `kEnumEntryCount = 0x62`.
- State words: `kStatePresent = 2`, `kStateChanged = 1`, `kStatusOk = 0`, `kStatusNoDevice = 0x80000001`, `kStatusBadParam = 0x80000004`.
- `PS2X_MIC_GAMEREAD_DUMP` is **not** read by the module: the module hands the bytes it served to `IopHost` (Task 1's `micRead` returns them, and the runtime writes the dump from the same call), so the knob stays on the runtime side and the module stays environment-free.

**Steps:**

- [ ] **Step 1: re-derive three offsets before writing a line of code.** The reviewer's independent check, and the thing the whole task rests on. Put the output in the ledger verbatim.

```bash
sed -n '91095,91110p' game/analysis/socom2_game.elf.decomp.c   # 0x08 Read: sizes, +0x12, +0x20, +0x30
sed -n '91025,91040p' game/analysis/socom2_game.elf.decomp.c   # 0x02 Open: openparam copy, handle at +0x0c
sed -n '48336,48346p'  game/analysis/socom2_game.elf.decomp.c   # the openparam the game builds: 0x2b11
sed -n '91752,91765p' game/analysis/socom2_game.elf.decomp.c   # 0x0f's end function: the state-word merge
grep -n "FUN_00244820(" game/analysis/socom2_game.elf.decomp.c  # 0x12: definition only, no caller
```
  Expected, and record it exactly so: Read sends 0x30 and receives `((n+0x3f)>>4)<<4`, with the count at `+0x20` and the payload at `+0x30`; Open copies 14 bytes of openparam to `+0x20` and reads the handle back from `+0x0c`; the openparam is `{2, _, 1, 0x10, 0x2b11, 500}`; `0x0f`'s end function merges `reply+0x04` into `DAT_003dcfb8` and clears the latched bit when the merged value is exactly 1; `0x12` has no caller. **If any of those five disagrees with this plan's tables, stop and raise it before Step 2** — the stop rule at the end of Task 1 applies.

- [ ] **Step 2: RED — the harness and the sequence the game actually runs.** New file `socom2_lgaud_tests.cpp`, with an `LgAudTestHost` (an `IopHost` with guest memory, copied from `Snd989TestHost` at `socom2_audio_tests.cpp:106-178`, plus a scripted microphone) and an `LgAudHarness` (`Snd989HarnessT`'s shape at `:222-254`, but `kSid = 0x50494c42` and the **send and receive buffers at the same address**, because that is what the game does):

```cpp
    class LgAudTestHost final : public LgAudTestHostBase
    {
    public:
        std::vector<int16_t> micFrames;      // 16 kHz mono, what the "device" holds
        size_t micCursor = 0u;
        bool micOn = false;

        [[nodiscard]] bool micAvailable() const override { return micOn; }
        size_t micRead(int16_t *out, size_t frames) override
        {
            const size_t have = micFrames.size() - micCursor;
            const size_t take = frames < have ? frames : have;
            for (size_t i = 0; i < take; ++i)
                out[i] = micFrames[micCursor + i];
            micCursor += take;
            return take;
        }
    };

    struct LgAudHarness
    {
        static constexpr uint32_t kSid = 0x50494c42u;      // 'BLIP'
        static constexpr uint32_t kBuf = 0x2000u;          // send AND receive: the game passes DAT_003dcfb4 twice

        LgAudTestHost host;
        std::unique_ptr<ps2x::iop::detail::IopService> service{ps2x::iop::detail::createLgAudService(host)};

        uint32_t call(uint32_t fno, uint32_t sendBytes, uint32_t recvBytes)
        {
            ps2x::iop::RpcRequest request{};
            request.sid = kSid;
            request.function = fno;
            request.send = {kBuf, sendBytes};
            request.receive = {kBuf, recvBytes};
            (void)service->handleRpc(request);
            return word(0x00);
        }
        void put32(uint32_t off, uint32_t v) { (void)host.writeGuest(kBuf + off, &v, sizeof(v)); }
        void put8(uint32_t off, uint8_t v)   { (void)host.writeGuest(kBuf + off, &v, sizeof(v)); }
        uint32_t word(uint32_t off) const
        {
            uint32_t v = 0u;
            (void)host.readGuest(kBuf + off, &v, sizeof(v));
            return v;
        }
    };
```

  and the case that is the whole task in one sequence — the game's own order, from `:48334-48347` and `:211163-211489`:

```cpp
        tc.Run("Enumerate/Open/StartRecording/Read returns the fake microphone's bytes, resampled to 11025", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            h.host.micFrames.resize(16000);                        // one second at the ring's rate
            for (size_t i = 0; i < h.host.micFrames.size(); ++i)
                h.host.micFrames[i] = static_cast<int16_t>(i % 1000 * 30 - 15000);

            h.put32(0x08, 0u);
            t.Equals(h.call(0x01, 0x20u, 0x170u), 0u, "Enumerate(0) answers one device");
            uint8_t entries = 0xffu;
            (void)h.host.readGuest(LgAudHarness::kBuf + 0x20u + 0x62u, &entries, 1u);
            t.Equals(uint32_t(entries), 0u, "and no vendor-extension entries (decomp :247063)");
            h.put32(0x08, 1u);
            t.Equals(h.call(0x01, 0x20u, 0x170u), 0x80000001u, "Enumerate(1) answers no device: that is 'one device'");

            h.put32(0x08, 0u);
            h.put8(0x20, 2u);      // Mode = capture
            h.put8(0x22, 1u);      // channels
            h.put8(0x23, 0x10u);   // bits
            uint16_t rate = 0x2b11u;                               // 11025, decomp :48341
            (void)h.host.writeGuest(LgAudHarness::kBuf + 0x24u, &rate, sizeof(rate));
            t.Equals(h.call(0x02, 0x30u, 0x20u), 0u, "Open succeeds");
            const uint32_t handle = h.word(0x0c);
            t.IsTrue(handle != 0u && handle != 0xffffffffu, "and hands back a usable handle at +0x0c");
            t.Equals(h.word(0x04) & 2u, 2u, "the state word says a device is present");

            h.put32(0x0c, handle);
            t.Equals(h.call(0x04, 0x20u, 0x20u), 0u, "StartRecording succeeds");

            h.put32(0x0c, handle);
            h.put8(0x12, 1u);
            h.put32(0x20, 0x500u);                                  // what the capture loop asks for (:211485)
            t.Equals(h.call(0x08, 0x30u, 0x530u), 0u, "Read succeeds");
            const uint32_t got = h.word(0x20);
            t.IsTrue(got > 0u && got <= 0x500u, "it returns at most what was asked for");
            t.Equals(got % 2u, 0u, "and a whole number of 16-bit frames");
            int16_t first = 0;
            (void)h.host.readGuest(LgAudHarness::kBuf + 0x30u, &first, sizeof(first));
            t.IsTrue(first != 0, "the payload at +0x30 carries the microphone, not zeros");
            // 0x500 bytes at 11025 Hz is 640 frames; 16 kHz gives at most 16000 frames, so one call is short of
            // the full request and that is correct -- the game simply does not advance (:211489).
            t.IsTrue(h.word(0x00) == 0u, "a short read is a success, not an error");
        });
```

  Run: `cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8`
  Expected failure, first the link/compile: `error: no member named 'micAvailable' in ...` is already gone after Task 1, so the real first failure is `socom2_lgaud_tests.cpp` not being in the build — add it to `ps2xTest/CMakeLists.txt` at `:65`, then the case fails at runtime with `Enumerate(0) answers one device` (`expected 0, got 2147483649`), because today's module answers `0x80000001` to everything but `0x10`.

- [ ] **Step 3: GREEN — read the send block first, then reply.** The one structural rule (R112). The rewritten `handleRpc` opens with:

```cpp
                // R112: the EE passes DAT_003dcfb4 as BOTH send and receive (decomp :90956, :91033, :91102).
                // Every field we need must be copied out BEFORE a single reply word is written, or we would
                // clobber the handle and the byte count we are about to use.
                Request in{};
                in.function = request.function;
                in.deviceIndex = readWord(request.send, kMsgDeviceIndex);
                in.handle      = readWord(request.send, kMsgHandle);
                in.byteCount   = readWord(request.send, kMsgByteCount);
                in.flag        = readByte(request.send, kMsgFlag);
                in.mixerChannel = readByte(request.send, kMsgMixerChannel);
                in.mixerLevel   = readByte(request.send, kMsgMixerLevel);
                if (request.function == kRpcOpen)
                    (void)m_host.readGuest(request.send.address + kMsgOpenParam, in.openParam.data(), in.openParam.size());
                else if (request.function == kRpcWrite || request.function == kRpcWriteVag)
                    readPayload(request.send, in);
```
  and only then zeroes the receive buffer and dispatches. RED for this specific rule: a case that pre-loads `+0x20` with the requested count and `+0x0c` with the handle and asserts the reply's `+0x20` is the *served* count while the served bytes match the handle that was sent — an implementation that zeroes first fails with `Read succeeds` -> `expected 0, got 2147483649` (handle 0 is not open).

- [ ] **Step 4: GREEN — Enumerate (0x01) and EnumHint (0x0f).** Enumerate: `deviceIndex != 0` or `!m_host.micAvailable()` -> `status = kStatusNoDevice`, `state = 0`. Otherwise `status = 0`, `state = kStatePresent`, and a `kEnumBlockBytes`-byte block at `kEnumBlock` whose first 98 bytes are the NUL-terminated name `"SOCOM Unzipped Headset"` and whose `kEnumEntryCount` byte is **0** (R113: no Logitech vendor extensions; the only reader, `FUN_0034ba60` at `:247060`, then scans nothing and moves on). The receive buffer is 0x170, so the block fits with 0x20 of header in front of it.

  EnumHint (0x0f, async): the reply is one word. `state = kStatePresent | kStateChanged` the **first** time after a device appears, `kStatePresent` every time after (`m_hintSent`). The EE's end function (`:91755-91762`) merges it and clears the latch, so a "changed" that is repeated forever makes the game re-enumerate forever — which is exactly the 5,316-poll pathology in `docs/KNOWN.md:101`, only with a device. Case:

```cpp
        tc.Run("EnumHint says changed once and present thereafter", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            (void)h.call(0x0f, 0x20u, 0x20u);
            t.Equals(h.word(0x04), 3u, "first hint: present (2) + changed (1), decomp :91757");
            for (int i = 0; i < 5; ++i)
                (void)h.call(0x0f, 0x20u, 0x20u);
            t.Equals(h.word(0x04), 2u, "and steady at present, so the game stops re-enumerating");
        });
```

- [ ] **Step 5: GREEN — Open (0x02) and Close (0x03) / PrepareForReboot (0x14).** Open: refuse with `kStatusNoDevice` when `deviceIndex != 0` or no microphone; decode the openparam into a `MicFormat` from bytes 2, 3 and the u16 at 4; refuse with `kStatusBadParam` when `!format.supported()` (R114) and log the refused triple once; otherwise allocate `m_handle = m_host.allocateIopHandle(IopHandleKind::RpcPacket) | 0x4c470000u` (a value that is neither 0 nor -1, the two the game tests), store the format, set `m_open`, write `handle` to `kMsgHandle` and `state = kStatePresent`. Log once, at Info:

```cpp
                    std::ostringstream m;
                    m << "[lgaud] lgAudOpen mode=" << int(in.openParam[0]) << " rec=" << int(in.openParam[2])
                      << "ch/" << int(in.openParam[3]) << "bit/" << m_format.rate << "Hz"
                      << " play=" << int(in.openParam[8]) << "ch/" << int(in.openParam[9]) << "bit/"
                      << (in.openParam[10] | (in.openParam[11] << 8)) << "Hz -> handle 0x" << std::hex << m_handle;
                    m_host.log(LogLevel::Info, m.str());
```
  That one line is the first time this project has ever seen the game's real openparam, so it goes in the run log and into `docs/KNOWN.md` in Task 6. Close and PrepareForReboot clear `m_open`, `m_recording` and `m_handle`, answer 0, and leave the device alone (the runtime owns `HostMic`'s lifetime, `ps2_runtime.cpp:590,2887`).

- [ ] **Step 6: GREEN — StartRecording (0x04), 0x05, and the playback family accepted.** `0x04`: refuse unless `m_open` and the handle matches; set `m_recording`, reset `m_bytesRead` and `m_phase`, answer 0. `0x05`, `0x06`, `0x07`, `0x11`: answer 0 and record the transition, with `0x05` treated as StopRecording (**ASSUMED**, `docs/KNOWN.md:101`) — it clears `m_recording` and nothing else, which is harmless if the guess is wrong because the game only ever calls it on the way out. `0x09` / `0x15` Write and `0x13` RemainingPlaybackBytes: accepted, counted, the payload written to `PS2X_MIC_DUMP_PLAYBACK` through the host when that dump is open and **discarded otherwise** — hearing the other player is Task 5, deliberately after the capture path is proven. `0x13` answers 0 remaining, so the game never waits on us.

- [ ] **Step 7: GREEN — Read (0x08) and GetAvailableRecordingBytes (0x12).** The core:

```cpp
                // The game asks for `byteCount` bytes at the rate it opened with; our ring is 16 kHz mono s16.
                // Frames out = bytes / 2 (MicFormat::supported() has already pinned mono 16-bit).
                const uint32_t asked = std::min<uint32_t>(in.byteCount, kMaxPayload);
                const uint32_t roomInReply = request.receive.size > kMsgPayload
                                                 ? request.receive.size - kMsgPayload : 0u;
                const size_t wantFrames = std::min<uint32_t>(asked, roomInReply) / 2u;
                const size_t needFrames = micFramesNeeded(wantFrames, HostMic::kSampleRate, m_format.rate, m_phase);
                m_scratch.resize(needFrames);
                const size_t gotFrames = m_host.micRead(m_scratch.data(), needFrames);
                m_out.resize(wantFrames);
                const size_t outFrames = micResampleLinear(m_scratch.data(), gotFrames, HostMic::kSampleRate,
                                                           m_out.data(), wantFrames, m_format.rate, m_phase);
                const uint32_t bytes = static_cast<uint32_t>(outFrames * 2u);
                ...                                             // reply words first, then the payload
                (void)m_host.writeGuest(request.receive.address + kMsgPayload, m_out.data(), bytes);
```
  with `status = 0`, `state = kStatePresent`, `byteCount = bytes`, and `bytes` allowed to be 0 (see the capture loop's point 1: the game simply does not advance). `0x12` answers the same arithmetic without consuming: `available_bytes = frames_in_ring * outRate / 16000 * 2`, clamped to `kMaxPayload`. Its case asserts the clamp and that it does **not** move the ring cursor:

```cpp
        tc.Run("GetAvailableRecordingBytes reports in the opened rate and consumes nothing", [](TestCase &t)
        {
            LgAudHarness h;
            openAt(h, 11025u);                                  // helper: Enumerate + Open + StartRecording
            h.host.micFrames.resize(16000);
            const size_t before = h.host.micCursor;
            h.put32(0x0c, h.word(0x0c));
            t.Equals(h.call(0x12, 0x20u, 0x30u), 0u, "0x12 succeeds");
            t.Equals(h.host.micCursor, before, "and reads nothing out of the ring");
            const uint32_t avail = h.word(0x20);
            t.IsTrue(avail <= 0x7d0u, "clamped to the 0x7d0 payload cap (decomp :90880)");
            t.IsTrue(avail > 0u, "with a full second in the ring there is something to report");
        });
```
  **Note in the ledger** that the game never calls this (Handoff note 2); it is implemented for completeness and for the harness, not for the proof.

- [ ] **Step 8: GREEN — the mixer family (0x0b / 0x0c / 0x0d / 0x0e).** `0x0d` and `0x0e` store `(channel, level)` into `m_gain` and answer 0; `0x0e` is the one the capture loop's AGC drives every fifth pass (`:211504-211527`), so refusing it would leave the game hunting. `0x0b` / `0x0c` move the 16-byte struct at `+0x20` in and out and `0x0b` writes the u16 the EE reads back at reply `+0x2c` (`:91240`). Case: set gain to 0x32 (what the game sets right after Open, `:48347`), read it back through `0x0b`, assert it survives.

- [ ] **Step 9: the off path, pinned byte for byte.** The constraint that keeps the gate untouched:

```cpp
        tc.Run("with no microphone the module answers exactly what it answered before this goal", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = false;                               // PS2X_MIC_DEVICE and PS2X_MIC_FAKE both unset
            t.Equals(h.call(0x10, 0x20u, 0x30u), 0u, "lgAudInit still succeeds");
            t.Equals(h.word(0x08), 0x108u, "version 1.08 at reply word 2, which the EE halts without");
            t.Equals(h.word(0x20), 0x800u, "0x800 at reply word 8, which is where the EE's 0x840 comes from");
            t.Equals(h.call(0x01, 0x20u, 0x170u), 0x80000001u, "Enumerate: no device");
            t.Equals(h.call(0x02, 0x30u, 0x20u), 0x80000001u, "Open: no device");
            t.Equals(h.call(0x0f, 0x20u, 0x20u), 0x80000001u, "EnumHint: no device");
            t.Equals(h.call(0x08, 0x30u, 0x530u), 0x80000001u, "Read: no device");
        });
```
  (`word(0x08)` and `word(0x20)` are reply words 2 and 8 — the two `docs/KNOWN.md:101` names as load-bearing.)

- [ ] **Step 10: suite, gate, and one single-instance launch.** Full suite first, then the gate, because this commit changes `dist/socom2.exe`:

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "goal 3 task 2 suite" -- ./build.sh test
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g3_gate
```
  Expected: `[  FAILED  ] 0`, gate `PASS 3/3` — the gate runs with no mic knob, so Step 9's off path is what it exercises.

  Then `logs/s8_voice_read.sh`, a **single** instance to the online lobby with the fake microphone, which is the cheapest place the game reaches `0x02`:

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:$HOME/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
. scripts/parity/env.sh
export PS2X_MIC_FAKE="$PWD/scripts/parity/refs/voice_ref.wav"
export PS2X_MIC_GAMEREAD_DUMP="$PWD/logs/parity/s8_voice_read/A_gameread.wav"
mkdir -p logs/parity/s8_voice_read
python -m tools_py.parity.online_match_ours --only A --hold 90 --out logs/parity/s8_voice_read
rc=$?
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/s8_voice_read.done
exit $rc
```
```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s8_voice_read.sh logs/s8_voice_read.marker
cat logs/s8_voice_read.marker 2>/dev/null || echo running
grep -n "\[lgaud\]" logs/run_A_<stamp>.log | head -20
grep -c "\[lgaud:stub\]" logs/run_A_<stamp>.log
```
  **Expected:** one `lgAudInit` line, one `lgAudOpen mode=... rec=1ch/16bit/11025Hz ... -> handle 0x...` line, **zero** `[lgaud:stub]` lines, and `logs/parity/s8_voice_read/A_gameread.wav` non-empty. If `lgAudOpen` never appears, the game did not reach the voice path in the lobby — that is Task 3's push-to-talk question, not a fault in this task; record what the last `[lgaud]` line was and continue to Task 3 before Task 4.

- [ ] **Step 11: commit.**

```bash
git commit -m "feat(lgaud): the headset module served for real -- Enumerate answers one device, Open decodes the game's own openparam (11025 Hz mono 16-bit), StartRecording/Read serve HostMic resampled, EnumHint settles, the mixer family stores; unchanged byte for byte with no microphone (Sprint 8 Goal 3 Task 2)" -- \
  third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp \
  third_party/ps2recomp/ps2xTest/src/socom2_lgaud_tests.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt \
  logs/s8_voice_read.sh
git push
```

---

## Task 3 — The launcher's wiring, and the push-to-talk question (spec Goal 3; brief: "does the game gate voice on a pad button? find it")

**Files:**
- Create: `docs/research/35-voice-path.md` <!-- docmaint: future -->
- Modify: `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp` (one added case)
- Read only: `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp:345`, `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h:44`, `game/analysis/socom2_game.elf.decomp.c:211100-211200`, `game/analysis/socom2_game.elf.strings.txt:707-731`
- Test: `launcher_tests.cpp`

**Interfaces:** none new. This task changes no shipping behaviour; it produces an answer and a document.

**Steps:**

- [ ] **Step 1: confirm the launcher already does its half, and pin it.** `launcher_config.cpp:345` pushes `PS2X_MIC_DEVICE=<name>` and `launcher_tests.cpp:344-347` already asserts both the empty and the non-empty case. **Nothing needs adding for the device.** Add one case that pins the *shape* the runtime now depends on — that no mic variable is exported when no device is picked, so the gate's off path cannot be broken from the launcher side:

```cpp
            t.IsTrue(!hasKey(env, "PS2X_MIC_FAKE"), "the launcher never sets the fake source: that knob is the harness's");
```
  Expected failure before the case is added: none — this is a pin, not a RED. Say so in one sentence in the ledger, per the Global Constraint.

- [ ] **Step 2: find what gates the recording state machine.** `:211163-211172` sets the "recording started" byte only inside `if (bVar4)`, and `bVar4` is decided by the loop ending at `LAB_0030ee70` (`:211140-211143`) over a 12-entry, 8-byte-strided table at `param_1 + 0xd0`. Read outward from there:

```bash
sed -n '211080,211175p' game/analysis/socom2_game.elf.decomp.c
grep -n "FUN_0030ec10(" game/analysis/socom2_game.elf.decomp.c | head
grep -n "0045b718" game/analysis/socom2_game.elf.decomp.c | head -40
```
  The three possible answers, and what each means for us: (a) **open mic** — `bVar4` is a level/VAD test on the buffer the loop just scaled at `:211149-211159`, and nothing else is needed; (b) **push-to-talk on a pad button** — the gate reads the pad, and the driven round in Task 4 must hold that button, which changes `logs/pad_A.txt` (`tools_py/parity/online_login_ours.py:58`); (c) **a lobby/team state** — the gate is a channel or team check, and the round must reach that state. The `VOICE MODULATION: ON/OFF` and `UIVOICE` strings (`socom2_game.elf.strings.txt:707-708,610`) say there is at least a menu option in the area; find which variable they write.

- [ ] **Step 3: write `docs/research/35-voice-path.md`.** Sections: (1) the RPC block and the per-function table from this plan, with the file:line for each field and the ESTABLISHED/ASSUMED verdict carried over verbatim; (2) the capture loop, its 0x500/58 ms cadence and its AGC; (3) the answer to Step 2 with its evidence, or the exact listing of what was read and why it is still open; (4) **what is on the wire**, which is the honest negative below; (5) the three dumps and how to reproduce them. This is the document Task 4 cites and Task 6's KNOWN row points at. <!-- docmaint: future -->

- [ ] **Step 4: state the wire question and its experiment, because no document answers it.** Searched: `grep -rn -i "voice|headset|mic" docs/research/*.md`. What exists:
  - `docs/research/05-code-package-and-harness.md:15` — the network stack inside ZSealEtc includes SCE-RT DME client 1.32.0070, `rt_udp 01.02.0048`, **`rt_audio` (voice)**, `rt_crypt`, Medius Client Library 1.50.0013. **Names the library, nothing else.**
  - `docs/research/02-socom2-online-servers.md:31` — SOCOM II is a Medius **peer-to-peer** title; match traffic is host-based P2P over UDP, "(voice too)", explicitly marked *inferred* from Horizon's `NetConnectionTypePeerToPeerUDP`, hashsploit's notes and a DSLReports thread. **No message type, no port, no layout.**
  - `docs/research/11-recom-applicability.md:34` — the class name `CZNetVoice` (PTT) appears in the symbol inventory. It is **not** in `game/analysis/socom2_game.elf.strings.txt` (`grep -i znetvoice` finds nothing), so it came from another image; nothing is decoded.
  - `docs/research/23-frostfire-ground-probe.md:318,355,433-435` — the **Nellymoser** codec is in the ELF (`SaseEncVad/.../VoicLD.c`, `shared/fftIf.c`), its VU0 FFT microcode at 0x3d5980 is never enabled (mode word at 0x1d55a0 is 0 in the ELF and all 18 RDRAM images), so it runs scalar. Entry points not located.
  - `docs/research/01-ps2-static-recompilation.md:31` — "mic capture -> voice packets" is listed as unstarted.

  **Verdict: nothing in the tree identifies SOCOM II's voice packets on the wire.** The codec is known, the transport is inferred, the message type is unknown.

  **The experiment that identifies them, using instruments that already exist.** `socom2_libnetb.cpp:74` reads `PS2X_SOCOM2_NET_TRACE` and `:120` reads `PS2X_SOCOM2_NET_TRACE_PEERS=<n>`; with both set, every peer UDP send prints `udp send #N to <ip>:<port> len <L> -> <n> (handle h)` (`:816-818`) and the first `n` peer packets print `udp peer send #N to <ip>:<port> ra=<hex> <48 bytes of hex>` (`:820-823`). **`ra=` is the EE return address of the caller** — a different call site is a different `ra`, and that is the identifier. So: run the Task 4 round **twice**, once with `PS2X_MIC_FAKE` set and once without, everything else identical, and diff:
  1. the set of distinct `ra=` values (a voice send has an `ra` that appears only in the mic-on run);
  2. the histogram of `len` (voice frames arrive at **17.2 per second**, one per 0x500-byte read, so a length class at ~17 Hz that is absent from the control run is the flow);
  3. the destination port (peer, so `tracePort` at `:110` traces it by default: ports below 10000 or all of them with `PS2X_SOCOM2_NET_TRACE_PORTS`).
  The DME server's log is the second witness: `server/logs/console-DME.log` shows per-client UDP sockets from 50000 upward (`server/README.md:49,97`), so a flow that appears only in the mic-on run is visible there too. Record the answer — `ra`, length class, port, rate — in `docs/research/35-voice-path.md` §4. <!-- docmaint: future -->

- [ ] **Step 5: commit.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "goal 3 task 3 suite" -- ./build.sh test
git commit -m "docs(voice): research/35 -- the lgaud block field by field with established/assumed per field, the 0x500/58 ms capture loop and its AGC, what gates recording, and the experiment that identifies voice on the wire (nothing in the tree does) (Sprint 8 Goal 3 Task 3)" -- \
  docs/research/35-voice-path.md third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp
git push
```

---

## Task 4 — The driven two-instance proof, with the three dumps (spec Goal 3: "a WAV of what the game read is the proof")

**Files:**
- Create: `logs/s8_voice_round.sh`, `tools_py/tests/test_audio_corr.py`
- Modify: `tools_py/parity/audio_corr.py`, `tools_py/parity/online_login_ours.py` (:57-66)
- Read only: `tools_py/parity/online_match_ours.py:4412-4420`, `scripts/parity/env.sh`
- Test: `python -m unittest tools_py.tests.test_audio_corr -v`

**Interfaces:**
- `audio_corr --ref-wav <path>`: the reference comes from a WAV instead of the disc's raw PCM. `read_wav` (`audio_corr.py:47`) and `correlate_arrays` (`:159`) already exist and already take arrays; this adds one branch in `main` (`:304-330`) that reads the reference through `read_wav` and one guard that `--ref-wav` and the positional `pcm` are mutually exclusive. `--rate` already exists (`:311`) and must be passed `11025` for a game-read dump.
- `online_login_ours.INSTANCES` gains a per-side mic block, so A and B do not share one dump path:

```python
INSTANCES = {
    "A": {..., **_mic_env("A")},
    "B": {..., **_mic_env("B")},
}
```
  where `_mic_env(side)` returns `{}` unless `PS2X_MIC_FAKE` (or `PS2X_MIC_DEVICE`) is in the operator's environment, and otherwise gives A the fake source plus `PS2X_MIC_GAMEREAD_DUMP=logs/parity/<out>/A_gameread.wav` and B `PS2X_MIC_DUMP_PLAYBACK=logs/parity/<out>/B_playback.wav` **and no capture source at all** — B listens, A talks (R116).

**Steps:**

- [ ] **Step 1: RED — `--ref-wav`, against a synthetic pair.** `tools_py/tests/test_audio_corr.py`, `unittest` only:

```python
import unittest
import numpy as np
from tools_py.parity import audio_corr


class RefWavCorrelation(unittest.TestCase):
    def test_a_resampled_copy_of_the_reference_correlates_above_the_bar(self):
        rate_in, rate_out = 16000, 11025
        n = rate_in * 4
        t = np.arange(n) / rate_in
        ref = (12000 * np.sin(2 * np.pi * 300 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)))
        # the same signal as the game would have read it: linearly resampled to 11025
        m = int(n * rate_out / rate_in)
        pos = np.arange(m) * rate_in / rate_out
        i0 = pos.astype(int)
        frac = pos - i0
        got = ref[i0] * (1 - frac) + ref[np.minimum(i0 + 1, n - 1)] * frac
        refd = ref[i0]            # the reference decimated to the same rate, which is what --ref-wav does
        rows = audio_corr.correlate_arrays(got, refd, window_s=1.0, rate=rate_out)
        self.assertGreaterEqual(audio_corr.min_corr(rows), 0.95)

    def test_an_unrelated_signal_does_not(self):
        ...
```
  Run: `python -m unittest tools_py.tests.test_audio_corr -v`
  Expected failure: `AttributeError: module 'tools_py.parity.audio_corr' has no attribute 'correlate_arrays'` is **not** what happens — it exists at `:159`; the real first failure is the `--ref-wav` argument, so add a third case that calls `audio_corr.main([...])` with `--ref-wav` and expect `error: unrecognized arguments: --ref-wav`.

- [ ] **Step 2: GREEN — the flag, and the per-side environment.** One branch in `audio_corr.main`; one `_mic_env` helper in `online_login_ours.py` beside `INSTANCES` (`:57`), with the comment saying why B has no capture source. Re-run both suites.

- [ ] **Step 3: the round.** `logs/s8_voice_round.sh`:

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:$HOME/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
. scripts/parity/env.sh
export PS2X_MIC_FAKE="$PWD/scripts/parity/refs/voice_ref.wav"
export PS2X_SOCOM2_NET_TRACE=1
export PS2X_SOCOM2_NET_TRACE_PEERS=400
mkdir -p logs/parity/s8_voice_round
python -m tools_py.parity.online_match_ours --hold 120 --out logs/parity/s8_voice_round
rc=$?
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/s8_voice_round.done
exit $rc
```
```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s8_voice_round.sh logs/s8_voice_round.marker
cat logs/s8_voice_round.marker 2>/dev/null || echo running
```
  Then the **control** round: the identical script with the two mic exports removed and `--out logs/parity/s8_voice_control`. Two launches, one at a time, under the loop lock.

- [ ] **Step 4: the capture bar.**

```bash
python -m tools_py.parity.audio_corr logs/parity/s8_voice_round/A_gameread.wav \
    --ref-wav scripts/parity/refs/voice_ref.wav --rate 11025 --window-s 2 --bar 0.95
```
  **Bar: `min_corr >= 0.95` and exit 0.** The reference is 11025 Hz and the dump is 11025 Hz, so no rate argument juggling is needed; the resample this measures is the 16000 -> 11025 one inside the module. A `min_corr` above 0.95 with a *stepping* `offset_samples` means frames were dropped — report the step size in samples, because at 11025 Hz one 0x500 read is 640 samples and a step that is a multiple of 640 is a lost Read, which is a different defect from a resampler fault.

- [ ] **Step 5: the wire bar.** Task 3 Step 4's experiment, run on the two rounds (a good subagent job: a histogram, no judgement):

```bash
grep -o "udp send #[0-9]* to [0-9.]*:[0-9]* len [0-9]*" logs/run_A_<voice>.log   | awk '{print $NF}' | sort -n | uniq -c | sort -rn | head -20
grep -o "udp send #[0-9]* to [0-9.]*:[0-9]* len [0-9]*" logs/run_A_<control>.log | awk '{print $NF}' | sort -n | uniq -c | sort -rn | head -20
grep -o "ra=0x[0-9a-f]*" logs/run_A_<voice>.log   | sort -u > /tmp/ra_voice.txt
grep -o "ra=0x[0-9a-f]*" logs/run_A_<control>.log | sort -u > /tmp/ra_control.txt
comm -23 /tmp/ra_voice.txt /tmp/ra_control.txt
```
  **Bar: at least one `ra=` present only in the voice round, with a length class arriving at 15-20 per second.** Record the `ra`, the length, the destination port and the rate in `docs/research/35-voice-path.md` §4 and in the ledger. <!-- docmaint: future -->

- [ ] **Step 6: the end-to-end bar, if Task 5 has not run yet it is the Write dump.** B's `PS2X_MIC_DUMP_PLAYBACK` is written by Task 2 Step 6's accepted-and-dumped playback path, which exists before Task 5 does the mixing:

```bash
python -m tools_py.parity.audio_corr logs/parity/s8_voice_round/B_playback.wav \
    --ref-wav scripts/parity/refs/voice_ref.wav --rate 11025 --window-s 2 --bar 0.90
```
  **Bar: `min_corr >= 0.90`** — lower than the capture bar on purpose, because this signal has been through Nellymoser at 160 samples a block and back, and that codec is lossy. A correlation in the 0.6-0.9 band with a constant offset is **still the proof that the path works**; report the number rather than failing the goal on it, and put the measured value in KNOWN as the figure a later listen is compared against. Below 0.5, or silence, is a failure and Task 5 does not start.

- [ ] **Step 7: commit.**

```bash
git commit -m "test(voice): the driven two-instance proof -- audio_corr --ref-wav, per-side mic environment (A talks, B listens), and the round that reads the game's own 0x08 bytes back out of a WAV (Sprint 8 Goal 3 Task 4)" -- \
  tools_py/parity/audio_corr.py tools_py/parity/online_login_ours.py \
  tools_py/tests/test_audio_corr.py logs/s8_voice_round.sh
git push
```

**STOP RULE (from the brief).** If no voice packets leave instance A in the driven round — Step 5 finds no `ra` that the control round lacks and no length class at 15-20 Hz — **stop here** and file what the game did instead: the last `[lgaud]` line, whether `0x04 StartRecording` was ever reached, the value of the gate Task 3 Step 2 identified, and the full `udp send` length histogram of both rounds. Do not start Task 5, and do not tune the game.

---

## Task 5 — The other player, heard (spec Goal 3, the second half of the path)

*(This task is deliberately last among the code tasks: routing PCM into the mixer is only worth doing once the capture path is proven, and it is the only part of this goal that can make the game sound worse.)*

**Files:**
- Modify: `third_party/ps2recomp/ps2xIOP/include/ps2x/iop/iop_host.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_iop_host.h` + `.cpp`, `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_audio.cpp`, `third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp`, `third_party/ps2recomp/ps2xTest/src/socom2_lgaud_tests.cpp`
- Read only: `third_party/ps2recomp/ps2xIOP/src/modules/snd989.cpp:396-410` (how PCM already reaches `audioPcmWrite`), `docs/research/32-audio-path.md` §7 (the PCM stream ring and the shared master group)
- Test: `socom2_lgaud_tests.cpp` and `socom2_audio_tests.cpp`

**Interfaces:**
- `IopHost::micPlaybackWrite(const int16_t *pcm, size_t frames, uint32_t rate)` — default no-op, overridden in `PS2IopHostAdapter` to reach a new `PS2AudioBackend::onHeadsetPlayback`.
- `PS2AudioBackend::onHeadsetPlayback` opens **its own** raylib `AudioStream` at the rate `lgAudOpen`'s playback half named, never the 989snd PCM ring — the ring is the game's own stream and `docs/research/32-audio-path.md` §7 records the shared render mutex and the unclamped sum as a live hazard. A separate stream is a separate source and cannot make an existing cue late.

**Steps:**

- [ ] **Step 1: RED — the module routes Write to the host.** In `socom2_lgaud_tests.cpp`: open with `Mode = 3`, call `0x09 Write` with 0x140 bytes of a known ramp at `+0x30`, assert `LgAudTestHost::playbackFrames` received them and that the reply's `+0x20` equals the byte count. Expected failure: `error: no member named 'micPlaybackWrite' in 'ps2x::iop::IopHost'`.
- [ ] **Step 2: GREEN — the seam, mirroring Task 1 Step 7.** Same three files, same comment discipline.
- [ ] **Step 3: RED — the backend opens a stream and does not touch the 989snd ring.** In `socom2_audio_tests.cpp`, with a `Snd989MixerHost`-style host: feed `onHeadsetPlayback` a second of audio and assert `pcmPosition` (the game's own ring, `:980`) is unmoved and no `snd989::Mixer` slot was taken. Expected failure: `error: no member named 'onHeadsetPlayback' in 'PS2AudioBackend'`.
- [ ] **Step 4: GREEN — the stream.** Resample the incoming rate to the device rate with `micResampleLinear` (the same pure function, the same phase discipline), buffer it in a `MicRing`, and fill the raylib stream from it. Underrun is silence, never a repeat: that is the defect `docs/KNOWN.md`'s R97 row already names for the PCM ring, and this stream must not reintroduce it.
- [ ] **Step 5: the bar.** Re-run Task 4's round with Task 5's code in and re-measure Step 6's correlation from `B_playback.wav`, which is now a tee off the mixer path rather than the module's own dump; the number must not fall. Plus: the three-stage gate 3/3 (this touches `ps2_audio.cpp`), and `pcm_underruns` still 0 in the run log.
- [ ] **Step 6: commit**, pathspecs explicit, the same trailer.

---

## Task 6 — Close-out (KNOWN, STATUS, CURRENT_SPRINT, HUMAN_TASKS)

**Files:** `docs/KNOWN.md` (:101), `docs/STATUS.md`, `docs/CURRENT_SPRINT.md` (:151-154), `docs/HUMAN_TASKS.md` (:93-110), this plan.

**Steps:**

- [ ] **Step 1: rewrite `docs/KNOWN.md:101`.** The row moves out of "believed bounded" into what was measured. It must now say: the openparam is decoded and the game asks for **11025 Hz mono 16-bit** with `Mode` 2 or 3 (`decomp:48341`), which **retracts** `host_mic.h`'s 16 kHz FORMAT ASSUMPTION; the capture loop reads 0x500 bytes 17.2 times a second and drives an AGC through `0x0e`; `0x12` is never called; the payload rides the RPC receive buffer at `+0x30`, so no separate SIF path was needed; the measured game-read correlation and the measured playback correlation, both as numbers.
- [ ] **Step 2: add the row this goal creates** — whatever Task 3 Step 2 found about what gates recording, and whatever Task 4 Step 5 found on the wire, each with its evidence and its experiment if still open.
- [ ] **Step 3: `docs/CURRENT_SPRINT.md:151-154`** — item 2 marked done with the three dumps named, or stopped with which stop rule fired.
- [ ] **Step 4: `docs/HUMAN_TASKS.md`.** The item at `:93-110` ("Speak in an online lobby, and expect to be unheard") is now **wrong** and must be replaced, not amended: the new item is the owner's two-machine *"can you hear me"* — both machines on the hosted server, each with a microphone picked in the launcher, one speaks and the other listens, then swap. What to report in one line: (a) was the voice audible and intelligible; (b) was there a delay, and roughly how long; (c) did it need a button held, or did it carry the moment they spoke (this confirms or refutes Task 3 Step 2's answer from the other side). The numbers being confirmed: the measured game-read correlation from Task 4 Step 4, and the codec's 58 ms frame. The microphone-meter item at `:93-99` stays as it is.
- [ ] **Step 5: `docs/STATUS.md`** — one dated paragraph, the three dumps' paths, the launches spent.
- [ ] **Step 6: commit and push**, explicit pathspecs, the same trailer.

---

## Rulings made in this plan's text (recorded 2026-09-25, Sprint 13 Task R3)

This plan numbered R111-R116 (its commit, `d3fbd66`) but gave them no rulings section: each was made inline, in the
sentence its number labels. The 2026-09-25 documents audit (D56) found no text for R114 and R116 and counted R112 as
a step's label; reading the labelled sentences, all four were made here, so they are recorded rather than declared
vacant. Each line below is the labelled sentence, unchanged in substance. R111 is the hosted-server plan's; R115 is
written in a ruling's own shape at Task 1 Step 4 and is not repeated.

- **R112** (Handoff note 4, and Task 2 Step 3, "the one structural rule"): **the module reads the entire send block
  before it writes one byte of reply.** Every lgaud call passes `DAT_003dcfb4` as both the send and the receive
  buffer, so a reply written early overwrites the handle and the byte count it is about to use.
- **R113** (Task 2 Step 4): **Enumerate's block reports zero Logitech vendor extensions** (`kEnumEntryCount` = 0).
  The only reader, `FUN_0034ba60`, then scans nothing and moves on. Sprint 10's R219 keeps it with its meaning
  corrected.
- **R114** (Task 1's interface list, `MicFormat::supported()`, and Task 2 Step 5): **only mono, 16-bit, 4000-48000 Hz
  is supported; any other format is refused at Open** with `kStatusBadParam`, and the refused triple is logged once.
- **R116** (Task 4, the driven match's `_mic_env`): **in the driven two-instance match A talks and B listens.** A gets
  the fake source and the game-read dump, B the playback dump and no capture source at all.

---

## Self-review (per superpowers:writing-plans)

- **Every task is independently verifiable.** Tasks 1, 2 and 5 end in `ps2x_tests` cases with named expected failures; Task 3 ends in a document and one pinned launcher case; Task 4 ends in two correlation numbers and a packet histogram; Task 6 ends in documents. No task's "done" depends on a human.
- **Every step that changes runtime code names its RED and its exact failure text**, except Task 3 Step 1, which says in one sentence that it is a pin rather than a RED, as the Global Constraints require.
- **No placeholders.** Every command is runnable as written against paths that exist in this checkout; every struct offset carries a `file:line`; every code block is the code to write, not a sketch.
- **The design decisions from the brief are implemented, not redesigned**: off unless `PS2X_MIC_DEVICE`; Enumerate answers one device; EnumHint changes once; Open returns a handle; StartRecording resets; Available from the ring fill in the opened format; Read through the module's existing reply path; async completes immediately; playback accepted and dumped in this goal, mixed in Task 5; mixer stored; Close stops. The four places where the tree or the decomp contradicts the brief are called out in the Handoff notes with the command that re-derives each, and are corrected rather than followed.
- **Both stop rules from the brief are placed where they fire** (end of Task 1, end of Task 4) and each says exactly what to file.
- **The budget is stated and over-spent deliberately** (three launches against the spec's one), with the launch to drop named if it is enforced.
- **Known weakness, recorded rather than hidden:** the entry stride of 6 in Enumerate's device-info block is ASSUMED, and the record/playback halves of the openparam are ASSUMED to be in that order. Both are harmless here — we answer `entryCount = 0`, and we read only the first half — but if a later goal needs the vendor-extension path or the playback format, those two are what to re-derive first.
