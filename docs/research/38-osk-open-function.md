# 38. The on-screen keyboard's open routine, its text buffer and its caps (Sprint 10 Goal 9, Task 1)

Date: 2026-09-21. Written by the Goal 9 agent (worktree `wt-goal9`, branch `agent/goal9`) from the code as it
stands on `sprint-10`; a static pass first -- the dynamic confirmation, six driven logins on 2026-09-21, is the
last section, and it found one thing the static pass could not (the runtime unwinds guest calls). Sources: the synthetic ELF `game/overlays/socom2_game.elf`
(scanned for `lui`/`addiu` pairs and `jal` targets with a 60-line Python script, `logs/osk/xref.py`), the
recompiler's per-instruction disassembly comments in `recomp/output/*.cpp` (the main tree, read-only), the
function list `recomp/socom2_ghidra.csv`, and the disc image itself for the UI scripts. Ghidra's GUI was not
needed: every question below was answered by address arithmetic over the ELF.

## The answer in one table (the values Task 2 and Task 3 copy)

| Name in the plan | Value | Where it comes from |
|---|---|---|
| `kOskOpenAddr` | **`0x0038D770`** (`FUN_0038d770`) | the `GetTextInput` UI action's handler; entry id 18 of the 208-entry action table at `0x3dd4d0` (`{id, name, handler, argument parser}` x 16 bytes; the row is at `0x3dd5e0`, its handler word is the thunk `0x2808d0` = `j 0x38d770`) |
| its arguments | `a0` = the parsed argument block (0xAC bytes, layout below); `a1` = the dispatcher's context (unused by the prefill) | the dispatcher `FUN_002745a0` (`jalr handler(msg, ctx)` at `0x2747a8`); `FUN_0038d770` passes `a0` straight to `FUN_00397640` |
| the target text buffer | **`0x0049EC70`**, a zero-initialised bss buffer that is the keyboard's INITIAL text; `FUN_0038d770` passes it as the second argument of `FUN_0038b440(spec, text)` (`0x38d848`), which feeds it through `FUN_00398ea0` -> `FUN_0039a5b0(text, spec)` (laid out into the edit object at `0x4a1450`) and `FUN_0039a1d0(strlen(text), spec, 0)` (the cursor placed after it) | the only reference to `0x49ec70` in the whole ELF is that one `addiu` (every other `0xec70` immediate is a different base register); nothing ever writes it, which is why every keyboard in the game opens empty |
| the buffer's room | at least **0x48 bytes** (`0x49ec70`..`0x49ecb7`; the next written global is the byte at `0x49ecb8`, `FUN_0038b440:0x38b510`) | the neighbouring globals' references |
| `kOskNameCap` | **14 characters** (`MaxChars`), 31 bytes (`MaxBytes`) | the login screen's `GetTextInput` for the name: `Purpose=_455_EnterPlayerName_MSG` ("Enter Player Name"), `SkbName=CREATEPLAYERNAME`, `NoDQuote=1`, `AllowEmpty=0` -- the serialised argument block in the disc's UI data at ISO offset `0x7617a984` |
| `kOskPasswordCap` | **12 characters** (`MaxChars`), 31 bytes (`MaxBytes`) | the same screen's `GetTextInput` for the password: `Purpose=_604_EnterPassword_MSG` ("Enter Player Password"), `SkbName=CREATEPLAYERNAME`, `NoDQuote=0`, `AllowEmpty=0` -- ISO offset `0x7617ac4c` |
| what tells the two keyboards apart | the `Purpose` string at `msg+0x10` (a message key, copied verbatim from the script; `_455_EnterPlayerName_MSG` vs `_604_EnterPassword_MSG`) together with `SkbName` at `msg+0x58` (`CREATEPLAYERNAME`); NOT the `UiVar` id at `msg+0x8`, which is a per-screen string-table index (11 and 3 on this screen, 3 and 20 on others) | the argument parser `FUN_00395f40` and the serialised blocks |
| the live caps | `MaxBytes` at `msg+0x98`, `MaxChars` at `msg+0x9C` (both `int32`) -- the override reads the cap from the live message rather than trusting this table | `FUN_00395f40:0x396024/0x396048` |

