# 66. The chat step: R1 opens the chat box, and R221's peek reads through a pointer

Date: 2026-09-25/26. Sprint 13 Task O2, issue #26 ("No run has shown a received chat line crossing the client bound:
the harness cannot open the chat box") and R221 (the talk-slot peek, Sprint 10 Q5). No byte of the game is in this
note: the strings quoted are the UI's own message keys and the texts a player reads on screen.

## 1. What opens the chat box (read before any launch)

**R1.** Both rooms say so on screen, in the captures the failed chain7 attempt itself left
(`logs/parity/s11_chat_A/` on the build machine, git-ignored):

- `11_briefing_room.png` -- the BRIEFING ROOM's button bar: "R1 TEXT CHAT  TRIANGLE BACK  CROSS SELECT", and the
  chat panel's header "Chat Display. L1 and L2 to scroll chat".
- `17_game_lobby_ok.png` -- the GAME LOBBY's chat panel: "R1 Text chat.  L1 and L2 to scroll chat".

The disc's message table carries the same strings with their button glyphs: `_518_TextChat_MSG` ("TEXT CHAT"),
`_519_ChatDisplay_MSG`, `_343_TextChat_MSG` ("Text chat.  ... to scroll chat") and `_864_TextChatBack_MSG`.

chain7's `--then type:hello` (R246) waited twelve seconds for a keyboard nothing had opened, then "recovered" with
CROSS and with TRIANGLE+CROSS -- in the game lobby those are ARMORY and BACK -- and never pressed R1
(`logs/chain7_chat_A.log`: "on-screen keyboard still not up after 12s" three times, then
`RESULT LOBBY-FAIL login-keyboard`). The second half of #26's evidence (B's `NO-GAMES channel=1`) was the other
sequencing defect: B looked for the game before A had hosted it. The two-instance driver (online_match_ours) already
sequences A hosts, B joins; the chat step goes after the join.

**The keyboard R1 opens** is the UI's `GetTextInput` action (research/38's handler `FUN_0038d770`) with
`Purpose=_361_EnterChatMessage_MSG` ("Enter a Chat Message") -- the compiled UI scripts in the disc's UI data hold
eighteen such blocks, on the soft keyboards `ChatSkb` and `PlayerChatSkb`, each followed by `PruneUIVarSpaces` and
`SendMediusChat`; round 1 (section 3) saw `ChatSkb` open in the game lobby. The keyboard specs (`SoftKeyboards` in the UI params) give the
chat keyboards their own background pieces (`SKB_English_Set.tif` / `SKB_English_Set2.tif`); the grid read as
shared (`~ ! @ ... BackSpace`, ..., `Switch1 Recip { } : < > ? | Space`), and round 1 showed the chat keyboard lays
it out with one more row than the login's (section 3).
The step's read-back is therefore the runtime's OSK wrap: with `--prefilled` armed it prints
`[socom2] on-screen keyboard open: purpose="..." skb="..."` for every keyboard the game opens, chat included.

**A product note, not this task's:** R1 is outside the host keyboard's Menus scope (`socom2_host_input.cpp`,
Sprint 10 Q3, R210: the d-pad, the four face buttons, START and SELECT). A player with no pad cannot open the chat
box from the keyboard unless the launcher's mapping gives R1 a key; the harness posts it as `E` because every harness
launch is PS2X_DEV (Full scope). The Q3 comment says "the game's menus ... read nothing else"; the chat box is the
exception.

**Where the line goes (inference, not observed: no Horizon log was read for the rounds' windows).** `SendMediusChat` sends a Medius chat message; our Horizon (`server/horizon-server`,
`MLS.ProcessChatMessage` / `ProcessGenericChatMessage`) relays a Broadcast to every other client in the sender's
CHANNEL (`clientObject.CurrentChannel`) -- the briefing room's channel, which a player in a game lobby still has --
as `MediusChatFwdMessage`, clamped (`ChatClamp.Fit`). The client's forward callback is the wrap Sprint 11 Task 2
bounds (`chatFanoutRecv`, `[socom2] chat receive bound: seen=<n> fixed=<n> skipped=<n>`, printed on its first call
and afterwards only when a call changed a field).

