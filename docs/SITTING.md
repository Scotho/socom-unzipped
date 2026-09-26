# The owner's sitting

> **Generated -- do not edit.** Written by `python -m tools_py.sitting` from `docs/HUMAN_TASKS.md` (the O rows and the stamp of the sittings), the rulings `docs/RULINGS.md` shows (`tools_py.rulings.rows()`), `docs/BACKLOG.md` (the `Carried` column) and `docs/PLAYTEST.md` (its build block). Change a source and regenerate; `python -m tools_py.sitting --check` exits 1 when this file is stale.

The page as of 2026-09-26, for the sitting after the one of 2026-09-17: 17 open O rows (2 answered or struck); 244 active rulings since 2026-09-17 (110 dated, 134 placed by number or home, 68 undated and unplaceable, not listed); 3 issues carried twice; the build: built.

**How to answer.** One line per item, by number -- "O5: acceptable for v1", "R271: overturn", "#25: close" -- in the next session's prompt or as a line in the open plan's Log.

## 1. The O rows

17 open, 2 answered or struck. Each stands on its default until you answer; days waited are to 2026-09-26.

| O | the hand needed | the default the loop is on | first asked | days waited |
|---|---|---|---|---|
| O1 | The legal position on shipping `socom2.exe` and the decrypted `socom2_game.elf` | no public download; builds reach testers only by your hand | 2026-09-20 | 6 |
| O2 | The release archives for `v0.10.0`, `v0.11.0`, `v0.12.0` and `v0.13.0` (its draft 2026-09-26; `v0.14.0`'s at the Sprint 14 close) | the drafts stay empty; the loop may build the archives short of the upload (a backlog row); publishing is always your click | 2026-09-20 | 6 |
| O3 | What the public tree holds and under which terms | nothing moves; GPL-3.0 for the whole tree; unsigned (the FAQ says what SmartScreen shows); the deploy is yours, its wording drafted in `docs/INSTALL.md` | 2026-09-20 | 6 |
| O4 | The bug pipeline's words and the site | no reply is sent (G7: no); the triage routine never opens a public issue for a security report; the relays and the message unsent; no data page | 2026-09-20 | 6 |
| O5 | PSRewired and the mixed revisions | the community preset stays `COMMUNITY_SERVER_ADDRESS_TBC`; nothing connects to a server that is not ours; Task 11b stays withdrawn; the HDD maps are out of v1… | 2026-09-17 | 9 |
| O6 | The machine's windows and a second machine | the scheduled entry stays DISABLED and the ladder runs by hand at night under the lock (S13 O1); every online result is two instances on one host | 2026-09-17 | 9 |
| O7 | Your ears and hands on the current build | the loop does not wait (the listen gate has been bypassed since 2026-09-20); no profile viewer | 2026-09-17 | 9 |
| O8 | A PLAYTEST sitting on the current build | the loop rewrites PLAYTEST for each build it can hand over; the report's log box stays OFF; the download keeps its debugger | 2026-09-20 | 6 |
| O10 | Public actions upstream | nothing filed; the register `docs/UPSTREAM.md` (2026-09-26) holds the vendors' `main` bugs with their local status, the rest beside the drafts; the owner files… | 2026-09-25 | 1 |
| O11 | The naming programme's owner rows | the defaults stand; no hand names; the 148 stay applied; nothing is looked for | 2026-09-25 | 1 |
| O12 | The crouch default | the launcher's `l3` | 2026-09-25 | 1 |
| O13 | Repository settings and history | as they are; no history rewrite | 2026-09-20 | 6 |
| O14 | The merged-branch sweep | the branches and the ruleset stay | 2026-09-20 | 6 |
| O15 | Linux on real hardware | CI and the VM stand in; R107's number stays unmeasured; the VM half (the no-audio-device sentence in LAST RUN, the Linux bug-report send) is the loop's backlog | 2026-09-18 | 8 |
| O16 | Three issues carried twice | keep all three on the backlog; the next plan that names one takes it | 2026-09-26 | 0 |
| O18 | The private-inputs location | nothing changes; the fetch script stays; the loop touches nothing (R277) | 2026-09-26 | 0 |
| O19 | `tools_py/story/site.py`, modified and uncommitted in the main tree | stashed around each night chain and restored (R281) | 2026-09-26 | 0 |

Answered or struck since the last sitting (struck rows live in the archive, `docs/archive/HUMAN_TASKS-to-2026-09-25.md`, its "Struck rows moved from the live table" section; reopenable by number):

- O9: The story's five missing days -- Answered by default (keep), 2026-09-25: S13 S4 wrote them (`d4a8f0ea`, merged `1dcaa57b`); the `../scotho` site copy is the controller's.
- O17: Merge PR #61 (Sprint 13 -> main) -- Done 2026-09-26: you granted the scope; merged `6a82caaa`, tagged `v0.13.0`. The full row is in the archive.

## 2. The rulings since the last sitting

244 active rulings on or after 2026-09-17, in the counter's order (the sprint-local names last, by date): 110 dated on or after it, and 134 with no date in the label but *placed by number* -- above the highest-numbered active ruling dated before 2026-09-17 -- or *placed by home*, its file dated on or after it. Each stands until you overturn it; an overturn is its number and the word. Left out: 68 active rulings with no date, which neither signal places (`docs/RULINGS.md` lists every ruling).

- **R81** (2026-09-17) the guest clock counts wall time by default; the 2026-09-08 exclusion of VU1 and render back-pressure time is now `PS2X_CLOCK_EXCLUDE=1` for an A/B. -- overturn by number
- **R82** (2026-09-17) texture-cache CLUT ids are keyed on the palette's content (FNV-1a over the snapshot), not the CLUT serial. -- overturn by number
- **R85** (2026-09-17) the ten-launch lobby-rate measurement was skipped in favour of the twenty-map sweep and the ladder launches, which reached the lobby on 22 of 24 attempts with… -- overturn by number
- **R86** (2026-09-17) the sceMpeg HLE's demux always consumes its whole input; a video packet the game's stream callback refuses is taken anyway, an audio packet it refuses is set a… -- overturn by number
- **R87** (2026-09-17) the picture presenter drops pictures overdue by a whole interval instead of drifting behind real time, and the decode lookahead is eight pictures (two, the har… -- overturn by number
- **R88** (2026-09-17) a demux call that consumes nothing lets a ready guest thread of any priority run once (`EeScheduler::yieldToAnyReady`), a deliberate departure from the kernel'… -- overturn by number
- **R89** (2026-09-17) the launcher's server picker ships with placeholder addresses for the community and Unzipped servers, and the default preset stays Custom until ours is hosted. -- overturn by number
- **R90** (2026-09-17) the ISO handoff, the hostname resolution, the server's `-PublicIp` and the harness's `env.sh` landed in one fix wave under tests, gated once on the rebuilt exe… -- overturn by number
- **R91** (2026-09-17) `GL_ARB_clip_control` absent is a note, not a fallback trigger. -- overturn by number
- **R93** (2026-09-17) the drag bar is read over the drag window, not the whole stage. -- overturn by number
- **R94** (2026-09-17) the 2x comparison takes two launches of its own (640x448 and 1280x896, same boot screen at launch+40 s, both from the runtime's exported frame) instead of ridi… -- overturn by number
- **R95** (2026-09-18) a 0.15 stick dead zone is applied in all three host pad paths, not just SOCOM's own poll. -- overturn by number
- **R96** (2026-09-18) the page trace ran on the offline mission stage and on the online login stage of a launch that missed the lobby, not on an online gameplay round, because the l… -- overturn by number
- **R97** (2026-09-18) the 989snd PCM ring plays a 256-frame block only if the game rewrote it since the head last played it; a stale block is silence and counts (`pcmUnderruns`, on… -- overturn by number
- **R98** (2026-09-18) the mission dump's bar "RMS never at zero for 10 s under the HUD" is replaced by "no quieter than the pre-change baseline": the driven mission stage ends with… -- overturn by number
- **R99** (placed by number) hostnet's BSD half is a per-platform compat block plus inline forwarders, not a `#else` clause inside each of the seventeen functions. -- overturn by number
- **R100** (placed by number) `win32glue::GameProcess` gains its POSIX state as extra members under `#ifndef _WIN32`, not by packing a pid into the existing `void *process`. -- overturn by number
- **R101** (placed by number) `posix_spawn` with `posix_spawn_file_actions_addchdir_np`, with a `fork`+`chdir`+`execv` fallback only where the extension is absent. -- overturn by number
- **R102** (placed by number) the Linux build writes `dist-linux/`, not `dist/`. -- overturn by number
- **R103** (placed by number) `PS2X_HOST_PROF_ALL` and `PS2X_HOST_PROF_STACKS` are not implemented on Linux this sprint, and say so out loud. -- overturn by number
- **R104** (placed by number) `keep_on_top` on Linux is `xdotool windowraise`, a momentary raise, not a sticky always-on-top. -- overturn by number
- **R105** (placed by number) `dist/socom2.exe` is allowed to move exactly once in this sprint — when `HostProfLine::format` and `CpuTimeMs::perSecond` are extracted and the Windows code st… -- overturn by number
- **R106** (2026-09-18) the audio bar (the intro correlating with the disc at 0.99) is read from the gate's driven title stage in the VM (Task 10), not from the bare boot Task 8 plann… -- overturn by number
- **R107** (placed by number) the per-call trace is a new knob on its own line, not a widening of the `[gs-gl stats]` line. -- overturn by number
- **R107b** (2026-09-18) the Linux audio bar (the title music correlating with the disc at 0.99) is not readable in the VM and moves to the owner's real-GPU run (HUMAN_TASKS). -- overturn by number
- **R108** (placed by number) a merge is allowed only where the merged rectangle is covered exactly by the rectangles it replaces. -- overturn by number
- **R108b** (2026-09-19) per-call overhead is not the menus' cost, so the tile coalescer (Task 2) and its bar (Task 3) are not built. -- overturn by number
- **R109** (placed by number) the end-to-end GL case is guarded by `PS2X_GS_TESTS_GL`, and the coalescer's own cases are not. -- overturn by number
- **R109b** (2026-09-19) The launcher's default preset moves from `custom` to `unzipped` now that 3.143.65.100 is real — why: the Sprint 7 spec said the default switches "when ours is… -- overturn by number
- **R110** (placed by number) the bar is read over the login-screen window, not over the whole run. -- overturn by number
- **R110b** (2026-09-19) The static IP ships in the launcher rather than a DNS name — why: no domain is owned and buying one is the owner's money; `horizon-ctl.sh public-ip` and the pr… -- overturn by number
- **R111** (2026-09-19) Task 2's test was written before the script but never seen RED (the script followed in the same step); its six cases were run GREEN only — why: the rule's purp… -- overturn by number
- **R112** (placed by number) the module reads the entire send block before it writes one byte of reply. -- overturn by number
- **R113** (placed by number) Enumerate's block reports zero Logitech vendor extensions (`kEnumEntryCount` = 0). (amended: see the ledger) -- overturn by number
- **R114** (placed by number) (Task 1's interface list, `MicFormat::supported()`, and Task 2 Step 5): only mono, 16-bit, 4000-48000 Hz is supported; any other format is refused at Open with… -- overturn by number
- **R115** (placed by number) `PS2X_MIC_FAKE` beats `PS2X_MIC_DEVICE` when both are set — because every driven run sets the fake one deliberately and a stale device name in the environment… -- overturn by number
- **R116** (placed by number) in the driven two-instance match A talks and B listens. -- overturn by number
- **R117** (placed by number) `[gs-transfer]` is a second line under the existing knob, not a widening of `[gs-upload]` or of `[gs-gl stats]`. -- overturn by number
- **R118** (placed by number) an identical upload is skipped only when no render target overlapping its pages is `gpuDirty` or `shadowStale`. -- overturn by number
- **R119** (placed by number) only an upload that delivers the whole transfer in one call is a skip candidate. -- overturn by number
- **R120** (placed by number) the identity check is a hash of the incoming bytes, not a `memcmp` against the shadow. -- overturn by number
- **R121** (placed by number) Task 3's content is chosen by Task 1's table, not by this plan, and the branch not taken is recorded as such. -- overturn by number
- **R123** (2026-09-19) the fix moves to the consumer. -- overturn by number
- **R124** (2026-09-19) a hard ceiling on pending GS command bytes. -- overturn by number
- **R125** (2026-09-19) the goal closes on the symptom, not on the 60 ms/s proxy. -- overturn by number
- **R126** (placed by number) the shared code lives in a new library, `third_party/ps2recomp/ps2xShared/` (`ps2x_shared`), and `iso9660`, `sha256` and `launcher_config` move into it with th… -- overturn by number
- **R127** (placed by number) the numbers are 66-72 contiguous, and 1 and 3 are named rather than moved. 66 disc not found, 67 not r0001, 68 ELF, 69 config, 70 crash, 71 out of memory, 72 c… -- overturn by number
- **R128** (placed by number) a crash keeps its native exit status, and `ExitCodes::classify` folds it onto 70 for whoever reads it; the crash handlers are not touched. -- overturn by number
- **R129** (placed by number) "audio device absent" is a `[notice] ` line in the log, read back by the launcher, not an exit code. -- overturn by number
- **R130** (placed by number) the preflight is fatal, runs for every start of `socom2_game.elf` including the gate's, and has no off switch. -- overturn by number
- **R131** (placed by number) the bare run — absent `config.json` is the defaults, the environment wins over the file, the card folder is made absolute, the process changes directory to its… -- overturn by number
- **R132** (placed by number) a bare run writes `logs/run_<stamp>.log` itself and, on Windows, lets go of a console it alone owns. -- overturn by number
- **R133** (placed by number) the zip writer is written here: STORE only, CRC-32, no zip64, built in memory. -- overturn by number
- **R134** (placed by number) "credential fields removed" is an allowlist, the ISO path is cut to its file name, the home directory is scrubbed from every entry — and `server`, `profile` an… -- overturn by number
- **R135** (placed by number) the crash record is the log's own `[crash]` / `[terminate]` / `[main] fatal` / `[oom]` / `[preflight] exit` / `[gs-gl] FATAL` lines, and the log is clipped to… -- overturn by number
- **R136** (placed by number) `socom2 --fail-test crash|oom` ships in the release executable. -- overturn by number
- **R137** (placed by number) the button is renamed SAVE DIAGNOSTICS, writes `diagnostics/socom_unzipped_<stamp>.zip`, and opens that folder. -- overturn by number
- **R138** (placed by number) `scripts/make_portable.sh` writes `version.txt` (`SOCOM Unzipped <git describe> (<UTC date>)`). -- overturn by number
- **R139** (2026-09-19) a crouch shortcut. -- overturn by number
- **R140** (placed by number) "release" is a second build tree with different switch values, not a CMake build type; it writes `dist-release/` and nothing else reads that folder unless told… -- overturn by number
- **R141** (placed by number) the override is `SOCOM_EXE`, beside `SOCOM_ISO`, not a `PS2X_*` name and not a `--exe` flag; the runner must still be called `socom2[.exe]`; the gate's summary… -- overturn by number
- **R142** (placed by number) the runtime library stays at `-O3`; `-Os` for it is not built. -- overturn by number
- **R143** (placed by number) between `-O2` and `-Os` for the generated code, the smaller archive wins unless they are within 2 %, in which case `-O2`; speed is a floor (97 % of the develop… -- overturn by number
- **R144** (placed by number) how the stop rule is read. *"Past 30 minutes"*: `link_seconds` from `.ninja_log`, and — because a runaway link must be stoppable without watching it — a wall-c… -- overturn by number
- **R145** (placed by number) the Windows folder ships the sixteen DLLs the import tables reach, and `libwinpthread-1.dll` is dropped with the other fourteen. -- overturn by number
- **R146** (placed by number) symbols are the symbol table split out with `objcopy --only-keep-debug`, not DWARF; the release is not built with `-g`. -- overturn by number
- **R147** (placed by number) `SHA256SUMS` is an integrity check, one file per archive directory, in `sha256sum -c` format; it is not a signature and the archives are not reproducible. -- overturn by number
- **R148** (placed by number) the 3/3 bar is the Windows gate's; Linux's release build is proven by the exit-code suite on the release runner, the audit, the checksum and the tarball's own… -- overturn by number
- **R149** (placed by number) identical-code folding (`--icf=all`) is measured although the spec does not name it, and ships only under the same stop rule as LTO. -- overturn by number
- **R150** (placed by number) the closure rule applies to the developer packaging too (`make_portable.sh` with no flag), not only to `--release`. -- overturn by number
- **R151** (2026-09-20) the release executable keeps `-O1` for the generated code; `-Os`, and both LTO scopes, are not built. -- overturn by number
- **R152** (placed by number) the number is 134, and the scope is what a shipped executable reads. -- overturn by number
- **R153** (placed by number) the registry is the accessor's table — one X-macro header in `ps2x_shared`, read by Python with a regex, exactly as `exit_codes.h` is. -- overturn by number
- **R154** (placed by number) `ps2x::knob` never snapshots the environment, and its unset path is one `getenv` with no table search; the ten hot sites cache at the site. -- overturn by number
- **R155** (placed by number) developer mode is `--dev` or `PS2X_DEV=1`; the harness gets it from `run.sh`, `env.sh` and `hostplatform.dev_env`, by default-if-unset, so… -- overturn by number
- **R156** (placed by number) the launcher never sets developer mode and gets no hidden option; it drops inherited `PS2X_*` variables from the game's environment unless it was itself starte… -- overturn by number
- **R157** (placed by number) one gate for all eight no-behaviour-change batches, not one per runtime commit; the batch commits stay local until it passes. -- overturn by number
- **R158** (placed by number) the five deletions ride on Task 7's gate rather than their own. -- overturn by number
- **R159** (placed by number) five names are DEAD on the evidence in the inventory section; two more were never knobs. -- overturn by number
- **R160** (placed by number) `PS2X_SOCOM2_PAD` flips from opt-in-by-presence to on-by-default; it stays Shipping and the launcher keeps sending `1`. -- overturn by number
- **R161** (placed by number) seven presence-tested A/B switches (and the pad) move to the flag rule; presence-tested traces do not. -- overturn by number
- **R162** (placed by number) under enforcement an empty value is unset, for every knob. -- overturn by number
- **R163** (placed by number) "the gate 3/3 with an empty environment" is restated as: *(a) with no developer mode, a launch whose environment holds six behaviour-changing Dev knobs runs as… -- overturn by number
- **R164** (placed by number) precedence stays asymmetric: `config.json` beats an inherited variable under the launcher; the variable beats `config.json` in a bare run. -- overturn by number
- **R165** (placed by number) `PS2X_FPU_TRAP` is migrated too, at the price of one full generated rebuild (twice: the host and the VM; and the release tree the next time `build.sh release`… -- overturn by number
- **R166** (placed by number) one online control round after the flip, although no online knob's meaning changes. -- overturn by number
- **R167** (placed by number) Linux is proven by CI, the VM's C++ and Python suites and `test_knobs_line` on the Linux runner; the VM's title stage is read for its log, not its score. -- overturn by number
- **R168** (placed by number) the namespace-scope-read check is a heuristic on this tree's naming (`g_` globals, column-0 `static`), not a parser. -- overturn by number
- **R169** (placed by number) `parentHandle` is a queue, and the wire says so. -- overturn by number
- **R170** (placed by number) a fade belongs to the cue, not to the handle. -- overturn by number
- **R171** (placed by number) the stream decoder reads the VAG flags the bank decoder always read. -- overturn by number
- **R172** (placed by number) PROPOSED, not taken: the concurrency cap and the clip. -- overturn by number
- **R173** (2026-09-19) the CONTROLLER page's live pad DISPLAY stays alive while the game runs -- it moves no focus, and a player who alt-tabs to check a pad should not find a dead pi… -- overturn by number
- **R174** (placed by number) Goal 12 is split: the data path is Sprint 9, the UI is Sprint 10. *Decided 2026-09-19 by the controller under an explicit delegation from the owner* ("overseer… -- overturn by number
- **R175** (placed by number) P6's persona measurement is not run, the launcher's default preset moves to `socom.scotho.com`, and the hosted server goes on advertising its IP literal. *Deci… -- overturn by number
- **R176** (placed by number) ADVANCED is a per-page section, it holds one thing today, and it cannot hide a setting that is doing something. *Decided 2026-09-19 by the controller; the spec… -- overturn by number
- **R177** (placed by number) the mix is rendered into a device the runtime opens itself, at 20 ms periods x 4 (80 ms in flight), not raylib's 10 ms x 3. *Decided 2026-09-20 by the controll… -- overturn by number
- **R178** (placed by number) the mixer runs the conductor grains: child sounds, registers, markers, cycles, as the open 989snd reimplementation runs them. *Decided 2026-09-20 by the contro… -- overturn by number
- **R179** (placed by number) the password is stored in plain text in `config.json`, masked on screen. -- overturn by number
- **R180** (placed by number) prefill, never auto-submit. -- overturn by number
- **R181** (placed by number) secret scanning, push protection and Dependabot alerts are ON, turned on by the controller under the owner's words. *Decided 2026-09-20.* HANDOFF §5 rule 13 ke… -- overturn by number
- **R182** (placed by number) rulesets on `main` and `sprint-*`, as GIT_STRATEGY §6 designed them, with one deviation: no CODEOWNERS review required and no bypass. *Decided 2026-09-20.*… -- overturn by number
- **R183** (placed by number) the leak check is the monitor's rules adapted for a SOURCE tree, not copied. *Decided 2026-09-20.* The monitor's set was built for a published snapshot, where… -- overturn by number
- **R184** (placed by number) the mid-sprint merge to `main` -- the owner asked for the hardening and the developer setup on `main` as soon as possible (PR #5, `sprint-10` -> `main`, valida… -- overturn by number
- **R185** (placed by number) any drift refuses, whatever `--only` asked for. -- overturn by number
- **R186** (placed by number) the harness is recorded, never compared. -- overturn by number
- **R187** (placed by number) an operator's extra `PS2X_*` variable is a drift. -- overturn by number
- **R188** (placed by number) the first run that prints a mapping hash is refused until accepted. -- overturn by number
- **R189** (placed by number) the state stream is absorbed, not waited on. -- overturn by number
- **R190** (placed by number) `Present` is droppable at the cap on a latched stall. -- overturn by number
- **R191** (placed by number) the bounds: 512 rectangle pieces, 8 per key, 256 palettes, 4 MB. 256 is the replay's own CLUT eviction window (a re-anchor of more would evict its own first en… -- overturn by number
- **R192** (placed by number) no launch from this branch. -- overturn by number
- **R193** (placed by number) the mapping is per profile, and a default mapping is not written and not sent. config.json carries a mapping only for a profile that changed one;… -- overturn by number
- **R194** (placed by number) the environment string is the whole table or nothing. -- overturn by number
- **R195** (placed by number) the keyboard table is data but not rebindable from the page. -- overturn by number
- **R196** (placed by number) the sticks and Triangle's pressure are not in the table. -- overturn by number
- **R197** (placed by number) "per-profile presets" is read as the mapping saved per profile, nothing more. -- overturn by number
- **R198** (placed by number) bind on RELEASE, B held cancels, a tap of B binds B. -- overturn by number
- **R199** (placed by number) the section switch is launcher state, not a setting. -- overturn by number
- **R200** (placed by number) the override is a runtime `replaceFunction` wrap, not a `recomp/socom2.toml` stub; no recompile. -- overturn by number
- **R201** (placed by number) the persona name keeps every character the game's keyboard has, not only letters and digits. -- overturn by number
- **R202** (placed by number) the password is capped at 12 in the launcher (the plan drew its field at 32). -- overturn by number
- **R203** (placed by number) `PS2X_DEV` enters the harness below the gate's env pin, and the pin is not widened for it. -- overturn by number
- **R204** (placed by number) `PS2X_INPUT_MAPPING` is the eighteenth Shipping name. -- overturn by number
- **R205** (placed by number) `PS2X_LAUNCHER_API_BASE` is a Dev knob read through `ps2x::knob` in the launcher, and the launcher's Python test sets `PS2X_DEV=1` on the launcher it starts. -- overturn by number
- **R206** (placed by number) The two helpers `SchedTrace.cpp` grew after the plan (`envOn`, `envMsToNs`) are migrated under rule 2 like the plan's seven, and a check that no non-literal… -- overturn by number
- **R207** (placed by number) Every Path-kind knob is constrained to the portable folder, or refused -- but not in this pass. -- overturn by number
- **R208** (2026-09-21) The `[knobs]` line never writes a credential's value: `PS2X_SOCOM2_LOGIN_PASS` is printed as `[redacted]`, in developer mode too. -- overturn by number
- **R209** (placed by number) "Q2's Task 8 VM ring deferred to the sprint close, CI is the Linux ring, the VM stays off" -- overturn by number
- **R210** (placed by number) The keyboard's gameplay mapping — the WASD/IJKL sticks and the keys bound to L1/R1/L2/R2/L3/R3 — is honoured only in developer mode (`PS2X_DEV=1` / `--dev`), w… -- overturn by number
- **R211** (placed by number) while the game runs the pad drives the launcher NEVER, in front or behind; the switch is the one button the gate passes. -- overturn by number
- **R212** (placed by number) the switch is a binding, in BUTTONS, with OFF beside it; the guide by default. -- overturn by number
- **R213** (placed by number) an Xbox pad's guide button is read from XInput's ordinal 100 on Windows. -- overturn by number
- **R214** (placed by number) no header bar on the game window in this pass. -- overturn by number
- **R215** (placed by number) the game window's title is `"<game> -- SOCOM Unzipped"` and the harness's key moved with it. -- overturn by number
- **R216** (placed by number) the launcher's cues play at 0.45 of their rendered level, and the setting lives on AUDIO. -- overturn by number
- **R217** (placed by number) the cache is keyed by content, not by path. -- overturn by number
- **R218** (placed by number) Goal 4 is closed on its own stop rule, without a launch. -- overturn by number
- **R219** (placed by number) Sprint 8's R113 stands with its meaning corrected, and the HLE is not changed for it. -- overturn by number
- **R220** (placed by number) the HLE's state word stays at "1 once, then 2". -- overturn by number
- **R221** (placed by number) the one launch worth making is a peek, not a proof, and it is queued behind the sprint's ranked items. -- overturn by number
- **R222** (placed by number) the console-replay case runs wherever `game/console_replay` exists and says "skipped" where it does not; the GL half stays behind `PS2X_CONSOLE_REPLAY_GL=1` (R… -- overturn by number
- **R223** (placed by number) the card's cluster count is walked once per game-side change, not per poll. -- overturn by number
- **R224** (placed by number) a card root that cannot take a file answers "no card" and leaves exit 72; it does not stop the game from inside the HLE. -- overturn by number
- **R225** (placed by number) a write past the card's capacity is refused whole with `sceMcResFullDevice` (-3), never partially written. libmc's answer; a partial write would leave a save t… -- overturn by number
- **R226** (placed by number) the microphone resampler walks the product `phase + step * k`, not a running sum, and reports what it consumed. -- overturn by number
- **R227** (placed by number) the stub helpers live in namespace `stub_support` with a global using-directive in the header. -- overturn by number
- **R228** (placed by number) the synthetic Linux packaging test asserts the executable bit on Linux only. -- overturn by number
- **R230** (placed by number) the expectations file holds sha256 digests of whole game files, in the tree. -- overturn by number
- **R231** (placed by number) a difference in the image's *shape* is a note, not a refusal. -- overturn by number
- **R232** (placed by number) the four DNAS cipher addresses are recorded rather than derived. -- overturn by number
- **R233** (placed by number) the extracted tree is verified by size against the image's own directory records, not re-hashed. -- overturn by number
- **R234** (placed by number) `CONTRIBUTING.md` now says the game build is supported, on the evidence of one disc image on one machine. -- overturn by number
- **R235** (placed by number) the from-nothing run reused the toolchain archives already in the main tree's bootstrap cache. -- overturn by number
- **R236** (placed by number) the launcher's default window is the game's own 640x448 (the owner, 2026-09-22: "the default res should be the 640x448"), overturning Sprint 7 Task 1c's 2x def… -- overturn by number
- **R237** (placed by number) REWRITTEN 2026-09-23: the prefilled login STAYS in the player path, because the experiment the ruling set itself failed. -- overturn by number
- **R238** (placed by number) a failure the player can see must never be silent, and that is not a question of knobs. (amended: see the ledger) -- overturn by number
- **R240** (placed by number) the join driver presses REFRESH LIST before JOIN GAME, and takes a channel. -- overturn by number
- **R241** (placed by number) the four external-repo items (upstream PR #244's real-IRX IOP, the cherry-pickable GS/VIF/SIF PRs, the SOCOM 1 demo symbols, the MrCoolTheCucumber fork) become… -- overturn by number
- **R242** (placed by number) Goal 4's per-map kill routes carry to Sprint 11 as [A] filler; the speed-freeze half is re-measured from existing logs. -- overturn by number
- **R243** (placed by number) milestone U item 1's step (b) is redefined as a differential test, not a music-parity number. -- overturn by number
- **R244** (placed by number) W8's fallback run is not run separately: the ladder streak proves the join driver's R240 path. -- overturn by number
- **R245** (2026-09-23) option B is not scheduled. -- overturn by number
- **R246** (2026-09-23) the chat bound's install is the proof Milestone S ships on; the traversal is a filler row. -- overturn by number
- **R247** (2026-09-23) the vendored tree's baggage goes. -- overturn by number
- **R248** (2026-09-23) the r0004 patch is PSRewired's resident capsule, and the build applies it, not a package. (amended: see the ledger) -- overturn by number
- **R250** (2026-09-23) R249 was half right: the DNAS bypass is the door, and the r0004 package is behind it, served by PSRewired. -- overturn by number
- **R251** (2026-09-23) R249 retracted on substance; r0004 is a real rebuild and its ELF exists. -- overturn by number
- **R252** (2026-09-23) the known-issue stack opens on GitHub issues. -- overturn by number
- **R253** (2026-09-24) one closed KNOWN §2 row and every pointer to it are retired from the public documentation; history and the old branch tips stay. -- overturn by number
- **R254** (2026-09-24) the r0004 reboot is an image defect, undone from the capsule's decoded write stack, never patched per call site. -- overturn by number
- **R255** (2026-09-24) the loop lock goes to the r0004 critical path first. -- overturn by number
- **R256** (2026-09-24) an override the runtime cannot execute is not an override. -- overturn by number
- **R257** (2026-09-24) the demo names apply to the function map in `Class_Method` form, one reviewed commit at a build window. (amended: see the ledger) -- overturn by number
- **R258** (2026-09-24) Task 7b: positional naming between anchors and the Aug 18 2003 demo as a bridge, lock-free, a second proposals file under its own rule, never the csv directly. -- overturn by number
- **R259** (2026-09-24) deferred to a future sprint: Ghidra Version Tracking as a cross-check of the 987, and the ccc route for the demo's `.debug` types; the voice-codec record is in… -- overturn by number
- **R260** (2026-09-24) Task 7c: vtable-slot matching through RTTI, its own lock-free task after 7b lands, a third proposals file (pass name `vtable-slot`, scored below `exact`). (ame… -- overturn by number
- **R261** (2026-09-24) R257's rename commit also writes a tracked provenance sidecar beside `recomp/socom2_ghidra.csv` (address, name, source pass, score, evidence), carried by… (ame… -- overturn by number
- **R262** (2026-09-24) declined, with the peer's reasons: a custom Ghidra Function ID database (it is `fingerprint.py` plus the callee-set pass re-implemented, and cannot cross the 7… -- overturn by number
- **R263** (2026-09-24) the naming programme is Sprint 12, not Sprint 11. -- overturn by number
- **R264** (2026-09-25) (after: Sprint 12's rulings are `S12-R1`–`S12-R25` in the plan's "Rulings made on the o…) they keep those names — renumbering twenty-five rulings cited across… -- overturn by number
- **R265** (2026-09-25) the four oldest backlog rows owned or declined -- overturn by number
- **R266** (2026-09-25) the six issues Sprint 11 carried go once into Sprint 13's milestone -- overturn by number
- **R267** (2026-09-25) one home for the carry (`docs/BACKLOG.md`, generated, a Sprint 13 file) -- overturn by number
- **R268** (2026-09-25) byte ceilings on the appending documents and a tag check on "merged as vX" claims. -- overturn by number
- **R269** (2026-09-26) an infrastructure sprint ahead of visible defects, in the order G, I, W, D, S, E, M. -- overturn by number
- **R270** (2026-09-26) KNOWN §4's standing hazards move to their own file (`docs/HAZARDS.md`, class L, headed by the area each bites), KNOWN keeping §1–§3. -- overturn by number
- **R271** (2026-09-26) an owner row that has stood through two sittings without an answer is closed by default at the next close, under a ruling, struck with the date and the default… -- overturn by number
- **R272** (2026-09-26) STATUS's log below its live block is archived verbatim and the changelog is generated from the merge commits and tags (`python -m tools_py.changelog`, class G). -- overturn by number
- **R273** (2026-09-26) sprint-local ruling namespaces are retired from this sprint on; the global counter in HANDOFF is the only one, and its second line in CURRENT_SPRINT goes (Task… -- overturn by number
- **R274** (2026-09-26) a held-out capture leg the implementing agents never see, twelve references under `scripts/parity/refs/heldout/`, taken by the controller at a quiet window, re… -- overturn by number
- **R275** (2026-09-26) at most two building agents at once, enforced by the queue (a third build ticket is refused with "queue full: do lock-free work"). -- overturn by number
- **R276** (2026-09-26) Sprint 15 is "borrowed confidence", opened from the confidence register at this sprint's close, its pair proposed beside this one (… -- overturn by number
- **R277** (2026-09-26) the private location that served the owner's ELF dumps to cloud sessions has no consumer and is the owner's to retire or rotate (HUMAN_TASKS row O18); the fetc… -- overturn by number
- **R278** (2026-09-26) while the lock is held or queued by other sessions' builders, lock-free tasks from Milestones D, S and M may run ahead of Milestone W; W's tasks start at the f… -- overturn by number
- **R279** (2026-09-26) the open plan's ceiling is one number in `CEILINGS` like the others: ratcheted at each close from the closing plan's size (before CURRENT_SPRINT's `plans:` lin… -- overturn by number
- **R280** (2026-09-26) the held-out leg's twelve stamps are chosen for stability across green runs: title s03, s09, s15; transition s06, s08; mission s06, s08, s10, s12, s16, s20, s2… -- overturn by number
- **R281** (2026-09-26) an orphaned working-copy change in the main tree (a modified tracked file whose session is gone) is stashed by the controller around each lock-bound chain (… -- overturn by number
- **R282** (2026-09-26) the LLE IOP running the disc's own IRX is a candidate for the audio trial, with its bar argued both ways in X1; the owner decides whether it is tried. -- overturn by number
- **R283** (2026-09-26) a candidate that changes the generated image's shape runs only with a full recomp, the re-derivation job green, `--accept-pins` after a green run, and a ruling. -- overturn by number
- **R284** (2026-09-26) no upstream PR or issue is filed from this sprint; what we could give back is written into `docs/UPSTREAM.md` for row O10. -- overturn by number
- **R285** (2026-09-26) register rows that are Proven today are excluded from the survey unless a source contradicts the proof, and then the artefact it contradicts is named. -- overturn by number
- **R286** (2026-09-26) the time boxes are R half a day, X one day, T1 and T2 the second and third days, the close by the fourth; T3 and T4 only if time allows; a phase past its box h… -- overturn by number
- **R287** (2026-09-26) the "overwhelming case" bar for a large take stands: a TAKE over about five hundred lines needs a ruling of its own. -- overturn by number
- **R288** (2026-09-26) the order of the work is audio first, then #67 the drag freeze beside it, then the measurements #59 and #32. -- overturn by number
- **R289** (2026-09-26) the walk list's non-audio subsystems are deferred to `docs/LATER.md` and not registered this sprint; VU1 is deferred there with its experiment written. -- overturn by number
- **S12-R1** (2026-09-24) the four naming defaults stand as the spec states them: `Class_Method` with an argument-list suffix only on collision (D1); no hand-named row is ever renamed b… -- overturn by number
- **S12-R11** (2026-09-24) a rename that moves a decoded range is accepted only when the cloud's own recomp shows no new `unmapped` or `unhandled` continuation and no function dropped; a… -- overturn by number
- **S12-R12** (2026-09-24) an `offset-multiset` pass is Task 13 at 0.75, and an independent body key is a valid second signal for a prologue pair (amends S12-R3). research/54: the multis… -- overturn by number
- **S12-R13** (2026-09-24) the sidecar is the one home of a name, and the recompiler reads it; the csv's `Name` column is never rewritten by the applier (amends S12-R4's letter; retires… -- overturn by number
- **S12-R14** (2026-09-24) leading underscores are stripped where the live sanitiser would rewrite them, with research/47's `u`×k spelling only as the collision fallback. research/47's R… -- overturn by number
- **S12-R15** (2026-09-24) the UI script-binding table is a pass, Task 14. research/55 §4.2: both builds carry a table of (command string, handler) rows; the demo names 131 of its 147 ha… -- overturn by number
- **S12-R16** (2026-09-24) Goal 3's rules are amended to what research/51 measured. -- overturn by number
- **S12-R17** (2026-09-24) `sceCdDiskReady` is 0x0018ef70, as the toml binds it; Task 7's row for 0x0018ed78 is held, the third line of the holds file. -- overturn by number
- **S12-R18** (2026-09-24) a `callgraph` pass is Task 15, in two tiers, and two independent keys agreeing is the sprint's promotion rule. research/52: the caller side alone adds 45 pairs… -- overturn by number
- **S12-R19** (2026-09-24) a name is legal when the LIVE sanitiser returns it unchanged; the code generator's unused copy is not a bar. research/61 §1.5:… -- overturn by number
- **S12-R2** (2026-09-24) the tools are installed natively under `/home/user/tools/`, not in a container, and a refusal retires the goal. -- overturn by number
- **S12-R20** (2026-09-24) the UI script-binding table outranks a sub-64-byte `exact` anchor, and a held address is no anchor for any lever. -- overturn by number
- **S12-R22** (2026-09-24) BinDiff confirms under a bounded rule and never proposes alone; the big engine routines stay the owner's hand review (amends S12-R3 and D5). research/49: raw B… -- overturn by number
- **S12-R3** (2026-09-24) no prefix pair is admitted on a person's reading; R257's "reviewed by hand for the big engine routines" is replaced for this sprint by a second mechanical sign… -- overturn by number
- **S12-R4** (2026-09-24) the csv and the sidecar are the one home of a name; the toml's stub list stays what it is, a handler selector, held to the csv by a test. (amended: see the led… -- overturn by number
- **S12-R5** (2026-09-24) research/43b's `match.json` rate (81.1 %, 12,071 placements) is not reproducible from tracked inputs, and the sprint's r0004 carry rests on the documented reci… -- overturn by number
- **S12-R6** (2026-09-24) research numbers 46–59 are Sprint 12's, assigned in Task 0b's table; 60 is Task 4's note. -- overturn by number
- **S12-R7** (2026-09-24) the sidecar's backfill is 69 Ghidra rows, not 113 hand rows; the placeholder predicate is anchored and shared by the audit and the carry; uniqueness is scoped… -- overturn by number
- **S12-R8** (2026-09-24) a `string-set` pass is Task 12, and Task 7's row 478 is held out of the rename until a body read settles it. research/53 measured the set of shared strings a b… -- overturn by number
- **S12-R9** (2026-09-24) row 478 is wrong, and the applier keeps a tracked holds file. -- overturn by number
- **S12-R21** (2026-09-25) a hold names an (address, proposed name) pair, not an address. -- overturn by number
- **S12-R23** (2026-09-25) BinDiff is not a confirming key for promotion (narrows S12-R22), and a BinDiff contradiction of another lever's strict row is a dispute to read, not a tie to i… -- overturn by number
- **S12-R24** (2026-09-25) a hold can un-apply; an alias is not a contradiction; the entry row keeps `entry`; a Ghidra-split tail is not a function. -- overturn by number
- **S12-R25** (2026-09-25) research/46 is the peer's day-one record; the consumers note is research/61. -- overturn by number
- **S13-R1** (2026-09-25) the order is V, R, H, C, U, S, N, O. -- overturn by number
- **S13-R10** (2026-09-25) the oversized function bounds go to the backlog as issue #55, not this sprint. -- overturn by number
- **S13-R11** (2026-09-25) no cloud session was opened this sprint, so the [C] tasks are dispositioned without one: N3 is done by R7 (`docs/BACKLOG.md` is the carry's home); U3 (#253's e… -- overturn by number
- **S13-R2** (2026-09-25) lock-bound runs on the owner's nights are allowed, one at a time, never a game window when the owner has said they are at the machine, nothing that needs their… -- overturn by number
- **S13-R3** (2026-09-25) the frame-time pin is informational until three gates agree on its spread; the refusal rule is set then, from the numbers. -- overturn by number
- **S13-R4** (2026-09-25) a live write primitive jumps the order. -- overturn by number
- **S13-R5** (2026-09-25) a run whose stages FAIL sets no standard. -- overturn by number
- **S13-R6** (2026-09-25) the codex audit's work is dispositioned on its merits; its allocation to a second model, and the head-to-head that would measure it, are declined. -- overturn by number
- **S13-R7** (2026-09-25) process-specific loopback capture is not added as an audio instrument now. -- overturn by number
- **S13-R8** (2026-09-25) the link-resolving containment applies to the memory-card root only; the disc and host roots keep the lexical walk. -- overturn by number
- **S13-R9** (2026-09-25) a server name that does not resolve is a LAST RUN notice, not a process exit code. -- overturn by number
- **S13-R12** (2026-09-26) the close's issue-stack read, acted on. -- overturn by number
- **S13-R13** (2026-09-26) the frame-time pin stays informational; #59 carries with the measured reason. -- overturn by number
- **S13-R14** (2026-09-26) the carried-twice three go to the owner, the rest carry once to the backlog. #25 (the Linux VM suites; no Sprint 13 task), #26 (the chat bound's path; O2 resta… -- overturn by number

## 3. The issues carried twice

3 issues carried twice at `Carried` 2 or more in `docs/BACKLOG.md`: keep each on the backlog, or close it as not planned under a ruling.

- #25 (linux, carried 2) The Linux VM's suites are not green on the merged tree: four C++ and four Python cases
- #26 (harness, carried 2) No run has shown a received chat line crossing the client bound: the harness cannot open the chat box
- #42 (audio, carried 2) About 50 ms of the mission music is lost between the mixer's render() and the device, on any endpoint

## 4. The build

The build `docs/PLAYTEST.md` names, to play and to check against:

```
build:    2026-09-26T16:19:17Z   commit 352fed01dc2b (sprint-14)
archive:  socom2-portable.zip   (dist-release/portable/socom2-portable.zip)
sha256: 6f8246448ecbb8bd4fe1d909a793813ea1130f3436c64ede69b6d6681cf533f6
exe:      socom2.exe sha256: 8be2ee0c8bc9aa059f79392f2150c199a46916f22abc1fc45f27083183f23568
```
