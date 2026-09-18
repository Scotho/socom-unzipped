# Human tasks

Things only the owner can do: hands-on checks on the real machine with real ears and hands. The autonomous loop
adds items here when it reaches a step it cannot verify itself, and moves on. Report back in one line each; the
loop picks the answer up from the next session's prompt or from a note in `docs/STATUS.md`.

## Open

- [ ] **Listen to the title screen and the intro** (Task 6c Step 4; research/32 §7.1). Launch `dist/socom2.exe`
  (or the launcher), sit through the logos, the intro movie and the title loop. What to listen for: the music
  should be continuous and clean; a short blip right as the intro movie starts and again as the title loop begins
  is a known residual (the first ~10 s after each stream start fill a little short). Anything else -- crackle,
  stutter, repeats, wrong pitch, wrong channel balance -- is new and worth a line: *when* (logos / intro / title
  loop, and roughly how far in) and *what* it sounds like. Measured state on 2026-09-17: the mixed output correlates
  with the disc's PCM at 0.99 through both movies, so this listen is the confirmation, not the diagnosis. Re-measured
  on 2026-09-17 after the mixer moved its disc reads off the audio callback (Sprint 7 Task 1e) and the CD cursor fix
  (Task 2c): the title loop correlates at 1.000 in every 4 s window with a constant offset (`s7_audio_title`). The
  number you are confirming: **1.000** on the title loop, 0.99 on the intro. Command: `dist/socom2.exe` from the repo
  root, or `bash scripts/parity/env.sh` then `python -m tools_py.parity.drive --only title` for the driven version.
- [ ] **Listen in free play** (Task 6c Step 4). A mission with gunfire, voice-overs and the mission music. Mission
  audio was reported good on 2026-09-17; this is to confirm it stayed good after the demux changes that fixed the
  title screen. Same reporting: when and what. Command: `dist/socom2.exe`, NEW GAME, any mission; five minutes is
  enough. No correlation number exists for mission audio (its sounds are mixed from many voices, not one stream);
  the driven mission stage passes the gate 3/3 daily (`s7_gl_gate2`), which says nothing about how it sounds.
- [ ] **The launcher with the Xbox pad** (Task 8b Step 4). Run `dist/socom_unzipped_launcher.exe`: point it at the
  ISO, check the controller test area sees the pad (sticks, triggers, every button), pick a video size, press
  Launch. Report: did the pad register in the test area, did the game start, did the pad work in the game. Since
  2026-09-17 the launcher opens the game at 1280x896 by default (Sprint 7 Task 1c, ruling R92; the 2x frame measured
  0.83 mean |diff| against the 1x frame, i.e. scaled, not cropped) and the window is DPI-aware: one more line worth
  having is whether the window looks right on your display (sharp, the whole frame visible, no tiny window).

- [ ] **The two server addresses for the launcher's picker** (owner request 2026-09-17; audit §2.6). The launcher now
  offers *SOCOM Community (public Horizon)*, *SOCOM Unzipped (project server)* and *Custom*. Both preset addresses are
  deliberate placeholders (`COMMUNITY_SERVER_ADDRESS_TBC`, `UNZIPPED_SERVER_ADDRESS_TBC`) in
  `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h`, because neither is known to the tree: the
  community server's is whatever the SOCOM community's Horizon publishes for SOCOM II (a hostname or IP), and ours does
  not exist until a machine hosts it. Two lines back: the community address, and, once hosted, ours (with the ports
  forwarded per `server/README.md`). The default preset switches to *SOCOM Unzipped* when ours is real.
  The server half is ready to hand over (Sprint 7 Task 4, 2026-09-17): `bash scripts/make_server_zip.sh` builds
  `socom-unzipped-server.zip` (~17 MB, prebuilt binaries, no seeded database) for whatever machine hosts it, the
  `-PublicIp`/`-ShowIp` rewrite was verified end to end on a test address, and `server/README.md`'s forward list
  matches what the stack actually binds. Only the two addresses and the hosting machine are missing.
