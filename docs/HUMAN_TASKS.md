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
  with the disc's PCM at 0.99 through both movies, so this listen is the confirmation, not the diagnosis.
- [ ] **Listen in free play** (Task 6c Step 4). A mission with gunfire, voice-overs and the mission music. Mission
  audio was reported good on 2026-09-17; this is to confirm it stayed good after the demux changes that fixed the
  title screen. Same reporting: when and what.
- [ ] **The launcher with the Xbox pad** (Task 8b Step 4). Run `dist/socom_unzipped_launcher.exe`: point it at the
  ISO, check the controller test area sees the pad (sticks, triggers, every button), pick a video size, press
  Launch. Report: did the pad register in the test area, did the game start, did the pad work in the game.

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

## Done

(none yet)
