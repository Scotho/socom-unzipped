# 37 — Can the launcher's ONLINE tab feed the game its persona name and password?

**Asked by the owner, 2026-09-20:** "investigate if it's possible for us to allow player name and password input
on the online tab to be read in game automatically." An investigation, not a build; the owner said this may be
scoped in a later sprint. Written by the launcher session (socom-pc-f3) from the code as it stands on
`sprint-10`; nothing here was run.

## Short answer

Yes, it is possible, and the runtime already has every hook it needs. The credentials never leave the game in
the clear over the wire, but they DO pass through host code in the clear: the Medius stream's RC4 is a host
override (`ps2xRuntime/src/lib/socom2_crypto.cpp`, bound at recompile time through `recomp/socom2.toml`), so the
runtime sees every `MediusAccountLoginRequest` and `MediusAccountRegistrationRequest` as plaintext before it is
encrypted. There are three routes, in rising order of polish and cost; the second is the one worth scoping.

## What the game does today (from the harness and KNOWN.md)

- Going online, the game shows a **persona list** saved on the memory card, keyed per server (`docs/KNOWN.md`, the
  "saved online personas per server" row). A stranger's first login on a server is a *create persona* login: an
  on-screen keyboard (OSK) for the **name**, then an OSK for the **password**, then CONNECT.
- A returning player's persona is pre-filled from the card; the **password is not saved** -- "a saved persona
  opens the password keyboard directly" (`docs/archive/HANDOFF-2026-09-08.md:363`). So the name half of the
  owner's ask is already what the game does on the second login; the password half never is.
- The parity harness types both on the OSK by dead-reckoned pad presses and reads the typed length back from a
  screenshot (`tools_py/parity/online_login_ours.py`, `OSK_*` constants). That is the blind class research/28 §5
  named; a runtime-side fill would retire it for the harness as well as for players.
- The server side: Horizon's `CreateAccountOnNotFound=True` makes the account on first login
  (`docs/superpowers/plans/2026-09-19-sprint-8-hosted-server.md:86`). The plaintext request the client sends
  carries `USERNAME` and `PASS` fields (`docs/research/28-lobby-taxonomy.md:161` quotes one from the server log).

## The routes

### Route A -- rewrite the login request in the host crypto path (cheapest; half an answer)

The launcher already passes settings as `PS2X_*` environment variables (`launcher::environmentFor`). Add
`PS2X_SOCOM2_LOGIN_NAME` / `PS2X_SOCOM2_LOGIN_PASS`; in `rc4EncryptFn` (or the `send` in `socom2_hostnet.cpp`)
recognise the account-login and account-registration messages by their Medius type byte and overwrite the two
fixed-width string fields before encryption.

- Cost: one afternoon in the runtime; a unit test on the rewrite from a captured plaintext.
- What it does NOT do: the player still walks the two keyboards and must type *something* (the game refuses an
  empty field client-side -- the harness's "CONNECT with an empty password" landed on the persona dialog, which
  is the server's answer, so an empty PASS does reach the wire; an empty NAME may not). The persona the card
  saves is the one typed, not the one sent, so the list shows the wrong name next time. Not the owner's ask.

### Route B -- fill the game's own text buffers when each keyboard opens (the one to scope)

The OSK is the game's own code with a target buffer and a max length. A recompiled function override (the
mechanism `game_overrides_socom2.cpp` uses for the loader, the RSA key pair and the crash handler) at the
function that opens the keyboard can write the launcher's string into the target buffer and return as if ENTER
had been pressed -- or, less invasively, pre-fill the buffer and let the keyboard open with the text already
in it, so the player only presses ENTER twice (and can still edit).

- What has to be found first (Ghidra, `ghidra_proj/`): the OSK open function and its buffer/length arguments,
  and which caller is the persona-name keyboard versus the password keyboard. research/03 notes the r0005 patch
  community found the password buffers (`0x30D278 / 0x2BC7D0 / 0x30D43C`, hashed pw `0x45A1A8`) -- r0005
  addresses, not ours, but the same code, so the functions are findable by the same strings.
- Cost: a day of Ghidra plus a day in the runtime and harness; the harness's `online_login_ours.py` then drops
  its OSK typing entirely on our exe (PCSX2's path stays), which is the largest single lobby-failure class left.
- Risk: the game's `sceInet` persona save keys per server (KNOWN.md); a name written by the launcher that
  differs from the card's saved persona is a create-persona login, which is correct behaviour, not a trap.

### Route C -- skip the login screens altogether (not recommended yet)

Drive the whole ONLINE -> LOGIN -> universe -> persona -> CONNECT walk from the runtime with the launcher's
values (an in-runtime macro of the harness's stage machine). Fragile against the same dialogs the harness
already classifies (SERVER NEWS, "Choose a different persona", the write-down notice); only worth it if the
owner wants a one-click "go online" later.

## What the launcher side is, whatever the route

- Two fields on ONLINE under PROFILE: **PLAYER NAME** (the persona; today's "profile" is the card directory,
  not the persona, and the help text says so) and **PASSWORD** (masked; a SHOW toggle). Both in `Config` and
  `config.json`. The password sits in a plain file next to the launcher -- the same as every launcher of this
  kind, but the ABOUT page's "where things live" line should say it.
- Validation the game applies: persona names are letters, digits and a few marks up to the OSK's cap (the
  harness typed 6-char names; the cap needs reading from the OSK code in the same Ghidra pass).
- The environment: two more `PS2X_*` entries from `environmentFor`, tested where the others are.

## Recommendation

Scope Route B as one sprint goal with the Ghidra pass as its first task and Route A's request rewrite as its
fallback if the OSK functions prove awkward. The harness win (no more dead-reckoned OSK typing on our exe) pays
for it on its own; the player-facing part is the two fields and about forty lines.
