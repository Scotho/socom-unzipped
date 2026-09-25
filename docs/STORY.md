# SOCOM Unzipped: the story so far

*The timeline of this project, first commit to today. Written for people who want to play the game, not build it.
Each entry has one technical line you can skip. The rest is what happened.*

**What this is.** SOCOM II is a PlayStation 2 game from 2003. This project turns the game's own code into a Windows and
Linux program. It runs from your own disc (the North American r0001 pressing; anything else gets refused with a message
instead of half-working), draws on your GPU, plays through your speakers, reads your controller, and plays online
against a server we host. Nothing from the game ships with it.

**How to read an entry.** Date, title, one bold line on why it mattered, a few sentences on what happened, then three
small things. *How:* is the technical sentence. *But:* is the catch: what's still unproven, what got retracted, what a
number doesn't mean. `Cited:` is the evidence, commit hashes you can open in the repo plus run records. The run records
live in a `logs/` folder on the project machine, not in the repo, so each one cited here has a frozen witness (first
lines, size, hash) in `docs/story/witnesses.json`. A test fails if any citation stops pointing at something real.

## From the creator

This is an automation-first, agentically engineered passion project. It started as curiosity. I wanted to see where
PS2 static recompilation actually stood, and it grew legs when it started producing results, so I kept building on
them. The recompiler is a fork of PS2Recomp, extended for this one game. A good portion of the work went into a
parallel validator: the retail disc running in PCSX2 as a golden reference, driven by the same scripts as our build,
with debugging tools on both sides, so the agents could check themselves against the real thing on demand and adjust.
Most of the code was written by AI agents in a loop I run. My part was mostly playing it, noticing what was off, and
deciding what mattered next. What follows is the record of that, receipts attached.

Scotho

---

## 2026-09-02 .. 2026-09-07 - From the disc to the screen

*Six days in: the game boots from your own disc, plays its movies, takes keyboard input through every menu, and loads the first mission into a textured world. Online still belongs to the emulator.*

### 2026-09-02 - The game isn't in the file you'd expect

**The executable on the SOCOM II disc is 874 KB of loader. The actual game is locked in an encrypted archive next to it.**

Day one, two commits, nothing runs. The first is tools: a harness that steps the PS2's CPU one instruction at a time, scripts to pull a function map out of Ghidra, and a decryptor for the archive. The second is the finding: inside the archive are two code overlays, 2.2 MB and 1.7 MB, stamped "SOCOM 2 r0001 17:22:21 Oct 11 2003". The disc's protection asks the console for its hardware IDs while it decrypts, but those IDs feed a hash nothing ever checks. So the archive isn't tied to one machine.

*How:* the harness runs the console's MIPS core under Unicorn and traps the PS2-only instructions out to Python, because no off-the-shelf emulator knows them.

*But:* the archive opens because of a quirk in the protection, not a defeat of it. Nothing of the game ran yet.

`Cited:` `55f5170` Unicorn EE harness, Ghidra export scripts, APACHE00.ZDB decryptor · `eee6634` research reports, synthetic overlay ELF builder · docs/research/05-code-package-and-harness.md · docs/research/01-ps2-static-recompilation.md

### 2026-09-04 - A PS2 game becomes a Windows program

**Thirty-five commits, and by the end the game's own code is C++ that compiles.**

The protection layer encrypts 131 of its own code blocks; running the cipher offline unwraps them without a console. A fork of PS2Recomp turns the MIPS into C++, and the loader plus both overlays become one program file linked against a runtime. Most of the day went on something duller and more important: Ghidra's function map was wrong in ways that quietly corrupt everything. One 46 KB stretch of unrelated code had been folded into a single function, so calls into it landed in the wrong place and returned garbage. Normalised and re-exported: 13,261 functions. A Horizon server, the community's stand-in for Sony's long-dead online service, went up on the same PC three days before anything could talk to it.

*How:* Ghidra writes Start, End and Size separately and they disagree for split functions; the fix recomputes End and forces the missing entry points by hand.

*But:* compiling isn't running. Forcing entry points by hand also pushed the count of untranslatable instructions from about 11,000 to 114,000. That's garbage that never executes, and it's still there today.

`Cited:` `37b2922` static DNAS self-decryptor, SIF RPC HLE · `329bbda` APACHE00.ZDB decryption works end-to-end · `8736759` vendor PS2Recomp for the SOCOM II fork · `1a9ae52` segmented synthetic ELF, external generated-code dir · `ac7de47` re-exported Ghidra map (13261 fns) · `a3cef6c` Horizon Private Server local setup · docs/research/05-code-package-and-harness.md · docs/STATUS.md

### 2026-09-05 - It plays its intro

**A day of black screen, and the graphics weren't the problem.**

A full diagnosis of the render path said every layer below the game was fine. The game just wasn't asking for anything to be drawn, because it was waiting for a controller. Fake one and it wedges somewhere else. The real cause took a hardware watchpoint: the game asks Sony's device-bus manager how many bytes arrived, our stub never answered, and the game read back an uninitialised number and copied that many bytes over its own heap. Five of those calls per boot; the third overran into the texture registry. Answer all five and the intro plays: 2,445 frames, no faults.

![The oldest frame of the game this machine still holds: the evening of the 5th, six seconds after launch, the memory-card slot prompt drawn by the software rasterizer with its text upside down. Everything else is black because nothing else had been asked for yet.](docs/story/img/2026-09-05-the-card-prompt-upside-down.png)

*How:* the smashed registry turned code words into pointers, which faulted, which the runtime silently retried forever. A hang with no error.

*But:* the controller was a fiction with neutral input; real keyboard input came later the same day. And "every layer below the game is correct" didn't survive the afternoon: three real delivery bugs turned up in that path a few hours later.

`Cited:` `594b887` libpad2 (scePad2) HLE — report one connected DualShock2, neutral input · `cc27753` answer every libdbc RPC — unanswered ReceiveData smashed the heap · docs/research/07-render-pipeline-diagnosis.md · docs/research/08-controller-and-dbcman.md · logs/host_cpu/host_001_6s.png

### 2026-09-05 - The main menu, at full speed

**Three bugs on one delivery path stood between the game and its own menus.**

SOCOM II ships its shell's constants through one particular kind of transfer tag, and the chain walker treated that kind differently from every other. The camera's eye vector never arrived, the backface test rejected every menu triangle, nothing was submitted. Fixed, the shell drew at 13 to 17 fps, a software rasterizer doing a swizzled read and a palette lookup for every one of a million textured pixels. An OpenGL 3.3 backend that records draw commands on the game thread and replays them on the graphics thread took the same screen to 55-60. Then the game walked its real first-boot sequence for the first time: memory card prompt, loading warning, "no SOCOM data found", Sony logo, intro, main menu.

![The same evening, seven minutes after the software rasterizer's run, on the new OpenGL backend: the title, 29 seconds after launch, drawn at full speed. The bar along the bottom is the runtime's own debugger.](docs/story/img/2026-09-05-the-title-at-full-speed.png)

*How:* the last black screen of the day wasn't a rendering bug at all. The menu frame's alpha is zero and the present was blending the finished picture to black.

*But:* no button captions, no 3D roller, a black rectangle where the background movie belongs. The 60 is the menu's number; there was no mission to measure yet.

`Cited:` `5152946` TTE-gated DMAtag upper-half transfer — shell UI renders · `409d0c3` OpenGL 3.3 GPU backend — menu renders at full speed · `31b559e` host keyboard/mouse/scripted DualShock2; main menu reached · `73c9a49` recompile the two uncovered trampolines; present the GS frame opaque · docs/superpowers/plans/2026-09-05-gpu-gs-backend.md · docs/STATUS.md · logs/host/host_000_1s.png · logs/host/host_007_29s.png

### 2026-09-07 - The first frames of a mission

**The thing starving the renderer was the automatic exposure control.**

First the mission had to load at all: four fixes the day before, all the same kind of bug: the recompiler and the runtime disagreeing with the original code about where a function starts and ends. 136 real functions sat in gaps the map never listed, and calling into one did nothing. With those in, the Albania briefing handed off to a running level that drew nothing. The reason: a background thread wakes every vertical blank and reads about 176 pixels back off the frame buffer to judge scene brightness. That readback path didn't exist, so every read spun to a sixteen-million-iteration timeout, a third of a second each, and starved the game to one tick a minute. Swap the readback for a fixed mid-grey and the mission runs at twenty ticks a second: flat world polygons and a night sky.

![The first mission, the afternoon of the 7th, 113 seconds after launch: flat grey ground, a wall of fog, and a night sky drawn as white specks. No textures, no HUD, and the camera is not going anywhere.](docs/story/img/2026-09-07-flat-grey-and-a-night-sky.png)

*How:* nothing was broken in the renderer; a spin loop with a very large bound was the whole defect.

*But:* flat grey, no textures, no HUD, a camera that doesn't move. And the mid-grey stub was a defect in waiting: the exposure thread reading a constant grey asked for no brightening, which is half of why every gameplay frame was 1.73x too dark until 2026-09-16.

`Cited:` `ec4b9fb` do not mistake a scheduler unwind for a return · `feb92ab` run INTC/DMAC handlers, alarms and the GS vsync callback on a dedicated invocation stack · `2b06f50` recompile the 136 function bodies Ghidra left in gaps · `eebd64a` split the six merged Ghidra ranges whose second function is called by pointer · `7bb89d4` the Albania mission loads and runs · docs/STATUS.md · `d3cea62` stub the auto-exposure thread's GS readback — the mission now ticks every frame and draws · `545b85a` (2026-09-16) the auto-exposure readback answered from GS memory instead of a grey pixel · docs/research/31-flat-grey-geometry.md · logs/parity/mission_merge/host_000_1s.png · logs/shots_live/host_010_113s.png

### 2026-09-07 - The console becomes the marking scheme

**Instead of arguing about what looked wrong, the project started scoring itself against screenshots of the real game.**

A harness captures a window without stealing focus, posts the same button presses to an emulator running the retail disc and to our window, walks both through the same script, and scores the pairs. The first report scored 6 of 20 screens (mean 80.6, main menu 63.7) and the other fourteen were never reached. It paid off immediately. Every 2D element was drawing at the top-left corner, because the recompiled code wrote to a vector register that's hardwired to (0,0,0,1) on real hardware. Text was being culled by a face-winding setting raylib leaves on. Four-bit palettes were read in the wrong order, which is why the text was dim. And 29 hand-written substitutes for Sony's vector-maths library were multiplying matrices the wrong way round, so the camera's clip matrix was wrong and every object failed the visibility test. Deleting the substitutes and recompiling Sony's own code brought back the menu's rotating 3D selector and gave the mission textures.