**The two call sites the plan asked for are not two `jal`s.** The keyboard is opened by the game's data-driven
UI: the login screen's script (a compiled `.rdr` on the disc) contains two `GetTextInput` actions, one per field,
and the C++ side has ONE handler for the action. Both fields therefore arrive at the same function with a
different argument block; the argument block is what distinguishes them.

## How the pieces fit

```
UI script action "GetTextInput UiVar=<var> Purpose=<key> SkbName=<kbd> MaxChars=N MaxBytes=M NoDQuote AllowEmpty"
  |  parsed once by FUN_00395f40 (the row's 4th word) into a 0xAC-byte block:
  |    +0x02 flags     +0x06 byte     +0x08 u16 UiVar string-table id     +0x0C u16 0
  |    +0x10 char[0x40] Purpose       +0x50 i32 MsgPlayerTitle id (-1)    +0x54 i32 Action2Title id (-1)
  |    +0x58 char[0x20] SkbName       +0x78 char[0x20] UiVar2
  |    +0x98 i32 MaxBytes  +0x9C i32 MaxChars  +0xA0 i32 MaxBytes2  +0xA4 i32 MaxChars2
  |    +0xA8 u8 NoDQuote   +0xA9 u8 AllowEmpty
  v
FUN_002745a0 (dispatch by handler name)  ->  0x2808d0 thunk  ->  FUN_0038d770(msg, ctx)      <-- the override point
     FUN_00397640(msg): stashes the request in globals -- the target variable's NAME as a std::string at 0x4a1300
                        (bit 0 of word 0 = heap flag; inline text at +1, heap pointer at +8), UiVar2 at 0x4a0a30,
                        MaxBytes/MaxChars/MaxBytes2/MaxChars2 at 0x4a10c8/0x4a10d0/0x4a10d8/0x4a10e0, the purpose
                        at 0x4a08f0 (and on the title object 0x4a1150), NoDQuote 0x4a0a58, AllowEmpty 0x4a0a50;
                        returns &msg->SkbName
     finds the keyboard spec named SkbName (or "KEYBOARD") in the list at 0x49ecf0 (count 0x49ecec), loaded at boot
                        by FUN_0038d6a0 from data/common/UiParams.rdr "SoftKeyboards"
     FUN_0038b440(spec, 0x49ec70): activates it --
         FUN_00398ea0(spec, spec+0x5e0, text): FUN_0039a5b0(text, spec) lays `text` out into the edit object
                        (0x4a1450; 0x4a1520 is the second edit of a two-edit keyboard); FUN_0039a1d0(strlen(text),
                        spec, 0) puts the cursor after it
         pushes the keyboard state (vcall +0x60/+0x38 on spec+0x178), sets 0x49ecd0 = spec
     sets the UI variable "skb_done" to 0, plays the open sound (FUN_00395de0), returns 1
...the player types...
FUN_0038c040 (the keyboard's own event handler):
     FUN_003998a0: "unchanged?" -- compares the edit text (0x4a146c + 0x4a14bc, i.e. edit object +0x1c/+0x6c,
                        plus the second edit's 0x4a153c + 0x4a158c) with the target variable's current value
                        (FUN_00385900(0x437e80 = the CUIVarManager, name); a type-3 variable's char* is at +4)
     FUN_00399d20: apply -- FUN_003857c0(0x437e80, name, 0, 1) then FUN_003862a0(var, text) writes the string
                        into the UI variable, then posts event 0xE/0xF (ON_SKB_APPLY / ON_SKB_APPLY2)
LobbyLogin (FUN_0027dd20, action id 39): reads the UI variables PLAYERNAMEVAR and PLAYERPASSWORD
                        (FUN_003857c0(0x437e80, "PLAYERNAMEVAR"/"PLAYERPASSWORD", 0, 1); +0 type == 3, +4 char*),
                        refuses when either is empty, and only then raises the connect event
```

So the buffer to fill is the initial-text buffer `0x49ec70`, BEFORE `FUN_0038d770` runs, and it must be emptied
again AFTER it returns so the next keyboard (a chat line, a game name) opens empty as today. The keyboard then
opens showing the text with the cursor at its end, exactly as if it had been typed; ENTER applies it to the UI
variable the same way (R180: prefilled, never submitted). The launcher's strings never touch the UI variables
or the wire path directly.

## The mechanism: NOT a `recomp/socom2.toml` binding

