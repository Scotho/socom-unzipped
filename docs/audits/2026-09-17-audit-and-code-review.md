# Audit and code review — 2026-09-17 (end of Sprint 6's autonomous run)

**The goal this audit measures against:** SOCOM Unzipped — SOCOM II: U.S. Navy SEALs running natively on PC, with online
play, that a stranger can run by pointing the launcher at their own r0001 ISO and playing a round against another
stranger on a hosted Horizon server (packaging outline §7, the owner's decisions of 2026-09-15/16). Every finding below
is ranked by how far it stands between today's tree and that sentence.

**Method.** Four read-only reviews over the tree at `HEAD` (commit 9447feb, branch `sprint-6`; the fix wave in §2.6 landed on top of it), each by a reviewer with
its own area and the same brief: rank by impact on the goal, cite file and line, name the failure a player would see,
estimate the fix. Areas: the runtime core (scheduler, sceMpeg/CD/IPU/SIF HLE, guest heap, audio); the render path (GS
frontend and GL backend, VU1, the present path); the harness, tests, online plumbing and packaging; the documentation
and the sprint's own ledger. The reviews' reports were merged and de-duplicated here; where two reviewers disagreed,
the code was read again and the disagreement is noted. Nothing was built or launched for this audit.

**How to read it.** §1 is the verdict and the gap to the goal in dependency order. §2 lists the findings that change what
the next sprints do, with severity and the action. §3 is the Sprint 6 ledger as the code and docs actually stand. §4 is
debt that does not block the goal but costs every sprint. §5 is the process review. §6 proposes Sprints 7–9; the sprint
file (`docs/CURRENT_SPRINT.md`) carries the binding version.

## 1. Verdict, and the gap to the goal

**Verdict.** The game plays: the mission gate passes 3/3 every day, twenty of twenty online maps run a control round, the
kill readout is proven and repeats, the audio path is measured sample-exact against the disc, and the launcher checks the
disc. **A stranger still cannot play**, and the reasons are plumbing, not gameplay. In dependency order:

| # | Gap | State today | Owner or autonomous |
|---|---|---|---|
| G1 | The launcher never handed the verified ISO to the game (no `PS2X_CD_IMAGE`); the runtime fell back to "any `.iso` next to the ELF", which the portable folder does not ship | **fixed in this audit's fix wave** (launcher emits `PS2X_CD_IMAGE`; test) | done |
| G2 | The runtime discarded a hostname server address (numeric only); a hosted server will be a DNS name | **fixed in this audit's fix wave** (getaddrinfo fallback; test) | done |
| G3 | The Horizon configs advertise the developer's LAN address in four tracked fields with no override; two strangers get `CONNECT_ACCEPT` pointing at 192.168.2.10 | `start-servers.ps1 -PublicIp` in this fix wave | done (script), owner (a host machine) |
| G4 | No hosted server exists; the launcher's default server is loopback; the server picker has placeholders for the community and Unzipped addresses | picker built in this fix wave with placeholders | **owner**: the machine, the router, the two addresses |
| G5 | Every online result is two instances on one host; NAT, advertised address, clock skew, two clients on the same RSA key have never been exercised | nothing | **owner** (a second machine) + autonomous scripts |
| G6 | Hidden GL requirement: GL 3.3 + dual-source blending, no probe, no fallback; on failure the window stays black and the command queue grows without bound | nothing | autonomous (Sprint 7) |
| G7 | The command queue is unbounded whenever the back-pressure latch trips (a window drag does it); memory balloons, then a hitch | nothing | autonomous (Sprint 7) |
| G8 | The three hands-on checks (title listen, free play, pad) are unreported; the portable zip has never been run on a clean machine | `docs/HUMAN_TASKS.md` (since 2026-09-25 `docs/archive/HUMAN_TASKS-to-2026-09-25.md`) | **owner** |
| G9 | Online reliability numbers: the lobby rate was never measured (Task 2 Step 4); freeze shape 2 unrooted (Task 3); 21k texture decodes/s fails the ladder's back-pressure bar | partial | autonomous (Sprint 7) |
| G10 | Bare-run robustness: no exit-code taxonomy, "the game exited" with no reason, no `SHA256SUMS`, 285 MB unsigned | nothing | autonomous (Sprint 8), owner for signing |

Everything below G5 is what makes the experience good once G1–G5 let it happen at all.

## 2. Findings that change the plan

Severity is impact on the goal. "Fix wave" = landed during this audit under tests (see §2.6). Estimates: S under a
day, M a few days, L a week or more.

### 2.1 Packaging and online plumbing (the harness/network review)

| Sev | Where | Finding | Action |
|---|---|---|---|
| blocker | `ps2xLauncher/src/launcher_config.cpp` `environmentFor` | The verified ISO was never passed to the runtime | fix wave (S) |
| high | `ps2xRuntime/src/lib/socom2_hostnet.cpp` `loadHosts` | A hostname server address was silently discarded; only `resolve()` had a getaddrinfo path | fix wave (S) |
| high | `server/config/{medius,dme,muis}.json` | Advertised address hardcoded to the developer's LAN IP in four fields; `server/README.md` still says 127.0.0.1 | fix wave: `-PublicIp`, port list (S) |
| high | `launcher_config.h` | Default server loopback; no reachability probe or message | picker built; the addresses are the owner's (S) |
| medium | `game_overrides_socom2.cpp:59-66`, `socom2_rsa_key.h` | Two strangers with default config publish the same RSA key A in their DME records; the harness always sets key B for instance B, so the shared-key case has not run since the fix | derive the key per profile, or one same-key control round (S) |
| medium | five scripts, `dns_stub.py`, `pcsx2_ctl.py` | The harness defaulted to 192.168.2.10 in five places; the 573-char peek block was copy-pasted | fix wave: `scripts/parity/env.sh`, `SOCOM_SERVER_IP` (S) |
| medium | `drive.py:27`, `pcsx2_ctl.py`, `keys.py:27`, `gate.py:90` | ISO path, window title `PS2-Recomp`, card directories are literals of this machine | one config module (S) |
| medium | `win32_glue.cpp`, `launcher main.cpp` | On a crash the launcher says "the game exited" with no code; no exit-code taxonomy | Sprint 8 (M) |
| low | `socom2_hostnet.cpp` `localIp()` | Behind NAT the interface address reported to the peer is the LAN IP; harmless while the peer channel carries zero data, untested for two machines | with G5 |
| low | `make_portable.sh` | Ships harness-only DLLs (OpenEXR, jxl, brotli); no `SHA256SUMS`, no version stamp | Sprint 8 (S) |

### 2.2 Render path (the render review)

| Sev | Where | Finding | Action |
|---|---|---|---|
| high | `gs_gl_backend.cpp` `markShadowPages`, `executeUpload`, `resolveTexture` (:1593, :1623, :2883, :2909) | **The likely cause of the 21k decodes/s (KNOWN §2):** page marks are a global generation bump at page-row granularity with no x-extent, and a render target that overlaps a sampled texture is downloaded and its whole span re-stamped every frame. The post-process draws the half-size frame into the depth-buffer pages every gameplay frame; those pages overlap the parked streamed textures, so every cache hit fails the generation check and re-decodes (a `glGenTextures`+`glTexImage2D` per decode). | Settle with `PS2X_GS_TRACE_PAGES` on a HUD texture page (download lines preceding decode lines each frame); then mark only the downloaded rows, include `dsax/rrw` in the upload span, compare per-page generations only for touched pages, reuse GL texture objects. Add a decodes-per-present budget to the console-replay GL test. (M) |
| high | `gs_gl_backend.cpp:953-981, :242`; `ps2_runtime.cpp:2582` | GL 3.3 core + dual-source blend required with no probe and no failure latch: on failure `ensureGl` recompiles the shaders every host frame, `m_glReady` never sets, and the EE records into `m_pending` forever with no cap. A stranger on an older iGPU, a VM or RDP gets a black window and a RAM climb. | Probe once, latch, fall back to the CPU backend with a visible error. (S/M) |
| high | `ps2_runtime.cpp:2576`, `gs_gl_backend.cpp:1037`, `gs_frame_backpressure.cpp:56` | GL replay runs on the raylib window thread; a title-bar drag enters the modal size-move loop, the 2000 ms cap trips, the latch makes every later frame `Skipped`, and `m_pending` grows unbounded until the drag ends (the "working set ~15 GB" note in KNOWN §4 fits). | Cap pending presents/bytes when latched (drop guest frames, keep uploads), or replay on a dedicated GL thread. (M) |
| medium | `gs_gl_backend.cpp:2258, :2143, :916` | Synchronous `glReadPixels` on the render thread for every exposure readback (10 Hz) and every RT-overlap resolve; a full pipeline drain each time | PBO ring with one-frame latency; restrict RT downloads to `gpuRows`. (M) |
| medium | `gs_gl_backend.cpp:721-820` | Local-to-host and local-to-local copies out of GPU-dirty pages block the EE until the GL thread reaches a readback: a lock-step round trip that collapses the N=3 pipeline when it happens per frame | Measure `readback=` per second with `PS2X_GS_STATS`; if per-frame, GPU-side blit. (M) |
| medium | `gs_gl_backend.cpp:2210-2256` | `downloadRenderTargetToCpu` rewrites the shadow but never marks the pages (research/31 §3 case 2, still open): a texture decoded from RT pages can keep a stale entry | Mark the downloaded rows. (S) |
| medium | `vu/native/vu1_native_programs.cpp:11`, `ps2_vu1_core.cpp:2495` | The native VU1 dispatcher is keyed to one microcode hash; any other disc revision silently runs the interpreter at a much lower frame rate | One-line warning when no native program matches; the launcher names the supported disc. (S) |
| low | `ps2_runtime.cpp:731`, `gs_gl_backend.cpp:40, :1544` | 640x448 default with no HIGHDPI flag (tiny on a 150 % laptop); every render target allocated at 1024x1024 x scale² RGBA8 plus DEPTH32F (128 MB per target at scale 4) | HIGHDPI flag, launcher default 2x; size targets from `usedHeight`. (S) |

### 2.3 Runtime core (the runtime review)

| Sev | Where | Finding | Action |
|---|---|---|---|
| medium | `Kernel/Stubs/CD.cpp:328` | `sceCdRead` advances the CD *stream* cursor (`g_cdStreamingLbn = lbn + sectors`), and `sceCdStResume` does not restore it: a plain read while a stream is open makes the next stream read deliver bytes from after that file. Unobserved so far; fits the unexplained 0.26 s slip in research/32 §7.1. | Separate stream cursor; test "StRead after Read resumes at the stream LBN". (S) |
| medium | `EeScheduler.cpp:371-402`, `ee_scheduler.h:269` | **Equal-priority threads are round-robined every 65536 cycles (0.22 ms).** The PS2 kernel never time-slices; equal-priority threads run until they block or rotate. Any pair of equal-priority SOCOM threads sharing an unlocked structure (network RX/TX queues are the usual shape) can interleave mid-update on ours only: exactly the shape of the one-side-only intermittent defects the ladder has chased. | Log SOCOM's thread priorities once; expire the slice only for strictly higher priority; a test pinning the semantics. (S, and settle it before shipping online) |
| medium | `snd989_mixer.cpp:881-990, :340` | Disk I/O inside the audio callback under the mixer mutex (`readChunkPair` seeks and reads the ISO); `pcmStreamPosition`, polled 30/s by the game's audio thread through a synchronous RPC, takes the same mutex. On a stranger's HDD or under antivirus scanning, one slow read drops audio and blocks the EE inside an RPC. | Pre-decode streams on a worker into a ring; render touches memory only. (M) |
| medium | `Kernel/Stubs/Helpers/Support.h:4-32` | Mutable stub state in an anonymous namespace in a header, one copy per TU across 19 stub files; latent until the first cross-TU reader sees stale zeros | Move to `Support.cpp` with externs. (S) |
| low/med | `EeScheduler.cpp:1293`, `ps2_runtime.cpp:978, :2068` | Invocation stacks are never released and the pool is 64 slots; exhaustion is caught and the game thread exits with a printed line and a black window | Free-list per depth, or a loud "stack pool at N/64" warning. (S) |
| low/med | `MPEG.cpp:1893` | The aside-audio cap drops the *oldest* packet; packets are odd-length, so a drop flips sample parity (research/32 §7.1 fault 3) until the next stream start. Reachable only if the audio thread stops draining. | Drop in pairs or drop the newest; parity test. (S) |
| low | `MPEG.cpp:2374` | Stream restart makes a fresh playback state without freeing the aside scratch block: the idle title screen leaks guest heap per loop | Free in the reset path. (S) |
| low | `EeScheduler.cpp:931` | `yieldToAnyReady` restores the saved priority unconditionally; a `ChangeThreadPriority` in the window is overwritten | Restore only if still 127. (S) |
| low | `game_overrides_socom2.cpp:534-567` | The ISO fallback takes the first `.iso` in the directory: a stranger's SOCOM 1 beside SOCOM 2 boots the wrong disc silently | Moot once the launcher always sets the image (G1); refuse when more than one is found. (S) |
| low | `CD.cpp:262-300` | On a failed read `sceCdRead` guesses among five register permutations and writes whatever resolves | Gate behind a trace knob; never guess by default. (S) |

### 2.4 Tests that do not exist and would let a regression through silently

- Texture-cache invalidation precision and a decodes-per-present budget on the console-replay GL test (the 64k/s class).
- `ensureGl` failure latch and CPU fallback; a bound on `m_pending` while the back-pressure latch is `Skipped`.
- The aside-audio path, the refusal semantics (video taken / audio set aside), `skipOverdueDecodedFrames`, `setAlarm`/`cancelAlarm`, `completeVSync` field parity: the code that changed most in the last 48 hours has no test.
- CD stream pacing and "a read between pause and resume leaves the stream LBN alone" (fails today).
- Equal-priority preemption semantics (would pass by accident today).
- `hostnet::loadHosts` (now covered), the launcher's environment (now covered).
- Eleven gate tests skip without gitignored run directories that `archive_logs.ps1` will move; four tests need the disc, PCSX2 or `dist/socom2.exe`; the lock race tests run only under `LOOP_LOCK_SLOW_TESTS=1`.

### 2.5 Harness debt worth one pass

`online_match_ours.py` is 5170 lines with about 40 flags; `--probe`, `--sweep`, `--calibrate`, `--walk-to-b` sit beside `approach` doing the same walk; a block is marked "RETIRED before it was ever used". The screen detectors are pixel boxes on a 640x448 capture, all broken at once by any HUD-scale change. Twelve test files mock the shell, so a detector threshold can be green while the real shell is red. `PS2X_SOCOM2_PAD` is opt-in in the runtime yet always set by the launcher: the non-pad path is dead for players. README says `build.sh test` runs no Python tests; it does.

### 2.6 The fix wave (landed during this audit, each under a test, none launched)

1. Launcher emits `PS2X_CD_IMAGE=<iso>` (blocker G1). Test: the environment carries the verified disc; no ISO, no key.
2. `socom2_hostnet::parseServerAddress`: numeric, else getaddrinfo (AF_INET, first IPv4), else one stderr line and the old value (G2). Test: `192.168.2.10`, `localhost`, `no-such-host.invalid`.
3. `server/start-servers.ps1 -PublicIp <ip>` rewrites the advertised fields in the three configs (never the MPS loopback), `-ShowIp` prints them, `server/README.md` lists the ports to forward (G3). Test on temp copies.
4. `scripts/parity/env.sh`: one `SOCOM_SERVER_IP` knob and the shared trace/peek block; the four online scripts source it; `dns_stub.py` reads it. The three peek copies were byte-identical; `mixed_match.sh` keeps its shorter one on purpose. Test.
5. The launcher's server picker (owner request): SOCOM Community, SOCOM Unzipped, Custom; the address locked to the preset except for Custom; both real addresses are deliberate placeholders until the owner supplies them (`docs/HUMAN_TASKS.md`; since 2026-09-25 `docs/archive/HUMAN_TASKS-to-2026-09-25.md`).

## 3. Sprint 6, as it actually stands

The plan's checkboxes were not maintained: only Task 8 and one step of Task 1b are ticked, while STATUS records most of
the rest as done. The ledger, from the commit log and STATUS:

| Task | State | Evidence and what is left |
|---|---|---|
| 0 paused fixes, pop-up gate step | done | `f6a4434`…`a81eb74`, gate `s6_blockptr`; boxes never ticked |
| 1 a gate that can see (fail screen, console compare, guest probe) | done | `34ed2ac`, `4c1b294`; the water bar flipped to passing with the 09-16 water fix |
| 2 lobby hardening | partial | Steps 1–3 done (`78a81d1`, research/28, `b8d2410`…`c669185`); **Step 4's ten-launch rate was never measured** |
| 3 online freeze root cause | partial | Step 1 done (`freeze_trace.py`, research/29); Steps 2–3 not; the CLUT and clock fixes addressed a *different* freeze; research/29's shape 2 (`waitReadable` blocking 10 s) is still a candidate |
| 4 acceptance repeatability | effectively met | `ebf13be`; `s6_ladder8` 4/4 KILL, `s6_ladder12` 3/4; the strict bar (both scorers agreeing on two launches) not recorded; the RUNG0 back-pressure bar fails on the 21k decodes |
| 5a water / 5b root decay / 5c DBP offset | done / done / likely done | 5a by the blend and exposure HLEs and the VIF wait, not the `0x34` theory (KNOWN §2 row stale); 5b by the probe (`s6_probe`); 5c as a side effect of `545b85a`, never verified against the loading screen |
| 6 exact-oracle math, HLE leg 3 | not started | |
| 6b map sweep | done | research/33; Requiem and Foxhunt settled 09-17; 20/20 |
| 6c audio | done except the listen | research/32; `HUMAN_TASKS` |
| 7 mixed match | partial | tooling `9447feb`; leg 1 ran, no joiner (the PCSX2 macro drifted at boot) |
| 8 harness | done | `bd27443` |
| 8b launcher | done except the pad test and the diagnostics zip | `770d5fb`, `2a8f8e4` |
| 9 close-out | not started | sprint-6 unmerged; ROADMAP §6 items 10–12 (replay cost, display-env A/B, VU aliasing) were never carried into the plan |

## 4. Documentation drift (to fix in the close-out)

- KNOWN §2 still believes the `0x34` env-map pass for the shards; §4 says "cause still open"; research/31 §15–17 and the 09-16 fixes superseded both. KNOWN's header says "last audited 2026-09-15, nothing promoted".
- KNOWN §4 "runtime frozen at `92d30f0`" and "back-pressure waits are excluded from guest time" are dead (the freeze lifted; wall time is the default); the scheduler's own R35/R41/R54 comments say the same dead thing; `ee_scheduler.h` still defaults `m_excludeHostTime = true` until the first `accountCycles`.
- KNOWN §4 "the kill is not repeatable yet on demand" vs §1 (4/4) and `ebf13be`; §4 "lobby reaches gameplay about 4 in 10" and "every online launch fails at login" both superseded by the lobby work.
- KNOWN §2 "the motion-pack overwrite: `StreamSafeCdRead` prime suspect" cleared by research/25.
- STATUS's "current state" block is dated 09-16 and predates audio; the map count is 18, 19 or 20 depending on the file.
- CURRENT_SPRINT's top block still says Sprint 5 pending merge; the live block is buried at line 33; ROADMAP §6's Sprint 6 order is the 09-13 one and its Sprint 7 headline (aim repeatability) is done.
- research/32 §7 still says the ring is at 0x900000 with a warning; `vu1_native_programs.cpp` says native is opt-in; `gs_gl_backend.cpp:1047` describes the cap without saying the queue is unbounded.
- The "Rulings made on the owner's behalf" section stops at R80 (09-15). Since then, unrecorded: the wall-time clock default (a moved default, which the plan's Global Constraints forbid), content-keyed CLUT ids, the transition floor 5→3, the untilref threshold 30→40, the HUD reference re-captured twice, `PS2X_HOST_GAMEPAD` default, skipping Task 2 Step 4's measurement, the sceMpeg demux semantics (consume everything, set audio aside), the presenter drop policy, the equal-priority yield. Each gets a numbered ruling with cost-if-wrong in the close-out.

## 5. Process

The commit rules held throughout (pathspecs, the trailer, `simulated.db` never staged, `ONBOARDING.md` untracked, a
test named in nearly every runtime commit, gate stamps named in STATUS). Two rules did not: the host-window rule was
overtaken by the owner's "proceed autonomously" without being rewritten (CURRENT_SPRINT still states it), and the
same-hour retraction rule for KNOWN was broken by every row in §4 above. The task-review-per-task step (a fresh
implementer, a reviewer re-deriving a number) is not evidenced after 09-15; the last two days read as single-session
work, which is what they were. New standing rule from the owner (09-17): bounded mechanical work goes to Opus agents,
Fable keeps the judgment work; this audit's fix wave was run that way.

## 6. The next sprints

Each sprint ends in something a stranger could notice. Owner items are marked; everything else is autonomous.

**Sprint 7 — "Two strangers, two machines, one hosted server."** A friend on another PC joins a round on a Horizon
instance the project hosts, both from the portable zip.
1. Close Sprint 6 honestly: tick the plan, the KNOWN audit (§4 above), rulings R81+, ROADMAP §6 refreshed, `sprint-6` merged. *(autonomous, first)*
2. The stranger's machine, defensively: the GL capability probe with a CPU fallback and a visible error; a bound on the pending queue when the latch trips; the HIGHDPI flag; the native-VU1 mismatch warning; the ISO handoff already in. *(autonomous)*
3. Online correctness before scale: the equal-priority time-slice removed under a test; the same-RSA-key control round or a per-profile key; the CD stream cursor fix; Task 2 Step 4's ten-launch lobby rate; Task 3's shape-2 freeze A/B. *(autonomous)*
4. The 21k decodes: settle the page-marking hypothesis with the page trace, fix the marking granularity, add the decode budget test; then the ladder's RUNG0 bar passes for real. *(autonomous)*
5. The hosted server: a machine, a public address or DNS name, the router's port forwards, `start-servers.ps1 -PublicIp`, the two picker addresses filled in and the launcher default switched to Unzipped. *(**owner** for the machine and addresses; autonomous for the rest)*
6. The first two-machine match over the internet from the portable zip, both directions of hosting; NAT and clock-skew findings to KNOWN §1 or §2. *(**owner** hands-on with a second machine; the scripts and the readout are autonomous)*
7. The three HUMAN_TASKS reported. *(**owner**)*

**Sprint 8 — "It looks and sounds finished, and it does not scare the machine."**
1. Window policy: default size and fullscreen-borderless, `PS2X_GS_SCALE=2` as the launcher's default with the gate scoring it; render targets sized from use. *(autonomous; **owner** picks the default)*
2. Audio: streams pre-decoded off the audio callback; the aside-cap parity fix and the scratch leak; the stream-start underfill; a per-stage sound regression fixture. *(autonomous; owner listen)*
3. Bare-run robustness: `socom2.exe` with no argument reads `config.json`; an exit-code taxonomy the launcher shows; the diagnostics zip; `SHA256SUMS`; a release build (`-Os`/LTO, stripped, harness DLLs dropped, under 100 MB). *(autonomous; signing is **owner** money and identity)*
4. Knob retirement pass 2 (about 80 `PS2X_*` entries) into a config file plus `--dev`; the stub-state header into a `.cpp`; the invocation stack pool. *(autonomous)*
5. Task 5c verified against the loading screen; the VU0 flag latency; the readback PBO ring. *(autonomous)*
6. An installer (Inno, outline §6) if the owner wants one. *(**owner** decision)*

**Sprint 9 — "Console players in the same lobby, and it stays up."**
1. Task 7 both directions with screen-verified PCSX2 steps. *(autonomous)*
2. A nightly job: N consecutive ladder passes and the lobby rate tracked and published. *(autonomous; **owner** names the machine)*
3. Per-map kill routes for the sweep maps; the two-instance speed freeze lifted. *(autonomous)*
4. Task 6's math oracles and HLE leg 3 as filler. *(autonomous)*
5. Stats and clans across restarts (a real DB) if wanted; the public README and the legal position text. *(**owner** decisions)*