- [ ] **A second machine for the first two-machine match** (audit §1 G5, Sprint 7 Task 5 / spec Goal 5). Every online
  result so far is two instances on one PC, so NAT, the advertised address, the clock skew between two machines and two
  clients on one account key have never been exercised at all. When a second PC (or a friend) can run the portable zip:

  1. **Copy the zip.** `bash scripts/make_portable.sh` writes `dist/portable/socom2-portable.zip` (the folder it zips is
     `dist/portable/socom2/`). Unzip it on the second machine; nothing is installed, and it is deleted by deleting the
     folder. The second machine needs its own SOCOM II ISO (NTSC, SCUS-97275 r0001) -- the disc is not in the zip.
  2. **Pick the preset.** In `socom_unzipped_launcher.exe`'s Online panel: *SOCOM Unzipped (project server)* once that
     address exists (the item above), otherwise *Custom* with the host machine's address -- the public one if the two
     machines are on different networks, the LAN one if they are on the same. Both machines must be set to the SAME
     address. `server/README.md` has the ports to forward on the machine running the stack.
  3. **Play one round each way.** Machine 1 hosts and machine 2 joins; then swap, so both directions of hosting are
     exercised. In each round, both players walk around for a few seconds where the other can see them. No kills needed.
  4. **Collect the two run logs.** Each machine writes `logs/run_*.log` inside its own portable folder. Take the newest
     from each, put them side by side on one machine, and run:

     ```bash
     bash scripts/parity/two_machine_readout.sh <log from machine 1> <log from machine 2>
     ```

     It prints one block -- lobby class per side, `saw_peer_move A=/B=`, the clock skew and the row counts. Paste the
     block back. (Exit 0 means the bar was met: a lobby reached and both players seen moving. A run driven by this
     repo's harness can add its `logs/parity/drive_<name>.txt` as a third argument, which fills in the lobby class;
     from the zip alone that line reads `class=-`, which is expected and not a failure.)

  **Four things to report in words**, because no log can answer them:
  - **NAT shape** -- same LAN, or across the internet; and on each side, was the router doing anything special
    (UPnP on, ports forwarded by hand, carrier-grade NAT / no forwarding possible).
  - **The advertised address** -- what address was typed into each launcher, and whether the joining machine ever
    got as far as the game list (an exe that advertises `127.0.0.1` shows as a lobby that lists no games).
  - **Whether key sharing mattered** -- did both machines use the same account/profile name, or different ones, and
    did the second one to log in get thrown off.
  - **What you SAW** -- did the other player's soldier actually move on your screen. The readout reads each player's
    motion out of that player's own log, so it can say the other guy moved; it cannot say he was drawn moving on
    your screen. Your eyes are the only instrument for that half.

- [ ] **Pick the pad in the launcher, then play with it** (Sprint 7 Task 8, owner request 2026-09-18). Plug the
  Xbox pad in and run `dist/socom_unzipped_launcher.exe`. The Controller panel now lists every pad Windows
  reports as `[<slot>] <name>` with *first available* at the top; pick yours, watch the test area (it draws the
  slot you picked, not slot 0), and move the **dead zone** slider until the sticks read dead at rest and still
  reach the edge of the ring at full deflection. Press Launch, play one single-player mission and one online
  round. Report one line each: (a) did the pick hold -- was the pad you chose the one the game read, in the menus
  and in the round; (b) did the dead zone feel right at the value you left it on (say the number), or is the
  default too loose or too tight. The numbers you are confirming: the launcher writes
  `PS2X_HOST_GAMEPAD_INDEX=<slot>` and `PS2X_PAD_DEADZONE=<value>` (visible with
  `dist/socom_unzipped_launcher.exe --selftest`), and the default is **0.15**, the dead zone SOCOM's own poll has
  used since 2026-09-16 and which the other two pad paths did not apply at all until this task (ruling R95).
  Launcher build: the `dist/socom_unzipped_launcher.exe` sha256 from the commit below.

- [ ] **Pick the microphone and watch the meter** (Sprint 7 Task 9a, owner request 2026-09-18). Run
  `dist/socom_unzipped_launcher.exe`. The new Microphone panel lists every capture device Windows reports, with
  *None* first; pick your headset's and speak. Report in one line: does the bar move when you speak and sit at
  the left when you are quiet, and was the device you picked the one that reacted. If the list is empty or your
  headset is missing, press Rescan first and say so -- an empty list means miniaudio could not start the host's
  audio backend, which is a different fault from a missing device. The numbers you are confirming: the meter is
  RMS in dB across -60..0 dB, and the launcher writes `PS2X_MIC_DEVICE=<the name you picked>` (visible with
  `dist/socom_unzipped_launcher.exe --selftest`).
