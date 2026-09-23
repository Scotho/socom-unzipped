# 43. The r0004 capsule decoded: what PSRewired's `r0004v002.elf` actually writes

Date: 2026-09-23. Sprint 11, Task 19 Step 1, on ruling R248 ("the r0004 patch is PSRewired's resident capsule, and
the build applies it, not a package"). Read-only on the capsule: it stays a git-ignored copy in `game/r0004/`, and
neither it nor any decoded byte of it is in this repository. Sources: the capsule itself; the Based_Skid/Harry62
r0005 tooling in `research/r0005-patch/` (its `README.txt`, `MIPs_source/059/r0005 crypto.cds`,
`C_Source/059/update.dat`); `recomp/socom2_ghidra.csv`. Tool written for it: `tools_py/r0004/capsule.py`, tested on
synthetic stacks in `tools_py/tests/test_r0004_capsule.py`.

## Summary (ten lines)

1. The capsule is a ps2-packer ELF. One `PT_LOAD`; its first `0x18` bytes are the packer's stub header (entry,
   flag, memsz, a spare, load address, compressed length) and the rest is a zlib stream that inflates to a raw
   R5900 image, **125,838 bytes loaded at `0x00100000`, entry `0x001000E0`**. Not an ELF inside — a flat image.
2. That image carries exactly **one** encrypted code stack, and the scan proves it: over the whole image only one
   window decrypts to plausible store addresses.
3. The cipher is a **32-bit-word XOR against an eight-word key that cycles once per word**, not per pair. The key
   is 32 bytes of the capsule's own image (at image address `0x0011C410`, loaded by the apply routine at
   `0x00100FB0`) and it is **the same key the r0005 `README.txt` publishes for its "Patch Compiler"** — the
   tooling is shared. **No copy of it is in this repository**: the tool locates it in the image at run time by
   asking which 32-byte window decrypts the stack's first pairs to reachable store addresses, excluding the
   ciphertext itself — a window of the ciphertext one key-period in "decrypts" the stack to the XOR of two of its
   own addresses, which looks entirely plausible, and that is the one trap in the search.
4. The plaintext is `(address, value)` pairs, each applied as one 32-bit store. The stack ends at the first
   **ciphertext** word of zero in an address slot; because the key cycles, that word does not decrypt to zero,
   so the terminator must be tested before the XOR. Everything is one type: a word store. No cheat-type nibbles.
5. Header (reversed from the apply routine at `0x00100F68`, whose caller at `0x001015C4` passes it the header
   pointer `0x0011C4D0`): `char version[8]` NUL-padded, `u32 length` (ciphertext bytes, a multiple of 8), two
   reserved zero words, then the ciphertext at `+0x14`. This capsule's version field reads **`0000001`** and its
   length field reads **3,928 bytes = 491 pairs**, which is exactly where the terminator lands.
6. **491 writes. All 491 are resident.** Zero code patches and zero data constants into game memory — the stack
   does not touch the game at all. It pastes the patch's own code and variables and then arms the kernel hook.
7. Three runs: `80031000-8003127C` (160 words — the resident kernel function), `000A0000-000A0524` (330 words —
   a zeroed user-memory variable block with two fields set and a second version string), and one word at
   `800002FC` — the kernel syscall vector, turned into a jump to `80031000`. Same shape as r0005's, new addresses.
8. The game patch is **indirect**: the resident function carries two NUL-terminated `(address, value)` tables of
   its own (at `80031250` and `80031268`, two entries each) and walks one of them at runtime. It chooses by
   reading a version string out of the loaded game and comparing it to `"r000"` — `0x003F5DD8` selects the first
   table, `0x00421998` the second. **Our r0001 image has `"r0001"` at `0x003F5DD8`**, so the first table is ours.
   The two tables are not a guess from the write list: the chooser **loads both table addresses itself**, with
   `lui`/`ori` pairs at `0x800311C8-0x800311CC` and `0x800311E0-0x800311E4`. The scanner in the tool found the
   same two, which is how they were noticed, but the disassembly is what proves them.
9. Both tables do the same thing to a different build: they overwrite the first two instructions of one game
   function with an immediate return. For r0001 that function is `0x002CC670` — a function start that
   `recomp/socom2_ghidra.csv` already names (`FUN_002cc670`, 324 bytes). **Four bytes of patch, two instructions.**
10. The hook fires only when the game is up: it reads `0x001C5B18` and compares it against the instruction word
    that really is there in `SCUS_972.75`. That address is **inside `FUN_001c59c0` (`0x001C59C0-0x001C5B24`)**,
    twenty-four bytes before `FUN_001c5b30`, the loader's package chooser — Step 2 must open the former.

## The two routes, and which one worked

**Route (a), the r0005 scheme, worked, first try, and no emulation was needed.** The path was: read
`r0005 crypto.cds`'s `kernal__data` loop (it documents the shape — a data stack, a key stack, an 8-byte output
buffer, `sw value, (address)`); notice that `README.txt` publishes a *different*, 32-byte key for the "Patch
Compiler" that makes `update.dat`; notice that the key as published is byte-swapped per word relative to how it
lies in memory; validate on `update.dat` before touching r0004.