The plan's Task 1 Step 3 asks for `"socom2_OskOpen@0x<addr>"` in the recompiler's stub list. That list REPLACES a
function: the recompiler emits, for a stubbed address, only `ctx->pc = ra; ps2_stubs::X(...)` and never the
original body (see `recomp/output/FUN_003b24c0_0x3b24c0.cpp` for `socom2_LumReadPixel`). There is no
`_original` continuation, so a toml-bound stub at `0x38d770` would have to re-implement the keyboard's whole
activation (a spec search, two virtual calls, the sound) -- and a recompile.

The runtime already has the right tool: `PS2Runtime::replaceFunction(addr, fn)` with
`lookupFunction(addr)` for the original, the pattern `installRtNetPortShift` / `socom2_RtNetConfigInit` uses
in `game_overrides_socom2.cpp` (wrap, call the original, fix up after). The prefill is installed that way at
startup (`installOskPrefill`, only when `PS2X_SOCOM2_LOGIN_NAME` or `_PASS` is set), needs NO recompile, and
`recomp/socom2.toml` is left untouched. **Proposed ruling (the plan file carries it):** Task 1 Step 3 and the
recompile half of Task 2 Step 5 are dropped; `./build.sh runtime` (the runner) is what the controller rebuilds.

## What was tried, in order (the evidence trail)

1. **The plan's addresses are file offsets, not guest addresses.** `game/overlays/all_strings.txt` is
   `ftscore_strings.txt` (lines 1-3310) followed by `zsealetc_strings.txt`; its first column is the offset into
   `FTSCore.bin`, which is loaded verbatim at `0x1e7000` (research/05). So `PLAYERPASSWORD` "at 0x00207990" is at
   guest `0x3ee990`, `PLAYERPERSONALIST` at `0x3eeb20`, `<New Persona>` at `0x3eeb08`, `SAVEPASSWORD` at
   `0x3f5d80`, `AccountLogin` at `0x3f4a80`. The grep for `0x207990` in the recompiled output found only the
   functions that happen to live at those code addresses.
2. **Xrefs to the corrected addresses** (lui/addiu pairs): `PLAYERPASSWORD` and `PLAYERNAMEVAR` (`0x3ee980`) are
   read by the lobby actions `FUN_0027dd20` (LobbyLogin) and `FUN_0027dde0` (LobbyRegister) through the UI
   variable manager `FUN_003857c0(0x437e80, name, 0, 1)`; `PLAYERPERSONALIST` / `<New Persona>` are built by
   `FUN_00276af0` (called from the three MUIS persona actions `FUN_00275130`, `FUN_002761a0`, `FUN_00276780`).
   None of these opens a keyboard: the login form's fields are UI variables and the keyboards are script
   actions. That is where the plan's "find the call made on CROSS" model stops applying.
3. **The keyboard strings** (`SoftKeyboards`, `KEYBOARD`, `skb_done`, `MaxChars`, `MaxBytes`, `AllowEmpty`,
   `NoDQuote`, `Purpose`, `UiVar`, `SkbName`, `UiVar2`, `ON_SKB_APPLY`...) xref to `FUN_0038d6a0` (loads the
   keyboard specs from UiParams.rdr at boot), `FUN_0038d770` (opens one) and `FUN_00395f40` (parses the
   action's parameters). `FUN_0038d770` has no `jal` caller and no data word naming it: it is reached through
   the thunk `0x2808d0`, whose address IS in the data table at `0x3dd5e0` (`{0x12, 0x3ed7d8 -> "GetTextInput",
   0x2808d0, 0x395f40}`) next to the parser `FUN_00395f40` -- a 208-row `{id, name, handler, parser}` table
   (`0x3dd4d0`..`0x3de1c0`) that also holds `LobbyLogin` (39), `LobbyRegister` (37), `SendChatText` (31),
   `GetMUISPersonaInfo` (175), `MUISPersonaExists` (178).
4. **The dispatcher** `FUN_002745a0` resolves the action name (string id at `msg+6`), walks the table, and calls
   the handler as `handler(msg, ctx)`; the parser fills the 0xAC block from the script's parameters (`UiVar`,
   `Purpose`, `MaxBytes`, `MaxChars`, `MaxBytes2`, `MaxChars2`, `SkbName`, `UiVar2`, `MsgPlayerTitle`,
   `Action2Title`, `NoDQuote`, `AllowEmpty` -- string offsets `0x3fb418`..`0x3fb4a8`).