## 2. R221's peek: the table is behind a pointer

R221 (Sprint 10 Q5) asked for "`DAT_004415a8+0x12+0x0a` and `+0x12+0x0b`", written up since as the literal
addresses `0x4415c4/0x4415c5`. The decompilation reads the global as a POINTER: `FUN_002c64e0` computes
`*(byte *)((action & 0xff) + DAT_004415a8 + 0x12)`, and the same unit assigns it (`DAT_004415a8 = iVar2`), tests it
(`if (DAT_004415a8 == 0)`) and copies it (`DAT_004415b0 = DAT_004415a8`). The talk slots are therefore
`*(0x4415a8) + 0x1c` (action 0x0a) and `*(0x4415a8) + 0x1d` (action 0x0b); the literal pair reads the global's own
neighbours. The round peeks the pointer (`0x4415a8:1`) and twelve words behind it (`*0x4415a8:12`, `*(ptr)+0x00`
.. `+0x2f`), well under the 64-word cap. The pointer is `guest_addresses.talk_table_ptr`, r0004 `0x0044dfc8` by
`tools_py/data_via_twin.py` (16 sites, 15 evidence-twinned in 13 functions, unanimous; the `--column` run re-derives
it). **Ruling O2-R1 (mine):** the peek reads through the pointer and the literal pair is not peeked; R221's question
is unchanged (0x10 = unbound), only its address is corrected. Overturnable with one line of PS2X_PEEK.

## 3. The rounds

Each is one hold of the loop lock (`logs/o2_round.sh` under `loop_lock.sh run agent-s13-o2`), the main tree's exe
(`dist/socom2.exe` sha256 `f90eeec0...`), the r0001 image, the hosted Horizon box by name (env.sh), both memory
cards copied into the worktree, `scripts/parity/control_round_chat.sh` driving `online_match_ours --existing-b
--prefilled --chat hello --hold 60 --map frostfire`. The round directories and run logs are git-ignored, in the
`wt-s13-o2` worktree on the build machine.

### Round 1 -- 2026-09-26 01:26-01:33Z, `logs/parity/s13_o2_chat_20260925_222620`

`RESULT CHAT FAIL lobby=FAIL keyboard-A=PASS receive-B=FAIL keyboard-B=PASS receive-A=FAIL talk-slot-A=PASS
talk-slot-B=PASS`.

- **R1 opened the chat box on both instances.** A hosted Frostfire ("US East (Ohio)" channel), B refreshed,
  listed and joined (`B_[lobby] teams: ... -> ok`), then A pressed R1 in the game lobby and its log printed
  `[socom2] on-screen keyboard open: purpose="_361_EnterChatMessage_MSG" skb="ChatSkb" MaxChars=63 MaxBytes=63 ->
  not prefilled` within a second (`logs/run_A_20260925_222633.log`); B's R1 did the same
  (`logs/run_B_20260925_222633.log`). The keyboard is `ChatSkb` in the game lobby, 63 characters.
- **Nothing was sent.** The chat keyboard is the login grid plus one more row below it -- the accent toggle
  (`äèî`), a wide space bar, MESSAGE, IGNORE, LEGEND -- and it opens with the cursor on that row's accent key
  (`A_chat_01_open.png`). The login's walk, dead-reckoned from the login's opening key one row higher, typed
  `nd..l` for `hello` (`A_chat_key0_h.png` .. `A_chat_key4_o.png`) and its ENTER walk ran right off EXIT, wrapped
  to SHIFT and pressed it (`A_chat_02_entered.png`: the field `nd..l`, SHIFT lit, capitals showing). Every key of
  that is the walk shifted exactly one row down; `tools_py/tests/test_chat_round.py` replays it on a model of the
  grid. The step's "closed" read was wrong too: it looked for the room's title, and the chat panel covers only
  the lower two thirds of the screen, so the title stayed readable above the open keyboard.