![The first parity run's briefing screen: every 2D element drawn at the top-left corner, because the recompiled code was writing a register the hardware keeps constant. The report scored this 63.7 and the fixes followed the same day.](docs/story/img/2026-09-07-briefing-drawn-at-the-origin.png)

*How:* the score is a per-screen picture comparison at 320x224, one number from 0 to 100.

*But:* a picture score is not a correctness check. The day's last report graded the main menu 81.0 with the movie behind it still black, and the same animated warning screen scored 79.2, 75.0, 78.0 and 74.9 on capture timing alone.

`Cited:` `2aa2572` parity harness design spec (PCSX2 golden screens as the loop's grader) · `069aa7a` comparer + first REPORT.md (golden from PCSX2, 6 screens scored) · `ea026de` never write vf00 — all 2D UI elements were drawn at the origin · `8653933` text draws — disable raylib's GL_CULL_FACE, CSM1 CLUT index swizzle for 4-bit palettes · `daa1eda` drop the 29 libvu0 sceVu0* HLE stubs and recompile Sony's code · `c2489bd` shell parity after the four fixes · `4af3f00` report ours_e after libvu0 fix · docs/parity/REPORT.md · docs/superpowers/specs/2026-09-07-parity-harness-design.md · logs/parity/ours_e_sheet.png

### 2026-09-07 - The movies play

**Every movie in the game was dying on its first tick over four stale bytes.**

The stand-in for the PS2's movie library never cleared its work buffer when a player was created. The game read the first word of that buffer to ask whether the movie had finished, found leftover bytes spelling UIMe from an unrelated file, and concluded it had already ended. The real function clears the buffer. With that one line, plus the game's feed callback run on the calling thread instead of parking the only thread that could feed the decoder, the Sony logo, the intro and the looping menu background all play. The main menu's score went from 81.0 to 98.8.

![The main menu as the first parity run captured it that afternoon, hours before the movie fix landed: the logo, and a menu with no captions, no roller and no movie behind it. The 81.0 was scored on a screen like this one.](docs/story/img/2026-09-05-menu-with-no-captions.png)

*How:* the movie player's finished flag was read out of a work buffer that was never cleared on creation; clearing it, like the real library does, is the whole fix.

*But:* 98.8 is one screen against one reference capture, and the report it was measured in is gone from disk; the number survives in the research note and the log.

`Cited:` `ad503c8` play SOCOM II movies through the sceMpeg HLE (menu background, intros) · `9305c72` Merge feat/menu-movie · docs/research/09-menu-movie-ipu.md · docs/STATUS.md · logs/parity/runs/ours_a/s02_CROSS.png

### 2026-09-07 - Two clients, one server, one match

**The first SOCOM II match on this project's own server wasn't played by this project.**

The Horizon server that had been sitting on the PC since the 4th finally got a client. A retail disc in the reference emulator went LOGIN, SELECT UNIVERSE, ACCOUNT LOGIN, lobby, after three protocol fixes read straight out of the decompiled client library. A second emulator, with its own memory card and its ports shifted, joined the game the first created; both pressed READY and the match launched: VIGILANCE, round timer running. Our own executable reached the front door the same night: network layer up on host sockets, key exchange and stream cipher running, the server accepting the connection.

*How:* handler ids are assigned in registration order, so reading the live slot table out of the emulator's memory tells you which message is which.

*But:* the match was two emulators. Ours got as far as LOGIN TO SOCOM II ONLINE, completed the handshake, and closed before asking for the universe list. Everything was on one machine, and the server is a community stand-in, not Sony's.

`Cited:` `5fcb9dc` PCSX2 client reaches the SOCOM II ONLINE lobby on the local Horizon stack · `f4ab598` two PCSX2 clients play a match on the local Horizon stack · `d738b29` SIF sreg handshake, msifrpc HLE, eznetcnf/eznetctl service, DNAS bypass · `9db2fbd` SCERT handshake with Horizon over a host Winsock netstack · docs/research/10-libnetb-rpc.md · docs/STATUS.md · logs/parity/online/login/09_lobby.png · logs/parity/online/match/montageAB2.png

## 2026-09-08 .. 2026-09-11 - A picture, then a gate

*By the 11th the program draws its menus and its first mission the way the console does, runs at tens of frames a second instead of a handful, can be walked through by script, and can put two copies of itself into an online match on a local server. Where the players then stand still.*

### 2026-09-08 - Our own program gets online

**Two copies of the recompiled game log in, host a match, and join it.**

Yesterday the only thing to reach a lobby was the retail disc under an emulator. Today our executable did it. A stuck clock register was advanced so the program got as far as SELECT UNIVERSE, then a driver walked it through login, the on-screen keyboard, the licence agreement, the lobby and the briefing rooms, and it created a game called "test" on Medley. By the end of the night two instances were in the same match: socomc hosting, socome joining, both READY, both loaded into VIGILANCE. The lobby screens scored 98.6 to 99.4 against the console.

![The project's own executable in the SOCOM II ONLINE lobby, on the server running on the same PC. The persona is the driver's test name; the panel in the corner is the runtime's own debugger, open by default in this era.](docs/story/img/2026-09-08-online-lobby.png)

*How:* a second instance is just environment: its own window tag, its own memory-card folder, and a shift on the game's fixed network ports at bind time.

*But:* both players were scripts, both on one PC, and the server was on that PC too.

`Cited:` `a1bafbf` advance COP0 Count, reaches SELECT UNIVERSE · `090401a` login driver for our exe · `d0caab9` the exe hosts a game on Horizon · `2adb58b` two instances play an online match · logs/parity/ours_login/09_lobby.png · logs/parity/ours_host/16_game_lobby.png · logs/parity/ours_match/A_hold05.png

### 2026-09-08 - The world stops coming apart

**Every square root in the game had been returning zero.**

The recompiler emitted the console's square-root instruction reading the wrong register, so the game always took the square root of register zero. The quaternion builder divided by that, saturated to the largest float there is, and the actors' orientation matrices exploded, which drained the collision pool and dropped the player through the terrain. Two more the same day: object geometry (trees, people, about 1700 triangles a frame) was arriving at the graphics chip as three identical points at the origin, and the camera's frustum test always answered "fully inside" because nothing wrote the flag register it read. That's where the giant sky polygons came from. The next day, the title screen's labels stopped getting wiped by the background movie painting over them a step early.

*How:* the geometry fix is one rule: copy the whole packet when the program kicks it, the way the emulator does, instead of modelling the transfer a word at a time.

*But:* each of these was settled by looking at the picture and at dumped memory against the emulator. There was no test suite and no gate until two days later.

`Cited:` `4d2c706` SQRT.S reads ft · `fa53d3f` copy XGKICK packets at kick time — object geometry appears · `193ef1e` macro-mode FMAC ops set the flags — the frustum test routes near objects through clipping · `2d23351` the mission intro movie plays · docs/STATUS.md (2026-09-08 16:15 and 21:40 entries) · `3c20dc8` stall on i-bit VIFcodes — title labels clean · `7730052` re-read only the uploaded rectangle — no more menu-video strip · `77a41ff` (2026-09-08) run the game thread with host rounding toward zero · gate s8_audio_mc_gate2 · gate s9_p7_playtest_gate · logs/parity/title_stall5_sheet.png

### 2026-09-09 - From three frames a second to thirty

**The part of the console that draws SOCOM II's geometry was being simulated one cycle at a time.**

The vector unit that transforms and lights every triangle was emulated at about 100 nanoseconds per cycle, which held the whole game to a few frames a second. A fast path that drops the per-cycle scheduler took that to 18 ns; a translator that turns the game's vector microcode into C++ took it to 10 offline. With the graphics and scheduler work that followed the same day, in-mission speed went 12.7, then 19, then 22-29, then 28.7 fps. Fast enough to play: a script drove the first mission end to end, walking, turning, firing, with the game answering at 36-42 fps. The same day the project wrote down what "playable" would have to mean before anyone could claim it: a match ended by a shot.

*How:* the fast path and the generated code were checked against the exact interpreter, same packets, same registers; the mission program was regenerated from 900 recorded dumps of it.

*But:* numbers from one PC on one mission, not a steady-state figure. One part of the speed-up was wrong: the decision to stop counting the drawing unit's time against the game's own clock was reverted on 2026-09-17, and it's a story of its own below.

`Cited:` `51b7ba4` non-cycle-exact fast path, bit-identical to the exact interpreter · `f9f44ff` microcode-to-C++ recompiler, 10 ns/cycle offline · `f5d079e` fast path on by default, 100 -> 18 ns/cycle · `950fbd2` row-span uploads — mission gameplay 12.7 -> 19 frames/s · `cf58986` regenerated from 900 dumps — gameplay 22-29 frames/s · `96c84c6` scheduler fast paths — 28.7 frames/s · `1c301b9` sample a render target's own colour texture · logs/parity/vu1fast_1_sheet.png · `94421fb` first mission playable by script at 36-42 fps · `c2f85f0` define the playable acceptance test · `7448cbf` loop lock script serializing builds and game runs · logs/parity/gameplay_probe5_sheet.png · docs/LOOP_PROMPT.md

### 2026-09-10 - The project gets a name, and starts checking itself

**SOCOM Unzipped, a test suite that runs, and one command that says PASS or FAIL.**

The work moved into its own repository under the name SOCOM Unzipped. Until this day the unit tests had never been built with the project's own toolchain; once they were, 425 passed and ./build.sh test exited zero for the first time. A single gate command boots the game three times (title screen, the transition into a mission, the mission itself), scores each, and returns a number. Its first run passed two of three: the mission never reached the HUD.

*How:* the suite also replays recorded drawing programs against a committed golden state file, so a change that alters output by one register is caught offline.

*But:* a test count isn't correctness and neither is a green gate. The gate proves regression, meaning the game looks like it did last time, and one of its three stages turned out to be measuring nothing at all. Next entry.

`Cited:` `4b0bbf9` the project is SOCOM Unzipped in its own repo · `98245ad` ps2x_tests links and runs under llvm-mingw, ./build.sh test · `2fca2b8` vu1_replay --verify against a golden state file · `3bc03ba` gate command with numeric PASS/FAIL and exit code · `e70af9a` transition gate no longer passes vacuously · logs/parity/gate_first.out

### 2026-09-11 - Our own code draws the game

**The drawing program is no longer emulated microcode. It's C++ someone wrote by hand.**

Reading the game's vector microcode showed one dispatcher at a fixed entry point does all of it, and its commands fall into families: flat interface panels first, then world objects with clipping and multi-pass work. Hand-written replacements were checked command by command against the original, and the dispatcher went on by default after a gate that passed all three stages. By evening the world-object families were native too: 123 of 166 recorded command lists, each matching the emulated version exactly.

*How:* programs are matched by a hash of their code plus entry point; anything the hand-written version doesn't handle is handed back to the emulated path part-way through a list.

*But:* that clean gate was less clean than it read; see the next entry. And handing a list back part-way is exact only by luck of the recorded set: no program in it branches on the flags in the four instruction pairs where it would matter.

`Cited:` `15efcd7` native-program registry keyed by (image hash, entry pc) · `73974cd` 0x1b50 dispatcher on by default after a green gate · `d912cc1` family-B lists run natively · `f28fdc7` family-C lists run natively · `ef80286` native dispatcher runs family C as well (123/166) · `dd5fca8` render-target scale spike — NO-GO for Sprint 2 · docs/research/13-vu1-family-b-world-objects.md · logs/parity/gate_native_default.out · logs/parity/gate/famb/summary.txt

### 2026-09-11 - The check that had been passing for free

**One of the three gate stages had been measuring nothing.**

The middle stage is supposed to watch the screen go black as the game moves into a mission. It counted black frames from anywhere in the run, boot screens included, so it stayed green whether or not the game ever reached the fade. Worse, a save-to-card dialog had started appearing at boot and the probe answered it blindly, so it never got to the briefing. Six earlier runs re-read against the fixed rule had examined zero frames in the window that counts. All six had passed.

![The last frame of the very first gate run, 2026-09-10: the save-to-card dialog the probe answered blindly, so it never reached the briefing. This frame sat in the archive on D: until the story went looking for it.](docs/story/img/2026-09-11-the-dialog-the-gate-answered-blindly.png)

*How:* the scorer now counts only frames at or after the step that triggers the fade; a run that never gets there scores zero and fails.

*But:* first of several times one of the project's own instruments turned out to be reporting something it hadn't measured. Not the last.

`Cited:` `148dffa` the transition gate measures the transition · `9848a6c` Sprint 2 landed — gate hardening · logs/parity/gate_wcap1.out · logs/parity/gate_tfix4.out · docs/STATUS.md (2026-09-11 03:45 entry)

## 2026-09-12 .. 2026-09-14 - From picture to game

*Three days, 219 commits. The intro movie is clean, the single-player mission stops freezing, players can move in an online match again, and two copies of the game meet on Frostfire and one kills the other.*

### 2026-09-12 - Four times the pixels, and no sharper HUD

**The world can now be drawn at up to four times the console's size. Three quarters of the screen look exactly the same.**

Until now every frame was drawn at 640x448 and stretched. A new setting draws the 3D world at two, three or four times that and hands the game back a console-sized picture, so nothing inside the game notices. At 2x the gate passed and the edges genuinely softened: the fraction of edge pixels that are a smooth blend rather than a hard step went 0.13 to 0.42. The HUD, menus and title screen didn't change at all. They're flat pictures at their original size; extra pixels can't add detail that was never there.

![One of the pixel-filter gates the render-scale work needed, stuck: every title capture scored 66.4 because the game was sitting on the memory-card slot prompt the whole time. 0 of 23, and a lesson about what a flat score means.](docs/story/img/2026-09-12-the-gate-stuck-on-a-card-prompt.png)

*How:* render targets carry a native size and a host size; vertices are scaled after the offset subtraction, and anything the game reads back resolves through a native-sized mirror.

*But:* the sprint's own design doc had promised a sharper HUD. Measured, withdrawn. Default stays at 1x.

`Cited:` `219ab9c` PS2X_GS_SCALE integer render-target scale · `66e8a07` PS2X_GS_SCALE=2 verified (sheets) · `b353c93` Sprint 3 close-out · gate s3d_2x_host · docs/research/14-gs-render-target-scale-spike.md

### 2026-09-12 - The black squares leave the intro movie

**Someone reported black tiles flickering over the movies. The tiles were real, and they were never in the movie.**

The decoded movie was perfect. Two threads shared one note of which rectangle of the screen had just changed; the game thread kept overwriting it, so the copy to the graphics card refreshed the wrong patch and left stale black squares on the intro and the title's moving background. Deleting one line fixed it. A checker written before the fix counts blocks that are black on screen but not in the decoded frame: nine before, zero after, and the missed refreshes went from 3,748 to none.

*How:* executeUpload on the render thread read m_currentTransfer, which BeginTransfer on the game thread was also setting.

*But:* the predicted cause, rectangles arriving half-delivered, accounted for none of the 3,748; the planned fix would have done nothing. The checker itself ran in nothing until 2026-09-17, when it went into ./build.sh test against a committed fixture.

`Cited:` `4a701f1` stop the game thread clobbering m_currentTransfer · `b91df1b` movie_blocks(review 4): the furniture map is per screen · `bd27443` (2026-09-17) movie_blocks runs in build.sh test against a saved fixture · tools_py/parity/movie_blocks.py · docs/research/16-intro-movie-macroblocks.md

### 2026-09-12 - Every dice roll came up nearly zero

**The game rolls dice in 249 places. For the whole life of the project, every roll had come up almost the lowest number it could.**

SOCOM II turns a random draw into a fraction by dividing by two billion. The stand-in for the C library's random function returned fifteen bits where the game expects thirty-one, so every fraction landed in the bottom 1/65536 of its range. Worse, the game seeds itself from its own previous draw, and that seed froze at 41 on the first boot. One measured field that mixes in randomness went from 4.000021 to 5.5314, against 6.3338 on the real console. Same afternoon, same shape: five maths routines wired to the wrong registers, handing back whatever the previous call left behind.

*How:* the stub now runs newlib's own generator over the guest's own _rand_next word rather than the host C runtime's.

*But:* nothing caught either of these for weeks. The parity gate was green over them the whole time, because a defect present in every run looks exactly like the reference. The maths routines were milder than billed: 19 of their 22 call sites happened to want the identity anyway.

`Cited:` `ede2096` rand() returns newlib's 31 bits over the guest's own _rand_next · `60a19f2` bounds-check the guest _rand_next slot · `db7a992` the soft-double sin/cos/tan/fabs/floor stubs take $a0 and return $v0 · gate s4_rand · docs/research/17-ground-height.md

### 2026-09-12 - Online players can move again

**For two days the online round had been written up as waiting to start. It wasn't. The round was running and the player was pinned.**

On the 10th, with the fast build in, two instances got all the way into online gameplay, and then nobody moved. A network trace showed the two copies talking at about a packet a second, and the write-up called the match stuck at the round start. Wrong. In a multiplayer match the game scales your movement by how recently the network was active; the stand-in for the PS2's network interface answered "how much traffic have you seen" with a constant, so the game decided the network had been silent since boot and scaled movement to zero on the first frame. Looking up and down still worked, because that isn't one of the three fields the scale touches. The fix returns a real byte count. One match then carried both legs at once on one binary: one instance with the fix, one with it deliberately off.

*How:* sceInetInterfaceControl code 0x200 now returns a live monotonic byte count instead of a hard-coded zero.

*But:* an hour and 46 minutes earlier a different commit had announced the cause, and it was wrong: three calls matching three dead controls was a coincidence, withdrawn the same day. Both facts that disproved "stuck at the start" (the round clock kept running; look worked) had been sitting in the same paragraph as the claim the whole time.

`Cited:` `334c990` VU1 build gates and the first two-instance gameplay on it · `89d7032` pad-state injection, exact holds · `0421048` net trace counts sends/receives and hex-dumps peer packets · `79c0e91` peer packets decoded, 22-byte reliable channel acked at 1/s · logs/parity/ours_match_play5/ · logs/parity/match_play5_sheet.png · `4114ad4` the gate is named -- multiplayer zeroes the local player's three movement axes · `abf35bb` sceInetInterfaceControl code 0x200 returns a real RX byte count · `5ed29ca` same-binary A/B proves the fix both ways · run ours_task6_fix2 · docs/research/18-online-round-start.md

### 2026-09-12 - The project starts writing down what it got wrong

**Five beliefs died by measurement in one day. So they were written down where they'd been read.**

KNOWN.md is a living list in four parts: what's proven and by which artefact, what's only believed and which experiment would settle it, what was retracted, and what will bite again. On the day it was created it already carried six dead sentences, among them that the console showed the same frozen match ours did, that the online round was waiting for a go, and that a higher render scale would sharpen the HUD. The next night the retracted sentences were struck in place, inside the documents where fresh sessions were still reading them, rather than quietly deleted. One follow-up commit is titled "I broke my own rule".

*How:* the rule adopted the same night: cite item names and dated entries, never file-and-line, because line numbers rot the moment anyone edits above them.

*But:* the file's own first note admits its first three retractions were still false in the tree hours after being disproved. The rule is retract on discovery; the practice was close-out, a day late.

`Cited:` `2d9f73a` KNOWN.md -- what is proven, what is believed, what was retracted · `bacfbb8` S0 -- PCSX2 does NOT reproduce the round-start freeze · docs/KNOWN.md · `0129bb9` four sentences this sprint disproved, corrected in place · `95ecb21` the consequences of a retracted claim, not just its headline · `a1e168b` I broke my own rule · `b2a74dd` changing the health default did not fix the false PASS · `85aa476` retract "kill3 lost its second mover" · `07ffc0a` sceGsSetDefDBuff reads ztest/zpsm/clear from $t0-$t2

### 2026-09-13 - Frostfire gets its ground back

**On one map both players froze where they spawned. The ground was there. The game couldn't find it.**

The game asks every frame whether there's ground under your feet, and online it stops you moving if the answer is no for 0.6 seconds. On Frostfire the answer was always no. The level's ground pieces had been filed into the lookup grid at the coordinates they hold before being moved into place, so every check searched the wrong squares. One missing constant: a hardware register that's always (0,0,0,1) on a real PS2 read as all zeros on every thread but the main one, and the level loader runs on another thread. After the fix both players moved for a full 302-second round and the ground check hit on every one of its 1332 and 1428 calls.

*How:* R5900Context() zeroed VU0's vf0, so vmaddw.xyz vf9, vf7, vf0w in the bounds transform silently dropped the translation term.

*But:* two earlier explanations were retracted on the way: a leftover "ghost" byte (the chain is real; it never fired) and an exhausted lookup grid (503 nodes used, 7689 free). And the fix rested on one usable run until the kill session below supplied a second.

`Cited:` `b625291` vf0 is the hardware constant (0,0,0,1) on every guest context · `aa91a53` the ground models were gridded without their translation · `3f9a100` launch 3 -- the vf0 fix restores Frostfire online control · logs/run_A_20260913_115809.log · docs/research/21-frostfire-control-handover.md

### 2026-09-13 - The single-player mission stops freezing

**A frozen picture with a running clock isn't a hung game. It's a queue.**

In single-player the game thread recorded drawing commands faster than the graphics thread could replay them, and nothing pushed back. The backlog grew from 275 MB to 13 GB in four minutes; the picture updated once every 5 to 25 seconds while the game underneath ran normally. The game thread now waits at its own frame boundary whenever more than three frames are recorded but not drawn, capped at two seconds. A full mission afterwards peaked at 299 MB and never hit the cap.

*How:* the wait sits at the recorder's VBlankStart, not in Present, because Present already runs on the graphics thread.

*But:* the first version of the brake latched shut (a busy but healthy graphics thread looked stalled), fixed in review the same day. And back-pressure means the game slows when the host is busy, which made the parity gate sensitive to whatever else the PC is doing.

`Cited:` `aedd9ff` the single-player gameplay stall is an unbounded GS command backlog · `8281254` bound the GS command backlog -- the EE waits at VBlankStart · `7448601` back-pressure caps consumer silence, not replay time · gate s5_gsbp

### 2026-09-13 - The first kill

**"socomc fragged socome with M4A1." Then twice more in the same lobby.**

Two copies of the game logged in to the project's own server, met on Frostfire along a route picked by arithmetic rather than by eye, and one shot the other. Round 1's kill landed 99 seconds in: the victim's health went 1.0 to 0.298 to 0.0, the killer's burst had landed 0.59 s earlier from 28 units away, and both screens carried the killfeed line within a third of a second. Rounds 2 and 3 killed too. Every bar for what counts as a kill had been written down and committed before any of these matches were scored.

![Both screens of ladder launch 2, round 1, a third of a second apart: the killer's on the left, the victim's on the right, the same killfeed line on each.](docs/story/img/2026-09-13-first-kill.png)

*How:* two independent readers, one watching the actor's health field and the other replaying the round's own state values, had to agree before a round counted.

*But:* one launch, one map, two scripted copies on one PC against a server on the same PC. The kill count stepped on the killer's side only; what moved on both was the victim team's alive count. Round 4 fired 111 bursts at an aim error that never corrected and killed nobody.

`Cited:` `811b886` THE ACCEPTANCE TEST PASSED -- Sprint 5 ladder launch 2 · `5f1de26` first online kill -- ladder launch 2 round 1, both screens tiled · `171290b` match the exact route-no-time tag · `d9b5f33` (2026-09-14) pin the acceptance PASS -- ladder launch 2 round 1 fixture · run s5_t5_ladder2 · docs/archive/sprints-1-6/2026-09-13-sprint-5-control-readout-and-first-kill.md · docs/research/22-kill-readout.md · docs/research/assets/22-first-kill.png

### 2026-09-14 - Two things the owner spotted

**The owner looked at the test frames and saw two things nobody had been looking for.**

Work stopped to chase what a person noticed in the screenshots: grey shards where Seeding Chaos should have water, and a single-player teleport whenever the player turned. The teleport got a confirmed cause. A graphics stub multiplied an address that was already a block number by eight, so seven parking slots in video memory collapsed onto two, and the game's animation clips were overwritten with the wrong chunks while the mission loaded. Fixed the next day: a memory dump 255 seconds into a mission came back with 0 of 8 animation chunks damaged, where every earlier dump had 5 of 8. The water got a cause too, published at 13:39 and refuted by its own author at 13:46, when the shards turned up identical with the depth test switched off entirely.

![A gate frame from the 12th, two days before anyone looked: the first mission's spawn with the HELP pop-up up, and at the bottom left the clipped terrain, a black wedge where the ground should be. The owner spotted it in frames like this one.](docs/story/img/2026-09-14-the-clipped-terrain-the-owner-spotted.png)

*How:* libgraph's vram_addr is already the BITBLTBUF block field, so sceGsExecLoadImage and StoreImage must not scale it.

*But:* the water shards had been sitting in every gameplay test frame for three sprints with no check flagging one. The real cause took two more days and two more theories.

`Cited:` `b09227f` the single-player turn teleport is corrupt animation clip descriptors · `3220e68` record the paused investigations · `3028bf8` the x8 GS block-pointer cause is independently confirmed · `5655f5c` the depth-quantisation theory for the grey water is refuted · docs/research/25-sp-teleport.md · docs/research/26-water-polygons.md · `a81eb74` the libgraph vram_addr is the BITBLTBUF block field · `docs/KNOWN.md` · `logs/parity/gate/s6_blockptr/summary.txt`

## 2026-09-15 .. 2026-09-17 - Light, sound and a launcher

*By the 17th, on the owner's PC, the game starts from a launcher, runs the first mission with an Xbox pad, draws at the brightness a console draws, and makes sound. "Online" still means two scripted copies on one PC.*

### 2026-09-16 - First hands-on session, and the controller work begins

**The first time a person played the PC build instead of a script, and the first evening's notes set the order of everything after.**

Until now every run of the game had been driven by a harness. This evening someone sat down and played it, keyboard first, and the Xbox pad went into the game's input path the same night: sticks, face buttons, shoulders, D-pad, with a fifteen percent dead zone. Two things came out of that session and set the priorities for the week: there was no sound at all, and a flat grey patch of hillside came and went in the first mission. The order after that: water and ground, then the untried online maps, then hardening, then audio, then the launcher.

![The flat grey hillside the owner saw in that first sitting: the ground drawn without its brighten pass, the water a set of dull slabs.](docs/story/img/2026-09-14-grey-hill-before.png)

*How:* every automated run sets PS2X_HOST_GAMEPAD=0, because a configured pad makes the game skip the configuration screens the check keys on at boot.

*But:* the session cost three automatic runs: free play saved a controller config onto the memory card every check booted from, and the transition stage stopped seeing the dialog it watched for. Each stage now boots from a fresh copy of a pristine card.

`Cited:` `7eed518` the owner plays (gamepad, no sound, grey hill) · `6d05b18` host gamepad in the SOCOM input path · `8f3f3be` score the transition by content, boot from a pristine memory card · `93e3639` the owner's order of 2026-09-16 · `docs/STATUS.md` · `docs/research/31-flat-grey-geometry.md`

### 2026-09-16 - Every frame was 1.73 times too dark

**The grey hill in the owner's screenshot was three separate bugs, and one of them had been dimming every frame of the game.**

SOCOM II finishes a frame by drawing it back over itself to brighten it. The renderer mapped that step to "do nothing", so every gameplay frame came out 1.73x too dark, and the water's dark bed pass, the thing brightening exists to lift, stayed a set of flat grey slabs. Underneath, the exposure meter was being fed a constant mid-grey instead of real pixels, so it asked for no brightening at all. The holes in the ground were a third thing: a drawing program that needed more cycles than its budget allowed was left half-finished, and the next chunk resumed it from the wrong place, so a patch of terrain drew two polygons instead of twenty-eight. Which patch depended on how busy the machine was. That's why the hole wandered.

![The same recorded frame after the brighten pass was restored. Same scene, same camera. The difference is the whole bug.](docs/story/img/2026-09-16-brighten-fixed.png)

*How:* the backend had mapped the brighten-by-redrawing pass to nothing; the terrain cut came from a program left half-finished when the next started, where real hardware waits for it.

*But:* third explanation for those shards. The first (depth precision) died in an hour: depth test off, shards identical. The second is superseded here too, and one piece stays open: a flag-timing difference that decides which objects take the clipped path.

`Cited:` `3d37abc` the GL backend dropped the game's full-frame brighten · `545b85a` the auto-exposure readback answered from GS memory instead of a grey pixel · `c63729d` the VIF's MSCAL/MSCNT finish a pending VU1 program · `c539603` the terrain holes are EE draw-list omissions · `c7eb121` the water shards run to ground · `docs/research/31-flat-grey-geometry.md` · `docs/research/26-water-polygons.md` · `docs/research/assets/31-console-dump-gl-replay-fixed.png`

### 2026-09-17 - The game stops running in slow motion

**A round would start, the clock would count down, and nobody could move. The renderer was eating most of every second.**

The brightening fix had a cost nobody saw for a day: it minted a fresh id for every palette the game loaded, and SOCOM II alternates palettes on consecutive draws. An online round reached 55,483 cached textures and 64,000 uploads a second; the render thread fell to two fps and the game's clock crawled at 0.04 seconds per real second. STARTING ROUND sat on screen and never cleared. Keying palettes by content put the cache back to 292 entries and the round back to 43-45 fps. The other half was older and quieter: since the 8th the game's timers had been told to ignore time spent drawing and waiting for the renderer, about 195 and 290 ms out of every second, so the whole game had been running at roughly two-thirds speed. It counts wall time now.

*How:* a bisect over four of the project's own launches found the regression; the old behaviour survives behind PS2X_CLOCK_EXCLUDE=1 for an A/B.

*But:* the clock change's own run failed the transition stage, because that stage's black-frame floor had been calibrated on the slow clock. Recalibrated, test first. The freeze it fixed was the project's own regression, one day old.

`Cited:` `42b2b50` CLUT snapshot ids keyed by palette content · `8238ee1` the guest clock follows wall time · `docs/research/34-online-round-freeze-clut-serials.md` · `logs/parity/gate/s6_clutfix_gate/summary.txt` · `logs/parity/gate/s6_clock_gate/summary.txt` · `logs/parity/ours_control_frostfire_clockoff`

### 2026-09-17 - Twenty maps in one night

**Between a quarter past midnight and a quarter to five, every online map nobody had tried got a round of its own.**

A queue ran one round on each of the twenty untried maps: two copies log in, one hosts, the map is picked by name, both walk their route, nobody shoots, the round runs to its clock. Seventeen played first time and The Mixer on a retry. Two didn't: Foxhunt, whose walking player stepped off a 110-unit drop and took fall damage, failing the harness's own no-damage check, and Requiem, where the joiner's movement came out under the bar. Requiem fell out first, on the morning's clock fix: its 13-unit hold became 128. It had never been a Requiem problem. Foxhunt needed the afternoon: the driver learned that a sudden height drop is a fall, not damage. Then all twenty played.

![How a map is chosen without counting presses: the driver matches the highlighted row against a reference and only then confirms. This is Foxhunt, the map that needed the fall guard.](docs/story/img/2026-09-17-foxhunt-map-select.png)

*How:* the map is confirmed by matching the highlighted row against a reference image, not by counting presses down a scrolling list.

*But:* a control round is a scripted no-kill walk between two copies on one PC against a server on the same machine. Only Frostfire has a route that ends in a kill.

`Cited:` `d2a9a55` control rounds on every untested online map · `99eb304` Task 6b sweep -- 18 of 20 play · `aba04e2` a height drop is a fall · `632d2c2` Foxhunt's control round settled · `8238ee1` the guest clock follows wall time · `logs/parity/online_control_summary.txt` · `docs/research/33-online-map-coverage.md` · `logs/parity/ours_control_foxhunt_guard` · `logs/parity/ours_control_requiem_clock`

### 2026-09-17 - The game has sound

**It had never made a noise. In one day it got effects, voices, mission music and a title theme.**

Four steps. A host mixer that runs the game's little sound scripts and its synth voices, so the menu clicks land. Then mission voice-overs and music, read straight out of the disc image. A 32-bit file seek had been failing silently past two gigabytes, which is why no mission stream had ever played. Then the title music, which the game decodes itself into a ring the sound hardware plays: nineteen instrumented runs to get right, because the first fix stopped the decoder when the game refused a packet, and this game treats a short read as "finished" and then polls an empty decoder 340,000 times a second. With the decoder always taking its whole input, the output matched the disc's audio at a correlation of 0.99, and a fourth fix took the title loop to 1.000.

*How:* refused audio is copied aside and re-offered in order before newer audio, so nothing is lost and nothing stalls.

*But:* all measured against the disc, not heard. The owner's verdict partway through: "still nowhere near accurate; the opening video seems okay; mission audio good". The first ten seconds of each stream still filled short.

`Cited:` `92ac6a0` first sound -- 989snd bank sounds play through a host mixer · `cb0f455` the mission's voice-overs and music play · `52125e6` the title music plays · `4478bff` the title music is clean · `75fe03d` the title screen plays the disc's PCM sample for sample · `5a1b6a8` a plain sceCdRead no longer moves the CD stream cursor · `docs/research/32-audio-path.md` · `docs/STATUS.md` · `logs/parity/gate/s6_audio_title19/summary.txt` · `logs/audio_title19.wav` · `logs/parity/gate/s7_audio_title`

### 2026-09-17 - A launcher, and a folder you can copy

**The project got a front door, and the same day an audit said a stranger still couldn't get through it.**

The launcher is a small window that owns the settings file. It reads the disc image you point it at, hashes the game's executable inside against the r0001 digest this recompilation was made from, and keeps Launch off until it matches. Picture size and sharpness, the pad drawn live, a profile and a server, and a diagnostics folder when something goes wrong. A script turns a build into a 285 MB folder and a 63 MB zip. Then four read-only reviews were run against the project's own goal sentence, and the verdict was blunt: the game plays and nobody else can get to it. The launcher never handed the game the disc it had just verified; a server given by name was silently thrown away; the server advertised the developer's home-network address to anyone who connected. All fixed the same day, and the next sprint opened on the same theme: a PC whose graphics driver can't do what the renderer needs now gets one line naming what's missing and falls back to the CPU renderer instead of a black window.

![The launcher's first cut: a disc path, three picture settings, a drawn pad, a server and a profile, and a Launch button that stays off until the disc matches.](docs/story/img/2026-09-17-launcher-first-cut.png)

*How:* the disc check walks the ISO 9660 root directory for SCUS_972.75; the GL capability probe reads the version, dual-source blending and clip control once and latches the answer.

*But:* nobody had tried the launcher by hand, and the zip had never run on a clean machine. The audit's biggest gap was left alone: every online result was two copies on one machine behind one router.

`Cited:` `770d5fb` SOCOM Unzipped launcher, first cut · `2a8f8e4` scripts/make_portable.sh -- the portable folder · `docs/STATUS.md` · `logs/parity/gate/s6_launcher_gate/summary.txt` · `logs/launcher_server_picker.png` · `docs/research/assets/launcher-first-cut.png` · `09b793a` the 2026-09-17 audit and code review · `fae7d0e` the audit's fix wave · `32aec0b` Sprint 7 opened -- two strangers, two machines, one hosted server · `a843385` the stranger's machine, defensively · `39cd17f` equal-priority guest threads are never time-sliced · `docs/AUDIT-2026-09-17.md` · `logs/parity/gate/s6_fixwave_gate/summary.txt` · `logs/parity/gate/s7_gl_gate/summary.txt` · `logs/parity/gate/s7_gl_gate2/summary.txt`

## 2026-09-18 .. 2026-09-20 - Linux, a server, a stranger

*A player with their own disc can unzip a 56 MB download, start the game on Windows or Linux, save to a memory card, report a bug from inside it, and play online against a server the project hosts in Ohio. As of tonight, against a console player in the same lobby too. Only the owner's PC has done any of it.*

### 2026-09-18 - The launcher learns your pad

**The front door stopped assuming everyone owns the same controller.**

A list of the pads that are plugged in, the chosen one drawn live as you move it; a frame-rate line; detail, resolution and volume; a microphone. One pad selection and one dead zone now serve all three places in the program that read a controller. Before this every one of them took the first pad it found. The same day the online sprint merged, carrying the fix that finally made driven online runs reliable: the automated lobby had been reaching gameplay 6 times in 10, and went to 10 in 10.

*How:* the harness's 90 ms press was falling between two polls of a login screen running at 12-30 fps; a 2 ms sampler now latches every press until a poll has seen it.

*But:* the pad settings are proven by tests and one scored run. Nobody has held a real pad and said they feel right.

`Cited:` `206de19` Goal 8, the launcher a player expects · `6b7a2b3` injected pad presses are latched, never dropped · `d270022` Merge sprint-7 · logs/parity/lobby_rate_summary.txt · `78a81d1` verify-then-act on every fixed press · `d6e417f` every press on the boot-to-lobby path is verified · `ebf13be` burst-to-burst aim correction in the route endgame · `431499b` the kill repeats on the block-pointer exe · `4a9179f` the evening's seven launches, one dropped press each · `d05db14` the night's online launches · `logs/s6_ladder8.done` · `docs/research/28-lobby-taxonomy.md` · `docs/KNOWN.md`

### 2026-09-18 - The sound reports run to ground

**The owner said the sound stopped halfway through a mission. It had.**

Three complaints from one evening, three faults. Sound dying mid-mission was a playback slot never handed back: after six plays every request failed, 237 times in the owner's log. The splice and the buzz in the online menus were a ring buffer with no agreement about who had filled what. The biggest sat under both: a routine the game calls whenever another part of it starts up was resetting the entire sound model, unloading the sound banks that had just been loaded. 971 rejected plays in one log. A second driven mission took those to zero unknown banks and one slot exhaustion.

*How:* sceSifInitRpc reset the IOP model on every call rather than only the first, and a stream that ended by itself never freed its slot.

*But:* measurements of a driven mission, not a listen. The owner's verdict the next day was still no.

`Cited:` `b3e3797` the owner's sound reports · `23a860d` sceSifInitRpc no longer wipes the IOP model on every call · `acc3310` audio_corr --repeat

### 2026-09-18 - The game runs on Linux

**The owner asked for Linux in the morning, offered a spare VM, and by evening the game was drawing frames on Ubuntu.**

An Ubuntu 24.04 machine, a build job on GitHub's Linux runners and the port itself landed the same day, under one rule: the Windows build stays byte-for-byte the same. The boot frame in the VM differs from Windows by 0.008 grey levels; the title check passes there at Windows' own 19 of 23. The first time the C++ suite ran on Linux it paid for itself: the system allocator aborted on a double free in the audio mixer that Windows had been tolerating for the life of the project.

![The first thing the game says on Ubuntu, inside the virtual machine: the same controller prompt Windows shows at boot, drawn by the software renderer.](docs/story/img/2026-09-18-linux-boot-dialog.png)

*How:* a refused stream header closed its file twice (two owners, one handle), fixed under a test that fails on Windows too.

*But:* every Linux number came from a VM on a software renderer at 0.8 to 2.9 fps. No real Linux machine or GPU has run it.

`Cited:` `2aa02c3` the Linux client, part one · `8f8981c` a refused stream header closed its file twice · `955c010` the gate's title stage runs on Linux · `9e70730` (2026-09-19) the tree sync re-stamps what it changed · logs/parity/vm/s8_vm_title5_summary.txt

### 2026-09-19 - The menus stop dropping frames

**The planned fix was thrown out by the measurement that was supposed to justify it.**

The login and lobby screens were the expensive part of the program, and the plan was to batch draw calls. A new trace split the cost term by term and put it somewhere else entirely, so the batching was never built. The texture cache was re-decoding itself every frame: any upload anywhere moved a counter, and a moved counter threw the whole cache away. Cached textures now check themselves against a hash of the bytes their decode read. Lobby decodes went 1331 a second to none; with four cores of the host deliberately busy, the login screen holds 58-60.

*How:* on a stale counter the same decode walk runs over current memory, and a matching hash re-stamps the entry instead of decoding it.

*But:* measured on the login screen and in the lobby, not in a mission. There's still no steady gameplay frame rate on a clean host.

`Cited:` `d238135` PS2X_GS_UPLOAD_TRACE -- the upload path's cost split per term · `4cd42b4` Goal 2 stopped by its own measurement · `759e218` cached textures revalidate by a hash of the bytes their decode read · `06f4072` the login screen holds 58-60 fps under a four-core load · docs/KNOWN.md

### 2026-09-19 - It can save, and it can hear you

**Two things every finished game has, and this one didn't.**

The owner tried to save and was told no memory card was inserted. The card stub had never created or even looked at a card folder. Now the first port always holds an inserted, formatted card whose folder is made on demand, free space is counted from what's actually there, and a guest path is checked one component at a time. The tests found a climbing path really did write outside the card root on Windows. A driven save wrote 12 files and 3020 KB to an empty folder, and a second launch read the profile and seven saves back with no prompt. The headset was the other one: the program answered the game's status question with the wrong number, so the game had never opened the microphone.

*How:* every call merges the reply into one status word and the voice tick reopens only on a merged word of exactly 1; the program had answered 3, then 2.

*But:* no voice has ever travelled. All sixteen pad buttons were held for three seconds each in a live round and nothing started recording. The talk action isn't bound in the control preset the disc loads.

`Cited:` `cef8d83` an empty or missing card folder is an inserted, formatted card · `c753808` a driven save on an empty memory card · `94937ec` the host microphone reaches the game's headset module · `79a9e26` the headset's status word · run s8_save_yes · run s8_save_second · run s8_voice_round4 · docs/KNOWN.md

### 2026-09-19 - The launcher gets a face

**Until now the front door was a box with some checkboxes in it.**

A rail of pages (PLAY, DISC, VIDEO, AUDIO, CONTROLLER, MICROPHONE, ONLINE, ABOUT, and REPORT A BUG by the end of the day), one focus model that behaves identically for keyboard and pad, open-licence type embedded in the executable so the folder stays self-contained, and a controller drawn from scratch whose buttons light up as you press them. A screenshot mode renders every page from a fixed fake state, so the work can be looked at without launching anything. A second pass answered the owner's notes: legible type at every size, a frameless window with its own top bar, a palette sampled from the SOCOM II logo.

![The redesigned launcher's CONTROLLER page, rendered by its own screenshot mode from a fixed fake state: the rail, the drawn pad, and what each button will mean to the game.](docs/story/img/2026-09-19-launcher-controller-page.png)

*How:* the one-frame flash on every page change was the frame being drawn from the old page's node list, so every label landed at the origin for a frame; the list is rebuilt after the page changes now.

*But:* proven by tests and by screenshots the loop reviewed itself. The mouse support it advertises is scheduled to be deleted.

`Cited:` `a8350cd` Sprint 8 spec, Goal 9 -- the launcher redesigned · `4c7a190` the launcher redesigned -- a rail and pages · `841d080` the owner's feedback pass · `dafb724` a preset whose address is still a placeholder is unavailable · `1966fa6` the page-change flash is a stale node list · run launcher_ui

### 2026-09-19 - A server of its own, on the internet

**Every online round the project had ever played was against a server on the same desk.**

A small rented machine went up in Ohio with a static address, start-up units, an installer and a control script that rewrites the advertised address everywhere it appears. The launcher's SOCOM Unzipped entry stopped being a placeholder and became the default. A control round ran to its clock over the internet, both round clocks in step to the second, and a ladder took two kills in four rounds on one lobby session. The server also learned to introduce itself: a message of the day, a channel name and a location that are settings rather than constants, with live statistics served for the project's site.

![Round 1 of the hosted ladder, from the host's side, moments after the kill: the first round ever played against a server that was not on the same desk.](docs/story/img/2026-09-19-hosted-kill-round-1.png)

*How:* an unattended upgrade restarted the stack mid-round, so the box is now told never to restart those units.

*But:* both players were driven copies on the owner's one PC behind one home network. Saved personas are keyed per server, so the box's address is load-bearing: move it and you risk orphaning every one.

`Cited:` `9bf44a9` the hosted Horizon server on Linux · `aa2b7f4` the SOCOM Unzipped preset is real · `52bd232` needrestart never restarts the Horizon units · `ff514f7` a first-time login · `6d31d06` the hosted server is listed by the launcher and was played on · `36559f8` the message of the day, the channel and the location are configuration · run s8_hosted_control2 · run s8_hosted_kill

### 2026-09-19 - It says why it won't start, and it weighs less

**A new sprint with one narrow question: what happens to somebody who has never seen this before.**

Every way the program can refuse now has a number and a plain sentence, shared by the runner, the launcher and the test suite. Started with no launcher at all, the runner reads the launcher's own settings. The LAST RUN line says what happened in words, and SAVE DIAGNOSTICS writes one scrubbed zip. Then the download was measured instead of guessed: a release build in its own tree, both executables stripped with their symbols kept beside them, and the folder cut to what the executables actually import. 15 of the 31 shipped Windows libraries were needed by nothing. The zip came down 15 percent to 55.7 MB, and the gate passed 3/3 on that exact stripped executable.

*How:* an import-closure auditor reads both platforms' import tables in pure Python and writes SHA256SUMS beside each archive.

*But:* the download is unsigned, so Windows warns anyone who runs it. Two promises are believed, not proven: that a double-clicked exe lets go of its console window, and that a missing audio device is reported on screen.

`Cited:` `bbc98ad` the exit-code taxonomy in one header · `6f9996d` a failure explains itself · `434bc3e` SAVE DIAGNOSTICS writes one zip · `8bec122` portable_audit -- PE and ELF import readers · `b3e7906` the portable folder carries the import closure and nothing else · `645ca27` the candidate's zip is 55.7 MB (-15%) · gate s9_g2_release_gate

### 2026-09-19 - A way to report what went wrong

**The only place in the whole program where a player can talk back.**

A REPORT A BUG page joined the rail, mirroring the form on the project's website: a title, what happened, an optional way to reach you, and a preview that says exactly what SEND would send. Attaching the last run's log is off by default; when it's on, the log is cut to 64 KB and scrubbed of your home folder and the folder your disc sits in. The ONLINE page gained a line that asks the server how it's doing every ten seconds. Five answers a server can give were driven against a local one in eight tests, on Windows and on the Linux job.

*How:* WinHTTP on Windows, a curl subprocess on Linux, certificate checks on; plain http is refused anywhere but loopback.

*But:* exactly one real report has ever been sent, from Windows. The project's own notes briefly recorded it as unevidenced, because the id is stored lower-case and shown upper-case, and the inbox mirror was 35 minutes stale. Found the next day.

`Cited:` `778ebcb` the bug report's pure half · `b34ef2d` REPORT A BUG on the rail, after ONLINE and before ABOUT · `ec773ee` the REPORT A BUG page, the ONLINE status line · `c3faf9a` the bug report's JSON reader builds under libstdc++ · `61fe083` Goal 8's live proof exists after all · docs/KNOWN.md

### 2026-09-19 - The things the owner actually noticed

**Not one of these came out of a test. They came out of somebody trying to play.**

Escape closed the game instead of pausing it, because raylib's default exit key had never been turned off; it's Start now. The Runtime Debugger opened over the game on every launch, for everyone, because it defaulted to visible. A PC pad could never crouch: SOCOM II reads how hard Triangle is pressed, and the pad reported every press as full, so the button could only go prone. And while a mission ran the launcher was still reading the pad behind it, so the aiming stick was walking a focus ring around a window nobody could see, and Start was asking for a second launch.

*How:* every pad reading in the launcher now passes through one pure gate that's the only thing which knows the game may own the pad.

*But:* the pause key has no test of its own; it needs a window. The crouch shortcut and the pad gate are proven by tests and unproven by hand.

`Cited:` `8bf72c5` Escape no longer closes the game; it is Start · `2d0463f` the Runtime Debugger starts closed · `c64373a` a crouch shortcut · `3b12fa4` while the game runs the pad belongs to the game · `54d77a2` snd_AutoVol is a timed ramp and reaches streams · `eca5450` a stream played with a parentHandle queues behind the playing one · run s9_p1_m51_audio2 · gate s9_p1_gate

### 2026-09-20 - The first build made for a person to play

**Building it found two bugs that would have shipped. Playing it found the one the whole sprint was for.**

The last code change before the candidate pointed the launcher at socom.scotho.com by default, with the raw address kept as a fallback. Then the candidate was packaged, gated 3/3 on the exact executable inside the archive, and tagged playtest-1: a 55.8 MB zip with its own checksums. It took longer than the hour it was given. The archive wouldn't build, because the bug-report feature had given the launcher a dependency on a Windows system library the packaging allowlist didn't know, and the check only runs when a release is packaged. Then the archive came out 7 MB heavier than the sprint had measured: a decision made six days earlier to build at the lower optimisation level, because the higher one made a larger download, had been written in three documents and applied in none. Both fixed under tests watched failing first. Then the owner sat down with the archive and the fourteen-step script, and stopped at step six. The mission music. Same symptoms as before, with all three of the week's music fixes in the build.

![The playtest candidate in the first mission, at the end of the gate's scripted walk, with the game's own stance tutorial up. This is the build the owner played that evening.](docs/story/img/2026-09-20-playtest-mission.png)

*How:* the trace the fixes were built on showed the mission never queues a stream at all, so the fixes were protocol-correct and inert; the fault was never reproduced by any instrument before it was declared fixed.

*But:* the packaging failure is the one to remember: the build script had already emptied the folder it was about to refill, the packaging step then refused, and the previous archive, twelve hours old and looking perfectly normal, stayed exactly where it was. A tag on that folder rather than on the run would have shipped it with no symptom.

`Cited:` `b723a5d` the project's server is reached by name · `80b1971` socom.scotho.com exists -- a DNS-only A record · `67c0182` P6's persona measurement was the wrong question · docs/PLAYTEST.md · docs/CURRENT_SPRINT.md · `210cb78` the playtest candidate could not be packaged and was built at the optimisation R151 rejected · gate s9_p7_playtest_gate · docs/KNOWN.md

### 2026-09-20 - The music, chased to the speaker

**Every audio measurement the project had ever made ran on a wired endpoint. The owner listens on a Bluetooth speaker.**

Four hours of measuring instead of reading. Recording what Windows actually sent to the owner's JBL Flip 6 during a driven mission, next to the mixer's own output: in one minute the mix dropped out twice, the speaker 42 times, and the emulator on the same speaker zero. raylib opens the device at 10 ms periods, three of them, and under load the device thread misses that deadline about forty times a minute. The runtime now opens its own device at 20 ms x 4: same minute, same speaker, 42 down to 2. The numbers found three more on the way: every music cue was playing 2.3 dB to the right (a sign bit dropped from the pan word), the game's positioned voice lines were starting at volume zero and never being turned up (SetSoundParams never reached a stream), and stream underruns had never been counted anywhere. Ruled out by measurement, not argument: the three fixes from earlier in the week, the reverb, loop flags, master-volume writes.

*How:* a WASAPI loopback of the default endpoint under the driver, scored beside the mixer's dump; the device spec is pinned by a test that was watched failing at "got 10 / got 30 ms".

*But:* the owner listened again an hour later: better, not done. "Stuttering, skipping a bit" walking to the first enemies, and two segments at once in the briefing. The rest of the night is the next entry.

`Cited:` `c611ad6` the mission music, investigated to the speaker · `7c0620f` R177 -- the mix device buffer · gate s9_q0_device_gate · gate s9_q0_trace_gate · docs/superpowers/plans/2026-09-20-sprint-9-q0-mission-music-investigation.md

### 2026-09-20 - An audio parity test, and the sound that was never there

**The owner asked for an audio version of the picture test. It found something no ear had named.**

The picture gate compares our frames to the console's. The new check does the same for sound: a loopback recording of the whole path to the speaker while the driver plays a step script on either target, one score per step window (level, silences, holes, splices, envelope wobble) against a console capture pinned as the reference. Its first verdict on ours was 10 of 48 windows within tolerance, and the honest windows said something specific: at the mission start the console holds a continuous floor of sound where ours is silent 69% of the time. That floor isn't a stream. It's one sound the game plays once at mission load and polls all mission long: a conductor of child sounds, driven by a register the game writes every frame, with markers and a loop. Our mixer skipped every grain type it uses. Modelled from the open 989snd reference and pinned by tests on the real block cut from the disc: the wind, the birds and the insects exist now. 10 of 48 became 31 of 48, with no mission window silent. Later the same day a reading of the original sound driver found why stems ever skipped: on the console a finished stream still answers "playing" until its slot is retaken, and the game's music manager queues the next stem on that answer. Ours answered "done", the manager dropped its cue, and every next stem began fresh or late.

*How:* scripts/parity/audio_parity.sh capture <pcsx2|ours> <stamp>, then compare; the conductor's grains (START/STOP_CHILD_SOUND, register tests, markers, loops) are modelled from open-goal's 989snd.

*But:* the bed plays 7-12 dB quieter than the console's, the logo movies' audio is about 18 dB low at the source, and the still-playing fix is in verification as this is written. The owner's ear closes this, not a number.

`Cited:` `19ae5f6` an audio parity check against the console · `842174c` the mission ambience is a CONDUCTOR sound · `77d5522` a VAG stream that played out still answers snd_SoundIsStillPlaying · gate s9_q0_children_gate · scripts/parity/audio_parity.sh · docs/superpowers/plans/2026-09-20-sprint-9-q0-mission-music-investigation.md

### 2026-09-20 - Version 0.9.0, and a robot that plays every night

**Sprint 9 merged to main and got a tag. Then a scheduled job started playing rounds against the hosted server on its own.**

The sprint that started as "a stranger's first run" closed with the playtest's verdict still open on the music, and the rest of it done: the release build, failures that explain themselves, the launcher finished, the server by name. Merged to main with a merge commit, tagged v0.9.0. The same morning a Windows scheduled task learned to run ladder rounds unattended and write a ledger. Its first two runs failed to create a game. The title matcher had the channel name "Channel 1" baked into its reference, and the hosted box says "US East (Ohio)". Fixed on the title words, and run three was KILL 4/4.

*How:* scripts/ladder_job.sh under the loop lock, tools_py/parity/ladder_ledger.py for the ledger, docs/LADDER.md for the rules; the Task Scheduler entry is created disabled until the owner names a window.

*But:* no GitHub release; that waits on a decision about what can legally ship. The ladder's bar is seven clean runs in a row, and the streak is one.

`Cited:` `4415254` Merge sprint-9: A stranger's first run (v0.9.0) · `19b4270` Sprint 9 closed · `0c20a6a` the first clean ladder row · run ladder_20260920_101741 · docs/LADDER.md

### 2026-09-20 - A console and a PC in the same match

**A PlayStation 2 client and our program, in one game, on the hosted server, both ways round.**

The console side is the reference emulator running the retail disc, driven by the same screen-verified lobby flow ours uses. It presses on what its screen shows, with references cut from console frames where its 7% narrower screen needs them. Leg one: the console joins a game ours hosts. Leg two: ours joins a game the console hosts. Each reached a running round with both players moving, twice in a row. Eleven runs to get there, each failure one specific thing: the narrower screen, the READY label's edges, a 30-second notice, the shared peer port, a host that pressed READY before the join.

![Our program, in a round hosted by the console client on the hosted server: the first time the two have shared a match.](docs/story/img/2026-09-20-mixed-match.png)

*How:* tools_py/parity/pcsx2_shell.py drives PCSX2 through the same step script and the same detectors as ours, over the DNS stub to the hosted box.

*But:* the "console" is an emulator on the same PC as ours, not a PlayStation 2 on a couch. Still owed: each guest's copy of the other's position, so "seen by the other" is measured rather than assumed. And still: no two humans have ever played each other.

`Cited:` `93677a5` the mixed match's leg 1 on the verified flow · `136c635` leg 1 reached · `25690ad` leg 2 reached · `984a342` Sprint 10 Goal 3's bar met · run mixed2_ours_hosts_g · run mixed2_pcsx2_hosts_g · tools_py/parity/pcsx2_shell.py · docs/superpowers/plans/2026-09-20-sprint-10-goal-3-mixed-match.md

## 2026-09-21 .. 2026-09-22 - Public, and played

*The code is public, and a stranger can build it from their own disc in under an hour. The owner played a build end to end and the fixes came out of what they hit. Still: nobody outside this house has played, and the music at the speaker is the open question.*

### 2026-09-21 - Anyone can read it now, and build it

**The repository went public on the evening of the 20th. The next day went on making that safe, and then on proving a stranger could actually use it.**

A leak check now stands at four doors: before a commit, before a push, on the build service over the whole history, and on the release folder before it's archived. It rehearses on 28 planted secret shapes before every scan, and a scanner that didn't run is never a pass. A second, independent scanner reads the same history. Then a fresh clone was made to build on Windows from nothing: a pinned toolchain download of 245 MB, a build in about four minutes on a bare rented runner, the suite green. A licence inventory with a test that fails on any dependency without a row. A release workflow that makes a draft on a tag and never publishes. And the newcomer's path was run for real, from a clone of the public address into an empty folder, every command one the documentation tells a stranger to type: 42 minutes from the clone to the game on screen, about 15 GB of disk.

*How:* tools_py/release/leakcheck.py has six modes and three exit states; gitleaks 8.30.1 pinned by sha256 is the second opinion; scripts/bootstrap_windows.sh pins llvm-mingw, CMake and Ninja by hash.

*But:* a stranger can build the game, not download and play it. That's the owner's order: harden the build first, no easy player setup until then. And an audit of disc-derived bytes in the public tree found five classes of them, sized and listed; whether any of it moves is the owner's decision, not made yet.

`Cited:` `3c06c5d` (2026-09-20) the leak gate in four places -- Sprint 10 reorganized around hardening the now-public repository · `00b0ce3` (2026-09-20) a fresh clone builds on Windows (H3), the suite stops littering the tree (H4), the licence inventory with its test (H5) · `92b92c6` Sprint 10 hardening to main · `110c286` the release-draft workflow (H8) · `eb94301` H7 -- disc-derived bytes in the public tree, five classes and fourteen rows sized · `065bdcc` the newcomer path run from a real clone -- 42 minutes to the game · gate s10_h6_scrub_gate · docs/GIT_STRATEGY.md

### 2026-09-21 - From your disc to a build, in one command

**The one step of the build a newcomer could not do had been run once, by hand, at the start of the project.**

Everything the recompiler needs comes out of the player's own disc: the loader, the encrypted archive, the two code overlays inside it. That path had been walked by hand on the 4th and promised in the contributing guide ever since. Now it's one script: point it at an ISO and it pulls the files, decrypts them, checks every digest against the six the owner recorded the first time, and stops cleanly if any differ. Running it for real, from an empty game folder to a built executable, took 29 minutes and matched the owner's digests byte for byte. Running the whole newcomer path after it found a bug the maintainer's machine could never see: the toolchain bootstrap extracted into one folder and renamed it, and on a fresh clone the rename failed at the very first command a stranger types. Fixed, and the first command finally has a test.

*How:* scripts/disc_to_elf.sh is idempotent and self-verifying, 43 tests; the two decryption scripts became callable so one command could drive them.

*But:* the recompile still reports 114,399 untranslatable instructions, the same number as on the 4th. It's garbage that never runs, and it's still there.

`Cited:` `41eb046` one command from a stranger's ISO to the files ./build.sh recomp needs · `6dfa2c4` merge: agent/disc -- the new-developer build chain closed · `67ff2e8` no rename -- extract each toolchain straight into tools/<name> · `403f593` the first command a stranger types finally has a test · `7e7e1f0` the game build IS supported now -- one command from your own disc, proven from nothing · docs/DEVELOPING.md

### 2026-09-21 - Eleven jobs, eleven worktrees, one gate each

**The most commits in a day so far, 150, and most of them written by agents that never touched the main tree.**

Each job got its own copy of the repository, a bounded brief and a stop rule. The controller merged what came back, rebuilt, and ran the three-stage picture gate before calling anything done. What landed: the gate now records every input it scored against and refuses to score at all if one has drifted. A render stall that used to eat the machine, 1.45 GB of queued commands over 600 frames, is bounded at 67 MB. A test that had been failing on the build service one run in two was fixed at its root, a simulated clock that starved one thread of its turn: 50 failures in 100 runs before, 0 in 300 after. And a console-replay test that had never actually run, runs. Two regressions got through the suite and were caught only by the gate. One was a tidy-up that moved some shared state into one file and quietly made nineteen stubs share a single disc-streaming cursor; the mission never loaded, and the change was reverted whole. The other finding was about the agents, not the code: one pushed to the main branch three times against its brief. The fix is not a stronger sentence in the brief. The next worktree is handed out with no address to push to.

*How:* each chunk ran in its own git worktree on a branch; a merge, ./build.sh runtime and python -m tools_py.parity.gate in the main tree paid for it.

*But:* the suite was green on both sides of the state revert, 764 of 764. Only the gate saw it. And removing the worktrees deleted the toolchain through their folder links, twice, before the order of operations was written down.

`Cited:` `691685d` the gate states what it measured -- PIN lines and pins.json beside the EXE line · `2342d60` a latched stall no longer grows the command queue on its state stream · `c303f74` the simulated Clock runs its threads in lockstep · `99a059c` the console-replay case runs · `955539c` the stub-state header stays per-TU · `1bfc047` the delegation finding -- an agent pushed to main three times against its brief · gate s10_q6_gate · gate s10_q7b_gate

### 2026-09-21 - A stranger's environment can't change the game

**About 150 environment variables could change how the game ran, and nothing said which ones a player was meant to touch.**

Every one of them is now a row in one table with a class: 18 that a player's launcher can send, the rest for developers only. One accessor reads them all, a generated page lists them, and a test fails on a name without a row, a row without a read, or a read that goes around the accessor. Developer settings need developer mode; outside it they read as unset, and the start-up line names what it ignored. Eight settings that switched something on when set to zero became plain flags. The launcher stopped passing on whatever it inherited. Proven by poisoning a launch with every setting at something hostile and watching the gate pass anyway. Found on the way: the start-up line was writing the login password in clear, and a five-letter password slipped under the scrubber's six-letter floor. Same day, the mouse left the launcher and the game entirely, and the keyboard was narrowed to menus and typing for a player. The full gameplay mapping survives in developer mode only, because the harness plays the game through it.

*How:* ps2x::knob is the one read path; --dev or PS2X_DEV=1 is developer mode; the [knobs] line in every log says what was honoured and what was ignored.

*But:* the mouse block that was deleted had never had a test. The count moved three times in a day, 145, 149, 151, as the registry found reads the inventory had missed.

`Cited:` `d76ec8d` the knob registry -- 145 PS2X_* names classified in one table · `1f94bae` docs/KNOBS.md generated from knobs.h · `869356e` a stranger's environment cannot change the game -- Dev knobs need --dev or PS2X_DEV · `2b49124` the scrub redacts PS2X_SOCOM2_LOGIN_PASS at any length · `954154a` Q2 / Goal 3 closed -- 151 knobs classified · `8ff45e7` the mouse leaves and the keyboard is narrowed to menus and typing · gate s9_g3_gating_gate · gate s10_q3_gate · docs/KNOBS.md

### 2026-09-21 - Press a button to bind it, and the game remembers who you are

**The pad's buttons were two tables compiled into the program. Now they're a setting, and the launcher lets you change it with the pad alone.**

On the CONTROLLER page every button of the game has a cell. Press it and the launcher listens for five seconds; the next pad button you let go of becomes the binding, and the drawn pad lights up to show it. Bind a button that's already taken and it asks: swap, replace, or cancel. Restore defaults asks first, and the default answer is no. The game logs a hash of the mapping it was given and the gate pins it. Then the rest of the launcher: the guide button swaps between launcher and game; the game window wears the launcher's name, icon and colours; and the menus click with the game's own sounds, decoded from the player's disc on the first run and cached, never shipped. And the login: the launcher's player name and password now appear in the game's own on-screen keyboard, ready to confirm. That took two findings to work at all. The game's menu calls the keyboard through a tiny forwarding routine the first wrap never intercepted; and once it did, the text vanished, because the wrap's clean-up ran when the game's scheduler unwound the call, before the keyboard had read it. Three logins with nothing typed, and the ladder streak reached four of the seven clean runs the bar wants.

*How:* the mapping is one table resolved from config.json per profile, with today's values as the defaults byte for byte; the four menu cues are the disc's HUDUI bank rendered through the runtime's own mixer.

*But:* the remapping page is proven by tests and screenshots; the owner's hands haven't touched it. The menu sounds were rendered and measured, not heard. And the hold-to-remap gesture the owner would ask for was a day away.

`Cited:` `3d7dd22` Q3b, the mapping data path (R174) · `384dd0d` Goal 8, the controller mapping UI (R174, part 2) · `0acf90b` the window switch -- the guide button swaps launcher and game · `283130c` the game window wears the launcher's name, icon and palette · `0162d71` menu sounds from the game's HUDUI bank, decoded from the player's own ISO on first run and cached, never shipped · `103122a` the on-screen keyboard opens holding the launcher's persona name and password · `2bc56ec` the prefill wrap is installed on the thunk the UI action table calls · `f47cfe0` the prefill buffer is written before the open and never after · `d99dad1` run 4 by hand -- KILL 4/4 on the hosted server · gate s10_g8_gate · gate s10_q4_gate · run s10_g8_control_frostfire · docs/LADDER.md

### 2026-09-21 - One round, on film

**The first kill was on the 13th and came as two stills. This one you can watch.**

Two of our clients on one desk, both on that night's build, both in the same round on the hosted server, both driven by the agent while the owner watched. The whole round, four minutes and a quarter of it, cropped to the two windows and nothing else: the round card, a long circling of the yard, the shot at 3:41, the killfeed on both screens, the scoreboard, and the next round's opening card.

![Round's end, both screens: SOCOM-B on the left has just died, SOCOM-A on the right did it, and the same killfeed line sits on each. Press play for the whole round; the shot is at 3:41.](docs/story/img/2026-09-21-online-kill.mp4)

*But:* it is not graceful. The camera sways, the aim hunts, and the approach takes most of a four-minute round. It is functional: the round ends by a shot, both screens say so, and the scoreboard counts it.

`Cited:` `0eef452` run 2 by hand -- KILL 4/4 on the hosted server · docs/LADDER.md

### 2026-09-22 - The owner plays it, and the save fails the first time

**A new build for one sitting, and the notes that came back were the useful kind: small, specific, and none of them from a test.**

The archive was built the night before, gated on the exact executable inside it and checked for leaks. The owner played it end to end and reported as they went. The pad stopped working in the launcher after a click into a text field, because the only ways out of a field were keyboard keys. A space typed into the player name was shown in the field, saved to disk, and silently dropped before the game got it, so the login failed with nothing on screen to say why. The launcher's default window went back to the game's own 640 by 448. And the one that mattered: on a fresh install the first save failed, and the second launch worked. The build the owner played recorded nothing about it, because a failed memory-card command said nothing at any setting. Fixed first: any failure prints one line, in every build, no setting needed. That line found the bug the same night. The game lists a brand-new card by asking for its parent folder, "..", and our path checker refused that as an attempt to climb out of the card. The game read "permission denied" as a card it couldn't use. On the second launch the save folder existed, the path resolved, and it worked.

*How:* a trailing ".." now resolves to the card's root, which is its own parent; a ".." followed by anything is still refused, so "/../escape.bin" never names a file.

*But:* the first cut of the diagnostics ruling was wrong. It reclassed two developer settings as shipping ones, believing developer settings are compiled out of a player's build. They aren't, and the suite refused the change. Fixing the actual hole, silence on failure, is what found the save bug.

`Cited:` `ffebba2` (2026-09-21) tonight's archive -- built from acbc693, gate s10_playtest2_gate 3/3 on the exe inside the zip · `46a6594` fix wave A (W1-W3, R236-R238): the pad regression, the field accept-set, and a card failure that is never silent · `152579a` finding 3, root cause and fix: the game asks a virgin card for '..' and we answered "card refused" · gate s10_playtest2_gate · gate fixwave_a · docs/superpowers/plans/2026-09-22-fix-wave-playthrough.md

### 2026-09-22 - Hold a button to remap it, and a sound that was never there

**The rest of the owner's notes, and one of the project's own claims that didn't survive being measured.**

The owner asked for a second way to remap: hold any pad button on the CONTROLLER page and the same bind flow opens for it, with hints that walk you through it, a meter that fills as you hold, and a gold ring closing in on the control. Five buttons can't be held, for reasons the code states: the two that move around the page, and three whose press is already spent on tabs and launch. The pad drawing got redone while it was open. The join driver learned that an empty games list is a result of its own and not a failure, after it had pressed JOIN GAME four times into "There are no games to join" trying to reach the owner's lobby. Then the "blop" the owner hears on the online screens. The project's notes had charged it to one sound bank on the strength of a correlation, and the correlation had been drawn by bucketing the owner's log by line number. Log lines are not time. Measured on one clock, with the play commands stamped on the mixer's own frame counter, the bank's one-shots sit 0.2 dB against the music bed. Inaudible. Cleared. What the same instrument did find: over ten minutes on the owner's Bluetooth speaker, 31 dropouts at the speaker that the mixer's own output doesn't contain.

*How:* the new drive script skips the cinematics and reaches gameplay on the existing boot chain minus about 50 seconds of dead wait; audio_dips classifies each dip as DEVICE, STARVATION or COMMAND against the log.

*But:* a lead, not a finding: one run, one device. It settles on a wired speaker, and that run hasn't happened. The join driver's refresh press has no visible mark, and nobody has joined a real lobby with it. And a driven hold captures almost no music, because standing still at the start of a mission plays only short voice cues; the capture that matches what the owner heard needs the drive to walk.

`Cited:` `668c7f5` fix wave A (W9, W5): hold a button to remap it, a better pad, and the bank cleared of the online blop · `00d8348` fix wave A (W7, W8, R240): an empty games list is not a join failure · `0b1250b` fix wave A (W7): the instrument is proven, the drive that feeds it is not -- and the endpoint is dropping audio again · gate fixwave_b · run blop_c · run mission_music_ours_20260922_024457 · docs/KNOWN.md

---

## Where it stands tonight, 2026-09-22 — and what the night answered

*Not an entry and no `Cited:` line. This is the view from the end of the record on the night it ends, and it gets
replaced by real entries as things land. **It is kept exactly as written and answered underneath**, because the
answers arrived within hours and a paragraph that is wrong with its correction beside it is worth more than a
paragraph quietly rewritten.*

> **Superseded as a live statement, 2026-09-25.** The paragraph below is the record of one night and is kept word
> for word; **read none of its numbers as current.** A commit count, a branch name, a tag list, a streak and a task
> count are the five things this document's class forbids, and all five of them below are now wrong. Where to read
> each instead, which is what this document should have said in the first place: the live queue is
> `docs/CURRENT_SPRINT.md`; the branches and tags are `docs/GIT_STRATEGY.md` §1; the ladder's streak is
> `docs/LADDER.md`, which is generated; what is proven, believed and retracted is `docs/KNOWN.md`, which wins over
> this page on any disagreement.

> The tree is at `e6a924d`, 1,028 commits, on `sprint-10`, with two tags: `playtest-1` and `v0.9.0`. The repository
> is public. Sprint 10's autonomous work is on `main`, slice by slice, the last two slices from the owner's
> playthrough. The scheduled ladder has four clean runs of the seven it needs. Sprint 11 has a spec: the r0004 update
> the community server requires, costed against the tree, waiting on a package only my memory card can supply.
>
> The open question is still the music, and it has moved from the mixer to the speaker. Every fix so far was measured
> on the mix as rendered. The one instrument that listens at the speaker heard 31 dropouts in ten minutes on my
> Bluetooth speaker that the mix doesn't contain. One run on a wired speaker decides whether that's the cable or us.
> Behind it, two decisions: whether the login the launcher prefills can go now that the save works on a fresh card,
> and how far a driven walk into the first mission should go before a death counts as "the music stopped".

**2026-09-23, the morning after.** Three of those sentences have moved.

The 31 dropouts were re-scored to 11 the same day — twenty of them were the scorer's own matching, not the game's —
and then the wired run happened. It gave 14 on the cable against 11 on the Bluetooth speaker over sixteen minutes.
**It's us.** Not the cable, not the speaker: something between the mixer's own output and the write that proves what
the mixer did. That is a smaller question than the one I had, and a much better one, because it can be instrumented
instead of argued about.

The two decisions were both taken by running them rather than deciding them. The prefilled login **stays** — a
virgin card keeps the persona through a restart and loses the saved password, so the game's own way in doesn't yet
reach the lobby on its own. And the driven walk is not enough: twelve minutes of walking in place produced ten
perfectly clean HELP popups, and the garbled one I saw was after the church, which a walk that never leaves the
insertion point can never reach. The experiment wasn't wrong; the route was too short, and the capture didn't even
record which settings it ran with — which is its own lesson, now written down.

Sprint 10 is closed. Sprint 11 is open, and the specs became a plan; `docs/CURRENT_SPRINT.md` is where its tasks
live, and this page does not count them.

No stranger has played yet. No two humans have played each other. Those are still the two sentences this page most
wants to lose.

**2026-09-25 — the record stops short.** This timeline's own first line promises "first commit to today", and its
last entry is 2026-09-22. Three days are missing, and they carry the project's biggest technical result: Sprint 10
merged and tagged; the chat receive path bounded on the client and clamped on the server; the community revision
r0004 rebuilt from PSRewired's package, gated three times over and played online on the project's own server; the
bug pipeline's GitHub half; 11.6 MB of vendored baggage deleted; a SOCOM 1 demo disc naming 987 anonymous
functions. Writing those entries is not a one-line edit — each needs its hashes and a witnessed run — so it is
**carried explicitly as a Sprint 12 item** rather than left to slip (Sprint 11 close review, row A22) — *and carried a
second time at Sprint 12's close (2026-09-25): that sprint took nothing but the naming programme, so the missing days
are now these three plus Sprint 12's two, a line in `docs/CURRENT_SPRINT.md`'s "Sprint 12 — CLOSED" carry and an
owner question in `docs/HUMAN_TASKS.md`*. Until it
lands, `docs/STATUS.md` and `docs/CURRENT_SPRINT.md` are where those three days are written down.

---

## How this document is checked

Every `Cited:` line is parsed and verified by `tools_py/story/cite.py`, in the project's Python suite:

```
python -m tools_py.story.cite
```

A commit hash must resolve, be unambiguous, be reachable from the published branch, and the words beside it must come
from the commit's real subject. A run or gate id must have a frozen witness in `docs/story/witnesses.json`, re-proved
against the file on the machine that has the logs. A tracked path must be tracked. `docs/story/timeline.json` is the
machine-readable form, rebuilt from this document by `python -m tools_py.story.timeline`, and the test fails if it
and this document disagree in either direction. The design is
`docs/superpowers/specs/2026-09-19-sprint-11-goal-6-progress-story-design.md`.
