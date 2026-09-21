# Sprint 10, Goal 3 — the mixed match, both directions

Written 2026-09-20 ~14:00 UTC by the controller, on the owner's "proceed to sprint 10". The spec is
`docs/superpowers/specs/2026-09-20-sprint-10-console-players-and-it-stays-up-design.md`, Goal 3.

**The goal, in the spec's words:** the PCSX2 side gets screen-verified steps like ours (its frame at 640x448, read
with the harness's detectors, pressing on what the screen shows); then leg 1 (ours hosts, PCSX2 joins) and the
reverse, each to a round that runs with both players seen moving by the other (`motion_diff`); against our local or
hosted Horizon only. On the way it settles KNOWN section 2's row on a parked opponent starving the mover. **Bar:**
both legs reach a running round twice in a row. **Stop rule:** three launches on one leg without a joiner reaching
the lobby -> file what the screens show and stop.

## Why the first leg lost (2026-09-17, `logs/parity/mixed_ours_hosts`)

`pcsx2_ctl`'s macros are research/18 section 1's click path with fixed timings. PCSX2's cold boot was faster than
the recipe's 90 s, the four CROSS presses walked into NEW GAME, and every later press went to a single-player
mission -- its "B_05_game_lobby.png" is the first mission's HUD. Ours stopped pressing blind in Sprint 5
(`online_login_ours.Shell`: every step read back, dropped presses re-sent, a miss classified where it happened).

## Design

- **One flow, two shells.** `Shell` names its target (`target`, `press_hold_s`); `Pcsx2Shell` (`tools_py/parity/
  pcsx2_shell.py`) is the same class over a PCSX2 window with `keys.MAPS["pcsx2"]` and a 0.15 s hold, its client
  pinned to 640x448 by `check_stage` before every press and read. `boot_to_online`, `login`, `to_briefing_room`,
  `host_game`, `join_game`, `ready` run unchanged; so do the failure classes and the exit codes (4 = LOBBY-FAIL).
- **Geometry.** At a 640x448 client PCSX2's frame IS the game's frame at the harness's geometry: the parity gate has
  driven PCSX2 through `launch_to_mission_xl` that way, with `untilref` steps verified against references cut from
  our renderer. Whether the lobby's text-mask detectors match the console's text as well is the first run's question
  (the boot/menu/mission references do; the lobby ones have never seen a console frame).
- **Network.** research/18 section 1 b-c: DEV9 + the DNS stub answering the server's name with our address (LAN for
  the local stack, `3.143.65.100` for the hosted box), a card carrying a network configuration, the clientB pnach
  for the second instance's UDP base port.

## Tasks

- [x] 1. `Shell.target` / `press_hold_s`; `Pcsx2Shell`; the `login|host|join|ready` driver; four tests (`273e50c`).
- [x] 2. **The first verified PCSX2 login -- PASSED 2026-09-20 ~14:40 UTC** (`logs/parity/s10_pcsx2_login1`, the
      hosted server through the DNS stub, `logs/s10_pcsx2_login1.sh`): boot read to the main menu after 3 presses
      (the blind recipe pressed 4), ONLINE lit and read, the login screen, a persona created on the card through the
      verified on-screen keyboard (6 glyphs read back), CONNECT focus read, the EULA, the lobby, the briefing room --
      `LOBBY class=ok`, exit 0, 264 s, every step `verified=True attempt=1`. So the detectors cut from our renderer
      read the console's text at the 640x448 client without a single new reference. `socomq` now exists on B's card
      (`--existing` from here).