- **B's log shows no `seen=`** after its mark (byte 4706875), nor A's after B typed back -- consistent with
  nothing having been sent either way. Neither log carries a `chat receive bound: seen=` line at all.
- The round then failed READY (`RESULT LOBBY-FAIL ready:cursor-not-found`): A's keyboard was still up over the
  lobby menu.
- **R221's peek, read.** `talk_table_ptr` (0x4415a8) held `0x00d4f340` from the 13th sampler row on, on both
  instances, and never changed (1589 of 1601 rows on A, 1567 of 1579 on B; the first twelve, at boot, null). The
  object it points at begins with the length-prefixed name `Default` (and the next preset, `Reverse`, follows at
  +0x20): the loaded controller preset. Its 13-byte action -> slot table at +0x12 (`FUN_002c5ff0` initialises
  exactly 13 bytes to 0x10) reads `09 10 0a 0f 0b 08 0e 10 10 0c 0d 07 01`: **action 0x0a -> slot 0x0d and action
  0x0b -> slot 0x07. Both talk actions are BOUND in the loaded preset**, which is the opposite of what KNOWN
  inferred from Sprint 8's sweep ("the talk action ... looks unbound in the loaded control preset"). Actions 1,
  7 and 8 are the unbound ones. This was read in the lobby (the round never reached gameplay); round 2 reads it
  in the round. Which physical button a slot is, is not established: if a slot is the libpad bit index, 0x0d is
  CIRCLE and 0x07 is d-pad LEFT, and Sprint 8 held both for 3 s in a live round with the talk flag not moving --
  so the talk gate would be one of the route conditions (`DAT_0045a0c1`, the hold timer, `+0xdcc`, the player
  state), not the preset. That is a hypothesis for whoever takes voice next, not a finding.

The fix (commit `e076c18a`): the walk enters the chat keyboard with RIGHT, UP (onto TEAM, a key the two grids
share) and dead-reckons from there; the close is read from the keyboard's top key row (column spread std 33 with
the keyboard up, 5.3 on the game lobby, 8.3 on the briefing room); ENTER is re-pressed once, then the keyboard is
left through EXIT so the round still reaches READY.

### Round 2 -- 2026-09-26 02:22-02:31Z, `logs/parity/s13_o2_chat_20260925_232224`

`RESULT CHAT FAIL lobby=PASS keyboard-A=PASS receive-B=FAIL keyboard-B=PASS receive-A=FAIL talk-slot-A=PASS
talk-slot-B=PASS` (driver rc 0).

- **The chat step works.** A pressed R1 in the game lobby (the OSK wrap's `_361_EnterChatMessage_MSG` /
  `ChatSkb` line), entered the grid with RIGHT, UP, typed `hello` (`A_chat_key4_o.png`: the field reads `hello`)
  and ENTER closed the keyboard (`A_chat_02_entered.png`: the chat panel shows `socomc (All): hello`).
- **The line crossed to B.** `B_chat_A_to_B.png`, taken on B 30 s later, shows `socomc (All): hello` in B's chat
  panel; B's reply crossed back (`A_chat_B_to_A.png`: `socomc (All): hello` then `socome (All): hello`). Then both
  went READY and the round started (`A_hold03.png`: Frostfire, 05:20 on the clock).
