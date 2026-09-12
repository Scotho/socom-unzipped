# 18 — Online round start

Why the two-instance online match has been frozen at "STARTING ROUND 1 OF 11" since 2026-09-10.

---

## 1. S0 — does the freeze reproduce on PCSX2 against our server? (2026-09-12)

### Verdict: **runtime implicated.** PCSX2 plays.

Two PCSX2 instances, driven against **our** local Horizon stack with **our** server configuration,
reached playable online gameplay and ran a full round to completion. "STARTING ROUND 1 OF 11" is a
**transient ~6 s banner** there, not a terminal state: it appears at t+24 s after both players press
READY, is replaced by "OBJECTIVE: ELIMINATE THE TERRORISTS" at t+30 s, and the players then walk,
strafe, turn, aim and shoot normally. At the end of the 6-minute round both instances advanced in
lockstep to **"STARTING ROUND 2 OF 11"** with ammo and timer reset.

Our exe, on the same server, in the same match configuration, sits on that banner forever with only
camera pitch (RY), fire and stance responding (STATUS 2026-09-10 20:10). The console-accurate
reference does not reproduce the defect, so the defect is ours. **S1 goes guest-side.**

The HANDOFF line that motivated this task — "The PCSX2 golden match is the same frozen state" —
is **wrong as a conclusion**, and the STATUS entry it came from says why: the golden pair
(`logs/parity/online/match/A_18_hold05`, `B_20_hold05`) is a pair of *screenshots taken ~1 minute in
with no input ever sent*. Movement was never driven on the reference, so "same frozen state" was
read off two stills of a game that was simply standing still. Treat that line as retracted.

### Evidence

Captures: `logs/parity/s4_pcsx2/` (gitignored). One frame per second per instance from READY
onwards, `A_ready<nnn>.png` / `B_ready<nnn>.png` (t=0 is the READY press), and `A_rend<nnn>.png` /
`B_rend<nnn>.png` over the round-1 → round-2 boundary. Because `logs/` does not survive a clean,
the fifteen cited frames are also tiled into a tracked contact sheet:
**`docs/research/assets/18-s0-evidence.png`**.

| frame | what it shows |
|---|---|
| `A_ready018` | VIGILANCE / SUPPRESSION briefing — the same screen ours reaches |
| `A_ready024` | **"STARTING ROUND 1 OF 11"** over the spawned player, round timer 05:56 |
| `A_ready030` | banner replaced by "OBJECTIVE: ELIMINATE THE TERRORISTS" — ours never gets here |
| `A_ready074` → `A_ready078` | `LUP` 3 s: the player walks forward from the spawn path into the stone wall |
| `A_ready082` → `A_ready085` | `LDOWN` 3 s: walks back out |
| `A_ready085` → `A_ready091` | **the single frame that decides it**: `LLEFT` 3 s moves the player to the plaster building **with the compass heading unchanged** — lateral translation, i.e. LX, the exact control ours ignores. `A_ready097` (`LRIGHT`) brings him back |
| `A_ready127` → `A_ready131` | `RLEFT` 2 s: camera yaw, compass rotates, **position held** — RX without translation |
| `A_ready140` | `RUP` 2 s: camera pitches up to the sky |
| `A_ready151` | `R1`: muzzle flash, ammo 30/30 → 27/30 |
| `B_ready203` → `B_ready207` | client B walks forward too — both clients are playable, not just the host |
| `A_rend055`, `B_rend055` | **"STARTING ROUND 2 OF 11"** on both instances at the same timer (05:57) |

**Controls tested, and how.** Posted key messages (`tools_py/parity/keys.py`, no focus change) against
PCSX2's `[Pad1]` keyboard bindings, one at a time, with a screenshot every second either side:

| control | key | result |
|---|---|---|
| left stick up / LY− (walk forward) | `W` | **works** — position changes |
| left stick down / LY+ (walk back) | `S` | **works** |
| left stick left / LX− | `A` | **works** |
| left stick right / LX+ | `D` | **works** |
| right stick left / RX− (yaw) | `F` | **works** |
| right stick right / RX+ | `H` | **works** |
| right stick up / RY− (pitch) | `T` | **works** |
| right stick down / RY+ | `G` | **works** |
| R1 (fire) | `E` | **works** — ammo 30/30 → 27/30, impact sparks |
| Circle (stance) | `L` | pressed; not conclusively read off the frames (camera was pitched down) — the one control in the list that is *not* proven here |

