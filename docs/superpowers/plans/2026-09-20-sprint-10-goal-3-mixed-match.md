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

- [x] 1. `Shell.target` / `press_hold_s`; `Pcsx2Shell`; the `login|host|join|ready` driver; four tests (`f07bc76`).
- [x] 2. **The first verified PCSX2 login -- PASSED 2026-09-20 ~14:40 UTC** (`logs/parity/s10_pcsx2_login1`, the
      hosted server through the DNS stub, `logs/s10_pcsx2_login1.sh`): boot read to the main menu after 3 presses
      (the blind recipe pressed 4), ONLINE lit and read, the login screen, a persona created on the card through the
      verified on-screen keyboard (6 glyphs read back), CONNECT focus read, the EULA, the lobby, the briefing room --
      `LOBBY class=ok`, exit 0, 264 s, every step `verified=True attempt=1`. So the detectors cut from our renderer
      read the console's text at the 640x448 client without a single new reference. `socomq` now exists on B's card
      (`--existing` from here).
- [ ] 3. **Leg 1, verified** (`scripts/parity/mixed_match2.sh`: ours hosts through `online_match_ours --foreign-b`,
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
      - (c): running as this is written -- the first run in which every part is in place.
      The movement half of the bar: ours' walk is read from its own peek (`0x416054:3`); the console's from PINE
      (`cam_poll --port 28012`); "seen by the other" needs the peer entity's position in each guest -- the next
      reading (research/18 section 3.5 has the local half).
- [ ] 4. **Leg 2, reversed:** PCSX2 hosts (`pcsx2_shell host A`), ours joins (`online_login_ours` with join). Same bar.
- [ ] 5. **The parked-opponent row** (KNOWN section 2): with PCSX2 as the parked side, does ours' mover starve? One
      leg-1 round with PCSX2 standing still through ours' walk answers it; the row is settled either way.
- [ ] 6. Records: KNOWN section 1 rows for what each leg proved, the spec's Goal 3 marked, this file's boxes.

## Rulings

None yet. R179 is the next free number.