- **And neither log has a `[socom2] chat receive bound: seen=` line** -- not after the marks (A->B: B's log from
  byte 5608473; B->A: A's from 6741219), and not anywhere: B's log carries the install line (line 73) and nothing
  more from that wrap (`logs/run_B_20260925_232239.log`), A's the same (`logs/run_A_20260925_232239.log`). The wrap
  prints its first call unconditionally, so **the function it wraps, `chatFanoutRecv` 0x2f4ef0, was never called
  on either instance while a chat line crossed each way.** The list wrap (`chat list bound: seen=1 fixed=0
  skipped=0`, B's line 3068) printed its first call at login, long before the chat, and is silent after that by
  design (it prints only calls that changed a field, and a five-letter line changes nothing).
- **The peek in the live round:** 2053 of 2065 rows on A and 2040 of 2052 on B, lobby and round alike, all read
  `talk_table_ptr` -> `0xd4f340`, action 0x0a -> slot 0x0d, action 0x0b -> slot 0x07. Both talk actions are
  bound in the loaded preset during the round too.

**What that makes #26's bar.** It asked for a two-instance run whose B log shows `chat receive bound: seen=1`. The
harness step it asked for exists and works; the run exists; the line crossed; and the bar's line cannot print,
because the wrapped callback is not on the path a game-lobby chat line takes (the only room these rounds typed in; briefing-room and in-round chat are untested). **Ruling O2-R2
(mine):** #26 is not closed on a bar that measures the wrong function; the finding is recorded as its own KNOWN §2
row (and the §1 row's "the receive path is bounded" narrowed), and #26's closing bar is the controller's to restate.
Cost: #26 stays open one more step; the alternative (closing on the screenshots) would certify a bound that the run
shows was not exercised.

What the static reading says about the path that WAS taken (r0001 decompilation, read after round 2):

- `FUN_002f4ef0` (the wrapped function) is one of three callbacks `{0x2f4ef0, 0x3009c0, 0x3008a0, 30000}` handed
  to the network library by `FUN_00300840`, which the UI action `MediusInit` runs (the action table row at
  `0x3dde24`/`0x3dde28`). Its body forwards only chat types 2 and 1 (or any type in UI state 0xb) to the HUD
  message line `FUN_002a4050`; it never touches the chat list.
- The chat panel's lines are 0x80-byte records in the channel holders at `0x44f568`, appended by `FUN_001f5020`
  (and rendered by `FUN_002f5020`, the list wrap's function). `FUN_001f5020` builds each record on its stack from
  its message and name arguments with `FUN_0039fc60(dst, src, n)` -- a copy that stops at `n - 1` bytes, backs off
  to a whole UTF-8 sequence and always writes the terminator -- with `n` = 0x20 for the name and 0x40 for the
  message. So the record the panel reads is terminated within its widths by the game's own copy.
- `FUN_001f5020` is reached from `FUN_001f4d20` (in UI state 0xb; `FUN_001f4df0` otherwise), a method in the
  table at `0x40503c` (`0x1f4440, 0x1f4630, 0x1f45e0, 0x1e7c70, 0x1f4d20, ...`). Which network callback calls that
  method is not established statically; round 3 call-traces these candidates.

### Round 3 (the last of the budget) -- 2026-09-26 03:32-03:40Z, `logs/parity/s13_o2_chat_20260926_003237`

The same round on the merged exe the controller's chain had just built (`dist/socom2.exe` sha256 `0633c484...`, main
tree `5ea83ecf`), with env.sh's call trace replaced for this round only (from the ignored `logs/o2_round.sh`):
`PS2X_CALL_TRACE=0x1f4d20:ChatDispatch,0x1f5020:ChatAppend,0x1f4df0:ChatOther,0x3009c0:ChatCb2,0x3008a0:ChatCb3`,
`PS2X_CALL_TRACE_EVERY=1`. `RESULT CHAT FAIL lobby=PASS keyboard-A=PASS receive-B=FAIL keyboard-B=PASS
receive-A=FAIL talk-slot-A=PASS talk-slot-B=PASS` (driver rc 0).

- The lines crossed both ways again: `B_chat_A_to_B.png` shows `socomc (All): y4oo0` on B (A's walk lost a press
  under the host's load this time -- the step does not read the field back, and any line serves the bar),
  `A_chat_B_to_A.png` shows that line and `socome (All): hello` on A.
- `[call-trace] tracing 5 guest functions` on both instances, and **not one `[call]` line**: none of the five was
  entered while two chat lines arrived (`logs/run_A_20260926_003247.log`, `logs/run_B_20260926_003247.log`). The
  receive wrap stayed silent as in round 2. The trace reaches a function called through the dispatcher (a `jal`, a
  `jalr` through a pointer or a vtable); a tail `j` compiled to a direct C++ call is the one route it cannot see
  (research/38, "two entries, not one") -- which leaves `ChatAppend` inconclusive if `ChatDispatch` tail-jumps to
  it, but `ChatDispatch` itself (a virtual method) and the two registered callbacks are reached only through the
  dispatcher, and none of them ran.
- The peek held: 1873 of 1885 rows on A, 1847 of 1859 on B, `0xd4f340` -> 0x0d / 0x07 throughout.

## 4. What is known, and what is owed

**Known, with the artefacts above:**

1. R1 opens the chat box in the game lobby; the keyboard is `ChatSkb`, 63 characters, the login grid plus one row
   below it, opening on that row's accent key. The harness step (`online_login_ours.chat_line`,
   `online_match_ours --chat`, `scripts/parity/control_round_chat.sh`) types a line and sends it (rounds 2 and 3).
2. With A hosting and B joined, a line A types appears in B's chat panel and B's in A's (rounds 2 and 3, both
   exes).
3. **The Sprint 11 receive wrap (`chatFanoutRecv` 0x2f4ef0) is not on that path.** Its first-call line never
   printed on either instance in three rounds (six chat lines received). The function is one of the three
   callbacks the `MediusInit` UI action hands the network library, and its body only posts chat types 2 and 1 to
   the HUD message line. Neither is the shell's chat method `FUN_001f4d20` (round 3). The function that receives a
   game-lobby chat line from the network is **not identified**.
4. What the panel draws is not established either: the 0x80-byte records of the briefing-room list (`0x44f568`),
   which the Task 2b list wrap walks and which `FUN_001f5020` fills through the game's own terminating copy, are
   one candidate; the game lobby may keep its own.
5. R221: in the loaded preset (`Default`, `*(0x4415a8)` = `0xd4f340` on r0001), action 0x0a is bound to slot 0x0d and
   action 0x0b to slot 0x07, in the lobby and in the round, on both instances, all three rounds.

**Owed (for the controller to rank):**

- #26's bar as written cannot be met by any run: it names a line from a function a game-lobby chat line does not pass
  through (briefing-room and in-round chat untested). Before a harness run can prove the receive bound, the receive function has to be found (a trace of
  the libnetb receive path down to the chat message's handler, or a `PS2X_WATCH` on the panel's record while a
  line arrives), and the wrap moved or added there -- a runtime change with its tests and a gate. The harness step
  is ready for that run: `bash scripts/loop_lock.sh run <owner> -- bash scripts/parity/control_round_chat.sh`.
- A send path the trace did not cover, named by the review: `SendChatText` (`0x3dd664` -> `FUN_0027cb80` -> `FUN_002f4860`), beside `SendMediusChat`; the '(All)' prefix and 'VOICE CHAT ALL' on B's screen point at game-room chat, which may be DME rather than MLS -- the next trace starts there.
- KNOWN §1's "the chat receive path is bounded on the client" is narrowed to what is shown: the wrap installs on
  every launch, and it did not see the lobby chat lines of these rounds.
- Which physical button each slot byte is (the pad-state layout `FUN_002c64e0` indexes); the talk flag's other
  gates, since Sprint 8 held every pad bit and the flag never moved while both talk actions were bound.

**Rulings of my own, recorded:** O2-R1 (section 2: the peek reads through the pointer, not R221's literal pair).
O2-R2 (round 2: #26 is not closed on screenshots against a bar that names the wrong function). O2-R3: the budget of
three rounds was spent on the step, the crossing, and the path; the fourth experiment (finding the receive function)
is static work first and a runtime change after, not another harness round tonight.
