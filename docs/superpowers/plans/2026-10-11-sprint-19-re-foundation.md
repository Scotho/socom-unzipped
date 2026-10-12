# Sprint 19 Implementation Plan — "the RE foundation" (OPEN 2026-10-12 10:19Z on `sprint-19` off `main` at `3ff74a11`, the v0.18.0 merge; R360; GitHub milestone 9)

> **For agentic workers:** REQUIRED SUB-SKILL: the project's `loop-iteration` skill runs this plan (one task at a time,
> a failing test first, a fresh reviewer per task, the lock for every build and run, every lock-bound step in chain Z-a or session Z-b).
> It is the project's form of superpowers:subagent-driven-development.

> Spec: `docs/superpowers/specs/2026-10-11-sprint-19-re-foundation-design.md` (APPROVED, R365). Research:
> `docs/research/89-re-foundation-phase0.md`. Drafted in the worktree `agent/s19-spec` off `sprint-17` at `d5fe0d59`.
> Task bodies are written at the open, one per task, in this file or a `-tasks` sibling as Sprint 18 did.

**Goal:** redotcom's readings become measurements on our instruments (one capture window), and the reverse-engineering
work of Harry62, redotcom and ours lands in one graded, cited, exported corpus (`re/`, the sidecars, the type master),
with a proven worked example of functional decompilation whose body stays private.

## Global Constraints

- **Order:** T1 and L1 first (lock-free, parallel); then Y, N, W, S, U, M, X1, Q, B1, E1-E3 lock-free in `agent/s19-*`
  worktrees; C1 once B1 and the probes are known; **Z-a** once in an owner-named window (O20, R297); **Z-b** (no
  build) in any short window or the owner's own PCSX2 session (spec §3: a late failure costs the proof, not the
  measurement); C3, X2/X3's records and K last. A task out of order needs a ruling.
- **The owner's rulings** R354, R355 and R356 bind every task: Harry's derived names with credit, never his corpus;
  no reconstructed body in the public tree; redotcom only as facts re-derived against our artefacts, cited "redotcom
  research N", no text, paths or tools copied.
