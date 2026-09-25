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
   **Answered below (Step 2): it is the UI command `DNASAuthenticate`, and the patch is a DNAS bypass.**
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

## Step 2 (2026-09-23): what the stub does

Read-only, from our own r0001 decompilation (`game/analysis/socom2_game.elf.decomp.c`,
`.functions.txt`, `.strings.txt`, `recomp/socom2_ghidra.csv`) and from the Step 1 plaintext stack
(git-ignored, `game/r0004/decoded/`). No build, no game run, no lock. No game bytes are reproduced
here: instruction words are named by their mnemonics, strings by their content.

### 1. `FUN_002cc670` is the UI command **`DNASAuthenticate`**

The function has **no caller anywhere in the image**. Its address appears exactly once: in the
handler slot of a row of the UI action table at `0x003DD4D0`. That table is an array of 16-byte rows
— `{ id, name pointer, handler, second handler }` — running from `0x003DD4D0` to about `0x003DE1C0`,
one row per named command the UI scripts can invoke. The row at `0x003DE120` is id `0xC7`, name
string `DNASAuthenticate` at `0x003EE760`, handler `0x002CC670`. Its neighbours in the table name the
neighbourhood exactly: `DownloadPatch` (`0x002CA340`), `DeletePatch` (`0x002CA330`),
`VerifyPatchLevel` (`0x002766B0`), `RemoveNonSuppressionMaps`, `IsMemcardSaveOK`,
`HardDriveOperation`.

**What the function does.** It is a *poll-until-done tick*, not a test. On the first call (global
`DAT_0044AF40` still null) it allocates and constructs the DNAS authentication state-machine object —
class name string `CSMDNASAuthenticate` at `0x003F33B0`, vtable `PTR_PTR_004065A0` — binds the UI
variable `DNAS_ERROR_CODE` (`0x003F33E0`) into it, starts it through its vtable, and returns **0**
("still working"). On every later call it asks the task whether it has finished (`FUN_003A5C10`); while
it has not, it returns 0 again; when it has, it releases the object through the vtable, clears the
global and returns **1**. The UI script therefore sits on this command, once per frame, until it
answers 1.

**Caller level 1 — the UI command dispatcher `FUN_002745A0`.** Given a UI script node, it takes the
node's command name, resolves it against the `0x003DD4D0` table by string compare, caches the row
index in the node (byte at node+10) so the lookup happens once, then calls the row's handler through
a register-indirect jump. Two details matter:

- the dispatcher loads the handler address **into `$v0`** and jumps with `jalr $v0`;
- it then masks the result with `andi $v0, $v0, 0xff` and returns it as the node's one-byte result.
  Its own "nothing to do / succeeded" paths return the literal 1.

**Caller level 2 — the UI script VM.** `FUN_002745A0` is itself registered, by `FUN_0025BC20` through
the registry helper `FUN_0026A8E0`, as the handler for the node type named **`ui::UI_COMMAND`**
(string at `0x003ED0C0`) on the UI registry object at `0x00414BB0` — the sibling registration in the
same run of code is `ui::UI_APP_COMMAND`. So the full chain is: a `ui::UI_COMMAND` node named
`DNASAuthenticate` in the front-end script → `FUN_002745A0` → `FUN_002CC670`, and the byte that comes
back is what the script branches on.

**What the two words change.** The capsule's first table (Step 1) is two pairs:

| address | written | meaning |
|---|---|---|
| `0x002CC670` | `jr ra` | return from the first instruction |
| `0x002CC674` | `nop` | the delay slot |

**The stub does not set `$v0`.** It leaves whatever was there. At the only call site that is the
handler's own address, because the dispatcher jumps with `jalr $v0` — so the dispatcher's `andi`
yields the low byte of `0x002CC670`, i.e. `0x70`: non-zero, which the script reads as true, but *not*
the game's canonical 1. (Anything that tested the result for equality with 1 rather than for
non-zero would read the patched command as still-running; PSRewired ship this patch and it works on
hardware, so nothing on this path does.)

**In plain words: the patch is a DNAS bypass, and nothing else.** With it, the front-end's DNAS
authentication step reports success on the very first poll. `CSMDNASAuthenticate` is never
constructed, `DNAS.BIN`/libdnas2 never run, `DNAS_ERROR_CODE` is never written, and the
`MP_DNAS_ERROR` / `DNAS Initialization Failure` paths are never reached. That is the whole
game-visible content of `r0004v002.elf`.