So every control our exe ignores online (RX, LX, LY) is live on the console reference. Note
`keys.py`'s `pcsx2` map used to carry only the digital buttons; the eight analog entries above (plus
`L3`/`R3`) are now **in tracked `tools_py/parity/keys.py`**, taken from the `[Pad1]`
`LUp/LDown/LLeft/LRight` = `W S A D` and `RUp/RDown/RLeft/RRight` = `T G F H` bindings, so any later
harness can drive movement on the reference. `logs/s4_ctl.py` still re-applies them so it stays
standalone.

### The server's view over the same seconds

`logs/parity/s4_pcsx2/slice-DME.log`, `slice-Medius.log` (sliced from the line counts in
`baseline.txt`, taken immediately before the READY presses).

- Medius: `MediusWorldReport0 … WorldStatus:WorldStaging` once, then 17 × `WorldStatus:WorldActive`,
  plus one `MediusPlayerReport` per player. Exactly the sequence the ours runs produce.
- **DME TCP**, over the match **from the READY press** through the round-1 → round-2 transition:
  **5 `RT_MSG_CLIENT_APP_BROADCAST`, 5 `RT_MSG_CLIENT_APP_SINGLE`, 114 `RT_MSG_CLIENT_ECHO`.**
  All five broadcasts are at initial spawn (`SealObject` for socomp with `mp51_seal1`, `SealObject`
  for socomq with `mp51_terror1`, the turret objects, and the two `00-0F` player records). After
  that the DME TCP channel carries **nothing but ECHO keepalives** — including across the round
  boundary. (Over the full join→end window the broadcast count is 11: six more at lobby/join.)

**Channel caveat, and it matters:** `server/logs/console-DME.log` contains **zero UDP lines** — every
entry is `Server.Dme.TcpServer`. Everything below is therefore proven for the DME **TCP** channel
only, not for the aux-UDP channel at 50000/50001, which this log does not see at all.

Two conclusions follow, and they are the load-bearing part of this note:

1. **The server sends nothing on DME TCP at round start or round advance.** The round state machine
   runs peer-to-peer over the game's own UDP channel (A 3658 ↔ B 3660). A DME-TCP cause for the
   freeze is therefore excluded: Horizon has no "go" message on that channel to fail to send.
2. **The server log cannot tell a playing match from a frozen one — they are byte-profile
   identical.** Counted over the full join→end window and compared against the frozen-ours slice
   (`logs/dme_probe7.txt`), PCSX2-playing and ours-frozen give the **same** profile:
   **11 `APP_BROADCAST` / 30 `APP_SINGLE` / 7 `APP_TOSERVER` / 2 aux-UDP connects each**, with
   identical broadcast opcode histograms (6 × `00-04`, 4 × `00-0F`, 1 × `02-19`). A server whose
   observable output is bit-for-bit the same shape in both cases carries no signal about the
   defect. **Stop using the server log as the discriminator for this class of bug**; the
   discriminator is the peer UDP channel and the guest state above it.

Not measured (no packet-capture tool on this host, and no admin): the **peer UDP packet rate** on
the PCSX2 reference. Ours sits at ~1 packet/s per direction while frozen, and a real match is
expected to stream tens/s. Getting that number off a playing PCSX2 pair would give S1 a hard target
to compare our trace against; it needs npcap/Wireshark or an elevated `netsh trace`.

Unexplained but harmless: DME logs this match as `worldId:11` while Medius reports
`MediusWorldID:12` for the same game. The two components number worlds independently; nothing in
the run depends on them agreeing, and both are internally consistent.

### Recipe — reproducing this from scratch

Host is `192.168.2.10` (the LAN adapter). Everything below is one-off except the last block.

**a. Second PCSX2 install.** `tools/` is gitignored, so this leaves no git noise.

```
robocopy tools\pcsx2 tools\pcsx2_b /E /XD sstates snaps dumps cache logs
```
then in `tools/pcsx2_b/inis/PCSX2.ini`: `PINESlot = 28012` (A keeps 28011) and
`Slot2_Enable = false`; and
`cp scripts/parity/pcsx2/0F6FC6CF.clientB.pnach tools/pcsx2_b/patches/0F6FC6CF.pnach`
(A keeps `scripts/parity/pcsx2/0F6FC6CF.pnach`). Both pnaches are the unconditional DNAS bypass;
B's adds `patch=1,EE,20620678,extended,24040E4C`, the base peer UDP port 3658 → 3660, because two
guests on one host adapter would otherwise both bind 3658/3659 and DME replies land on the wrong
socket. Verify the pnach actually loads: `tools/pcsx2/logs/emulog.txt` must say
`Found 1 game patches in …0F6FC6CF.pnach` / `2 game patches are active` for CRC `0F6FC6CF`. (The
toast "No cheats or patches are found / enabled" that appears when you open EDIT NETWORK
CONFIGURATIONS is about `SCUSNGUI.ELF`, the Sony network-settings ELF on the disc, not about the
game — it is harmless.)