- **Servers:** no connection to a server not ours (R293); captures read only files on disk or our local stack.
- **Agents:** Opus (`model: "opus"`); a fresh reviewer per task; Fable only for the spec review (the day's one).
- **The repo is public:** leakcheck on every commit; no private or LAN address (Harry's codes file stays out).
- **Commits:** `type(scope): what and why`, subject near 100 chars, `-- <paths>`, the session trailer.
- **Documents:** the `doc-maintenance` skill before writing into KNOWN, HAZARDS, LATER, DEVELOPING, HUMAN_TASKS.

## The task table

Kind: **free** = lock-free; **Z-a** = a step of the one chain; **Z-b** = the PCSX2 session. Bars in short; the spec §5 holds them in full.

| id | title | kind | depends | bar |
|---|---|---|---|---|
| T0 | The open: `sprint-19` off `main`, milestone, the spec's D-a..D-i numbered as rulings, CURRENT_SPRINT | free | 17 and 18 closed | docmaint OK; rulings in this file -- **DONE 2026-10-12 10:19Z** (R368-R374) |
| T1 | The twin table: `re/exports/twins.csv` generated from match.json, bogus and capsule rows flagged; its header carries the SHA-256 of match.json and the two input csvs | free | T0 | 14,879 rows; `how` counts equal the summary; the test asserts the csv hashes on every run (CI sees a stale table) and regenerates byte-identical where match.json is present |
| L1 | `re/` README, the types and facts schemas, the validating test, the registry row | free | T0 | planted bad anchor, bad evidence kind, over-grade each fail; docmaint OK |
| Y1 | The type master: `GameObject`, `PlayerObject`, `cAppCamera`, the replication record, aliases per source | free | L1, N-T1 | every field cited; the `+0x113` / `+0x115..+0x119` conflict held with its settling read |
| Y2 | The runtime header `socom2_types_generated.h` + `static_assert`s in the hand headers | free (compiles in Z) | Y1 | `clang -fsyntax-only` clean; regenerates byte-identical |
| Y3 | Ghidra `ImportNames.java`/`ImportTypes.java`; `re/exports/types.json`, `facts.json`, `socom2-types.d.ts` | free (never beside a build) | Y1 | one headless run on r0004 with counts in the Log; exports fresh under test |
| N-T1 | The ps2dis reader promoted to `tools_py` (object block -> `re/types` candidates tagged `harry62`) | free | T0 | synthetic round trip byte-identical; real file reproduces 5,956 labels, 3 objects, 512 new names |
| N-T2 | The `.cds` exporter and the labels-only way back (old T2, T3); **the owner alone sends anything to Harry, each time, as a HUMAN_TASKS row** | free | N-T1 | unittest: no memory or uninterpreted block in the output |
| N1 | The lever: `Pass=ps2dis-harry62`, provenance per source, screening pass, loose (D-c: by construction it lands almost none of the 512 new names; their yield is N2 + N3) | free | N-T1 | `apply_names --report-only` accounts for every candidate |
| N2 | Hand file for the 62 self-evident loader names, `file:line` each | free | N1 | report-only: applied count, 0 refused |
| N3 | r0004-only body reads (101 no-twin + 112 non-exact) within the time box, `Pass=hand` | free | N1 | `name_provenance audit` 0 findings; uncovered count recorded |
| N5 | redotcom-sourced names as `Pass=hand` rows on our own read, "redotcom research N" in `Source` | free | T1 | each row our `file:line`; a reviewer finds no copied text or path |
| D1 | The 32 disagreements dispositioned under test, with an alias column for the old D3's 18 function-name aliases (field aliases go to Y1) | free | N-T1 | test: every row has a disposition; the 18 aliases in the column |
| D2 | The five real conflicts, one body read each, a ruling and holds line per moved name | free | D1 | five artefacts; report-only shows no unruled change |
| W1 | Weapons and damage at r0004 into `re/facts/weapons_damage.json` (incl. `MPBOMB Ammo` `damage_point`, `docs/research/43-what-changed-in-r0004.md:75`) | free (probes in Z-a) | T1, L1 | each entry an r0004 read, re-read by a second agent |
| S1 | The stats record and rating at r0004 into `re/facts/stats.json` | free (PEEK in Z) | T1, L1 | as W1 |
| U1 | The UI command table at r0004 into `re/facts/ui_commands.json` | free (trace in Z) | T1, L1 | as W1; constant vs non-constant answers marked |
| M1 | DME class-2 ids and the voice pair at r0004 into `re/facts/dme_messages.json`, checked against the s4 log and the box's DME logs on disk | free | T1, L1, N1 | one KNOWN row per verified id |
| M2 | Protocol map vs `server/horizon-server` (old P1-P2): a `Server.Test` case or a LATER row per missing message; if the sprint runs long, M2/M3 become one LATER row (spec §7) | free | M1 | `dotnet test` green; every row classified |
| M3 | #26's receive path as the map's first entry (old P3) | free | M2 | LATER row 7 points at it |
| X1 | MENULOOP's picture count from our ISO, SHA checked | free | T0 | count and SHA in the Log; KNOWN row; banner on research/09 |
| Q1 | The MemoryCard stub's `Mkdir` answer, re-derived against our libmc read | free (builds in Z) | T0 | planted runtime test |
| Q2 | `tools_py/card_save.py` fill byte and flattening, re-derived against the game's own card writes | free | T0 | Python test |
| Q3 | Whether the launcher's card creator adopts Q2 | free | Q2 | a LATER row or a task |
| B1 | The coverage bitmap (knob-gated in `lookupFunction`) and its `tools_py` reader | free (collected in Z) | T0 | reader unittest on a synthetic dump; tail-call caveat printed |
| E1 | `PS2X_PRIVATE_OVERRIDES_DIR`: an optional CMake hook adding outside sources to the runner target `ps2EntryRunner` (not the static library, which drops a self-registering TU) | free (builds in Z-a) | T0 | configures unset and set; the sources land on `ps2EntryRunner`; no public body |
| E2 | The `PS2X_SHADOW` harness: snapshot, original, restore, body, compare GPRs/`sp`/`f0`/write log | free (builds in Z-a) | E1 | a planted mismatch caught under test; an original exit with `pc != ra` (the `eeCheckpointDue()` back-edge return, resume entry `0x3c4b50` r0001) detected and that call skipped/re-queued, under test |
| E3 | `CZWeaponList_GetWeapon` (r0004 `0x003e6cc0`): the public contract note (behaviour, offsets, return rule; no statement-by-statement code -- close to a reconstruction for a 72-byte leaf, D-i); the body private (D-a) | free | E2 | the note in `docs/research/`; a test that the public tree holds no body for it |
| C1 | The capture script and manifest: the drivable items, the knobs, the facts each settles; the named normaliser behind "equal apart from timings" (drops wall-clock stamps, host addresses, thread timings; keeps guest values, call order, payload bytes) | free | B1, W1, S1, U1 | dry-run of the script; manifest schema-tested; the normaliser's unittest |
| Z-a | The chain (spec §3): apply N, recomp, census, build, the r0004 gate, **C2 twice right after it**, the E gate with shadow on, the r0001 gate | **lock-bound, one owner-named window** | all free tasks above | census `extents_changed: 0`; gates 3/3 PINS MATCH; two capture runs equal after C1's normaliser; shadow calls > 0 and mismatches 0 |
| Z-b | The PCSX2 legs: X2's counter reads in the named revision, X3's title-loop recording | **lock-bound, no build; any short window or the owner's own session** | X2's address step | the two counter reads with revision and address; the recording |
| C3 | Promote the facts C2 settled to `capture`/`probe` evidence; the coverage hot set recorded | free | Z-a | facts re-validated; hot-set file in the Log |
| X2 | The frame clock in a named revision: default the plain r0001 disc (not instance A, whose card loads r0004) reading `0x004a4490` (an r0001 data address; match.json maps functions only); on r0004, the counter's address first derived lock-free by data-via-twin and the cap word's xrefs | free + Z-b leg | T1 | revision and address named before Z-b; KNOWN row; research/09 banner |
| X3 | The movie PCM ring: Z-b's recording cross-correlated both ways; `Mixer::pcmStream*` checked | free + Z-b leg | Z-b | KNOWN row; research/32 banner; a fix task for the next window if blocks win |
| K1 | The census before and after, per revision, region and provenance | free | Z-a | printed in the Log (baseline r0004 1,736/16,417, r0001 1,871/14,879, 2026-10-02) |
| K2 | DEVELOPING "Reverse engineering", README credits (Harry62, redotcom), KNOWN rows | free | C3 | docmaint OK; leakcheck passes |
| K3 | LATER rows: the PC engine fixes the route is for, DebugServer, matching rejected, the next functions | free | E3 | rows with triggers |

## Rulings made on the owner's behalf

- **R364 (2026-10-11 22:28Z, the owner's word; amends R354 and the spec's D-d) -- all of Harry62's work comes into the project, credited as "h62": his raw work (the `.ide`, the return set, the label CSVs, his scripts and object notes) stays in the repository's tree git-ignored under `game/harry62/`; what is tracked is a digested research set, `docs/research/h62/`, that restates his findings in our words and maps them onto our names, addresses and types, outside his tooling and conventions, for future work.** The owner: "We want to bring in all of Harry's work and reference it as h62 ... a 'digested' version for future work as it maps onto ours. His work stays in the repo gitignored. He gave approval for us to include his findings; I just want to be respectful." Harry's approval covers his findings; the digest credits him on every page, carries no LAN address, and the owner alone sends anything back to him (D-d).
- **R365 (2026-10-11 22:28Z, the owner's word) -- the spec is APPROVED with D-a..D-i at their defaults, D-d as R364 amends it, and D-h amended: when the redotcom export (`re/exports/`) is finished it is handed to redotcom's main controller as a handoff, and that seat decides what to take.** The owner: "agreed. When the export for redotcom is finished provide it to the main controller as a handoff and let it decide."
- **R368-R374 (2026-10-12 10:19Z, the open, under R365: the spec §4's decisions at their defaults; the full text and the
  reasons are §4's rows).** Each stands until the owner overturns it by number.
  - **R368 (D-a):** E3's reconstructed body lives in a git-ignored folder in the main tree, read by
    `PS2X_PRIVATE_OVERRIDES_DIR`, until the owner creates a private repository (R355); nothing public depends on it.
  - **R369 (D-b):** no Metrowerks compiler is obtained or used; the route is functional decompilation.
  - **R370 (D-c):** Harry's lever is loose: a name lands where a strict lever of ours agrees; the yield is N2's 62 hand
    rows plus N3's body reads.
  - **R371 (D-e):** the harness scripts the capture session (`PS2X_HOST_GAMEPAD`) on two of our clients, or ours plus a
    PCSX2; an item needing human hands becomes an owner row.
  - **R372 (D-f):** Z-a runs in one window the owner names (O20/R297); Z-b in any short window or the owner's own PCSX2
    session; every lock-free task lands meanwhile.
  - **R373 (D-g):** README credits Harry62 and redotcom with one line each in "License and credits", drafted by K2; the
    owner may reword.
  - **R374 (D-i):** a public contract note for a small leaf says behaviour, signature, offsets and the return rule, never
    statement-by-statement code; the owner may tighten it.

## Outcome

(filled at the close: what landed, Z's artefacts, the facts promoted, the KNOWN rows moved, the LATER rows written, the
owner's rows left)

## Log (newest first)

- **2026-10-12 10:19Z** -- OPEN (T0): `sprint-19` cut off `main` at `3ff74a11` (PR #138, `v0.18.0`) by the main-tree controller after Sprints 17 and 18 closed in R352's window. GitHub milestone 9 (created at Sprint 18's close); the spec's seven open decisions numbered R368-R374 at their defaults (D-d and D-h were R364 and R365); CURRENT_SPRINT's header and HANDOFF's counter (past R374) rewritten. First lock-free tasks: T1 (the twin table) and L1 (`re/`'s README and schemas). Z-a waits for a window the owner names (R372).
- **2026-10-11 22:19Z** -- The Fable review of 9d517511 (APPROVE WITH CHANGES), all eight applied: X2 names its revision
  and the counter's address (`_DAT_004a4490` is r0001 data); E2's bar catches the checkpoint return (`pc != ra`) and
  E1's sources go on `ps2EntryRunner`; Z split into Z-a (captures right after the first r0004 gate) and Z-b (the
  PCSX2 legs, no build); the owner-alone way back to Harry restored and D3's aliases moved to D1's table; T1's
  table carries its input hashes; the MPBOMB cite is research/43 §4; note 89 keeps only the 13-of-964 fact; D-c
  says loose lands almost none of the 512. Also: C1's normaliser, D-i (the contract note's line), the M2/M3
  fallback.

- **2026-10-11 22:05Z** -- Drafted, PROPOSED: the spec, this plan and `docs/research/89-re-foundation-phase0.md`, from
  the four phase-0 reports (revisions and tooling; compiler and route; types, grading and layout; redotcom's needs) of
  R361's agents, in the worktree `agent/s19-spec` off `sprint-17` at `d5fe0d59`. The two-cartographers spec of
  2026-10-02 carries a superseded banner (R360). No ruling taken; the owner's Fable review and his word are owed.
