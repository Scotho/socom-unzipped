# Disc-derived bytes in the public tree -- the audit and its rows (Sprint 10 H7; Sprint 11 Goal 1 item 3)

*2026-09-21, the controller. The repository has been public since 2026-09-20, so every row below is already
published: the question is no longer "may this go out" but "what do we do about what is out". Nothing here was
changed by this audit; the rows say what to do, in order of exposure, and the two decisions only the owner can make
are at the end and in `docs/HUMAN_TASKS.md`.*

## The classes

- **A -- verbatim bytes of the disc.** Game code or game assets as they are on the disc (or as the game loads them).
  The clearest exposure: this is the thing CONTRIBUTING says may never be added.
- **B -- derived from the disc's code by our tools.** Not the disc's bytes, but a mechanical transformation of them
  (a microprogram recompiled to C++). Same legal character as the shipped `socom2.exe` (decision D2).
- **C -- pictures of the game's output.** Frames our renderer or PCSX2 drew: the game's art, at 320x224 or 640x448,
  used as test references. Fair illustration of our own output is arguable; the art is still Sony's.
- **D -- facts about the binary.** Names, addresses, sizes, hashes, register states: no bytes of the game.
- **E -- circumvention tooling.** Code that decrypts what the disc encrypts. No game bytes; a legal question (D2).

## The rows

| Family | Files | Size | Class | What it is | What to do |
|---|---|---|---|---|---|
| `tests/fixtures/audio/hudui_block.bin`, `hudui_vag.bin` | 2 | 64 KB | **A** | chunks 0 and 1 of the game's HUDUI sound bank, cut from the disc | **Regenerate from the contributor's disc at test time** (`game/disc/RUN/SOUNDS/...` through the existing bank reader), skip cleanly without one (`test_music_state_poll.test_the_real_disc` is the precedent), and keep a synthetic bank built by `socom2_audio_tests.cpp`'s own writers for CI. Then remove the two files from HEAD. |
| `tests/fixtures/audio/m51_am_block.bin` | 1 | 26 KB | **A** | the M51_AM bank block the conductor test (R178) reads | same as above; the conductor test needs the real bank's grain list, so without a disc it skips and the hand-built conductor test stands in |
| `tests/fixtures/vu1/title/*.bin`, `dispatch_0x1b50/*.bin`, `clamp/*.bin` | 29 | 900 KB | **A** (the microcode) + **D** (registers) | VU1 dump images captured from the running game: each holds the microprogram (the game's VU1 code) with the VU memory, registers and packets at the moment of the dump | the goldens of the VU1 replay verify and the vram-diff -- **the project's second-strongest regression bar after the gate**. Regenerating needs a RUN, not just a disc (`PS2X_VU1_DUMP`). Option: the images move to a git-ignored `tests/fixtures-disc/` populated by a documented dump run, `build.sh test` skips the verify when absent, and CI loses the check (the `windows`/`linux` jobs then prove less). **Owner's call**: keep the bar in the public tree, or keep the tree clean of microcode. |
| `ps2xRuntime/src/lib/vu/generated/vu1_d418194495c25213.cpp` | 1 | 650 KB | **B** | one VU1 microprogram recompiled to C++ by `vu1_replay --gen` | the same character as `socom2.exe` itself: recompiled game code. Stays or goes with D2. If it goes, it is generated at build time from the dump image (which is row 3's decision). |
| `tests/fixtures/gate/**` (title 16, transition 5, mission 17) | 38 | ~1 MB | **C** | frames from our renderer at gate resolution, the gate's scoring fixtures | keep: our own output, small, needed by the Python suite on every CI run; the pictures are of the game's menus and HUD -- **the owner decides the line** (Sprint 11 Goal 6 says the same for the story's pictures) |
| `tests/fixtures/movie/*.png` | 16 | ~1 MB | **C** | presents of the intro movie and the title over it (gpu and shadow layers) | as above; the movie frames are the most "art-like" of the class -- first to go if the line is drawn tight |
| `scripts/parity/ref_*.png`, `scripts/parity/refs/*.png` | 64 | 2.8 MB | **C** | screen references the harness matches against (ours and PCSX2's) | as above; these are load-bearing for every online run and cannot be generated without a run |
| `tools_py/tests/fixtures/{lobby,online,replay,mission}/*.png` | ~110 | 2.3 MB | **C** | crops of lobby rows, prompts, HUD bands for the recogniser tests | as above; small crops, mostly text |
| `docs/research/assets/*.png` | 7 | 1.5 MB | **C** | evidence screenshots in the research notes | as above; illustration |
| `scripts/parity/refs/audio_*.pcsx2.json` | 2 | small | **D** | per-window scores of the console's audio: numbers, not samples | keep |
| `recomp/socom2_ghidra.csv`, `socom2.toml`, `extra_functions.txt`, `merge_ranges.txt` | 4 | 600 KB | **D** | function names, addresses, ranges, stub lists: facts about the binary, the recompiler's configuration | keep; nothing of the game's bytes |
| `tools_py/decrypt_apache.py`, `dnas_selfdecrypt.py` | 2 | small | **E** | the ZDB decryptor and the DNAS self-decryptor: how the disc's encrypted overlays become the ELF the recompiler reads | no game bytes; whether circumvention tooling may be published is **D2**, a question for the owner and, if wanted, a lawyer |
| `third_party/ps2recomp/ps2xAnalyzer/include/ps2recomp/sce_symbol_database_data.h` | 1 | 12 MB | **D** (SDK) | upstream PS2Recomp's database of Sony SDK symbol names | upstream's; a Sprint 11 Goal 1 baggage row (remove or keep with upstream) |
| `game/`, `recomp/output/`, `logs/`, `research/` | -- | -- | A | the disc, the generated code, the runs, the reference checkouts | git-ignored and never tracked: `leakcheck ignored` proves it on every CI run |

## What the audit changes about the order

Class A is three families, and only the first two are cheap: the audio fixtures can be regenerated from a disc
with code that mostly exists, and their tests already know how to skip. The VU1 dump images are the expensive one,
because they are a regression bar and not just data. Everything in class C is our own rendering of the game's art;
its exposure is the same in kind for every row, so it is decided once, by the owner, as a line -- not file by file.

**Removing a file from HEAD does not remove it from public history.** Every row above is in every clone made since
2026-09-20. A tree that no longer carries class A but a history that does is a smaller target, not a clean one; the
clean one needs a `git filter-repo` over the paths and a force-push -- the same operation as the address rewrite,
the same owner-approved step, and this time with public clones that will keep the old objects.

## The two decisions (owner)

1. **Class A:** (a) regenerate the audio fixtures from the disc and drop them from HEAD; (b) move the VU1 dump
   images out of the tree and lose the verify in CI, or keep them; and, for either, (c) whether history is rewritten
   to remove them.
2. **Class C, the line:** all of it stays as fair illustration of our own output; or the movie frames go; or every
   picture of the game's art goes and the harness references move to a git-ignored, documented capture.

Until decided, nothing moves; `leakcheck` does not police this class (it is not a secret), and CONTRIBUTING's rule --
nothing new of the disc's -- is enforced by review.
