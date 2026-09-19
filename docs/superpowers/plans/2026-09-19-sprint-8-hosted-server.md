# Sprint 8 Goal 12 — The Hosted Server, on a Machine That Exists: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Horizon instance the project hosts, reachable from the internet, that the launcher lists as *SOCOM Unzipped (project server)* and that a driven two-instance match starts a round on (the bar) and registers a kill on (the hope). Owner's order, 2026-09-19: "Lightsail 2GB. Setup a sprint to create the machine and bring the server online, making the required linux changes."

**Architecture:** One AWS Lightsail instance (Ubuntu 24.04, 2 GB / 2 vCPU, us-east-2, static IP). The Horizon binaries are framework-dependent `net9.0` and run unchanged under `dotnet <dll> <configdir>`; only the glue is Windows. The Linux glue is three files under `server/linux/`: four systemd units, `horizon-ctl.sh` (the PowerShell script's verbs, including the six-field advertised-address rewrite), `install.sh`. The database is seeded on Windows and copied up. The machine's particulars live git-ignored under `vm/lightsail/` (the VM's convention) with a memory note.

**Spec:** `docs/superpowers/specs/2026-09-18-sprint-8-linux-and-finish-design.md` — Goal 12. **Required reading:** `server/README.md` (ports, the advertised address, simulated mode), `vm/lightsail/README.md` (the door; git-ignored, on this host only), this plan's Global Constraints.

## Global Constraints

- **Shared checkout.** Session `socom-pc-d1` builds and launches from this tree on `sprint-8`. Never `git checkout` another branch here. Commits: `git commit -m "…" -- <paths>`, explicit pathspecs, never `git add -A`; `server/config/simulated.db` never staged; `ONBOARDING.md` untracked; nothing under `vm/` ever staged.
- **Files that are not ours** (d1's, in flight until its launcher commit): `ps2xLauncher/src/main.cpp`, `ps2xLauncher/CMakeLists.txt`, `ps2xLauncher/src/ui/**`, `ps2xLauncher/assets/**`, `scripts/embed_font.py`, `scripts/make_portable.sh`, `ps2xTest/src/launcher_tests.cpp`. The preset change (Task 5) is **made by d1** from the address and note we send. `docs/CURRENT_SPRINT.md` and `docs/HUMAN_TASKS.md`: append-only blocks.
- **Host launches.** One at a time, through `scripts/run_detached.sh` under the loop lock, and a build overlapping a driven launch has already cost a gate: the two online rounds (Task 6) run **in d1's queue with its builders held** (its offer (a)), or in a window it declares "clear". This session starts no launch, no `build.sh test`, no gate on its own.
- **Money.** The account is on the free plan: $78.46 of credit on 2026-09-19, expiry 2027-03-05. The instance is the only billable thing this goal creates (bundle ~$12/month; the static IP is free while attached; automatic snapshots bill by size, cents). Anything else that bills needs the owner's word. Stop rule: burn above $15/month.
- **Secrets.** The Lightsail key pair, the static IP's allocation and the DB passphrase stay out of git. The public address itself is public (it ships in the launcher).
- **The community server is not touched.** No connection to PSRewired (memory: psrewired-community-server).
- Rulings on the owner's behalf are numbered from **R109**.

## Task 1 — the machine

- [x] `aws lightsail get-bundles --region us-east-2` → pick the 2 GB Linux bundle with IPv4 (expected `small_3_0`, $12); `get-blueprints` → `ubuntu_24_04`. Record both ids in `vm/lightsail/README.md`.
- [x] `create-key-pair --key-pair-name socom-unzipped` → private key to `vm/lightsail/keys/socom_unzipped.pem` (ACL: the owner only).
- [x] `create-instances --instance-names socom-unzipped-server --availability-zone us-east-2a --blueprint-id ubuntu_24_04 --bundle-id <id> --key-pair-name socom-unzipped`; wait for `running`.
- [x] `allocate-static-ip --static-ip-name socom-unzipped-ip`; `attach-static-ip`. **The address is the deliverable of this task.**
- [x] `put-instance-public-ports` (it replaces the whole set): 22/tcp from the owner's current public address `/32`; 10071, 10073, 10075, 10078/tcp; 10070/udp; 50000-50100/udp from anywhere. 10077 absent. Verify with `get-instance-port-states`.
- [x] `enable-add-on` AutoSnapshot (daily). Ruling R109 if it is left off.
- [x] `vm/lightsail/README.md` + `vm/lightsail/ssh.sh` (the door: `ssh -i keys/… ubuntu@<ip> "$@"`), and the memory note `lightsail-socom-unzipped-server`.

## Task 2 — the Linux glue, in the tree

- [x] `server/linux/horizon-ctl.sh`: `start|stop|restart|status|show-ip|public-ip <addr>`. `public-ip` rewrites exactly `medius.json: PublicIpOverride, NATIp`, `dme.json: PublicIpOverride`, `muis.json: every Endpoint`; never `dme.json: MPS.Ip`; validates IP-or-hostname with the PowerShell script's rule; refuses to write a file that does not parse as JSON afterwards (`python3 -m json.tool`); prints one `<file>: <field> -> <addr>` line per change. `status` = `ss -ltnu` against the port table plus `systemctl is-active` for the four units.
- [x] **Test first:** `tools_py/tests/test_horizon_ctl.py` (unittest, runs `bash server/linux/horizon-ctl.sh public-ip … --config-dir <tmp copy of server/config/*.json>`): the six fields change, `MPS.Ip` does not, every other byte is preserved, a bad address is refused with nothing written, a second run reports "already". Skips where `bash` is absent. RED before the script exists.
- [x] `server/linux/horizon-{nat,muis,medius,dme}.service`: `User=horizon`, `WorkingDirectory=/opt/socom-unzipped-server`, `ExecStart=/usr/bin/dotnet horizon-server/<Proj>/bin/Release/net9.0/<Proj>.dll /opt/socom-unzipped-server/config`, `Restart=on-failure`, `RestartSec=5`, `Environment=DOTNET_gcServer=0 DOTNET_TieredPGO=0`; DME `After=horizon-medius.service` with `ExecStartPre` polling 10077 for up to 30 s; `horizon.target` groups the four.
- [x] `server/linux/install.sh` (run as root on the box): installs `dotnet-runtime-9.0` (Ubuntu's feed, else Microsoft's), creates `horizon`, lays the folder under `/opt/socom-unzipped-server`, installs the units and a logrotate rule for `logs/*.log`, enables `horizon.target`. Idempotent.
- [x] `scripts/make_server_zip.sh`: also ships `linux/`; the README.txt it writes gains the Linux five-liner. `server/README.md`: a "Hosting it on Linux" section; the status line updated when Task 4 has a result.

## Task 3 — the server on the box

- [x] Build check: `server/horizon-server/*/bin/Release/net9.0/*.dll` exist and are current (`start-servers.ps1 -Build` otherwise — a dotnet build, not a game build; still ask d1 for quiet if one of its launches is running).
- [x] `bash scripts/make_server_zip.sh`; seed a database for the box into a scratch directory (`seed-simulated-db.ps1` with an output path; if it has none, seed in place with the local servers stopped, copy, restore the local file byte for byte — `simulated.db` is the owner's and unstaged). `CreateAccountOnNotFound=True`, `EnableEncryption=False` as on the LAN.
- [x] `scp` the folder and the database; `sudo bash linux/install.sh`; `horizon-ctl.sh public-ip <static ip>`; `start`; `status` shows 10071, 10073, 10075, 10077, 10078/tcp and 10070/udp.
- [x] `free -m` and `systemctl status` after ten minutes: resident set per process recorded in the README (the 2 GB sizing was an estimate; this is the measurement). `sudo reboot`; the five listeners return unattended.

## Task 4 — reachable from outside (bars 1 and 2)

- [x] From this host: `Test-NetConnection <ip> -Port` for the four public TCP ports (open) and 10077 (closed); a UDP datagram to 10070 gets the echo (a ten-line Python socket script in the scratchpad; the NAT service answers with the sender's address — record the answer).
- [x] `Server.Test` (the repo's scripted client, README §"What was verified" item 4) with its `config.json` pointed at the public address: the MAS handshake completes through `SERVER_CONNECT_COMPLETE`. Server side: `journalctl -u horizon-medius` shows the same exchange.
- [x] Record both in `server/README.md` ("Unverified on a real hosted machine" paragraph rewritten to what was verified, with the date).

## Task 5 — the launcher's list (bar 3; d1 makes the edit)

- [ ] Message d1: the address, and the preset's note text (`"the project's hosted server (us-east)"`). d1 changes `kServerPresets[1]` in `launcher_config.h`, the default `serverPreset` to `"unzipped"` per the Sprint 7 spec, and the test in `launcher_tests.cpp` (the preset's address is not a `_TBC` placeholder and parses as an IP or hostname; `effectiveServer` of a default config is that address), after its launcher commit lands.
- [ ] Proof: the launcher's `--screenshot` of the ONLINE page showing the preset and the address (d1's tool, d1's run). `docs/HUMAN_TASKS.md`: the "two server addresses" item gets a dated line — ours is supplied; the community's stays the owner's (and Goal 10's).

## Task 6 — a match on it (bar 4; in d1's queue)

- [ ] Message d1 the address; it runs, under the lock with builders held: (1) the control round (`scripts/parity/online_control_round.sh`-shape, `SOCOM_SERVER_IP=<ip>`), (2) the kill round (the ladder). Expected evidence per round: both instances' lobby reached, game created and joined, the round's start frame; for (2) the kill line.
- [ ] While each runs, this session watches the box: `journalctl -f` for the four units, `ss -lun | grep 500` for the per-client DME sockets, the advertised address in each reply. Saved to `logs/parity/<stamp>/server-side.log`.
- [ ] Verdict written where the round's is: round started Y/N, kill Y/N, and what the hosted path exercised for the first time (both clients behind one NAT — the hairpin case; the clock skew between the host and the box). Findings to `docs/KNOWN.md` **through d1** (one writer).
- [ ] Stop rule (spec): no round start here but one on the LAN server with the same exe → stop at the packet-level difference and file it.

## Task 7 — close-out

- [ ] Commit (pathspecs): `server/linux/**`, `server/README.md`, `scripts/make_server_zip.sh`, `tools_py/tests/test_horizon_ctl.py`, the spec, this plan. Python suite green first (`python -m unittest` for the new test file alone is lock-free; the full suite waits for a quiet host).
- [ ] `docs/CURRENT_SPRINT.md`: the Goal 12 block's result line. `docs/HUMAN_TASKS.md`: the owner's own match from the launcher against *SOCOM Unzipped*, from a second network if one is to hand.
- [ ] Memory notes updated: `packaging-decisions` (the host is no longer TBD), `lightsail-socom-unzipped-server`.
- [ ] The credit re-read (`aws freetier get-account-plan-state`) a day later against the $12/month estimate.

## Rulings made on the owner's behalf

- **R109 (2026-09-19).** The launcher's default preset moves from `custom` to `unzipped` now that 3.143.65.100 is real — why: the Sprint 7 spec said the default switches "when ours is real", and a stranger's first run should reach a lobby without typing an address; d1 added a guard so a `config.json` from before the picker (a typed `server`, no `serverPreset`) stays `custom` with the player's own address — cost if wrong: a first login goes to a server that is down or gone when the credit runs out (2027-03-05 at the latest); the ONLINE page still offers Custom.
- **R110 (2026-09-19).** The static IP ships in the launcher rather than a DNS name — why: no domain is owned and buying one is the owner's money; `horizon-ctl.sh public-ip` and the preset both take a hostname, so moving is one line each — cost if wrong: a change of host means a new launcher build for every player.
- **R111 (2026-09-19).** Task 2's test was written before the script but never seen RED (the script followed in the same step); its six cases were run GREEN only — why: the rule's purpose (a test that can fail) is served by the refusal and byte-preservation cases, which fail against a naive `sed` — cost if wrong: a vacuous assertion; mitigated by the on-box run printing the same five change lines the test expects.
- **Task 1-4 results (2026-09-19).** Instance `socom-unzipped-server` (`small_3_0`, `ubuntu_24_04`, us-east-2a), static IP 3.143.65.100, AutoSnapshot on. From the owner's host: 10071/10073/10075/10078 tcp open, 10077 closed, 10070/udp echoes the sender's public address; `Server.Test` completes the MAS handshake for app id 10472 (the server's journal shows HELLO through CONNECT_ACCEPT_TCP and the APP exchange); 335 MB resident across the four processes; a reboot brings all six listeners back unattended. SSH on IPv4 is limited to the owner's address; Lightsail's IPv6 rules were left at their defaults (key-only SSH).
