# Feature completion map (2026-10-11)

A snapshot of every part of the project scored on one stage scale, taken on `main` at `70c62146`. The scores are
judgement calls drawn from `docs/KNOWN.md`, the Sprint 17 and 18 plans, `docs/BACKLOG.md`, `docs/LATER.md` and the
code; no document states them. `docs/KNOWN.md` wins on any disagreement with this file.

**The game** (the first nine categories): **55%**. **Around it** (infrastructure and the web companion): **78%**.

## The stage scale

| % | Stage | Meaning |
|---|---|---|
| 0 | Not started | nothing in the tree yet |
| 10 | Researched | understood on paper or by a spike; no working code |
| 30 | Prototype | works under the harness or a developer knob, not for a player |
| 50 | Functional | works end to end, with known gaps a player would hit |
| 70 | Playable | a player can use it today; rough edges remain |
| 85 | Hardening | complete, being measured against the console and made robust |
| 100 | Ready | shipped quality: proven, measured, nothing known open |

## The goal track

The goal every sprint serves (`docs/CURRENT_SPRINT.md`): a stranger plays a stranger, from their own disc.

- [x] Boots from your own disc to the title
- [x] Plays a single-player mission
- [x] Logs in and plays a round online (harness, one host)
- [x] Rounds hold up across scheduled runs (ladder bar 7)
- [ ] A program-only public download
- [ ] Two people on different networks play a round
- [ ] Plays on a community server

## Categories

| Category | % | |
|---|---|---|
| Engine: CPU and system | 66 | `███████░░░` |
| Engine: graphics | 60 | `██████░░░░` |
| Sound and voice | 45 | `████░░░░░░` |
| Input and storage | 75 | `████████░░` |
| Game content | 71 | `███████░░░` |
| Online client | 53 | `█████░░░░░` |
| Server | 41 | `████░░░░░░` |
| Platforms | 55 | `██████░░░░` |
| Getting it to players | 33 | `███░░░░░░░` |
| Project infrastructure | 83 | `████████░░` |
| Web companion | 72 | `███████░░░` |

## Engine: CPU and system -- 66%

The recompiled game code and the PS2 it expects underneath.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| EE recompilation | 85 | Hardening | All 14,879 map rows recompile; gate 3/3 PINS MATCH on every chain; r0004 builds and passes too. | Map hygiene #54/#55, stub slot #60, VU0 flag latency #47; disc-to-ELF proven on one disc, Windows only. |
| Kernel, threads, DMA, boot | 80 | Playable | Priority scheduler; LoadExecPS2 restarts in-process (logoff to main menu, 2026-09-29); drag freeze fixed. | Scheduler, timers, FPU clamping and VIF1/GIF/DMAC never checked against a console (LATER 10, 11, 13). |
| Movies (IPU/MPEG) | 85 | Hardening | FFmpeg-backed MPEG HLE; intro macroblock race and PCM-ring starvation fixed; movies play on every gate. | Movie audio about 18 dB low; #114 stall seen during movies. |
| Decompilation (readable names) | 13 | Researched | 1,871 named functions of 14,879 (12.6%), each with evidence; renames proven identifier-only. | Nothing added since 2026-09-25; 518 loose rows wait for a second lever; a README lead thread with no work in flight. |

## Engine: graphics -- 60%

The GS, the vector unit and how fast a frame gets out.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| GS renderer (OpenGL) | 75 | Playable | OpenGL backend with a CPU rasteriser as its oracle (--vram-diff 15/15); 1x-4x internal resolution. | #114 GL replay can stall for good; #104 depth band on Frostfire; #96, #32; no mipmaps or deinterlace. |
| VU1 native programs | 55 | Functional | Native 0x1b50 dispatcher handles 162 of 166 commands; native 0x33c8 on by default since 2026-10-01; goldens bit-exact on 3 OSes. | Entry 0 and the 0x52 skinning pass still run generated microcode; 32% of dispatches hand back; unbounded stores (LATER 62). |
| Frame rate and timing | 50 | Functional | VBlank held at 16.67-16.9 ms; menus about 57-59 fps; two instances keep real time. | Missions run 22-25 game fps against the console's 30 (game thread bound: VU1 ~42%, GS front end ~22%); no frame-rate bar (#59). |

## Sound and voice -- 45%