That validation is the strongest evidence in this note, because r0005's plaintext is *documented*:
`research/r0005-patch/C_Source/059/update.dat` decodes to **3,065 writes**, and they land exactly where the r0005
sources say they should — `8007A000…` (the `.cds` file's literal `address $8007A000`), `800002FC` (its literal
`address $800002FC`), `000D0000…` ("Functions start @ 0x000D0000"), `000F76xx` (the README's variable table) —
plus 29 single-word patches into game text. A wrong key cannot produce four independently documented addresses.

**Route (b), Unicorn, was not needed** and was not run. The capsule's own apply routine was read statically
instead (`0x00100F68`, ~90 instructions): it copies the 32 key bytes to its stack frame, walks the ciphertext a
word at a time cycling eight key words, and stores each decrypted pair. Reading it is what pinned the header
layout and the ciphertext-zero terminator; the decrypt itself was already proven by (a).

## What the counts mean for Task 19's later steps

- **Step 2's classifier has nothing to classify.** Every one of the 491 writes is resident. The code patch this
  build has to reproduce is the pair of instructions in the resident table, applied at runtime, not in the stack.
- **Step 3's image** therefore changes two instructions in one overlay-resident function, and needs the resident
  function itself (160 words at `80031000`, plus its 330-word variable block) as a recompiled unit — or, more
  likely, as a native reimplementation, since what it does is a kernel-vector hook that has no meaning here.
- **Step 4's rulings get easier.** There is **no checksum scanner** in this capsule (r0005's kernel had two, with
  the freeze-on-mismatch loop; this one has none), **no patch-game password key** and **no code stack of features**.
  The r0005 ruling text about disabling scanners does not apply to r0004v002 as shipped.

## What is still unknown

1. **Whether this is the whole r0004 patch.** It is not, necessarily. The capsule is the *auto-updating* ELF: it
   looks for `mc0:UPDATE.DAT` first, loads it into the same header struct, and only falls back to the embedded
   stack. The community's live r0004 feature set may be an `UPDATE.DAT` nobody has handed us. The embedded stack
   is what a player who has only the capsule gets, which is the case that matters for our build — but the
   difference must be stated in the README and to the owner before "r0004" is claimed as a name.
2. **What `FUN_002cc670` is.** Not yet read. The whole patch is "make this function return immediately", so the
   name of that function *is* the patch. Step 2's Ghidra pass answers it.
3. **The second table's build.** `0x00421998` holds the version string in some other revision (not r0001 — that
   address is past the overlay image we have). Which revision, and whether we care, is open.
4. **The two reserved header words** are zero here and unread by the apply routine. They may be a checksum or a
   second length in the `UPDATE.DAT` path; only a real `UPDATE.DAT` from this generation of the tool would say.
5. **The version fields disagree**: the header says `0000001` and the block written to user memory says `0000011`.
   Neither is the string the splash screen prints. What numbers the tool actually stamps is not established.
6. **The classifier's two game-side windows are provisional and were never exercised.** All 491 writes here are
   resident, so `code_patch` and `data` have never been tested against a real write. The module's default bounds
   (`0x00100000` to `0x00500000` for text) are round numbers, and `0x00500000` cuts the r0001 image in half — its
   loaded segments run to `0x00686F80`. Steps 2 and 3 must pass `--elf <game ELF>`, which derives the windows from
   the program headers (text becomes `00100000-001D5000`, `001E7000-004B5380`, `004C5380-00686F80`); without it
   the tool now prints a warning whenever a write lands in a game-side class.
7. **`find_pair_tables` is pattern-matching, not proof.** Eight-byte alignment and instruction-aligned targets are
   the only things separating a real table from a run of constants; false positives and false negatives are both
   possible. On this capsule the disassembly confirms both tables (item 8), but a future capsule's tables must be
   confirmed the same way, never taken from the scanner alone.

## Where the tool lives

`tools_py/r0004/capsule.py` — `unpack()`, `locate_stack()`, `locate_key()`, `decrypt_stack()`, `classify()`,
`game_windows()`, `find_pair_tables()`, and a `main` that writes `stack.txt` and `summary.txt`. It reads the
capsule from wherever it is pointed and writes under `game/` (git-ignored); it embeds no game data and **no key**,
and its suite (`python -m unittest tools_py.tests.test_r0004_capsule`, 35 cases) runs on stacks the test encrypts
itself, plus one case that skips unless the capsule is on the machine.

The run that produced the numbers above, and the r0005 cross-check (`update.dat` carries no key of its own, so
`--key-image` points the search at the capsule):

```
python -m tools_py.r0004.capsule <dir>/r0004v002.elf --out <dir>/decoded --elf game/overlays/socom2_game.elf
python -m tools_py.r0004.capsule research/r0005-patch/C_Source/059/update.dat --out <scratch>        --key-image <dir>/r0004v002.elf
```

The plan names `game/r0004/stack.txt`; `main` defaults to `<capsule dir>/decoded/stack.txt`, so pass
`--out game/r0004` for the plan's exact path.
