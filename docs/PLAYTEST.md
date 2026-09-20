# The playtest — one sitting, in order

For the owner. This folds the open items of `docs/HUMAN_TASKS.md` into one evening, ordered so that each step sets up
the next and the things you have complained about come while your ears are fresh. One line back per step is enough;
"fine" is an answer. Anything not on this page that annoys you is the most useful note of all.

```
build:    2026-09-20, release at -O1 (R151)   tag: playtest-1   commit: the commit this tag sits on (git log -1 playtest-1)
archive:  dist-release/portable/socom2-portable.zip  55,829,577 bytes
          sha256: f8f8149cb247f328651a6f5664c5ea889f6588a8de14b91a7135430f0a68a041
gate:     s9_p7_playtest_gate -- 3/3 (title, transition, mission) on the exe INSIDE that archive:
          socom2.exe 226,849,280 bytes, sha256 a43bf45c321dbdefbfa91845e87fc80074aace6661a83475189c9470486523c0
```

**Ready.** The block above is filled in from the run that built it, not from the directory (KNOWN §4: a failed packaging leaves the previous archive in place). If you want to play before that, play `dist/` and say which commit
(`git log -1 --oneline`); the notes still count, but step 1 and step 9 only mean something on the archive.

## Before you start
- Close any launcher that is already open (an open one holds the exe locked and you would be testing the old build).
- Pad plugged in; headset if you have one; Steam Input and DS4Windows off for a Sony pad.
- Unzip the archive to a NEW folder, not over an old one. Play from there -- it is what a stranger gets.

## The sitting

1. **The download is whole** *(HUMAN_TASKS: the release download, c)*. `certutil -hashfile socom2-portable.zip SHA256`
   and compare with `SHA256SUMS`. Did Windows SmartScreen or your antivirus complain when you ran it? What did it say?
2. **Double-click `socom2.exe` with no launcher** *(failures explain themselves, a)*. It should start on the
   launcher's saved settings, or tell you in a sentence why it cannot. No black console window left behind. Quit.
3. **The launcher, by pad only** *(the launcher's look; the launcher with the pad; pick the pad)*. Does it look right?
   Walk every page with the pad. On CONTROLLER: is your pad in the list, does the drawn pad follow it, where did you
   leave the dead zone? **New since your notes:** the flash at the top left when you change page should be gone;
   UNZIPPED should sit level with SOCOM II; "Second instance" should be under ADVANCED; "what is a profile?" should be
   answered where you look for it. Say which of those is NOT fixed.
4. **A failure that explains itself** *(b)*. Point DISC at a path that does not exist, press LAUNCH: LAST RUN should
   say the disc was not found. Press SAVE DIAGNOSTICS, open the zip: your Windows user name should be nowhere in it.
   Point DISC back.
5. **Title and intro, by ear** *(listen to the title screen and the intro)*. Through the logos, the intro movie and a
   minute of the title loop. Clean and continuous? A short blip as each stream starts is known.
6. **THE MUSIC -- the reason for this build** *(Goal 10)*. NEW GAME, the first mission, X through the dialog, walk
   toward the first two targets: exactly the path where you heard it "getting louder and quieter and jumping between
   different tracks". Then back out through the menus, listening at every screen change. **Is it coherent now?** If
   not: where, and does it sound like a cut, a fade that should not be there, or two pieces of music at once? Those are
   three different bugs and the word you pick sends the next fix to the right place.
7. **The pad drives one window** *(Goal 9)*. While the game runs, press d-pad and face buttons: the launcher behind it
   must not move. When you quit the game, the launcher must respond again. "RUNNING" should sit level with its lamp.
8. **Crouch** *(R139)*. In that mission: L-stick click toggles stand/crouch (it acts on release); Y still goes prone
   and back. If you have a Sony pad: CROUCH SHORTCUT = TOUCHPAD, and the touchpad click crouches.
9. **The save** *(the save prompt)*. Pick the difficulty that asks to save, YES, slot 1. Quit the game, start it again:
   it should not ask again, and your progress should be there.
10. **Free play, five minutes** *(listen in free play; re-listen after the sound fixes)*. Gunfire, voice-overs, music.
    Does mission sound last the whole five minutes?
11. **Online, on the project server** *(play a match on the hosted server; the online-menu sound)*. ONLINE page: the
    status line should say the server is up and how many are on. Launch, go online. The preset now reaches the server by NAME. (An earlier draft warned that this
    might cost you your persona; it will not -- the name is resolved before the game ever sees it, R175.) **If
    the game cannot connect at all, pick "SOCOM Unzipped (by address)" and try again** -- that is the same
    box by its raw address, and it is there for exactly the case where your network cannot resolve the name.
    Tell me if you had to, because nothing on screen says that is what went wrong. Listen on
    the screen just after signing in, in CREATE GAME and in the lobby: that is where the splice and the buzz were.
    Host a game, start the round, walk around. Lag? (The box is in Ohio.)
12. **If a friend on another network is around** *(the first two-machine match -- carried since Sprint 7)*. They unzip
    the same archive, need their own r0001 ISO, pick the same preset, and join you; then swap who hosts. Did you SEE
    their soldier move? Afterwards, from each machine's `logs/` take the newest `run_*.log` and run
    `bash scripts/parity/two_machine_readout.sh <log1> <log2>`; paste the block. With a headset on both sides: could
    you hear each other? (Expected today: **no** -- the headset's talk button is not wired yet.)
13. **Microphone** *(pick the microphone and watch the meter)*. MICROPHONE page: pick the headset, speak. Does the bar
    move with your voice and rest when you are quiet?
14. **Report a bug from the launcher** *(Goal 8)*. REPORT A BUG: write one real note from tonight, leave the log box
    as you find it (it should be OFF), read what it says it will send, SEND. You should get a `BR-` id. Is the wording
    what you wanted?

## Decisions worth making while it is fresh
- **Who else gets this archive?** For you alone, nothing to decide. For anyone else, read Sprint 11's decision D2
  first (`docs/superpowers/specs/2026-09-20-sprint-11-release-hardening-design.md`): the archive contains code
  recompiled from the game, and the game's decrypted ELF.
- **The keyboard.** You asked for keyboard = menus and typing only. The automated tests play the game by typing the
  gameplay keys into the window, so the proposal is: players lose the gameplay keys, the test harness keeps them behind
  developer mode. Say yes, or say you want the harness moved to the pad first (about a sprint).
- **A profile viewer** in the launcher -- wanted?
- **Should the download drop the built-in debugger and the dump/trace probes** to get smaller? You will get a number
  (megabytes saved) before you have to answer.
- **The repository going public** needs six answers from you, D1-D6 in the Sprint 11 spec. None is urgent tonight.

## Where your notes go
Say them to the controller in any form. It files each one as a task, a `docs/KNOWN.md` row or a ticked item in
`docs/HUMAN_TASKS.md`, and they go to the top of the queue (Sprint 9, item Q0).