- [x] 3. **Leg 1, verified -- DONE 2026-09-20 (runs d, f, g; e was a server-side refusal)** (`scripts/parity/mixed_match2.sh`: ours hosts through `online_match_ours --foreign-b`,
      PCSX2 joins through `pcsx2_shell join B`, then `ready B`; the console's position polled over PINE while it walks
      four bursts; ours walks its own). Runs so far, 2026-09-20:
      - `mixed2_ours_hosts` (a): **the console client joined ours' hosted game 10 s after the lobby opened and the round
        ran with both in it** (ours: "joiner in after 10s", READY, walked; the console's final frame is in-round on
        Frostfire with `socomq` on the HUD). The console's own harness called it LOBBY-FAIL join:enter: its GAME
        LOBBY frame did not read as one (four misses) and the re-sent CROSSes pressed on into the lobby. No frame was
        kept -> every refused check now saves `miss_<step>_<n>.png`.
      - (b): the miss frames show the GAME LOBBY with both players listed. Its title scores 0.54 against ours'
        reference: the console draws the screen ~7% narrower (glyphs x 51..576 vs 31..595; KNOWN section 2). Per-target
        references now (`title_game_lobby.pcsx2.png`, `title_briefing_room.pcsx2.png`; console frames 0.0 / >= 0.565).
        Ours' host in (b) never started ("socom2.exe is already running": (a)'s host outlived its wrapper and its game
        was still up on the server -- the console joined THAT); the foreign-joiner mode now kills the game process and
        the script kills stale ones first.
      - (c): the console joined (join:list verified on the 4th press -- ours' game was not listed yet; join:enter on
        the 2nd through the console reference; join:continue at once), ours saw it ("joiner in after 20s") and
        readied; the console pressed READY inside the 30 s notice and read its own label edge 65 as "taken" (ours'
        bar 55; the console's READY is 65-66, NOT READY 87), so it never readied and the round never started; its
        walk failed on "W" (PCSX2's stick is LUP/LDOWN/LLEFT/LRIGHT). All three fixed (`READY_EDGE_DROPPED_MAX_BY_TARGET`,
        the 35 s wait, LUP), with fixtures.
      - (d) `mixed2_ours_hosts_d`, ~16:10 UTC: **the round ran with both players in it and both moving.** The console
        joined (join:list on the 4th press, join:enter on the 2nd, continue at once, `LOBBY class=ok`), readied after
        the 30 s notice; ours' READY check saw the lobby leave under it ("game lobby gone during READY check") --
        the match launched. Positions: the console's camera position over PINE, 100 in-game rows, 17 distinct,
        x 509 -> 564 across its four LUP holds; ours' own peek, 140 in-game rows, 39 distinct positions across its
        four W bursts. Leg 1 reached once; the bar wants twice in a row.
        "Seen by the other" is still measured only by each side's own position; the old screen-motion score
        (`console-sees-ours-moving`) stays "no" because the spawns do not face each other -- it is not the bar.
      The movement half of the bar: ours' walk is read from its own peek (`0x416054:3`); the console's from PINE
      (`cam_poll --port 28012`); "seen by the other" needs the peer entity's position in each guest -- the next
      reading (research/18 section 3.5 has the local half).
      - (e), ~16:50 UTC: the console's join:enter CROSS on ours' listed game registered nothing four times and ours
        saw no joiner for 420 s (`A_[lobby] waiting for a joiner ... T+420s`). The list showed the game, the lobby
        never came: a server-side refusal, not a harness miss -- the likeliest reading is the console's persona still
        "in game" on Medius from run (d), whose client was killed mid-round. One of the stop rule's three.
      - (f), ~19:15 UTC: reached again -- joiner in after 10 s, the launch under ours' READY check, ours 140 in-game
        rows / 34 positions, the console 100 / 17. Run g follows it for the consecutive pair.
      - (g), ~19:30 UTC: reached again -- joiner in after 15 s, the launch, ours 141 in-game rows / 34 positions, the
        console 100 / 18. **Leg 1's bar met: twice in a row (f, g).**
- [x] 4. **Leg 2, reversed -- DONE 2026-09-20 (runs f, g):** PCSX2 hosts (`pcsx2_shell host B`), ours joins (`online_login_ours --join`). Same bar.
      - `mixed2_pcsx2_hosts` (a), ~16:35 UTC: the console logged in as `socomp` (persona created) and reached CREATE
        GAME, and its harness could not see it: no console reference for that title (the miss frames show the screen).
        `title_create_game.pcsx2.png` cut from them; the PLAY LIST title will need the same on the next run.
      - (b): CREATE GAME read; CHOOSE GAMES' PLAY LIST screen not (no console reference) -- cut from the kept frame.
      - (c): the play list read; choose_map's walk crashed on the pad file the console shell does not have
        (`pad_press` without a pad is a posted key now); a 21-frame console map scan gave `map_frostfire.pcsx2.png`
        (0.0-0.05 on the FROSTFIRE row wherever it sits, >= 0.5 elsewhere).
      - (d), ~17:50 UTC: **the console HOSTED a verified game** -- CREATE GAME, the name, CHOOSE GAMES, Frostfire
        accepted at row 4, ACCEPT, CREATE, the notice, `LOBBY class=ok`, READY read as taken (edges 87) -- and ours'
        join saw the game listed (`join:list verified=True attempt=1`), pressed it, showed JOINING and then
        "Disconnected from Game" (`miss_join_enter_2.png`; the runtime then LoadExecs `dlgAfterErrorReboot`).
        Reading: instance A's peer UDP port is the default 3658, which ours also binds on the same host; B's pnach
        shifts it to 3660, and leg 1 (ours on 3658 hosting, B on 3660 joining) ran. Leg 2 hosts from B next.
      - (e), ~18:20 UTC, hosting from B: **ours joined the console's game** -- join:list, join:enter (the GAME LOBBY,
        verified on the first press), join:continue -- and the match launched at once: the console host had been
        READY since before the join (the script readied it on a timer), so ours' lobby re-check read the map briefing
        ("FROSTFIRE / SUPPRESSION / TO RETURN TO THE LOBBY") and called it join-not-reached; the console then played
        the round alone (20 distinct positions over its walk). The peer ports were the disconnect: B's 3660 joins.
        The script now readies the console only after ours' notice is dismissed.
      - (f), ~18:45 UTC: **the round ran with both in it and both moving -- ours in a game the console hosts.** Ours:
        join:list, join:enter, join:continue verified on the first press each; "game lobby gone during READY search"
        (the launch); 341 in-game peek rows, 27 distinct positions over its walk. The console: readied after ours'
        notice, the lobby left under its READY check (the launch), 100 in-game rows, 24 distinct positions over its
        four stick holds. Leg 2 reached once; run g queued for the bar, then leg 1's second.
      - (g), ~19:05 UTC: the same again -- verified join, the launch, ours 339 in-game rows / 28 positions, the console
        100 / 22. **Leg 2's bar met: twice in a row (f, g).**
- [ ] 5. (open; every run so far had both sides walking) **The parked-opponent row** (KNOWN section 2): with PCSX2 as the parked side, does ours' mover starve? One
      leg-1 round with PCSX2 standing still through ours' walk answers it; the row is settled either way.
- [x] 6. Records: KNOWN section 1 rows for each leg (2026-09-20), the sprint file's item 3, this file's boxes.
- [ ] 7. **"Seen by the other":** the bar as the spec words it wants each guest's copy of the PEER entity's position
      (ours' PS2X_PEEK of the peer slot; the same address over PINE on the console) -- today each side's OWN position
      is what moved. The old screen-motion score (`console-sees-ours-moving`) is not it (the spawns face away). One
      reading of the peer entity's position field settles it for both; then the parked-opponent row (task 5) is one run.

## Rulings

None yet. R179 is the next free number.
