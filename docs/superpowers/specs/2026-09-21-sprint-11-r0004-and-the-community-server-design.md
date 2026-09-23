# Sprint 11 — "r0004 and the community server" (design, drafted)

Requested by the owner on 2026-09-21: *"the r0004 patch — we NEED to apply it to play on existing hosted community
servers in the future, how it exists, how it is applied, and what it contains. More importantly, how WE could apply it
to project unzipped. Should it be a full recompile? Can it be included in the memory card like the original? How it is
applied in the launcher"* — and, from a PSRewired admin: *"the chat packets can lead to a overflow is the main one. the
game only allows for 32 bytes for chat but the message packet is actually 64 … Does the r0004 patch fix it?"*

**Supersedes Sprint 8 Goal 10** (`2026-09-18-sprint-8-linux-and-finish-design.md`), which the owner deferred to a
wishlist on 2026-09-19. That design was written from an investigation; this one is written from measurements taken on
2026-09-21 against the tree, so the costs below are counted rather than estimated. **Drafted, not opened**; the plan is
written when the sprint opens.

Markers: **[A]** autonomous; **[O]** the owner's; **[B: x]** blocked on x. Findings carry **[verified]** (evidence in
this repository or a primary source), **[inference]** (reasoned, unproven) and **[unknown]**.

## Why this is two jobs, not one

The owner asked one question and it splits cleanly. **The security fix is ours, is not blocked on anything, and does
not need r0004.** The r0004 build is blocked on a 1.5 MB file only the owner's memory card can supply. They have been
bundled together because the admin's report arrived attached to the community server; they should be scheduled apart.

Goal A runs now. Goals B–D are the parts of the r0004 job that can be built *and proven* with no r0004 package in
hand. Goals E–G wait on the package, on PSRewired, or on both.

---

## 1. What was established (2026-09-21)

### 1.1 r0004 is a whole code package, not a delta — **[verified]**

> **Corrected 2026-09-23.** The patch in hand is **PSRewired's capsule** `r0004v002.elf` (https://psrewired.com/downloads/r0004v002.elf, 67,267 bytes, sha256 `ad0ed7511b2c2d54…`; a git-ignored copy at `game/r0004/`). It is not the memory-card package: a MIPS ELF packed with ps2-packer (one LOAD at `0x01cf3400`, zlib payload at +0x18 → 125,838 bytes that load at `0x00100000`, entry `0x001000e0`), the Based_Skid/Harry62 tooling whose r0005 source is in `research/r0005-patch/` — the same `PasteASM`/`systemHook` shape. Its strings say what it does: loads SIO2MAN/CDVDMAN/PADMAN/MCMAN/MCSERV, hooks a kernel syscall through the vector table, looks for `mc0:UPDATE.DAT` ("Checking mc0 for patch… no update found"), shows "SOCOM II: Server — Patch: r0004", then `LoadExecPS2("cdrom0:\\SCUS_972.75;1")` — it boots the r0001 disc and patches it in memory. The patch body is an encrypted code stack (the high-entropy block at `0x0011c800`; r0005's `update.dat` has the same shape: a version string, then XOR-keyed address/value pairs) applied by the hook once the game is loaded; only 77 constant stores are in the ELF's own code, all its own globals and the GIF/DMAC registers of its splash screen. So for *this* project r0004 is a **delta after all** — the community's re-creation of the r0004 behaviour (and the login gate's version) laid over r0001 at runtime. Goal E's "the r0004 build itself" becomes: extract the stack's plaintext writes, apply the static ones to the r0001 image, and re-express the hooks in the runtime — the plan's Task 19. Whether the console's own r0004 card package still exists anywhere is now irrelevant to the build.

The disc's `SCUS_972.75` is only a loader (~350 KB of real code: MSL crt0, the libcdvd/libmc/libpad/libdma/libgraph/
libipu/libdbc/libusbkb RPC clients, zlib 1.1.4, `main()` at 0x1c4cc0). The game is `RUN/RAW/APACHE00.ZDB`: two
DNAS-encrypted, zlib-deflated Metrowerks `MWo3` overlays, `ftscore` at 0x1e7000 and `zsealetc` at 0x4c5380
(`research/03`, `research/05`). r0004 replaces that container wholesale — same two overlays, different code, ~1.5 MB.

