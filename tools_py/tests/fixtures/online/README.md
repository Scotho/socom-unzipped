# Online verdict fixtures (Sprint 5 Task 3 Step 0)

Trimmed excerpts of Sprint 4's real run logs, read by `tools_py/tests/test_online_verdict.py`.
`logs/` is gitignored, so `make_fixtures.py` in this folder is the record of what each file holds
and regenerates them (`python tools_py/tests/fixtures/online/make_fixtures.py`). Files are `.txt`
because `*.log` is gitignored.

## What was kept

Lines of the source log inside a time window (on that log's own `[call] <t>s` clock), of these
kinds only, in their original order:

- `[peek]` rows, reduced to the `@416054` camera item (3 words) and the **first 10 words** of the
  item whose word 0 is the actor vtable `006691a0` (words 7/8/9 = x/y/z). Other items dropped;
  tokens are verbatim.
- `[call]` / `[ret]` lines (only `MoveScale` was traced in these launches).
- `[socom2-input] state` lines, plus the continuation line of a state line that another stream's
  write tore in two (none fell inside these windows; `run_B_20260912_232834.log` has 2 in the whole
  log).

Consequence of trimming: a fixture has fewer `[call]` anchors than its source, so its clock can
differ from the full log's by a few hundredths of a second (the hold times below show it). The
frost1 windows contain no `[call]` line at all (frost1 logged MoveScale only at t = 371.4-372.0 s),
so their clock starts at 0 at the first kept row at the nominal 0.25 s/row.

## Files

| fixture | source (launch script / driver transcript) | window (s) | what it shows under `verdict_core` |
|---|---|---|---|
| `frost1_A.txt` | `logs/run_A_20260913_004754.log` (`logs/s4_task8_frost1.sh`, `logs/parity/drive_task8_frost1.txt`) | 399.0-427.0 | first two 1.5 s facing probes: net 0.00, snap 0.00, drift 0.00 (first) -> FAIL, FAIL -> side NO-CONTROL |
| `frost1_B.txt` | `logs/run_B_20260913_004754.log` (same launch) | 393.0-421.5 | same: net 0.00 on both probes -> side NO-CONTROL |
| `kill2_A_probe.txt` | `logs/run_A_20260912_231341.log` (`logs/s4_task8_kill2.sh`, `logs/parity/drive_task8_kill2.txt`) | 446.0-463.5 | facing probe 1.47 s on the fixture clock (1.51 s on the full log): net 60.35, snap 1.18, drift 0.00 -> PASS |
| `kill2_B_probe.txt` | `logs/run_B_20260912_231341.log` (same launch) | 440.0-458.0 | facing probe 1.51 s on the fixture clock (1.49 s on the full log): net 64.01, snap 0.72, drift 0.00 -> PASS |
| `kill2_A_closest.txt` | `logs/run_A_20260912_231341.log` | 664.0-694.0 | closest approach (A t = 679.2 s): 3-D 45.9, dy 43.9 |
| `kill2_B_closest.txt` | `logs/run_B_20260912_231341.log` | 658.0-688.0 | the same moment on B's clock (B + 5.8 s = A; each side's MoveScale #0: A 418.5, B 412.7). B's sampler ran at ~0.6 s/row here (50 rows in 30 s), against 0.25 s/row earlier in the same log |
| `kill3_B_probes.txt` | `logs/run_B_20260912_232834.log` (`logs/s4_task8_kill3.sh`, `logs/parity/drive_task8_kill3.txt`) | 440.0-465.0 | both facing probes. Probe 1 (1.46 s on the fixture clock, 1.50 s on the full log): net 66.93, snap 1.84, drift 0.00 -> PASS on ACTOR rows, while the `@416054` camera record stayed frozen (the driver's `d=0.00`). See the Step 0 report's finding |

The contact fixtures carry no `0x408f10` clock peek (Sprint 4 never peeked it), so the contact
scorer answers `NO-DATA` over them unless a clock is supplied.