**b. Host redirection.** PCSX2 has no `PS2X_SOCOM2_SERVER` equivalent and **its
`[DEV9/Eth/Hosts]` table is not honoured** (STATUS 2026-09-07 18:45). The redirect that works is
DEV9 + a DNS stub on the host:

- `[DEV9/Eth]` in both inis (already there; template `scripts/parity/pcsx2/PCSX2.ini.dev9-section`):
  `EthEnable=true`, `EthApi=Sockets`, `EthDevice={95852BA5-…}` (the Realtek adapter),
  `InterceptDHCP=true`, `AutoMask/AutoGateway=true`, `ModeDNS1=Manual`, `ModeDNS2=Manual`,
  `DNS1=DNS2=192.168.2.10`.
- `python -m tools_py.parity.dns_stub --bind 192.168.2.10 --answer 192.168.2.10` — answers
  `socom2-prod[.muis].pdonline.scea.com` and `gate1.*.dnas.playstation.org` with the host LAN IP
  and NXDOMAIN for everything else. **No administrator rights needed** (Windows does not reserve
  ports < 1024). Check with `nslookup socom2-prod.pdonline.scea.com 192.168.2.10`, and watch
  `logs/s4_dns_stub.log` for the guest's own queries during the run.
- Horizon must advertise the LAN IP, not loopback — `server/config/{medius,dme}.json`
  `PublicIpOverride`/`NATIp` and `muis.json` `Universes[].Endpoint` are all already `192.168.2.10`.
  Bring the stack up with `powershell -NoProfile -File server/start-servers.ps1` (`-Status` to check
  the five TCP listeners).