5. **The initial text**: `FUN_0038d770` calls `FUN_0038b440(spec, 0x49ec70)`; `0x49ec70` is referenced nowhere
   else in the ELF (a scan of every `0xec70` immediate and every data word), and lies in FTSCore's bss (zero at
   load). The keyboard's text therefore always starts empty; writing there is the prefill.
6. **The caps and the field identities** come from the disc: the compiled UI scripts hold the parsed 0xAC blocks
   verbatim (header `01 01 b2 02`, then the fields above). Four were decoded: the online name keyboard
   (`_455_EnterPlayerName_MSG`, `CREATEPLAYERNAME`, MaxChars 14, MaxBytes 31, NoDQuote), the online password
   keyboard (`_604_EnterPassword_MSG`, `CREATEPLAYERNAME`, MaxChars 12, MaxBytes 31), the LAN name keyboard
   (`_455_EnterPlayerName_MSG` with `SkbName=MPPLAYERNAME`, MaxChars 14 -- NOT prefilled: the LAN name is a
   different variable and was not asked for) and the join-a-passworded-game keyboard
   (`_423_EnterPassword_MSG` "Enter a Password to Connect.", MaxChars 12 -- NOT prefilled). The message keys'
   texts: `_455` = "Enter Player Name", `_604` = "Enter Player Password"; `_599_EnterPassword_MSG` is the
   help line "¦ Enter your password." on the same screen, not a keyboard.
