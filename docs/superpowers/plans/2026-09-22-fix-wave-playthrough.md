# Fix wave A -- the 2026-09-22 playthrough

**Why this exists.** The owner played tonight's portable build end to end and reported as they went
(`docs/CURRENT_SPRINT.md`, "The playthrough, 2026-09-22", rulings R236-R240). Their words at the close: "Complete a
mini sprint based on findings and your suggested fixes/debugging ideas ... proceed autonomously, validating what is
required at each step and persisting until the fix wave is complete." A separate reading agent also audited Sprint 10;
its review is chunk W11.

**The bar for the wave.** Every chunk pays its own bar before it is called done, and anything proven goes to `main`
the day it is proven, on its own frozen slice (`docs/GIT_STRATEGY.md` §2). Nothing here holds `v0.10.0`: the road to
the tag is unchanged, this is the playthrough's row of it.

**What "validated" means per chunk**, because three different kinds of work are mixed in here:
- *code with a test* -- `./build.sh test` green, the new test failing before the fix and passing after;
- *an instrument* -- shown working on a real run, with the line it prints quoted in the record;
- *an A/B* -- two runs that differ in one knob, with what changed named. An A/B that does not separate the two
  hypotheses is not a result and gets written down as "did not separate", never as a pass.

## The chunks

| # | What | Kind | Bar | State |
|---|---|---|---|---|
| W1 | **Diagnosability (R238)**: `PS2X_MC_TRACE` and `PS2X_AUDIO_DUMP` to Shipping; new Shipping `PS2X_SND_MUTE_BANK`; a refused or failed card operation logs in **any** build, knob or no knob; a run started without the launcher still writes a log | code + tests | suite green; the card line and the audio dump shown on a real run | |
| W2 | **The launcher's text fields (the audit's finding 1)**: the field's accept-set becomes the keyboard's accept-set, so a space or a `"` never enters the value; a config read from disk is normalised on load | code + tests | a test that types a space into PLAYER NAME and asserts field == what the game is handed | |
| W3 | **The pad dies after a text field takes focus** (the owner's finding 1) | code + test | a test that focuses a field, leaves it, and reads the pad | |
| W4 | **Build, suite, gate, slice** for W1-W3 + R236 | gate | `./build.sh test` green, the three-stage gate 3/3, PR merged to `main` | |
| W5 | **The blop A/B (R239)**: the online screen with bank `0x00a00000` muted, and again with `PS2X_AUDIO_DUMP` capturing | A/B | the bank is cleared or convicted, in writing | |
| W6 | **The garbled glyph atlas**: `PS2X_GS_NO_TEX_REVALIDATE=1` against the HELP popup | A/B | R123 cleared or convicted | |
| W7 | **The mission-music instrument** (the owner's explicit instruction): a drive script that **skips the cinematics** and reaches gameplay fast, plus a long in-mission capture scored against PCSX2 | instrument | a capture long enough to contain the degradation the owner heard | |
| W8 | **The join driver (R240)**: press REFRESH LIST before JOIN GAME, and take a `--channel` | code + a real join | a join into a real lobby, or a named reason it could not | |
| W9 | **The CONTROLLER page**: a better pad graphic, and **hold-a-button-to-remap** with hints that walk the player through it | code + tests | the hold gesture tested; the page's own tests green | |
| W10 | **The prefilled login leaves the player path (R237)**, and a persona + remember-password proven to survive a restart on a **virgin** card | code + a real run | the second launch logs in with nothing typed | |
| W11 | **Review the Sprint 10 audit** from the reading agent: verify every claim against the code, fix what is real, record what is not | review | each claim marked confirmed / partly / wrong, with the file and line | |

## W11 -- the audit, claim by claim

The audit read only; it launched and built nothing, which is the right shape for a provenance check. Verified so far:

**Provenance (confirmed).** The zip, the exe inside it and the commit all agree with `docs/PLAYTEST.md`, so KNOWN §4's
"a failed packaging leaves the previous archive in place" did not happen here. The nineteen commits after `acbc693`
are the developer-chain work and docs, which is why the archive is still the right thing to play. This is a genuinely
useful check and it belongs in the release procedure, not in a one-off review -- W11's output includes adding it.

**Finding 1, the login fields drop spaces silently: CONFIRMED, and it breaks an invariant the code claims.**
`typeInto` (`ps2xLauncher/src/ui/widgets.cpp:448`) accepts every character in 32..126, so a space and a `"` enter the
value. `keyboardText` (`ps2xShared/src/launcher_config.cpp:411`) keeps only `u > 0x20 && u < 0x7F`, dropping both --
but it runs at `environmentFor` (line 483), not at input. So `config.json` stores the string **with** the space, the
field displays it, and the game is handed a different string: the keyboard opens with the wrong text and the login
fails with nothing on screen to explain it. The comment above `keyboardText` asserts the opposite ("what the player
sees in the field is exactly what the keyboard will hold"), which makes this a broken invariant, not a missing
feature. Fixed in W2 by filtering at the field, so the invariant holds by construction rather than by comment.

**What could not be reviewed.** The audit as it reached this session ends mid-sentence inside finding 1 ("The code
co sees in the field is exactly what the"), so anything numbered 2 or higher was never seen here. Everything above is
the provenance check and finding 1; if the audit had more, it has not been read, let alone answered. Worth re-sending
whole rather than assumed handled.

## Order, and why

W1-W3 are small, central and share one build, so they go together and W4 pays for all three at once. The A/Bs (W5,
W6) need W4's exe, so they follow it. W7 and W8 touch only Python and can run beside the build. W9 is the largest
piece of UI work and starts once W4's build is out of the way, so nothing unproven is ever inside a gated exe. W10
ends the wave because its proof is a restart on a virgin card, which is also finding 3's reproduction.
