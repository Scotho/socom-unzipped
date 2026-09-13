# verdict_replay fixtures (Sprint 5 Task 6 Step 1)

Trimmed raw excerpts of Sprint 5's real run logs, read by `tools_py/tests/test_verdict_replay.py`,
both by `verdict_replay.parse_log` and (in the parser-parity test) by `verdict_core.parse_log`.
`logs/` is gitignored, so `make_fixtures.py` in this folder is the record of what each file holds
and regenerates them (`python tools_py/tests/fixtures/replay/make_fixtures.py`). Files are `.txt`
because `*.log` is gitignored.

## What was kept

Every kept line is verbatim from the source log, in its original order:

- the window runs from the first to the last MoveScale `[call]` line inside the source-clock
  window below, so every kept `[peek]` row lies between two clock anchors;
- MoveScale `[call]` lines only when >= 5 s after the previous kept one (the parsers' anchor
  spacing), plus the last one; other slots and `[ret]` lines dropped;
- every `[socom2-input] state` line inside the window;
- one `[peek]` row in every *stride*, reduced to: the first 10 words of the actor block (word 0 =
  vtable `006691a0`, words 7/8/9 = x/y/z), the item at actor+0x1044 (health), the first word of
  actor+0xF78 (+0xF7A = its byte 2), the value (2-word) and name-bytes (3-word) items of
  `mp_round_count`, `player_team`, `aiteam_00`, `aiteam_08`, `total_mp_kills`, and the statics
  `@4365c0` (guest clock) and `@408f10` (clock string). Tokens, addresses and word order untouched.

Consequences of trimming: row times on a fixture's clock differ slightly from the full log's (fewer
anchors, stride); actor+0xC8 is not covered (the 10-word actor item), so the team-word cross-check
reads "not peeked"; the MoveScale `#0` lines are outside the windows, so tests pass the process-clock
offset explicitly (B + offset = A: 8c 5.80 s, 3c 6.00 s, each side's MoveScale #0 in the full logs,
research/21 §8.3 and §9.1).

## Files

| fixture | source | window (s, source clock) | stride | what it shows |
|---|---|---|---|---|
| `l8c_A.txt` | `logs/run_A_20260913_132843.log` (launch 8c, Vigilance, research/21 §9) | 764.0-800.0 | 8 (~1.8 s) | the **clock round-end negative control**: clock string `00:14` -> `00:00` (from 778.9 on the fixture clock) -> `05:58`; `mp_round_count` 0 -> 1; `total_mp_kills` 0, `aiteam_00/08` 1, `player_team` 0, `+0x1044` 1.0, `+0xF7A` 1 on every row |
| `l8c_B.txt` | `logs/run_B_20260913_132843.log` (same launch) | 758.0-795.0 | 8 | the same on the joiner: clock string stops at `00:09` (never `00:00`), then `05:58`; `mp_round_count` 0 -> 1 at the same aligned moment; `player_team` 8; nothing a kill moves stepped |
| `l3c_A.txt` | `logs/run_A_20260913_115809.log` (launch 3c, Frostfire, research/21 §8) | 393.0-696.0 | 80 (~20 s) | a whole control round with no contact: `05:39` ... `00:58`, no valve step, `+0x1044` 1.0 |
| `l3c_B.txt` | `logs/run_B_20260913_115809.log` (same launch) | 387.0-690.0 | 80 | the same on the joiner (`player_team` 8) |

Sizes: 19-33 KB each (a 4 Hz peek row of the kept items is ~1 KB; the 3c files are mostly pad lines).

Verdicts (`python -m tools_py.parity.verdict_replay <A> <B> --offset-b <s>`): `NO-KILL no-death` on
both pairs. On the full logs (MoveScale #0 alignment) the same, with row counts A/B peek 3188/3166,
actor 1520/1521, valves 3177/3155 (8c) and peek 2770/2744, actor 1204/1202, valves 2759/2733 (3c) --
research/21 §8.2 and §9.3's numbers.