7. **The keyboard's character set** (from the harness's `OSK_ROWS`, `tools_py/parity/online_login.py`): the
   printable ASCII set without the space; the name keyboard additionally refuses `"` (`NoDQuote`). The launcher's
   normaliser keeps exactly that set, so a persona typed on the launcher is one the game's keyboard could have
   typed (the plan's "letters and digits only" would have mangled `Sgt_Rock`; a proposed ruling in the plan).

## The initial text: what the dynamic confirmation found (2026-09-21, six driven logins)

Everything in the table above held up in the game; what the static pass could not see was the runtime's own
execution model, and that is what emptied the keyboard in the first two logins.

**Two entries, not one (`2bc56ec`).** The action table's handler word is the thunk `0x2808d0` (`j func_38D770`),
and the recompiler emits that thunk as a direct C++ call of `FUN_0038d770_0x38d770` -- a `replaceFunction` at
`0x38d770` alone is never reached from the table (runs 1-2 of `logs/parity/s10_g9_prefill_gate`: armed, no
keyboard line at all). The wrap sits on both entries (`kOskOpenEntries`); `jal`s inside recompiled code go
through `dispatchGuestBranch` and the function table, so the wrap's own callees are traceable.

**The buffer is `0x49ec70`, confirmed** -- and the wrap was blanking it before the game read it. With the wrap on
the thunk, the game log said `on-screen keyboard open: purpose="_604_EnterPassword_MSG" skb="CREATEPLAYERNAME"
MaxChars=12 MaxBytes=31 -> prefilled: the password (5 chars)` and the keyboard still opened empty (`[osk]
prefilled: 0 of 5 in the field`). The third login (`logs/parity/s10_g9_prefill_diag3`) ran with
`PS2X_CALL_TRACE=0x38b440:OskActivate,0x398ea0:OskSetup,0x39a5b0:OskLayout,0x39ae50:OskWrap,...`,
`PS2X_WATCH=0x4a146c,0x4a14bc,0x4a1350,0x49ec70,0x49ecd0` and a temporary dump in the wrap after the original
returned. The trace, in log order:

```
[socom2] on-screen keyboard open: purpose="_604_EnterPassword_MSG" ... -> prefilled: the password (5 chars)
[call] OskStash #0 a0=0x16ee38c ... ra=0x38d788                          FUN_00397640(msg)
[call] OskActivate #0 a0=0xf721d0 a1=0x49ec70 ... ra=0x38d84c a1="socom"  FUN_0038b440(spec, buffer): the text is there
[ret-unwound] OskActivate #0 pc=0x3766a0 ra=0x38d84c                     <-- it did not return: it UNWOUND
[osk-diag] after open: buf="socom" active=0x0 ... text1=""               the wrap's post-call code ran here, and blanked the buffer
[call] OskSetup #0 a0=0xf721d0 a1=0xf727b0 a2=0x49ec70 ra=0x38b4c4        the resumed guest: FUN_00398ea0(spec, spec+0x5e0, buffer)
[call] OskLayout #0 a0=0x49ec70 a1=0xf721d0 ra=0x398f40                   FUN_0039a5b0(buffer, spec) -- no a0="..." : empty
[call] OskWrap #0 a1=0x49ec70 a2=0xf727b0 a3=0x1 f12=1.0 f13=310.0       FUN_0039ae50: 0 lines from an empty string
[ret] OskWrap #0 v0=0x1 ; [ret] OskLayout #0 v0=0x1                      "success", nothing laid out
```

The runtime's guest calls are not plain calls: `PS2Runtime::dispatchGuestBranch` charges every inter-function
transfer against the EE scheduler and, when a checkpoint is due, **unwinds** the whole recompiled call chain
(`markDispatchUnwind`; every generated function returns at once) and resumes the guest later at the saved pc.
`FUN_0038b440` hit that checkpoint at `0x3766a0` (inside the keyboard-state push, before `FUN_00398ea0`) in
every one of the six logins -- deterministic. A host wrapper that calls the original and then "fixes up after"
sees the original return at the unwind, not at the real return, and its fix-up runs while the guest is still
in the middle of the wrapped function. The call trace's own thunk knows this (`[ret-unwound]` when `ctx->pc !=
ra`); the prefill wrap did not, and blanked the buffer between the activation and the layout.

**The fix (`f47cfe0`)**: the wrap writes the buffer's whole image BEFORE the original -- the field's text for a
login keyboard, zeros for any other -- and never touches it after. That is enough because `0x49ec70` is read by
this handler alone (the xref scan above), so what one open leaves is overwritten by the next open through the
same wrap; the "blank it again after" of the first design was never needed. The rule for any future
`replaceFunction` wrap in this runtime: **post-call code is unreliable** unless it checks `ctx->pc == entry ra`
(the call trace's test), and even then the resumed original does not pass through the wrap again -- put the
work before the call, or on the next entry.

**The proof (`--existing --prefilled --name socomc --password socom`, the hosted server 3.143.65.100):**
`logs/parity/s10_g9_prefill_fix4` and `..._fix5`: `OskActivate a1="socom"`, `OskSetup a2="socom"`, `OskLayout
a0="socom"`, `[osk] prefilled: 5 of 5 in the field -> ENTER`, `[osk] enter: keyboard closed`, `LOBBY class=ok`
(97.0 s, 96.6 s). `..._fix6_newpersona`, a scratch copy of `game/disc/mc0_parity` (no persona on the box) with
`--name socomd`: the name keyboard `purpose="_455_EnterPlayerName_MSG" ... MaxChars=14 MaxBytes=31 -> prefilled:
persona name (6 chars)` opened showing `socomd` with the cursor after it (`run/03_name_kbd.png`), `[osk]
prefilled: 6 of 6 in the field -> ENTER`, `PLAYER NAME reads 6 glyphs`; then the password keyboard `5 of 5`;
`LOBBY class=ok` at 131.5 s through the first-login prompts. Both rows of the table above are therefore live:
the caps (14 / 12, 31 bytes), the purpose keys, the SkbName, the buffer.

**What the edit object looks like, for the record** (from the diag dump and `FUN_00399ec0`, the insert-a-character
routine, which reads the text the same way the "unchanged?" check does): `0x4a1450` is the first edit; `+0x1c`
is a `char*` to its text and `+0x6c` an offset added to it (`FUN_00399ec0:0x399f50`); `+0x40` its width as a
float (from the spec's per-edit block `spec+0xE0+idx*0x24`, `+0x14`), `+0x18` its font object; `0x4a1350` the
cursor index, `0x4a1330` the two-edit flag, `0x49ecd0` the active spec. The layout is `FUN_0039a5b0(text, spec)`
-> `FUN_0039ae50(&lines, text, font, 1, width, spec+0xC0)` (a word wrap) -> the first line set on the edit via
its vtable slot `+0x70` and `FUN_00362b70` (refresh); the typed-character path goes through the very same
layout, which is why a prefilled string behaves exactly as a typed one (ENTER, BACKSPACE, the caps).

- The r0004 package (the community server's) moves every address here; this note is for r0001 (ours).
