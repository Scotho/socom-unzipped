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

## Done

(none yet)