There is **no version field anywhere**: the revision *is* the loaded code. The recovered build id
`SOCOM 2 r0001 17:22:21 Oct 11 2003` sits at 0x3e17e0, inside `ftscore`, so even the stamp moves with the package.
Statics move throughout (`ftscore` statics are `+0x2C9C0` on four addresses verified against Socom2StreamData,
`research/19` F5); the DNAS check relocates from 0x2CC670 to 0x2CF330 (`research/02`, the PS Rewired pnach).

### 1.2 How it exists and how it is applied — **[verified]**

On the memory card, inside the game's save: `BASCUS-97275SOCOMII/APACHE00.ZDB`. At boot `main()` calls
`FUN_001c5b30(port)` to search the card slots for that file **first**, falling back to the disc's ZDB only when it is
absent; then the same DNAS decrypt → inflate → jump to 0x4c53c0. The "patch" is applied by the loader choosing a
different blob. SCEA's own announcement (10 March 2004, archived at socomlan.com) matches: the update is folded into
the SOCOM II save file, and a card with no save needs 3,000 KB free.

Delivery was HTTP from `updates.pdonline.scea.com/_socom2-prod/currentpatch/APACHE00.ZDB` (the `sceHTTP` client is in
`zsealetc`). PSRewired's DNS does not serve that name; they serve the package themselves. Their flow: boot r0001 with
the DNAS bypass (`r0004v002.elf` on hardware, `0F6FC6CF.pnach` "DNAS Bypass R0001 - r0004" on PCSX2), log in, accept
the prompt, write to card, reboot — the version string then reads r0004.

### 1.3 Why the community server needs it: a login gate, not security — **[verified]**

SCEA, same announcement: ***"You must download the update in order to log in to SOCOM II."*** PSRewired reproduces the
retail login flow, so the requirement is Sony's, and it is about code-revision parity between peers (an r0001 client
and an r0004 client run different code with different layouts), not about protecting anybody. The owner's assumption
that "r0004 is all that's required to play there, so it must be the security fix" does not follow.

### 1.4 The chat vulnerability: what is known, and what is not

**The report.** A PSRewired moderator, 2026-09-20, recorded in `SECURITY.md`: the chat packet overflows a 32-byte
buffer with 64 bytes; the community console servers patched it years ago; this project has not.

**What was verified in our own r0001 image** (`game/analysis/socom2_game.elf.decomp.c`, 2026-09-21) — **[verified]**:

1. **The wire field is 64 bytes end to end.** Every chat struct copies the message with `memcpy(dst, src, 0x40)`:
   `FUN_002f4860` (the body behind `SendChatText`/`SendMediusChat`), `FUN_002f4ba0`, `FUN_002f4d60`, `FUN_002f4df0`.
   The chat-log record is a fixed 0x70: `[?21][msgid 19][u32][u32][message 64]`, pushed by the 0x70-stride deque
   `FUN_002f5290`.