### 2. `0x003F5DD8` is a client-side join filter, not the login gate

`0x003F5DD8` holds the bare token `r0001` (distinct from the build banner `SOCOM 2 r0001 …` at
`0x003E17E0`, and from the loader's own copy at `0x001D44F0`). It has **exactly one reader in the
game**: `FUN_002FD6E0`, which is reached from exactly one place, `FUN_002766B0` — the handler of the
sibling UI command **`VerifyPatchLevel`**.

`FUN_002FD6E0` walks the session list (records of `0x3D8` bytes, base `DAT_0044FD58`, count
`DAT_0044FD54`), finds the session named by the caller, and compares that session's advertised
patch-level field (record + `0x338`) against this string; an empty field is accepted. `FUN_002766B0`
raises a `PatchServerURL` message when it does not match. So the string is a **client-side "can I
join this game" filter over the returned game list**. It is never copied into a packet, never sent to
Medius, and never compared at login.

**So how does a patched r0001 pass a server that wants r0004?** *The stubbed function is the gate.*
SCEA's "you must download the update in order to log in" was enforced through **DNAS** — the title
revision lives in the DNAS ticket, not in a string the client types onto the wire — which is why the
entire published patch is a DNAS stub, and why the PCSX2 equivalent is named, in full, "DNAS Bypass
R0001 - r0004". The capsule never rewrites `0x003F5DD8` because rewriting it would achieve nothing:
it is not what any server sees.

Bounds on that claim, stated plainly: this is proven **client-side**. Our image contains no path from
`0x003F5DD8` to the network, and the capsule contains no version rewrite. What PSRewired's own Medius
does with a version field is not visible from here — but a capsule that changes no version string
could not satisfy a server that compared one, so either the server does not compare one or it is
satisfied from the DNAS side. *[inference]*

**The capsule's own use of the same address is a different job.** Its build chooser reads
`0x003F5DD8` as one 32-bit word and compares it against the four characters `r000` — a **prefix**
test, not an equality with `r0001`. It means "the decrypted overlay is resident and it has this
build's data layout", and it is what selects the first patch table. `0x00421998` is the same token in
the other build's layout; that address is past the end of the overlay image we have, so that second
table is for a revision we do not hold (unchanged from Step 1).

### 3. `0x001C5B18` is a fingerprint, not a hook point

`0x001C5B18` lies inside **`FUN_001C59C0`** (`0x001C59C0`–`0x001C5B24`) — the function the runtime
already names "load DNAS.BIN from disc, decrypt APACHE00.ZDB into both overlay slots and run it".
`FUN_001C5B30`, the loader's memory-card update chooser, starts twenty-four bytes after the probed
word — three words past this function's end at `0x001C5B24`.
The word itself is the `lq s0, 0(sp)` one instruction before that function's `jr ra` — an ordinary
register restore in its epilogue. (Capstone decodes it as an MSA instruction; the EE's 128-bit
`lq`/`sq` have to be decoded by hand, as Step 1 warned.)

Nothing is ever written there, so it is **not a hook point**: it is a fingerprint. The address is in
the boot ELF — `SCUS_972.75` occupies everything below `0x001D5000` — so the test means precisely
"the r0001 boot ELF is resident in RAM", i.e. `LoadExecPS2` has happened and the capsule's own image
is gone.

The hook body runs from the kernel syscall vector (`0x800002FC`) on **every syscall**. On a match it
reads the flag at `0x000A0064`, and if it is zero writes zero to it again — which is a no-op, and
nothing in the whole 491-write stack ever sets that flag — then calls the build chooser. On a
mismatch it sets `0x000A0058` and clears `0x000A0060` and `0x000A0064`. Two consequences:

1. **The two probes are a pair.** `0x001C5B18` says the boot ELF is up; the `r000` probe at
   `0x003F5DD8` says the *overlay* is decrypted and is this layout. Only both together let the
   applier run, which is what keeps the write from landing before the overlay that would overwrite it.
2. **The patch is re-applied continuously**, at every syscall, for as long as the fingerprint holds.
   An overlay reload that restores the original two instructions is undone again at the next syscall.
   The runtime equivalent is therefore a *permanent* function replacement, not a one-shot memory poke.

### 4. Our runtime already does this — proposal

`third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` already carries the whole
game-visible effect of the capsule, and has since before r0004 was a topic:

- `ps2_stubs::socom2_DnasTickDone` (≈line 265) sets `$v0 = 1` and returns to `$ra`;
- `applySocom2` (line 2135) installs it unconditionally:
  `runtime.replaceFunction(socom2_addresses::current().dnasCheck, ps2_stubs::socom2_DnasTickDone);`
- `socom2_addresses::Table::dnasCheck` is `0x002CC670` (`runtime/socom2_addresses.h`), already a
  per-revision column, so an r0004 build needs one more number and no new code;
- the replacement is permanent for the process, which is exactly what the capsule achieves by
  re-writing on every syscall;
- `socom2_LoadGameCodeFromMemcard` (`FUN_001C5B30`, ≈line 546) answers "no update present", which is
  what the capsule itself observes — it finds no `mc0:UPDATE.DAT` and falls back to its embedded
  stack. Task 18's comment change at that line is correct as written.

**Ours is the stricter of the two.** The capsule leaves `$v0` holding the handler address (`0x70`
after the dispatcher's mask); we return the canonical 1. Any consumer that is satisfied by the
capsule is satisfied by us, and one that wanted an exact 1 would be satisfied only by us.

So the change to propose is **not a new override**. It is to say so in the code, put the one knob on
it that lets a run prove which override is carrying the login, and leave the behaviour alone:

> **Proposal.** Replace the bare line 2127 with an `installChatBound`-shaped
> `installDnasBypass(PS2Runtime &runtime)` beside the other installers: it reads
> `socom2_addresses::current().dnasCheck`, returns with a log line if `runtime.hasFunction` is false,
> honours a default-on knob `ps2x::knobOn("PS2X_SOCOM2_DNAS_BYPASS", true)` (0 = let the game's own
> DNAS tick run, for the one test that proves the bypass is what gets us past authentication), keeps
> the original in a `g_dnasTickOriginal` for that test, then
> `runtime.replaceFunction(addr, ps2_stubs::socom2_DnasTickDone)` and logs "DNAS bypass armed (the
> r0004 capsule's only game patch)". `socom2_DnasTickDone` itself does not change.

**It must not be gated on the launcher's GAME VERSION = r0004 choice**, for three reasons:

1. The bypass is needed by **r0001 too**. Every online round this project has ever run depended on it;
   gating it on r0004 would break them all.
2. The capsule does not gate on the revision either. Its trigger is "the r0001 image is resident" —
   it patches r0001, which is the only thing it ever patches.
3. The capsule's patch **is** the difference between "an r0001 disc" and "what PSRewired call an
   r0004 client". A runtime that already applies it is already on the far side of that line; making it
   conditional would be inventing a distinction the capsule does not make.

The GAME VERSION selector's job stays what Task 18 gives it — the preset's `requiresRevision`
warning — and it does not reach this override.

**What Step 3 therefore owes.** Very little on this function: the image work is two instructions the
runtime already supersedes. What the r0004 build genuinely needs is the *rest* of the delta, and this
capsule does not carry it (Step 1's open question, unchanged).

### 5. Two things found on the way

1. **`socom2_addresses.h`'s `versionString` points at the wrong string.** `kR0001.versionString` is
   `0x003E5C60` and the comment says it holds `SOCOM 2 r0001 17:22:21 Oct 11 2003`. It does not:
   `0x003E5C60` holds the boot path `cdrom0:\SCUS_972.75;1`. The banner is at `0x003E17E0`.
   `applySocom2` (≈line 2067) reads `0x003E5C60`, hands it to `selectFromVersionString`, whose
   `revisionOf()` finds no `r`+digits, and the table logs "no column for revision …" and keeps r0001.
   Right answer today, by luck; wrong the moment there is a second column. Two candidate fixes:
   `0x003E17E0` (the banner the comment describes) or `0x003F5DD8` (the bare patch-level token — which
   is what the capsule itself probes, and a shorter, more stable read). Worth a task.
2. **The DNAS comment's explanation of `$v0` is wrong.** ≈line 263 says the published pnach works
   "with v0 still holding the previous call's 1". The real mechanism is the dispatcher's `jalr $v0`:
   `$v0` holds `0x002CC670`, and the `andi` makes the node result `0x70`. Harmless — the effect is the
   same non-zero — but the comment should say what actually happens.
