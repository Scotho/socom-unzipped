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
| `l2r1_A.txt` | `logs/run_A_20260913_230442.log` (ladder launch 2, Frostfire, research/22 "Ladder launch 2"; archived under `D:/socom_archive/acceptance/s5_ladder2/`, manifest `docs/research/assets/22-first-kill-evidence.txt`) | 556.05-626.4 | 32 (~8 s); **2** over 581.05-591.05 | **the acceptance PASS, round 1**: the killer's side -- R1 burst, `total_mp_kills` 0 -> 1 and `aiteam_08` 1 -> 0 at the death, `player_team` 0, `+0x1044` 1.0 throughout; `mp_round_count` 0 -> 1 ~33 s later, the clock restart |
| `l2r1_B.txt` | `logs/run_B_20260913_230442.log` (same launch) | 550.45-620.8 | 32; **3** over 568.45-570.45, **2** over 575.45-585.45 | the victim's side: `+0x1044` 1.0 -> 0.298 -> 0.0 and `+0xF7A` 1 -> 2 on the death row (B clock 580.45), `aiteam_08` 1 -> 0, `player_team` 8, the same round step and restart |

Sizes: 19-33 KB each for 8c/3c (a 4 Hz peek row of the kept items is ~1 KB; the 3c files are mostly pad lines);
44 KB and 103 KB for `l2r1` (B's rows carry more bytes). The `l2r1` windows run from the death -30 s to the
restart +2 s with a finer stride only where the scorer reads a guest-clock endpoint or pairs rows (`make()`'s
`dense` spans; the stride changes only at a kept anchor, so index interpolation stays even). Rounds 2 and 3 of
the same launch would add ~150 KB each and are not included; the full logs score them `KILL` too (archive).

Verdicts (`python -m tools_py.parity.verdict_replay <A> <B> --offset-b <s>`): `NO-KILL no-death` on
the 8c and 3c pairs; `KILL killer=A victim=B t=141.33 round=1` on `l2r1` at `--offset-b 5.600` (with
`--per-round`: that line, then `NO-KILL no-death round=2`), attribution max 3-D 29.15 against the full logs'
29.22. The full ladder-2 logs (MoveScale #0 alignment, B + 5.60 s) score rounds 1-3 `KILL` and round 4
`NO-KILL no-death`, rows A/B peek 4932/4910, actor 3228/3228, `total_mp_kills` 4920/4899. On the full logs (MoveScale #0 alignment) the same, with row counts A/B peek 3188/3166,
actor 1520/1521, valves 3177/3155 (8c) and peek 2770/2744, actor 1204/1202, valves 2759/2733 (3c) --
research/21 §8.2 and §9.3's numbers.