2. **The 32-vs-64 asymmetry is a *policy* limit, not a code bound.** The typing cap lives in the disc's UI data as a
   `GetTextInput UiVar=CHATTEXT SkbName=PlayerChatSkb Purpose=_361_EnterChatMessage_MSG MaxChars=… MaxBytes=…` record
   (ISO ≈ 0x75c2_xxxx; the same mechanism as the login keyboard's 14-char/31-byte cap, `research/38`). The *code*
   sends and receives 64 regardless. A modified client fills it — exactly the shape the admin describes.
3. **The receive handler is `FUN_002f4ef0`, and it is unbounded:**
   `sprintf(stack[1024], "%s: %s", packet+0x1c /* originator name */, packet+0x40 /* message */)`. Both are
   fixed-width packet fields with no guaranteed NUL. `packet+0x3c` is the chat type the handler switches on, which
   fixes the name field at 32 bytes and the message at 64.
4. **Unterminated names propagate.** The display record (`FUN_002a4050`, stride 0xa1 = `[type 1][text 128][name 32]`)
   NUL-terminates the text but stores the name with `strncpy(dst, src, 0x20)`, which does not terminate at exactly 32
   bytes. `FUN_002a3e60` re-copies it the same way into a caller frame, and it is then handed to the ignore-list
   lookup (`FUN_0029e590`) and the renderer as a C string.

**Not established** — **[unknown]**: no 32-byte *destination* for chat text exists in the Medius lobby path. Either the
admin means the in-match DME/peer path (not yet located), or their "32" is the typing cap. Ask them; do not guess.

**A sourcing trap, recorded so nobody falls in it twice.** A web search for the vulnerability returns a confident
sentence about "32 bytes / 64 bytes / arbitrary code execution on every client in the room". That is an **earlier draft
of our own PR #3 body** being quoted back. It is not independent confirmation. The only primary source is the admin.

**Does r0004 fix it? Unknown, and not to be assumed** — **[inference]**, four reasons:

- The reason r0004 is required is §1.3, which says nothing about security.
- The published notes *do* touch chat, twice: *"Colored Chat Text: Players can no longer change the color of the chat
  text, bold text or insert symbols into the chat text"* and *"Chat Lock Out: Players will no longer be able to
  manipulate the briefing room chat text to prevent other players from writing text messages."* Same family — chat
  field manipulation — so the path was demonstrably touched. Both are content sanitisation, not memory safety, and
  SCEA explicitly withheld the rest "to further prevent potential player exploits". A second update (9 September 2004)
  fixed more, also unlisted.
- The admin's own phrasing is server-side ("the community servers patched it"). If r0004 had closed it in the client,
  the servers would not have needed to.
- A community r0005 patch exists (Zero1UP / harry6two: ELF injector, kernel and user hooks). r0004 was not the end.

**And it would not help us even if it did.** We would have to recompile r0004 to inherit the fix; r0001 is what every
player runs and would stay exposed; and a 2004 console-side fix was written for a world where the worst case is a hung
PS2, not native code execution under the player's Windows account.

### 1.5 What a second recompilation actually costs, measured — **[verified]**

`SCUS_972.75` is on the disc and stays there; r0004 replaces only `APACHE00.ZDB`. So every address in the loader
region (0x100000–0x1d5600) is unchanged **by construction**. Splitting every address-keyed thing in the tree on that
boundary (script kept at `tools_py/` when this goal opens):

| Address-keyed surface | Total | Loader (free) | Overlays (moves) |
|---|---|---|---|
| `recomp/socom2.toml` stub bindings (sce\*, libc, SIF, cdvd, mc, pad, usbkb) | 656 | **645** | 11 |
| `recomp/socom2.toml` instruction patches (incl. both crt0 bss-clear fixes) | 46 | **27** | 19 |
| Jump-table sites, hand-found | 31 | **7** | 24 |
| Runtime `replaceFunction`/`hasFunction`/`lookupFunction` (distinct) | 34 | **8** | 26 |

**~80 overlay items to re-resolve. Not 656.** Beside them:

- **Carries untouched:** all ~84k lines of `ps2xRuntime` (EE scheduler, DMAC and the MFIFO ring, the GS paths,
  VU0/VU1, the IOP host, 989snd, pads, memory cards, `socom2_hostnet` and the Medius redirect, audio), the launcher,
  the suites, CI, packaging, the Linux build, `ps2_recomp`/`ps2_analyzer`, the toolchain, and the whole ISO asset path
  — r0004 changes code, not data. The DNAS harness carries too: same container, same layering, same keys, and the
  console-ID hash is not verified against the content (`research/05`).
- **Regenerated by machine:** Ghidra headless re-analysis → `ExportPS2Functions.java` → `fix_ghidra_csv.py` →
  `find_imm_targets.py` gives the 14,880-row function map and the 3,087 `extra_functions.txt` entries; `ps2_recomp`
  then emits the 14,882 generated `.cpp` files; `[mmio]` (233 annotations) and the ~40 "potential self-modifying code"
  patches are analyzer output. Hours of CPU, not days of work.
- **VU1 degrades gracefully, already.** One generated program and one native program, both keyed by FNV-1a hash of the
  16 KB VU1 code memory. `vu1_native_programs.cpp:10` already says another revision hashes to something else, matches
  nothing, and runs on the interpreter with a one-time warning. Cost is frame rate, not correctness; `vu1_replay --gen`
  regenerates.

**Calibration.** r0001 went from nothing to an online round in 19 days and 1,015 commits (first commit 2026-09-02).
Nearly all of that was the runtime, which r0004 inherits free. **A sprint, not a project — conditional on the package.**

---

## 2. Goals

### Goal A — the chat receive path, bounded **[A]** — not blocked, and first

Not gated on r0004, on PSRewired, or on the owner. It is the only goal here that should run on the day the sprint opens.

1. **Bound and terminate at the boundary.** Every field of a received chat message is treated as fixed-width and
   never as a C string until it has been copied into a local of declared size and NUL-terminated: `FUN_002f4ef0`
   (both `%s` sources), `FUN_002a4050` (the 32-byte name `strncpy`), `FUN_002a3e60` (the same copy, into a caller
   frame), and the four 0x40 message copies. Replace the `sprintf` with a bounded format. This is a runtime-override
   job in `game_overrides_socom2.cpp`, not a recompilation, so **it lands in r0001 and any future r0004 for free**.
2. **Clamp at our own server too, as defence in depth.** The project's Horizon box truncates and NUL-terminates chat
   fields, so a hostile *client* cannot reach other players in a project-hosted room whatever build they run. Same
   thing the community console servers did.
3. **Ask the admin precisely**, through the private channel `SECURITY.md` defines: which struct and field, which
   revision they verified, whether r0004 closes it client-side, and what their server-side clamp actually was. Record
   the answer privately; `SECURITY.md`'s "details are deliberately not written up here" rule holds.
4. **Then narrow the README.** The current blanket "do not play online" becomes an honest statement about the project
   server once 1 and 2 are in and 3 has not contradicted them.

- **Bar:** a test that feeds the receive path a message with all fields filled to their declared width and no NUL, and
  asserts no read or write leaves the declared buffers; the suite green; a control round on the hosted server unchanged.
- **Stop rule:** if the fix changes what a legitimate chat line looks like on screen, stop and report — a truncation
  that silently eats normal messages is worse than the warning banner.
- **[O] decision D3** before step 1 lands: the fix is a public commit and its message is a disclosure. Coordinate the
  wording with the admin, or land it described only as hardening?

### Goal B — a revision-parameterised pipeline **[A]** — provable with no r0004 package

`scripts/build_revision.sh <rev> <APACHE00.ZDB>` runs `decrypt_apache.py`, `make_overlay_elf.py` and `ps2_recomp` into
`recomp/output_<rev>/` and builds `dist/socom2_<rev>.exe` beside `socom2_game_<rev>.elf`, leaving today's r0001 paths
exactly as they are. Every path in `build.sh` is hard-wired to r0001 today; this is the untangling.

- **Bar:** run on the **disc's own** package as `r0001check`: the decrypted overlays are byte-identical to
  `game/overlays/*.bin`, the ELF byte-identical to `dist/socom2_game.elf`, and the generated tree identical to
  `recomp/output/`. Anything less and the pipeline is not trustworthy on a package we cannot check.

### Goal C — the per-revision address table and the fingerprint matcher **[A]** — provable with no r0004 package

1. `socom2_addresses.h`: a struct of named addresses, one instance per revision, chosen at start from the ELF's
   identity. The 22 hex literals in `game_overrides_socom2.cpp`, the 11 overlay stub bindings, the 24 overlay
   jump-table sites and the 19 overlay instruction patches move behind it. Loader addresses stay literal and say why.
2. A fingerprint matcher between two images: normalised instruction hashes, call-graph neighbours, and the `+0x2C9C0`
   statics rule as a seed. It resolves every named address and lists each one it cannot.

- **Bar:** 100% resolution on r0001 against itself (identity) **and** against a synthetically relocated copy. Both
  run in CI, so the matcher stays honest without the real image.
- **Stop rule (for Goal E, stated here):** if the matcher leaves more than a tenth of the named addresses unresolved
  on the real r0004 image, stop and list them. That is a hand job with its own sprint.

### Goal D — the launcher's revision plumbing **[A]**

`main.cpp:115` hashes `SCUS_972.75` against a pinned r0001 digest and exits 67 otherwise (R130). That becomes a
revision-aware check. "Game version" appears on the PLAY and ONLINE pages: r0001 (your disc) or r0004 (community
update), the second enabled only when `socom2_r0004.exe` exists, with the reason when it does not. The community
preset carries 67.222.156.250 and the revision each preset requires; choosing the community preset with r0001 selected
warns, and the reverse. `socom2_LoadGameCodeFromMemcard` keeps answering "no update present" in **both** builds — the
package is compiled in, never hot-loaded, and that override should grow a comment saying so.

- **Bar:** the option and both warnings appear in `--screenshot` mode at both sizes, with tests.

### Goal E — the r0004 build itself **[B: the owner's memory card]**

The pipeline on the owner's package; the matcher filling the table; the unresolved overrides fixed by hand; then the
gate's three stages on the r0004 exe and one control round on **our own** Horizon (r0004 against r0004).

- **Bar:** `socom2_r0004.exe` reaches the main menu showing r0004, gate 3/3, one r0004 control round.
- **Stop rule:** if the r0004 package's DNAS layering does not decrypt with the disc's keys, stop at the pipeline and
  file what differs.

### Goal F — connecting to PSRewired **[B: the owner AND PSRewired]**

Their rules are not public. A non-console client on a community server is theirs to allow. The owner asks; the first
login is the owner's, hands-on, with their account. **Nothing connects to their server before that answer** — and,
added 2026-09-21, not before Goal A has landed either: pointing an unfixed client at a room full of strangers is the
exact situation the admin warned about.

### Goal G — the three HDD maps (speculative) **[B: Goal E, and an unknown]**

r0004's headline feature is three extra online maps that require the PS2 hard disk. The runtime has **no** DEV9/ATA/HDD
support — grep confirms nothing in `ps2xRuntime` touches it. But the interesting half is already done for us.

**What is already in r0001 — [verified], and this is the find.**

- The disc carries Sony's whole HDD stack: `game/disc/RUN/IRX/HDD/ATAD.IRX` (12,085 B), `HDD.IRX` (30,117 B),
  `PFS.IRX` (49,417 B), all dated 2003-10-09. The engine names all three at `ftscore` 0x3f7f60 / 0x3f7f80 / 0x3f7fa0,
  in the same table as `RUN\IRX\DEV9.IRX` (0x3f7ec0) — which the PCSX2 reference boot already loads at t≈12.5 s.
- The device strings are present: `hdd0:` (0x3f7ff8, 0x3fbb30), `pfs0:` (0x3fbb28), `pfs0:RUN` (0x3fbb10),
  `pfs0:/RUN` (0x3fbb70), `pfs0:/` (0x3fbc08), `RUN/ICONS/HDD/` (0x3fbba8), `HDD_ERROR` (0x3e2258, 0x3eed48).
- **The EE-side client is fileXio and it lives in the loader**: open 0x1a7cc0, read 0x1a8300, mkdir 0x1a8f40,
  dopen 0x1a94c0, dread 0x1a96f0, close/dclose 0x1a9588, format 0x1a9110, mount 0x1a9fd0, umount 0x1aa240,
  devctl 0x1aa498, bind 0x1a73f8. Loader addresses do not move between revisions — **this part is already recompiled
  and is r0004-proof**.
- The probe: `fileXioDevctl("hdd0:", 0x4807, …)` caches into `DAT_0049e2dc`, and the caller returns
  `DAT_0049e2dc == 0`. Everything downstream keys off that one word.
- The install: `FUN_0039d050` (ftscore) builds a partition name from eight complemented constants at 0x3e0620.., formats
  a PFS partition (`FUN_001a9110`), mounts `pfs0:`, `mkdir("pfs0:/RUN", 0x1ff)`, and on failure sets `DAT_0049e2e0 = 1`
  and raises the `0x4803` devctl. `FUN_0039d020` unmounts. A directory walk over `pfs0:RUN` reads install records.

**So the mechanism already exists in the revision we have already recompiled.** r0004 adds content that uses it.

**Two ways to provide it.**

- **(A) HLE at the fileXio RPC boundary — recommended.** Serve the protocol from a host folder, exactly as the
  simulated memory cards serve `mc0:`. No ATA, no APA, no on-disk PFS format, no DEV9 register emulation, and no IOP
  that executes IRX code (the project HLEs IOP modules; it does not run them). What it needs: the SIF RPC server for
  fileXio (read the SID off the bind with a trace — the loader's `FUN_001a73f8` does it); mount/umount, open/close/
  read/write/lseek, remove/mkdir/rmdir, dopen/dread/dclose, getstat, format, sync, devctl; `devctl("hdd0:", 0x4807)`
  answering 0; a partition listing that satisfies the dread loop; and a git-ignored `hdd/` directory beside the exe
  with a `PS2X_HDD_DIR` knob and a launcher switch. **[inference]** the effort is comparable to the simulated memory
  cards (Sprint 8 Goal 11), which is a known quantity.
- **(B) LLE.** Emulate DEV9/SPEED ATA registers and run the real ATAD/HDD/PFS IRXs against a raw image (the community
  `SOCOM II HDD.raw`). Needs an IOP that executes IRX code, which the project does not have and does not want.
  **Rejected** unless (A) proves impossible.

**The unknown that actually decides this — [unknown].** Where the three maps' *data* comes from is not established:

1. *Installed from the disc* — the HDD is a load-time cache, and r0004 enables three maps whose data always shipped.
   Then (A) is sufficient and no Sony content we lack is involved. `pfs0:RUN` / `pfs0:/RUN` / `RUN/ICONS/HDD/` read
   like a disc-to-HDD install, so this is not ruled out.
2. *Downloaded into `pfs0:/RUN`* — the data is Sony content we cannot ship, the retail source is dead, and only
   PSRewired could serve it: a permission question stacked on a technical one. **[inference]** more likely, given the
   update's own delivery model.

**The experiment that settles it, and needs no r0004 — [A], cheap, do it first.** Implement (A) against the **r0001**
build, point it at an empty `hdd/`, and watch. r0001 carries the whole install path; whatever it writes, and whatever
it asks the server for afterwards, answers the question. The HLE is needed either way, so nothing is wasted.

A second unknown only the r0004 image can answer: whether r0004 gates its extra maps on `DAT_0049e2dc == 0` alone, or
also on a downloaded manifest.

**Verdict: schedule the maps last and let nothing block on them.** Server compatibility does not need them — an r0004
client with no HDD is still an r0004 client, and the game already has an `HDD_ERROR` path for exactly that. The
published r0004 render-fix codes and PSRewired's own `/rfix on` chat command suggest the extra maps were rough on
console too.

- **Bar (if it runs):** the r0001 build with `hdd/` present passes the probe, formats and mounts a simulated `pfs0:`,
  and a log names every file the game writes. Stretch, only with r0004 and only in case 1: one of the three maps loads
  to a control round.
- **Stop rules:** if the fileXio HLE is not answering the probe within two days, stop and file the trace. If it proves
  to be case 2, stop at the finding, write it into `HUMAN_TASKS.md` as a question for PSRewired, and **do not attempt
  to source Sony map data**.

---

## 3. Decisions for the owner

- **D1 — distribution.** r0004 can only come from a player's own PS2 memory card. Sony's code; we cannot ship it, and
  the retail download is dead. Are we willing to ship a community-play feature that most players will not be able to
  use? (Ship it for the minority who have a card / drop community play / ask PSRewired whether they will serve the
  package to our client.)
- **D2 — ordering.** Recommendation: Goal A now; B, C, D when there is slack; E, F, G only after the package exists.
  Confirm, or reprioritise.
- **D3 — disclosure.** How much of the chat fix is described in its commit message and the public README
  (`SECURITY.md` currently says the mechanics are deliberately not written up here).
- **D4 — the HDD maps.** Worth a subsystem at all, or explicitly out of scope for v1?

## 4. Bars for the whole sprint item

Goal A's test green and the README narrowed; Goal B reproducing r0001 byte-identically; Goal C at 100% on identity and
on the synthetic relocation, both in CI; Goal D visible in the launcher's screenshot mode with tests. Goals E–G carry
their own bars above and are not counted against this sprint unless their blockers clear.

## 5. What this does not do

Any connection to PSRewired (Goal F's blockers). Any attempt to source, host or redistribute the r0004 package or HDD
map data. LLE of the PS2 hard disk. PCSX2 mixed matches. A public write-up of the chat vulnerability's mechanics.

## 6. Pointers

`docs/research/02-socom2-online-servers.md` (servers, the DNAS bypasses, the hostnames), `/03` (the disc and the code
package), `/05` (the loader, the overlays, the DNAS layering, the Unicorn harness), `/19` F5 (the r0001 ↔ r0004 statics
map) and F10 (why community absolute addresses are not ours), `/38` (the OSK caps and how UI text limits are declared).
`SECURITY.md` for the reporting channel and the standing "not written up here" rule. `docs/HUMAN_TASKS.md` for the
memory-card task. Sprint 8 Goal 10 for the superseded design.
