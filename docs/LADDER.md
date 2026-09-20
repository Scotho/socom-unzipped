# The ladder, scheduled -- Sprint 10 Goal 1, "it stays up"

One row per scheduled run of the engagement ladder against the hosted server (two instances on this host, in windows the owner is away). Written by `tools_py/parity/ladder_ledger.py` from `logs/ladder/ledger.jsonl`; a person commits it. The bar: **7 consecutive runs with no LOBBY-FAIL and no CRASH.**

**Runs:** 3  **Lobby rate:** 33%  **Round-start rate:** 100%  **Kill rate:** 25%  **Clean streak:** 1 of 7

| when (UTC) | run | outcome | rounds | usable | kills | best rung | harness | exe sha256 | server |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-20T08:34:39Z | `ladder_20260920_043246` | LOBBY-FAIL create-game:create | 0/4 | 0 | 0 | 0 | `e4fc806e` | `8c05a3e5` | 3.143.65.100 |
| 2026-09-20T13:12:19Z | `ladder_20260920_100713` | LOBBY-FAIL create-game:create | 0/4 | 0 | 0 | 0 | `9596f51e` | `b3abebd5` | 3.143.65.100 |
| 2026-09-20T13:45:54Z | `ladder_20260920_101741` | KILL | 4/4 | 4 | 1 | 3 | `32ba0d12` | `b3abebd5` | 3.143.65.100 |