- [ ] **Speak in an online lobby, and expect to be unheard** (Sprint 7 Task 9b/9c, owner request 2026-09-18).
  With a second machine in a lobby (the two-machine item above), pick your microphone in the launcher, join, and
  speak. **Expected answer: the other side hears NOTHING**, and that is not a fault in this sprint -- the IOP
  headset module still answers "no headset" to everything but its version query
  (`third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp`), so nothing carries the captured audio to the game
  yet. What is worth a line: (a) did anything at all come through (if it did, something we do not understand is
  happening); (b) did picking a microphone change the game's behaviour in any way -- a stutter, a longer boot, a
  new log line. To check the capture half by itself, without a second machine: run the game with
  `PS2X_MIC_DUMP=logs/mic.wav` set, speak for ten seconds, quit, and play `logs/mic.wav` back. If your voice is
  in that file the capture half works and only the game-side plumbing is missing -- which is the Sprint 8 job
  Task 9c's `docs/KNOWN.md` section 2 row scopes.

- [ ] **Re-listen after the sound fixes** (Sprint 7 Task 12; your report of 2026-09-18 01:52: "sound is off on the online menu just after
  signing in, skips and almost plays two different spliced segments"; "a persistent buzz during the create game playlist, also in
  the lobby"; "mid mission, sound stopped working altogether"). What was found and fixed, each under a test: the buzz and the
  splice were the menu-music ring replaying or skipping blocks when the game's fill ran late (the ring now plays a block once
  per fill and counts misses); the mission going silent was two leaks of the game's stream slots (a stopped stream never freed
  its slot; a stream that ended by itself never did either) plus the RPC init call wiping the whole sound model mid-mission
  (every loaded bank gone -- 971 rejected sounds in your log). Numbers now standing against your three sentences: online menus
  music continuous per screen, no repeat above 0.70 (bar 0.90), zero ring misses; mission log 0 unknown-bank rejects (was 971)
  and 1 slot exhaustion (was 237), 29 streams played (was 12). One caveat: your buzz happened while the login screen ran at
  12-30 fps, which the driven runs could not reproduce even under four spinning cores, so the ring's protection is proven by
  its test, not by a launch. Please run the same path (`dist/socom_unzipped_launcher.exe`, online, sign in, create game,
  lobby, then leave and play one mission) and report the same three things: the menu music, any buzz, whether mission sound
  lasts. If the buzz is back, one line on whether the game looked slow at that moment.

- [ ] **Run the Linux tarball on a real Linux machine or a Steam Deck** (Sprint 8 Goal 1; owner request 2026-09-18 "add linux
  support to the installer/launcher"). The port is built, unit-tested and booted in a VirtualBox Ubuntu machine that the loop
  created on this PC (`socom-linux`; your "Work" VM was not touched), so the WSL request is withdrawn. What a real box adds:
  a real GPU driver (the VM's Mesa gives GL 4.1 through VMSVGA), real audio, a real pad. The tarball: build it with
  `bash scripts/build_linux.sh` then `bash scripts/make_portable.sh` on a Linux checkout (or take
  `dist-linux/portable/socom2-linux.tar.gz` from the VM: `scripts/vm_sync.sh ssh 'cat ~/socom_pc/dist-linux/portable/socom2-linux.tar.gz' > socom2-linux.tar.gz`
  on this PC; 114 MB). Unpack anywhere, `./socom_unzipped_launcher`, point it at your ISO, Launch. Report: did the launcher
  open (it needs an X or XWayland session), did the game boot to the title screen, was there music, did the pad work, and
  the first three `[gs-gl]` lines of `logs/run_*.log` in the folder (the GL version and any UNSUPPORTED/note line). On a
  Steam Deck: desktop mode, and say whether it ran from the SD card or internal storage.
## Done

(none yet)