The 989snd HLE, the mix and the USB headset.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Music and effects playback | 80 | Playable | Mission music sample-exact; real 989SND.IRX on an LLE IOP is the oracle and agrees on every bank, stream and play. | Online-screen music hitches (#94); mission music degrades over time (#28); ~50 ms output holes (#42). |
| Mix accuracy vs console | 35 | Prototype | A parity compare exists and is scored per window. | Audio parity 12/48; mission ambient bed ~11 dB low (#91); title ring 4-6.5 dB low; LFO and plugin grains unmodelled. |
| Voice chat | 20 | Researched | lgaud service real; host mic resampled to 8 kHz; launcher level meter; codec identified (SASE). | The game never sends voice: the talk gate is not found; receive never tested. |

## Input and storage -- 75%

Pads, keyboards, memory cards and the disc.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Gamepad | 85 | Hardening | libpad2 HLE and DBCMAN drive every gate and ladder run; pressure crouch; dead zone; hold-to-remap per profile. | Pad read while unfocused (#105); one host pad only, no multitap; the owner's feel check (O7/O8). |
| Keyboard and mouse | 40 | Prototype | Keyboard walks the menus and types; mouse look exists behind PS2X_MOUSE (2026-10-09). | Gameplay keys only with --dev; mouse off by default and untested on Windows and Linux. |
| Memory cards and personas | 85 | Hardening | Empty folder is a formatted card; first save fixed; persona file decoded; launcher creator writes a card the game logs in with. | Multi-persona card layout never loaded by the game, PROFILE_INFO written empty (#111). |
| Disc reading and verification | 90 | Hardening | Every boot reads through CDVD; r0001 hash check with explained exit codes; guest paths contained. | Three HDD maps (pfs0:) not served (LATER 52). |

## Game content -- 71%

What a player actually walks through.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Offline menus and front end | 90 | Hardening | Title, attract, main menu, options and briefing pass the gate's title stage; the owner rated them excellent. | No menu-frame pixel fixture (#41). |
| Online menus | 75 | Playable | Login, lobby, create/join, team swap, READY, launch; logoff returns to the main menu; 16 screens mapped (research/80). | Online music (#94); screens ~7% wider than console; announcement scroller unchecked; clan/friends/settings screens never driven. |
| Single-player campaign | 45 | Prototype | First mission plays (menu, rank, briefing, scripted walk; owner played Mallard at the church). | No mission completed, no debrief, no campaign progression and no other mission recorded. Unmeasured, not known broken. |
| Multiplayer maps and modes | 75 | Playable | 18 of 20 maps played a control round in the September survey; Foxhunt and Requiem settled later; kills score. | The three HDD maps are not served; no mode-by-mode coverage beyond the control round. |

## Online client -- 53%

The game's own network code talking to a Horizon server.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Login and DNAS | 85 | Hardening | DNAS bypassed in the runtime; client key matches Horizon's; lobby rate 10/10 on the pinned harness. | Login runs unencrypted (encrypted path untried); personas keyed by server address (moving the IP orphans them). |
| Lobby and game setup | 70 | Playable | Briefing rooms listed, game list with map and settings, create/join/READY/launch, lobby chat both ways, MOTD. | Second room never exercised; return to lobby after a match not driven. |
| In-match netcode | 65 | Functional | Kill test passed; control rounds over the internet; ladder 8-run clean streak (bar 7); mixed matches with PCSX2 both ways. | Never played across two networks (NAT, real latency unmeasured); paused-peer freeze #34; host migration untested. |
| Clans, friends and stats | 15 | Researched | Screens exist in the game and are mapped for the harness. | No harness step for clans, friends or settings; server returns an empty player list and keeps no stats. |
| Community servers (r0004) | 35 | Prototype | r0004 ELF passes the gate and plays a scored round on our server; PSRewired's patch shown to be DNAS-only. | r0001 and r0004 cannot join each other; installer #71 not done; r0004 messages unmodelled (#72); never played on PSRewired. |
| Network security | 50 | Functional | Chat receive bounded; hostile memory records refused; receive path and message copies bounded (2026-09-28). | Game-lobby chat reaches the client by an unwrapped path (#26); a wider network-path audit is open. |

## Server -- 41%

The project's Horizon box at socom.scotho.com.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Hosting and operations | 80 | Playable | On AWS Lightsail since 2026-09-19; systemd install, health check, daily and off-box backups; live stats on the site. | Box runs 4d7e4816 (2026-09-23): the later hardening merge has no recorded deploy. |
| Server hardening | 60 | Functional | Chat clamp deployed; frame decode, relay caps and text bounds merged with 82 xUnit tests (2026-09-28). | Deploy of the 2026-09-28 hardening not confirmed. |
| Persistence (accounts, stats, ladders) | 10 | Researched | Simulated mode creates accounts on first login. | No database: stats, ladders and clans vanish on restart. |
| DNS for PCSX2 players | 15 | Researched | socom-dns service installed on the box (Sprint 18). | Disabled until the owner opens 53/udp on Lightsail (O33). |

## Platforms -- 55%

Where the native client runs.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Windows | 90 | Hardening | Everything is proven here: gate, ladder, online, launcher; CI green. | Owner-side play time and a frame-rate bar. |
| Linux | 50 | Functional | Builds, CI green, title stage 19/23 in a VM, recompile step runs on Linux. | Never on a real GPU or online on Linux hardware; VM suites red (#25); disc_to_elf never run on Linux. |
| macOS (Apple Silicon) | 25 | Researched | Community port boots to a mission on an M2 Pro (~30 ms a frame); arm64 CI passes. | No launcher, online, pad check or Retina; no upstream Mac to confirm. |

## Getting it to players -- 33%

From a clone to a download a stranger can run.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Launcher (native client) | 80 | Playable | Play, disc, video, audio, controller, mic, online, report and about pages; disc verify; server presets; persona list; tooltips. | Owner's persona-viewer pass (O25); community preset greyed until r0004 installs. |
| Launcher PCSX2 mode | 10 | Researched | Sprint 18 spec approved 2026-10-01. | All tasks T0-T8 open; no PCSX2 guide yet. |
| First-run ELF builder (#70) | 35 | Prototype | Built to the package stage, unmerged at 3d17f192. | ftscore decrypt step 2 returns 0 (research/76); owner's call on shipping the decrypt helper (O22). |
| r0004 update installer (#71) | 15 | Researched | Patch fetch plumbing (patch_fetch.h) only. | Decrypt, merge and the launcher toggle not started. |
| Public release | 25 | Researched | Player and developer archives build, are stripped, hashed and leak-checked; drafts v0.10.0-v0.16.0 exist. | Every release is a draft with no assets; tester archives still carry the game ELF until #70 lands. |

## Project infrastructure -- 83%

What keeps the work honest.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Build and CI | 85 | Hardening | Windows, Linux and macOS workflows plus docs, secrets, web and release-draft; green on main 70c62146. | Linux VM suites (#25); the lock flake (#110); macOS skips 5 wall-clock tests. |
| Parity gate | 80 | Playable | Three stages (title, transition, mission), PINS MATCH and HELDOUT 12/12; prints FRAME and SYNCV. | No frame-rate bar (#59), no audio bar, no menu fixture (#41); a regression fence, not a proof of correctness. |
| Online test harness | 80 | Playable | Login, match, ladder, ledger, verdict replay, PCSX2 control; fail-fast lobby classes; scheduled ladder. | Fragile on-screen-keyboard walks; one host only; social screens and voice not driven. |
| Documentation | 85 | Hardening | INSTALL, FAQ, PLAYTEST, DEVELOPING, KNOWN, generated BACKLOG/CHANGELOG/RULINGS, a doc-maintenance test in CI. | Drift: README says v0.15.0 and 27 ms; BACKLOG stale (lists #28/#42); HANDOFF dated 2026-09-30; wiki unposted (O23). |
| Licensing and no-game-data hygiene | 85 | Hardening | GPL-3.0 with a tested third-party list; leak check in hooks, CI and release drafts; push protection on. | Release legality hinges on #70 and the owner's O22 decision. |

## Web companion -- 72%

socomunzipped.com and the browser map viewer; a separate project that lives in web/.

| Feature | % | Stage | Works | Next stage needs |
|---|---|---|---|---|
| Landing site | 80 | Playable | Console-menu recreation, home, story, data pages, design-system gallery, live server stats, tester inbox. | Owner-side redeploy (O28), design-system merges (O26), PCSX2 guide (O30). |
| reCOM browser viewer | 65 | Functional | Decodes all 22 MP maps from the user's ISO in the browser; SEAL movement, weapons, HUD, offline match; ~1,750 tests. | Local single-player demo only since PR #130; no AI; maps still served from the box (disc-only planned, O28b). |

## Notes

- A category's score is the plain average of its rows.
- Single-player beyond the first mission is unmeasured, not known broken. It scores low for lack of evidence, not for defects.
- Drift the survey found: the README still says v0.15.0 and 27 ms a frame. `docs/BACKLOG.md` stops at #96 and lists #28 and #42, which the Sprint 17 plan calls closed and GitHub still shows open. `docs/HANDOFF.md` is dated 2026-09-30.