**c. Network configuration on the memory cards.** This is the step that is easy to miss: the cards
in `tools/pcsx2*/memcards/` carry the SOCOM II save but **no** PS2 network configuration, so ONLINE
stops at "No NETWORK CONFIGURATION present on the memory card in slot 1". Make one once, in
instance A: LOGIN screen → **EDIT NETWORK CONFIGURATIONS** (loads `SCUSNGUI.ELF`) → Add Setting →
memory card slot 1 → Ethernet → auto-detect OK → PPPoE "Not Required" → IP "Automatic" → DNS
"Automatic" (PCSX2's DHCP interception hands out `DNS1`) → name "Setting 1" → X to save →
"test the connection" answers **successful**. Then quit back to the game (it reboots the ISO).
Verify the save landed: the card image now contains the strings `BWNETCNF` and `net000.cnf`.
Copy it to B **while B is not running** —
`cp tools/pcsx2/memcards/Mcd001.ps2 tools/pcsx2_b/memcards/Mcd001.ps2` — rather than repeating the
wizard. Do **not** try to set DNS manually in that wizard: the octet editor increments one unit per
d-pad press.

**d. Savestates: do not rely on them.** `online_login.py` / `online_match.py` start from slots 9
(A) and 5 (B); neither exists any more (only 06/07/08/20/21/22 survive in `tools/pcsx2/sstates`),
and a state copied from the other install re-probes the card and loses the network configuration.
Cold-boot both instances instead — ~90 s each, and it removes the whole class of "state saved after
network traffic" failures.

**e. Drive it.** `logs/s4_ctl.py` is one command per invocation (launch / shot / press / hold /
type / watch / kill) so each screen can be looked at before the next press; `logs/s4_watch2.py`
captures both windows once a second; `logs/s4_pcsx2_match.sh` chains the whole thing detached with
a `.done` marker. All three are under `logs/` (gitignored), so the click path is written out here:

1. **Lock.** `bash scripts/loop_lock.sh wait task5 40` — PCSX2 counts as a game run, and you need
   two of them, so hold it for the entire session and `renew` while it runs.
2. **Boot** each instance (`-batch -nogui -fastboot <ISO>`, no `-state`): `cross` ×4 with ~5 s
   waits reaches the main menu (`NEW GAME` highlighted; if you overshoot into SELECT RANK, `triangle`
   backs out), then `down`, `cross` → **LOGIN TO SOCOM II ONLINE** showing "Setting 1".
3. **Log in**, A as `socomp`, B as `socomq` (password = name, typed on the on-screen keyboard by
   `online_login.osk_type`; new personas — the cards hold three empty `<New Persona>` slots):
   `cross` (→ SELECT UNIVERSE "SOCOM II Local", ~30 s) → `cross` (→ CONNECT TO SOCOM II, ~25 s) →
   `cross` (persona list) → `cross` (`<New Persona>`) → type name → `down`, `cross`, type password →
   `down`×4 (→ CONNECT) → `cross` → `cross` (write-your-name notice) → `right`,`cross` (save to
   card: **NO**) → `cross` (ACCEPT the user agreement) → lobby → `cross` (close SERVER NEWS) →
   `down`, `cross` (BRIEFING ROOMS) → `cross` (join Channel 1).
4. **A hosts:** `up`, `cross` (CREATE GAME) → `cross`, type `test` → `up`, `cross` (CHOOSE GAMES) →
   `cross` (Medley), `square` (ACCEPT PLAY LIST) → `square` (CREATE GAME, ~30 s) → `cross`
   (CONTINUE on the 30 s notice). Defaults: VIGILANCE, 16 players, **11 rounds**, 6 min.
5. **B joins:** `cross` (activate the games list) → `cross` (join "test", ~28 s). The joiner is
   auto-assigned to TERRORISTS. **Leave the teams opposite.** Do not use the `--same-team`
   equivalent here: the lobby requires players on both teams and refuses to launch otherwise
   (the notice says so, and STATUS 2026-09-10 20:10/probe4 records the same dead end). The brief
   for this task asked for same-team; it would have produced no round at all.
6. **READY** on both (A: `down`,`down` from ARMORY; B's cursor is already there) about 30 s after
   the game was created, with the 1 Hz dual capture already running. Timeline from the READY
   press: t+18 s briefing, t+24 s "STARTING ROUND 1 OF 11", t+30 s "OBJECTIVE", then gameplay.
7. **Probe the controls** with `hold <key> <seconds>` and read the frames either side (table above).
8. **Slice the server logs** from the line counts taken immediately before READY.

Run cost end to end, including making the network configuration: about 40 minutes of wall clock.

---

## 2. What S0 hands to S1

S0 settles the aim: **the console reference plays where we freeze, and the server's observable
output is identical in both cases**, so S1 is a guest-side investigation of our runtime and not a
server or protocol-coverage task. The two measured divergences between a playing PCSX2 pair and a
frozen ours pair both live in the peer connect payload — the DME `00-18` `APP_SINGLE`/broadcast
records that carry each client's key material and its two NetAddresses — and they are S1's starting
point:

- **(a) Our two clients present an identical RSA blob.** Ours' A and B both carry
  `89-AA-07-C4-C9-84-F3-C3…` in their `0x18`; PCSX2's two clients carry distinct blobs
  (`0D-9E-BC-50…` vs `D9-A7-74-2C…`). This confirms, observationally rather than by hypothesis, the
  long-standing STATUS suspicion (1): the fixed 512-bit client keypair in `socom2_rsa_key.h` /
  the `socom2_RsaGenerateKeyPair` recomp stub is shared by both instances, so the peer session
  cannot derive two distinct keys. Fix shape: make the keypair env- or instance-selected.
- **(b) Our client B advertises a port mismatch between its two NetAddresses** — internal
  `127.0.0.1:3658` but external `192.168.2.10:3660`. PCSX2's client B is `:3660` in **both** slots.
  **Check this one first.** It is a one-line question about how the runtime derives its own
  NetAddress, the receiver is known to validate the peer address against the DME list, and the
  slice it was read from (`logs/dme_probe7.txt`) **predates the `PS2X_SOCOM2_SERVER` fix** — so
  nobody has yet confirmed that fix corrected the *port* as well as the IP. Re-capture the `00-18`
  payloads on a current build before spending any time on (a).

Concretely, the first move is: run the two-instance ours match on today's build with
`PS2X_SOCOM2_SERVER=192.168.2.10` and `PS2X_SOCOM2_NET_TRACE=1`, pull both clients' `00-18`
payloads out of the DME slice, and answer two questions — does B still advertise `:3658` internally
against `:3660` externally, and are the two RSA blobs still identical? Whichever is still true is
the defect to chase; the PCSX2 pair is now a working reference for what both fields should look
like.
