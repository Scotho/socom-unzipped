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

---

## 3. S1 — what the peer channel actually carries, and the two measured divergences (2026-09-12)

### 3.0 The condition

> **The SCE-RT peer session is fully established and stays healthy for the whole match, but neither
> instance ever queues a single application-data message on it: over a ~10 minute match each client
> sends 600 UDP datagrams in total (~1/s), of which ~290 are peer packets and every one of those is
> SCE-RT *control* traffic — the app-0 JOIN/ping/pong retry and a 1 Hz clock-sync ping/pong (types
> 3/4) on the game app — and not one is a player-state update. The round does not fail to start
> because a "go" never arrives; it fails because the local player actor is never handed local
> control, so the game produces nothing to send.**
>
> Evidence: `logs/run_20260912_135813.log` (A) / `logs/run_20260912_135819.log` (B), 583 and 582
> decoded peer packets, `udp peer send/recv #n … ra=…` lines; last counters `udp send #600` /
> `udp recv #600` on both. The input trace in the same logs shows `lx=00` / `lx=ff` / `ly=…`
> reaching the guest on every hold (`[socom2-input] state buttons=0000 rx=80 ry=80 lx=00 ly=80`),
> so the pad values arrive and are ignored above the pad layer.

The part of the sentence S1 could **not** fill in is the "because Y never fires": which flag the
game tests before it lets the local actor move. That is what S2 would have to find, and it is why
this task closes `DONE_WITH_CONCERNS`.

### 3.1 The peer protocol, decoded from the guest

The 22/32-byte peer datagrams are SCE-RT `rt_net` datagrams built by `FUN_0063eba0`
(guest `socom2_game.elf`; `game/analysis/socom2_game.elf.decomp.c`). Layout, little-endian:

```
 0  u8    0
 1  u8    version (1)
 2  u16   body length
 4  8 bytes zero                      <- FUN_0063eba0 memsets 12 bytes and fills 0..3
12  u8    type | 0x80                 <- FUN_00624be0; the receiver clears 0x80 (FUN_00610c20)
13  u8    app id of the sending app   (0 = the SCE-RT control app)
14  u16   payload length              (checked against total-8 by the receiver)
16  u16   sender peer id              (0 = A/host, 1 = B; a packet whose id is my own is dropped)
18  u16   per-sender sequence
20  …     payload
```

Types seen, with the guest function that produces/consumes each:

| type | meaning | sender |
|---|---|---|
| 1 / 2 | PING / PONG, payload = the sender's current app id | `FUN_00624dc0` (per-app keepalive, 1.5 s) |
| 3 / 4 | clock-sync PING / PONG, 8-byte payload `0000000 <u32 timebase>` | `FUN_00624dc0` tail |
| 5 | app membership record, 12 bytes `0c 00 0a 00 03 00 00 00 <peer> 00 00 00` | `FUN_00624f…` |
| 8 / 12 / 15 | peer connect / accept / list-complete | `FUN_00625690` cases 8, 0xc, 0xf |
| 9 | **JOIN app N** (payload = N) — `FUN_00611938`, which sets `client+0x98 = N` on success | |
| 10 | LEAVE app N — `FUN_00611a40` | |

`FUN_00624dc0` is the per-app tick: for every peer in state 2 that has not been heard from in
1500 ms it sends a type-1 ping (payload `client+0x98`), and if the app has **no** connected peer at
all it re-sends the type-9 JOIN every 3 s.

### 3.2 What a frozen match looks like on the wire (run 1, `ours_task6_run1`)

Decoded from the two run logs (`tools_py`-free; the decoder is 20 lines of Python over the
`udp peer` lines):

- **App 10 — the game app — comes up cleanly and stays up.** type 8 → type 12 → 9 × type 15 and
  11/9 × type 5 in each direction, then an uninterrupted 1 Hz type-3/type-4 clock-sync ping/pong
  for the entire match (≈85 exchanges), every single one answered with the identical timebase word.
  Nothing about this link is broken.
- **App 0 — the control app — loops forever.** A re-JOINs app `1` 69 times and B re-JOINs app `5`
  75 times, each with its own type-1/2 ping/pong at 1.5 s. That is `FUN_00624dc0`'s "this app has
  no connected peers" retry, and for a 1-v-1 match with one player on each team it is *expected*:
  A and B are on opposite teams, each alone in its own team app. It is not the defect.
- **No application data on the peer channel.** Not one packet on app 10 other than the control/clock
  types above — this part *is* content-inspected, every peer datagram was decoded.
- **For the other channels this is a rate bound, not an observation.** Of the ~600 datagrams each
  instance sent, only ~300 were peer packets; the remaining ~300 went to the DME aux-UDP port
  (50000/50001) and the NAT service (10070) and were **never content-inspected** — the generic
  counter logs only #1–20 and every 200th, with no hex. So "neither channel carries anything but
  keepalives" was only ever "600 datagrams in 572 s is far too slow to be a game-state stream".
  `PS2X_SOCOM2_NET_TRACE_ALL=1` (added 2026-09-12, review) lifts the `port < 10000` condition on the
  hex dump and closes that gap; any future run investigating this must set it. (Its first version
  tested only `getenv() != nullptr`, so `=0` also enabled it; it now treats `0` and the empty string
  as off, as documented.)

So the freeze is *above* SCE-RT, exactly as the 2026-09-10 20:35 STATUS entry concluded from the
first 16 packets — this run confirms it over a whole match instead of an opening exchange.

**The inbound DME side looks like a *playing* match, and that matters.** The TCP trace on cid 3
carries 31 inbound records over the match: the join/spawn exchange (`03 …` APP_SINGLE frames
carrying the `0x16`, `0x15`, `0x18`, two `0x0f` player records and two `0x04`/`SealObject` spawn
records — e.g. B's `00-18` at `logs/run_20260912_142201.log:5190` and B's `SealObject` at `:6523`)
and then **21 ECHO keepalives and nothing else**. That is the same shape S0 measured on the *playing*
PCSX2 pair. So this is not a session that never started: the records arrive, the round runs (see
§3.8), and the open question is whether we then *mishandle* one of them. Do not read §3.2 as "the
game has nothing to say" — "the game receives the record that should enable control and does not act
on it" is equally consistent with everything here, and §3.9 is evidence for exactly that reading.

### 3.3 (b) The advertised port — **real, fixed, and not the cause**

Re-measured on the current build, as §2 asked. The `PS2X_SOCOM2_SERVER` fix corrected the **IP**
(`01-00-00-7F` → `0A-02-A8-C0`) but **not** the port: client B still advertised internal
`192.168.2.10:3658` (`4A-0E`) against external `192.168.2.10:3660` (`4C-0E`)
(`server/logs/console-DME.log`, the `00-18` payloads before line 3588).

Cause, in one line: `PS2X_SOCOM2_UDP_SHIFT` shifted only the **host** bind inside
`socom2_libnetb::doCreate`, so the guest never learned about it. rt_net `FUN_00620648` writes the
base peer port 3658 into its config object at `+0xC` (instruction `0x620678`,
`addiu $a0, $zero, 0xE4A`) and the client publishes *that* value as its internal NetAddress —
which is A's port. PCSX2's client B does not have this problem because its pnach
(`patch=1,EE,20620678,extended,24040E4C`) rewrites the same constant inside the guest.

**Fix (attempt 1, landed):** `game_overrides_socom2.cpp` now wraps `FUN_00620648` and rewrites the
base-port field to `3658 + PS2X_SOCOM2_UDP_SHIFT` after the original runs — the pnach, done in the
runtime — and `doCreate`'s shift is narrowed to the unshifted base ports so it cannot double-shift.
*Caveat (review):* that narrowing is `localPort >= 3658 && localPort < 3658 + shift`, which is only
correct for **shift ≥ 2**. At `shift = 1` the range covers 3658 alone, so 3659 would stay unshifted
and collide with instance A's second socket. The driver uses 2 and nothing else sets it, but a
future shift of 1 would be silently wrong.

**Result:** the record is now identical in shape to PCSX2's —
`…-00-00-0A-02-A8-C0-4C-0E-00-00-0A-02-A8-C0-4C-0E-…` for B and `4A-0E`/`4A-0E` for A
(`server/logs/console-DME.log` after line 3588) — and A no longer sends its first peer packet to
its own port (run 1's `udp peer send #1` and `#2` both go to `:3660`; the pre-fix run
`logs/run_20260910_191157.log` sent `#16` to `:3658`, i.e. to itself).
**The match behaves exactly as before: LX/LY/RX still do nothing.** So (b) was a real divergence
and is worth keeping fixed, but it was not the blocker — consistent with the guest dropping
self-addressed packets on its own (`FUN_00610c20`: `if (sender == client+0x78) return 0`).

### 3.4 (a) The shared RSA keypair — **real, fixed, and not the cause either**

Confirmed on the current build: both instances published `89-AA-07-C4-C9-84-F3-C3…` (the
`kSocom2RsaN` limbs of `socom2_rsa_key.h`, little-endian) in their `0x18` client record, because
the `socom2_RsaGenerateKeyPair` recomp stub writes one fixed pair for every process.

**Fix (attempt 2, landed):** a second precomputed pair (`kSocom2RsaNb`/`kSocom2RsaDb`, seed
`0x42434f4d`, e = 17, full 512-bit N) selected by `PS2X_SOCOM2_RSA_KEY=b`; the two-instance driver
passes it to instance B when `PS2X_SOCOM2_RSA_KEY_B=b` is in the environment.
*Caveat (review):* `online_login_ours.py` sets instance B's `PS2X_SOCOM2_RSA_KEY` to `""` when
`PS2X_SOCOM2_RSA_KEY_B` is unset, which **overrides** a globally exported `PS2X_SOCOM2_RSA_KEY=b`
for B only — so exporting the key variable directly silently does nothing for the instance it
matters for. Use `PS2X_SOCOM2_RSA_KEY_B`.

**Result:** the wire now shows two distinct public keys — A `89-AA-07-C4-…`, B `45-3D-B0-AE-…`
(`server/logs/console-DME.log` after line 3920) — the same shape as PCSX2's `0D-9E-BC-50…` /
`D9-A7-74-2C…`. **The match is unchanged.** The peer profile of run 2b is identical to run 1's,
packet type for packet type (604 peer packets each side: 72/75 × type 9, 63/66 × type 1/2 on
app 0, 39 × type 3/4 clock sync on app 10, 11 × type 5, 10 × type 15 — and, again, zero application
data), and the player still does not move.

This closes the oldest open hypothesis in the project (STATUS 2026-09-10 20:10 hypothesis (1)) by
observation rather than by argument, and it agrees with the 20:35 reading of the packets: there is
no crypto anywhere on the peer channel, so a shared keypair could not have gated it.

### 3.5 Measuring "the player does not move" reliably

The screenshot path is **not** a reliable movement probe in these runs: `Shell.shot` repeatedly
captured a stale frame (in run 1, 10 of A's 16 probe screens were byte-identical to the previous
one and the HUD timer did not advance between them). Use `PS2X_PC_SAMPLER=1` together with
`PS2X_PEEK=0x416054:3` instead — that prints the camera-orbit position once a second, and it is the
measurement that settles the question:

- run 2b, instance A: 579 `[peek]` rows, of which **369 are all-zero pre-gameplay rows**. Over the
  **210 in-game rows** x is constant at 538.684; y and z move only while the RY (K/I) holds are
  applied. No yaw, no translation.
- instance B: x is **not** constant — 63 distinct values from 1125.04 to 1144.78 over its 210
  in-game rows. Every change follows an **RY** hold and then decays asymptotically, and the rx/lx/ly
  holds show only the tail of the preceding RY move, so the reading is the same; but "x is constant"
  would have been false for B and the sample count is 210, not 579. (Both corrections from review,
  2026-09-12 — quote these numbers, not the first ones.)

`PS2X_SOCOM2_INPUT_TRACE=1` in the same logs proves the pad values arrive
(`[socom2-input] state buttons=0000 rx=80 ry=80 lx=00 ly=80` for each `A`/`D` hold), so the loss is
above the pad HLE.

### 3.6 Run recipe (both fixes are on by default; nothing here needs a code change to reproduce)

**Step 0, before anything else — the liveness check (§3.10).** Run with `PS2X_PC_SAMPLER=1` and
`PS2X_PEEK=0x416054:3`, and when the run ends count the `[peek] @416054` rows that are **not**
`00000000(0) 00000000(0) 00000000(0)`. A real gameplay window is ~210 of them. **If that count is
zero the run never reached gameplay — discard it, whatever its screenshots show.** One run in this
task drove all sixteen stick probes and wrote sixteen screenshots against a lobby keyboard; nothing
except this count said so. Also `bash scripts/loop_lock.sh check` first: the lock has no reaper.

```
bash scripts/loop_lock.sh wait task6 40
./build.sh runtime
bash logs/s4_task6_run2.sh          # detached; poll logs/task6_run2b.done
```
with `PS2X_SOCOM2_SERVER=192.168.2.10 PS2X_SOCOM2_NET_TRACE=1 PS2X_SOCOM2_NET_TRACE_PEERS=400
PS2X_SOCOM2_INPUT_TRACE=1 PS2X_PC_SAMPLER=1 PS2X_PEEK=0x416054:3 PS2X_SOCOM2_RSA_KEY_B=b` and
`online_match_ours --existing-b --hold 60 --probe --probe-both`. The Horizon stack must be up
(`powershell -NoProfile -File server/start-servers.ps1 -Status`). Regression checks, in order of
cost: (1) the `00-18` payloads in `server/logs/console-DME.log` must show `4A-0E` twice for A and
`4C-0E` twice for B and two different RSA blobs; (2) the peer profile must contain application
data on app 10, not only types 1/2/3/4/5/9/15 — that is the pass condition a working round start
would produce; (3) `[peek] @416054` x must change during the `A`/`D`/`W`/`S` holds.

### 3.7 Where S2 should start (superseded in part by §3.9 — read that first)

Both of S0's divergences are now closed and neither was the blocker, so the next layer is the one
the 2026-09-10 20:35 entry called (b): **the local control gate**, not the network. The evidence
that points there:

- Everything that does *not* touch the player actor's transform works online (camera pitch, fire,
  stance, the HUD round timer); everything that does (LX, LY translation and RX yaw) is ignored,
  while the same build moves the player 137 units in 8 s in single player.
- The SCE-RT session above which the game would publish that transform is healthy and idle. The
  game is not waiting for a packet — it has nothing to say.

So the question for S2 is a single-process one and does not need a two-instance match to *start*:
find the branch that the multiplayer path takes and the single-player path does not before applying
the left stick to the player. `DAT_0045a0c1` is the game's multiplayer flag (it selects the
multiplayer arms of `FUN_001fb420`, the round init that posts the "STARTING ROUND %d OF %d" banner
at `0x3e3520`, and of `FUN_001fb790`); the actor's think/controller path branches on the same kind
of flag. `PS2X_CALL_TRACE` on the movement entry points with `PS2X_CALL_TRACE_DUMP` on the actor
object, compared between an online spawn and a single-player spawn, is the cheapest discriminator —
and, unlike everything in this note, it does not cost a 12-minute two-instance run per iteration.

### 3.8 Retraction: the round DOES start, and the banner is not the symptom

**"STARTING ROUND 1 OF 11" is not a persistent banner on ours, and the round is not stalled at the
start.** The sprint spec, `docs/HANDOFF.md` and several STATUS entries describe the defect that way;
all of those descriptions are wrong and should be corrected at close-out.

Evidence: `logs/parity/ours_task6_run1/A_hold05.png` and `logs/parity/ours_match_probe10/A_hold05.png`
(the pre-S1 "frozen" run) both show the clean gameplay HUD one minute in, with **the round timer
counting down — 05:25 on the first** — the banner already gone. A stalled round would not have a
running timer. S0 established the same thing from the other side: the banner is a transient ~6 s
message on the console-accurate reference too.

So the shared mental model of this bug — "frozen at the round-start banner waiting for a go" — is
wrong twice over. The symptom to quote from here on is: **the round runs, and the local player
cannot move.**

---

## 3.9 The online-vs-single-player comparison (2026-09-12, diagnosis only)

Authorised as one bounded diagnostic after the two fix attempts were spent. **It did not name the
gate. It excluded the two strongest candidates and narrowed the search to one layer.** Both of those
exclusions are measurements, not arguments, and both are cheap to re-check.

### The path, from the decompilation

`FUN_00551ec0(float dt, actor *a)` is the player actor's per-frame update, and it is where the
input path is switched on or off:

```c
controller = a[0x30];                                   // actor+0xC0
if (controller != 0) {
    if ( (short)a[0x5d] == 8                            // actor+0x174: the "controllable" state
      || (a[0x1061] & 0x20)                             // an actor flag bit
      || (DAT_0045a0c1 && a[0xfcf] != 0) )              // multiplayer-only enable byte
    {
        controller->vtbl_0x14(dt, controller);          // run the controller = read the input
        ...
        a->vtbl_0x8c(dt, a);                            // = FUN_00594cf0, the actor update
    } else { ... }
}
```

`FUN_00594cf0(float dt, controller *c)` (`actor = c[1]`) then runs the controller's input method and,
**in multiplayer only**, can throw the result away:

```c
cVar7 = c->vtbl_0x8c(dt, c);                            // the input result
if (DAT_0045a0c1 && 0.6 < DAT_004365c0 - (float)actor[0x108]) {   // actor+0x420 = a timestamp
    SetPosition(actor, actor[0x100..0x102], actor+0x50);          // actor+0x400..0x408
    cVar7 = 1;                                                    // "input handled"
}
```

That override is the only multiplayer-exclusive thing on the path, and `actor[0x108]` is stamped from
the same clock by the position-apply path (`FUN_005794d0`: `piVar1[0x108] = DAT_004365c0;`), so
"no position updates arrive ⇒ the actor is snapped back to its last one every frame" was the obvious
candidate. **It is wrong.**

### 3.9a Exclusion 1 — the outer control guard resolves the same way in BOTH paths

`PS2X_CALL_TRACE="0x551ec0:ActorUpd,0x594cf0:PlayerUpd"`, same build, same instrument:

**Do not compare "calls logged".** `PS2X_CALL_TRACE_EVERY=240` logs the first ~300 calls and then
every 240th, so the logged-line counts (656/325/328) are a sampling artifact and say nothing about
rates — the *true* totals are single player **85,680** ActorUpd against online **6,240**/**6,960**,
because single player updates 37 actors and an online 1-v-1 updates 2. The two numbers that do
carry the argument:

| run | ActorUpd total | PlayerUpd total | PlayerUpd rate | PlayerUpd `ra` |
|---|---|---|---|---|
| single player, `logs/run_20260912_152755.log` | 85,680 | 2,160 over 159.7 s | **13.5/s** | `0x552108`, every call |
| online A, `logs/run_20260912_153438.log` | 6,240 | 3,120 over 209.3 s | **14.9/s** | `0x552108`, every call |
| online B, `logs/run_20260912_153444.log` | 6,960 | 3,360 over 203.7 s | **16.5/s** | `0x552108`, every call |

`0x552108` is inside `FUN_00551ec0`, so the caller is the actor update itself, and the per-player
rate is the same in both paths. (Both online instances reached gameplay: 210 non-zero
`[peek] @416054` rows each, `@45a0c1 = 0x01` so the multiplayer flag is set.)

**The guard's three operands, measured on the local actor in both paths** (dumps of `a0+0x174`,
`a0+0xfcc`, `a0+0x105c` from `logs/s4_task6_cmp.sh`):

| run | `actor+0x174` low16 | `actor+0xfcf` | `actor+0x1061` bit `0x20` |
|---|---|---|---|
| single player `…152755` | {0, 1} | 0 | clear |
| online A `…153438` | {0, 1} | 0 | clear |
| online B `…153444` | {0, 1} | 0 | clear |

**All three disjuncts are false in both paths** — the `== 8` state never appears, `0xfcf` is never
set, and the `0x1061` bit tested is `0x20`, which is never set. So the guard body never runs in
either path and both take the `else` arm. Identical. Not the gate, in either direction.

**And the arm matters.** `FUN_00594cf0` is not `actor->vtbl[0x8c]` as first written here — the
vtable dump (§3.9a) gives `actor->vtbl[0x8c] = FUN_00547350`, and `FUN_00594cf0` is called with the
**controller** in `a0`, from `controller->vtbl[0xc]` in the guard's **`else`** arm. So the player
takes the `else` arm in *both* paths, and the guard's true arm is the one that never runs. That is
consistent with the operands (§3.9a) and it is why `PlayerUpd` fires with all three disjuncts false.
**The guard is not the gate, in either direction.**

### Exclusion 2 — the multiplayer snap-back never fires

`PS2X_CALL_TRACE_DUMP="ActorUpd:a0+0x400:10"` plus `PS2X_PEEK=0x4365c0:1`, pairing each dump with the
nearest preceding clock sample (`logs/run_20260912_154530.log`, `logs/run_20260912_154536.log`):

```
A: 294 paired samples, DAT_004365c0 - actor[0x420] in [-0.683, 0.000], max 0.000
B: 308 paired samples,                                in [-0.699, 0.000], max 0.000
```

**Read that as "max 0.000", not as the range.** Peek rows are ~0.67 s apart and dumps ~7 s apart, so
pairing a dump with the *preceding* clock sample systematically understates the difference by
0–0.68 s — the negative spread and the −0.32 mean **are** that artifact, not a measurement. What
survives the artifact is the maximum: over 602 samples across both instances the difference never
exceeds 0.000, so the true difference is ≈ 0 and never anywhere near the 0.6 threshold.
`actor[0x420]` is a real timestamp tracking the clock for the whole match — at dump #6960 it reads
126.351 against a clock of 126.385.

One coverage gap to state honestly: the probe holds are 3.0 s and the dump stride is ~7 s, so **no
dump is guaranteed to land inside a stick hold**. The exclusion does not rest on that; it rests on
`actor[0x420]` tracking the clock continuously, which cannot be true only between holds.

**The snap-back branch is never taken, so it is not the gate either.** Anyone tempted by this
hypothesis again (it is a good one on paper) should re-run that one dump before spending a fix
attempt on it.

### What the same dump did show

`actor+0x400..0x408` settles at `(538.68, 158.492, 1457.58)` on A and does not move again. **State
that carefully** — the first version of this paragraph was wrong twice. The run's 328 dumps span
**two** actors (178 at `@17945d0`, the local player; 150 at `@17a9220`, the remote avatar at
`(1126.53, 63.48, 95.71)`), and the local actor's first **16** dumps do move — 539.76 → 540.80 →
538.75 — before pinning at `538.68` from dump #32 onward.

The claim that the player never moves rests on **§3.5**, not on these dumps: 210 in-game
`[peek] @416054` rows with x ≡ 538.684 and no change during any stick hold. What the dumps add is
that the stored position agrees with it — `538.68` in both — so the actor's position genuinely never
advances after the opening moments; nothing downstream is "moving it back", it is never moved.

### Where that leaves the condition

The sentence in §3.0 stands, and this narrows its missing half by one layer without closing it:

> the controller's input method runs every frame online (`FUN_00551ec0` dispatches `FUN_00594cf0`
> at a per-player rate of 14.9/s and 16.5/s online against 13.5/s in single player — **not** the
> "312/313" logged-line counts, which are the `CALL_TRACE_EVERY` artifact), nothing discards
> its result (the one override that could, never fires), and the actor's position still never
> changes — so the loss is **inside the controller's input method or in how its movement command is
> applied to the actor**, below both branches that were suspected.

S2's first move should be `controller->vtbl_0x14` and `controller->vtbl_0x8c`: resolve those two
slots from the controller object's vtable pointer in an online run and in a single-player run, and
compare. If the vtable differs, the multiplayer controller is a different class and the answer is
which one; if it is the same, trace the resolved function and diff its output (the movement command)
between the two paths. That is the same instrument used here, one level down, and it is still a
single-process question on the single-player side.

## 3.10 The harness is not trustworthy without a liveness check (finding, not an aside)

Three of the six two-instance runs in this task produced nothing usable, in two different ways, and
**both failure modes can masquerade as data**:

- **Silent instance loss.** `logs/run_20260912_141257.log`: instance A exited ~40 s after launch
  with a clean raylib shutdown ("Window closed successfully"), before SCE-RT init. The driver
  carried on and reported `A_game window not found` only at the host-game step, minutes later.
- **A lobby flake that still runs the whole probe.** `logs/parity/ours_task6_mp`: the on-screen
  keyboard entered accent mode (`logs/parity/drive_task6_mp.txt`,
  "A_keyboard in accent mode -> toggling"), the game name came out as `eq4P--` — visible only in the
  screenshot `logs/parity/ours_task6_mp/A_probe12_W.png`, it appears in **no** log — and the match
  never launched, yet the driver executed all 16 stick probes and wrote 16 screenshots and 84 files
  anyway. Read on its own that set looks like a gameplay probe. The only thing that gave it away:
  `logs/run_20260912_151558.log` and `…151604.log` contain 596 and 590 `[peek]` rows and **zero** of
  them are non-zero at `@416054`.
- **Stale screenshots.** In run 1, 10 of A's 16 probe screens were byte-identical to their
  predecessor with the HUD timer not advancing between them (§3.5).

### Do this, every time

1. **Verify `peek @416054` is non-zero before believing any movement claim from this harness.**
   Run with `PS2X_PC_SAMPLER=1 PS2X_PEEK=0x416054:3`, count the rows that are not
   `00000000(0) 00000000(0) 00000000(0)`, and if that count is zero the run never reached gameplay —
   **discard it**, whatever its screenshots show. A real gameplay window is ~210 non-zero rows; the
   sixteen-screenshot lobby-keyboard run had **zero**, and nothing else in its output said so.
2. **Never conclude anything from this harness's screenshots alone.** They go stale (§3.5) and they
   are written whether or not the match launched. They are illustration, not evidence.
3. **An instrument that emits zero rows is a FAILED run, not a quiet one.** Before reading any
   trace, count its lines; if a `PS2X_CALL_TRACE` target logged nothing, assume the target is wrong
   until proven otherwise. This task shipped a `NetIdleMs` trace on `FUN_0030be80` (`0x30be80`) that
   produced **zero** rows for four runs and was never noticed — the guest calls the thunk at
   `0x30cd80`, so idle-ms was simply never measured while the note implied it had been. That is
   exactly the failure this section exists to warn about, landing inside the section that warns
   about it. `PS2X_CALL_TRACE` prints `[call-trace] tracing <n> guest functions` at startup and a
   wrong-but-resolvable address still counts as traced, so that line is **not** evidence the right
   function was hooked.
4. **Release the loop lock in a `finally`, and check for an orphan before you wait on it.**
   `scripts/loop_lock.sh` has no reaper: an agent that finishes, crashes or is interrupted without
   `release` leaves the lock held, and the next agent blocks on it until the 45-minute staleness
   window expires. One orphan had to be cleared by hand during this task. `bash scripts/loop_lock.sh
   check` prints the holder and the age — if the age is large and the owner is a task that has
   plainly finished, it is an orphan.

5. **A finished `drive.py` kills the NEXT run's game.** `drive.py`'s cleanup runs
   `taskkill /F /IM socom2.exe`, which is process-wide: an *earlier* driver reaching its own end
   takes down whatever is running **now**. Task 8's second actor probe died 66 s in exactly this
   way — its run log froze at 127 sampler rows while its `drive.py` went on screenshotting a dead
   game for another four minutes, and only counting the instrument's rows against the wall clock
   (127 rows over 20 s of wall clock = 0.0 Hz) gave it away. **Kill the previous driver, not just
   the game**, before starting anything: `Get-CimInstance Win32_Process | Where-Object
   { $_.CommandLine -match 'tools_py.parity' }` finds it when `Get-Process socom2` shows nothing.
6. **A `MediusPlayerReport` in the Medius log is NOT a round end.** It is a periodic client stats
   report. `ours_task8_kill1` had exactly one, at T+156.7 s, with the two players 603 units apart,
   both still walking and no respawn in either position record — and the acceptance test printed
   `RESULT PASS signal=server` for it. A false PASS in the very test that is supposed to certify
   "playable" is the worst shape this class of defect takes. `KillWatch.FIRING` is now
   `("health", "respawn")`; the server mark is recorded, named in the FAIL line as a non-firing
   observation, and never believed. The DME TCP log is worse still and §1 already measured why: a
   playing match and a frozen one are byte-identical there.
7. **The liveness rule counts non-zero position rows, not DISTINCT ones**, so it passes while the
   player is in-game and not yet controllable. ~~`ours_task8_kill3` lost one of its two movers there:
   161 in-game rows, movement scale 1.0, and the record moving **0.00** units across a forward
   hold, a turn and a second forward hold.~~ **Retracted 2026-09-13 (`736193c`):** the record was the
   camera `0x416054`, frozen while B's actor walked ~65 units; B was controllable. Before measuring
   anything, check the record actually responds to a hold — and read the **actor**, not the camera.

This is the same class of defect the sprint has been closing in the gate all day: a check that can
quietly attest to nothing. The online harness has it too, and now it is written down.

---

## 3.11 The gate, named — **RETRACTED 2026-09-12; see §3.12 for the real one**

> ### RETRACTED — this names the wrong routine. §3.12 has the real gate; keep this section only as
> ### the record of how it was falsified.
>
> Three things killed it, none needing a run: `0x00567340` is a **generic** indexed axis setter
> (`*(float*)(this + 8 + 4*idx) = f12`) used in the same "clear 0,1,2" idiom in about a dozen places,
> not a multiplayer routine; `DAT_0045a1ca` is **1** online (measured, §3.12) because its only writer
> is the "network cable is disconnected" monitor and our own IOP module
> (`ps2xIOP/src/modules/eznetcnf.cpp`, fno 3) hardcodes link-up, so that arm cannot fire; and it is
> **self-refuting** — the arm it blames `return 1`s *before* `FUN_005966a0`, which is where all
> **four** axes including RY are written, so if it fired RY would be dead too.
> **"Three calls, three dead axes" was a coincidence of counts.** The asymmetry was the right thread
> to pull; this was not the mechanism producing it.
>
> ### The claim as originally written
>
> **`X` = the local player's three movement axes hold their pad values for a frame.
> `X` never becomes true online because `Y` = `FUN_00594cf0`'s `cVar7 == 0` arm, which is guarded by
> `if (DAT_0045a0c1 != 0)` and therefore runs in multiplayer only, fires on every frame and calls
> `controller->vtbl[0x20]` (`0x00567340`) three times with axis indices 0, 1 and 2 — zeroing them.
> Three axes, not four: LX, LY and RX are dead online, and RY, the fourth, still moves the camera.**

That last sentence is the reason to believe this one. Every previous candidate explained "the player
does not move"; this is the first that also explains, without being asked to, *why camera pitch is
the one control that survives*.

### The chain, and what is measured at each link

| # | link | how it is established |
|---|---|---|
| 1 | `FUN_00551ec0` takes its **`else`** arm in **both** paths | measured — §3.9a: all three disjuncts false on the local actor in single player and on both online instances |
| 2 | that arm calls `controller->vtbl[0xc]` | `game/disc/socom2_game.elf`, vtable `0x6694b0` `+0xc` → `0x00594cf0`; and every `PlayerUpd` call carries `ra=0x552108` (inside `FUN_00551ec0`) with the **controller** in `a0` |
| 3 | the controller class is the same in both paths | measured — actor vtable `0x6691a0`, controller vtable `0x6694b0`, slots `0x10..0x1c` and `0x88..0x94` byte-identical in `logs/run_20260912_162216.log` (SP) and `…162848`/`…162854` (online) |
| 4 | `cVar7 = controller->vtbl[0x8c]` (`FUN_00566940`) returns **0** | measured in **both** paths — online 374 + 345 logged calls, **every one `v0=0x0`** (`logs/run_20260912_164055.log`, `…164049.log`); single player 305 calls, every one `v0=0x0` (`logs/run_20260912_165209.log`) |
| 5 | it returns 0 because `controller+0x170 & 0x03 == 0` | source (`FUN_00566940`'s entry test) + measured: SP dump of `controller+0x170` reads `0x…20` on 305 of 305 samples — bits `0x01` and `0x02` clear |
| 6 | ~~the `cVar7 == 0` arm is multiplayer-exclusive~~ | **WRONG** — the arm is entered only when `DAT_0045a1ca == 0`, and that byte is **1** online (§3.12). Labelled "source" here, but the source says the opposite once the inner guard is read. |
| 7 | ~~that arm zeroes axes 0, 1, 2~~ | **WRONG** — `0x00567340` is a *generic* indexed axis setter (`*(float*)(this + 8 + 4*idx) = f12`) used in the same idiom in about a dozen places, and the arm `return 1`s before the code that writes any axis from the pad. |

**Links 1–5 are measurements; links 6 and 7 were labelled "read from the decompilation" and are
simply WRONG — see the two struck rows above.** Step 4 is the one that should have stopped this:
the controller's input method returns 0 in *single player too*. That should have been read as "the
question is wrong", not as "so the difference must be downstream". `cVar7` is `FUN_00566940`'s
"a scripted auto-move consumed this frame" result, driven by bits 0 and 1 of `controller+0x170`,
and **0 is simply the normal case in both paths**. *Why is `cVar7` 0 online?* was never the right
question, and chasing it cost a round trip.

### What is NOT yet established — do these before spending a fix attempt

1. **`0x00567340` was not disassembled.** It is called as `(0, actor, axis)` three times with
   consecutive indices, which reads as "set axis *n* to 0", but that is inference from the call
   shape. Ghidra did not split it as its own function (it falls inside the listing's
   `FUN_00566dc0`), so it needs a look.
2. **`DAT_0045a1ca` was not read at runtime.** The three calls sit inside `if (DAT_0045a1ca == 0)`.
   If that byte is non-zero online the arm does something else and this whole section is wrong.
   `PS2X_PEEK=0x45a1ca:1` answers it in one run, and any fix attempt should carry that peek.
3. **The axis indices were not mapped to LX/LY/RX.** Three indices and three dead controls is
   suggestive, not proof.

All three are cheap and all three are *reads*. Whoever takes the fix should confirm them in the same
run that tests it, so a green result cannot be a coincidence.

### Move 2: the soft-double ABI fix is not involved

Every Task 6 run before this one used `dist/socom2.exe` stamped 15:07:37 — **before** `db7a992`
(the soft-double `sin/cos/tan/fabs/floor` ABI fix) landed at 15:28. Since a broken `floor` breaks
`__kernel_rem_pio2` and the matrix-to-Euler gimbal guard, "dead yaw and dead translation with live
pitch" was a plausible shape for broken yaw trigonometry, so the online probe was re-run on a fresh
build (`dist/socom2.exe` 16:40, `logs/build_task6_move2.log`, `buildexit=0`).

**The symptom is unchanged.** `logs/run_20260912_164049.log`: 211 in-game `[peek] @416054` rows,
x takes two values 538.775 / 538.705 across the whole probe sequence — still pinned, still no yaw and
no translation. The soft-double fix is not the cause and is not part of the story.


---

## 3.12 THE GATE, and the fix that landed (2026-09-12)

> ### The condition, completed and verified
>
> **`X` = the local player's LX/LY/RX survive the frame that reads them. `X` never becomes true
> online because `Y` = the multiplayer movement scale `actor+0x1368` is clamped to **0.0** from the
> first frame, and `FUN_00551ec0` multiplies exactly the three fields it feeds from the controller —
> `actor[0x8f]`, `actor[0x90]`, `actor[0x91]` — by it. Pitch is not one of the three (it lives in
> `ctrl[0x4c]`), which is why RY is the one control that survives.**
>
> One qualification the first draft of this section dropped: the multiply is **not unconditional**.
> It is guarded by `if (controller->vtbl[0x2c]() != 0)`. That slot must be returning non-zero online,
> or scaling could not have been what pinned the player — but "unconditional in multiplayer" was an
> overstatement and is withdrawn.
>
> **And the scale is zero because of us.** `FUN_00594cf0` computes it as
> `clamp((5000 - (FUN_0030be80() - 1500)) * 0.001, 0.0, 1.0)`, and `FUN_0030be80` returns
> "milliseconds since the interface activity counter last **changed**":
>
> ```c
> if (0 < DAT_00457b04 && sceInetInterfaceControl(id, 0x200, &v, 4) == 0 && DAT_00458090 != v) {
>     DAT_00458098 = now();  DAT_00458090 = v;          // reset the last-activity timestamp
> }
> return now() - DAT_00458098;
> ```
>
> **`socom2_libnetb.cpp` answered code `0x200` with a hardcoded `0`.** `DAT_00458090` is BSS-zero, so
> `DAT_00458090 != v` is false on the very first call and for ever after; `DAT_00458098` is never
> written; the function returns the full uptime; the scale clamps to 0.0 on frame one and stays
> there. The `ComeFromLan` bypass (`FUN_003045b0(0x44fe10)`) is false for a Medius match, so nothing
> rescues it.

### The fix

`sceInetInterfaceControl` code `0x200` now returns a **real monotonic count of bytes received** on
every socket the table owns (`socom2_hostnet::rxBytes()`, incremented in `recv()` and `recvFrom()`),
which is what the PS2 interface-statistics API actually reports. `PS2X_SOCOM2_NET_STATS=0` restores
the old constant so the defect can be reproduced without a rebuild.

This is a correctness fix to **our HLE of a PS2 network API** — the right layer. It is emphatically
*not* a patch to `FUN_00594cf0`: that scale-down is real console behaviour for a client that has
genuinely lost network activity, and neutering it would have hidden the defect rather than fixed it.

### Verified

`logs/s4_task6_fix.sh`, run `logs/parity/ours_task6_fix2`, both instances in gameplay (**210
in-game `[peek] @416054` rows each** — §3.10 step 0 checked before any screenshot was believed):

| | before | after |
|---|---|---|
| `FUN_00553dc0` scale (`f12`) | pinned at 0.0 | **1.0 on all 332 / 331 logged calls** |
| instance A, distinct `@416054` x over 210 in-game rows | **1** (538.684) | **65** — x 539.68 → 471.01 (range 337.97–557.30), z 1481.79 → 1299.81 |
| instance B, distinct x | 63, all RY tails | **80** — x 1145.28 → 981.87 (range 980.96–1200.65), z 77.68 → 225.61 |

(First → last, with the range in brackets; an earlier draft quoted the min/max as if they were the
endpoints, and counted 73/82 distinct x instead of 65/80. These are the numbers to quote.)

Hundreds of units of displacement on both sides, against a camera-orbit radius of ~27 units, under
`--probe --probe-both` pad injection. `logs/parity/ours_task6_fix2/A_probe12_W.png` shows the player
several buildings away from the spawn the earlier runs were pinned at.

**The motion is stick-aligned, not drift.** Correlating `[peek] @416054` against the
`[socom2-input]` pad rows: mean displacement **1.3–1.4 units per sample at neutral** over 161
samples against **28–38 units on every LX/LY hold** and 22–25 on RX; motion starts on the frame a
hold starts and stops one sample after release; sixty consecutive zero rows precede the first probe;
LY moves z with x frozen, LX moves x with z frozen, and RY moves z with x *exactly* constant. Largest
single-sample jump 47–50 units, so nothing teleports.

**And the fix is stronger than "the scale is 1.0".** All 332/331 traced `FUN_00553dc0` calls carry
`ra=0x595028` — the **literal-1.0** call site, reached only when `idle - 1500 <= 0`. The game never
entered the clamped-decay branch at all. `DAT_00458090` and `DAT_00458098` now take 191 and 187
distinct values across the match where both were `0` for every sample before, which is the mechanism
proved directly rather than inferred.

**The online round start is unblocked: both instances move under LX/LY/RX.**

### The timing, corrected

The "1.5 s window" framing used while this was being chased is **wrong** and should not be repeated.
The scale holds at exactly **1.0 until idle exceeds 5500 ms**, and reaches 0 only at **6500 ms**;
1500 ms is merely the boundary between the literal-1.0 call site and the clamped one. The measured
reset cadence with the fix is **1.10 s mean with a worst observed gap of 2.7 s**, so `rxBytes()` has
roughly 2× margin against the real cliff.

The residual is worth stating plainly: a genuinely quiet stretch longer than 5.5 s would still decay
the scale. **That is honest console behaviour, not a defect** — it is what the scale is for — and it
is not something to "fix".

### Regression check

Re-run `logs/s4_task6_fix.sh`. It must show `MoveScale f12 = 1.0` and more than ~50 distinct
`@416054` x values per instance. `PS2X_SOCOM2_NET_STATS=0` reproduces the defect exactly (scale 0.0,
a single x value), which makes this an A/B with no rebuild.

### 3.12a The same-binary A/B (2026-09-12)

The first verification compared a fixed build against runs made on a binary two hours older, and
`PS2X_SOCOM2_NET_STATS=0` — the knob the note claimed "reproduces the defect exactly" — had never
been executed, so the fallback was untested code and the claim was an assertion. Both are now closed
by one run that carries **both legs of the A/B in the same match, on the same binary, one frame
apart**: instance A with the fix on, instance B with `PS2X_SOCOM2_NET_STATS_B=0`
(`logs/s4_task6_ab.sh`, `logs/parity/ours_task6_ab`, both instances with 210 in-game
`[peek] @416054` rows).

| | A — fix ON (`run_20260912_191727`) | B — `NET_STATS=0` (`run_20260912_191733`) |
|---|---|---|
| `FUN_00553dc0` scale (`f12`) | **1.0** on all 330 calls | **0.0** on all 339 calls |
| `thunk_FUN_0030be80` idle ms | 0 … **1490** (never reaches the 1500 boundary) | 0 … **504 210** (~8.4 min — the whole uptime) |
| `DAT_00458090` distinct values | **192** | **1** |
| `DAT_00458098` distinct values | **192** | **1** (never written) |
| distinct `@416054` x over 210 rows | **89** (538.90 → 507.51, range 387.41–556.94) | **6** (1144.48 → 1144.94 — a span of **0.46 units**) |

So the knob does reproduce the defect exactly, the fallback path executes, and every link of §3.12's
chain is now measured on one binary: constant counter → `DAT_00458090`/`DAT_00458098` frozen → idle
grows without bound → scale 0.0 → player pinned; real counter → both globals advance ~190 times →
idle capped at 1490 ms → scale 1.0 → player moves.

Note the idle figures against §3.12's corrected timing: with the fix, idle never exceeds 1490 ms, so
the game only ever reaches the **literal-1.0** call site and never the clamped one — which matches
the review's observation that all traced `FUN_00553dc0` calls carry `ra=0x595028`.

**This run also fixed the instrument.** The earlier `NetIdleMs` trace pointed at `FUN_0030be80`
(`0x30be80`) and logged **zero** rows across four runs without anyone noticing; the guest calls
`thunk_FUN_0030be80` at **`0x30cd80`**. Every idle-ms number above comes from the thunk. See §3.10
rule 3 — an instrument that emits zero rows is a failed run, not a quiet one.

---

## 3.13 S2 — movement and aim calibration, and `--walk-to-b` (2026-09-12)

With the movement blocker closed (§3.12), "how far does a hold move the player" is finally a
question worth asking. This section is the answer, the method that produced it, and the two things
the method found that the sprint's working assumptions had wrong.

### The instrument

`tools_py/parity/online_match_ours.py` grew a `RunLogTail`: the driver **follows each instance's own
run log while the match is running** and host-timestamps every `[peek] @416054` row and every
`MoveScale` `f12` row as it arrives. `run.sh` now honours `PS2X_RUN_LOG=<path>` so the driver knows
which file is which instance's. Three consequences, all of which the previous task paid for:

- **The liveness rule of §3.10 is enforced in-process**, before any hold is injected: `--calibrate`
  and `--walk-to-b` refuse to run unless both instances have produced in-game rows. The first run of
  this task ended in exactly that refusal instead of producing a folder of convincing screenshots of
  a lobby.
- **Every hold is scored against the movement scale.** `PS2X_CALL_TRACE="0x553dc0:MoveScale"` with
  `PS2X_CALL_TRACE_EVERY=10` gives ~2 `f12` rows/s; a hold whose window does not contain scale rows
  that are all exactly 1.0 is discarded. Zero rows counts as **not** ok — §3.10 rule 3. Across the
  whole calibration schedule all 623 `f12` rows on A and all 616 on B were 1.0, so nothing here was
  measured through the lag freeze.
- `PS2X_PC_SAMPLER=0.25` gives four position rows a second. At 1 Hz a 2 s hold is three samples,
  which is not enough to fit anything.

**The heading sensor is the position rows, not the compass.** Two independent readings come out of
one hold: fit a circle through the camera arc (`circle_fit`, Kasa) and take the swept angle; or walk
forward and take the direction the record travelled. The compass in the captured frames is not used
at all — screenshots go stale (§3.5) and a number read off one is not checkable later.

### Finding 1 — the camera record really is the player, 24.9 units behind, and that is now checked

`0x416054` is the orbiting camera, not the feet (STATUS 2026-09-10 20:10). The calibration turns it
into a player position: **the direction from the record to the fitted circle centre is the direction
the player walks**, measured over the three repeats as a difference of **+0.78, -8.51, -2.95 deg**.
So `player = record + R * (cos h, sin h)` with `h` the walk heading, and the three circle fits whose
residual is exactly **0.00** (a pure rotation with no translation mixed in) all give **R = 24.91**.
The two fits with translation in them bias R down to 22.16 / 22.19, which is why the three-repeat
mean (23.09, ptp 2.75) is the wrong number to quote: **24.9** is.

### Finding 2 — the left stick STRAFES; it does not turn. `D` is not a "Sure Shot turn"

The sprint spec and Task 7's brief both describe `D` (left stick right) as a turn. It is not, on the
preset this match runs (Precision Shooter). All three `A` holds travelled at a **constant world
bearing of -170.90 / -170.94 / -171.00 deg** and all three `D` holds at **+18.48 / +10.74 / +10.80**,
i.e. 180 deg apart and at facing -/+90 deg — a lateral translation, the same thing S0 saw on the
PCSX2 reference when `LLEFT` moved the player with the compass heading unchanged. Turning is the
right stick (`L` / `J`) only, and anything that plans a turn with the left stick plans a sidestep.

**"With the facing unchanged" is an overstatement, though, and the numbers say so.** Every lateral
hold fitted some rotation: 7–10 deg/s, i.e. **~18 deg of camera sweep per 2 s strafe** (|sweep|
14.63 / 17.33 / 18.02 / 20.92 on the four clean holds), and **two of the six classified as
rotations** rather than translations. The conclusion stands — the record travels a constant world
bearing hundreds of units long, which no rotation about a 24.9-unit orbit can produce — but the
right thing to carry forward is "a strafe also drifts the camera ~18 deg per 2 s", not "the facing
is unchanged".

### Finding 3 — the hold response is affine, not proportional

A hold delivers `rate * (seconds - lead)`, not `rate * seconds`, because the record is the camera
*trailing* the player and it takes that long to take up the slack:

| key | 2 s hold (3 repeats) | 4 s hold | implied steady rate | implied lead |
|---|---|---|---|---|
| `L` look | +171.09 / +154.63 / +168.03 deg | +380.78 deg | **108.1 deg/s** | **0.48 s** |
| `W` walk | 55.18 / 58.36 units (and one blocked 16.05) | 160.14 units | ~51 units/s | ~0.9 s |

**Those two columns are the derivation, not the shipped constants.** 108.1 / 0.48 comes from three
2 s holds against a single 4 s hold; the loop over-turned short corrections by ~1.6x on it. The
shipped `LOOK_DEG_PER_S` / `TURN_HOLD_LEAD_S` are the **19-hold least-squares fit below (104.9 /
0.44)**, which includes the 0.7–1.9 s holds the loop actually uses.

This is why a naive `hold = error / rate` correction of a small bearing error delivers nothing at
all: a 20 deg correction asks for 0.19 s, which is inside the lead. `turn_hold_seconds()` adds it.

### The three repeats, and the spread

Run `logs/parity/ours_task7_cal3`, drive log `logs/parity/drive_task7_cal3.txt`, per-instance rows in
`logs/run_A_20260912_202355.log` / `run_B_20260912_202355.log` (**709 in-game `[peek] @416054` rows
each**, A's x spanning 442.48-564.65 and z 1268.62-1489.76 over the schedule). Machine-readable:
`logs/parity/ours_task7_cal3/calibration_A_.json`.

| quantity | repeat 1 | repeat 2 | repeat 3 | mean | spread (ptp) | sd |
|---|---|---|---|---|---|---|
| look `L`, deg/s of a 2 s hold, circle fit | 85.42 | 77.16 | 83.85 | **82.14** | 8.26 | 3.58 |
| look `L`, deg/s of a 2 s hold, walk-heading delta | 86.31 | 88.82 | 87.42 | **87.52** | 2.51 | 1.03 |
| camera orbit radius, units | 24.91 | 22.19 | 22.16 | 23.09 | 2.75 | 1.29 |
| record->centre vs walk heading, deg | +0.78 | -8.51 | -2.95 | -3.56 | 9.28 | 3.81 |
| walk `W`, units/s of a 2 s hold | 8.01 | 27.55 | 29.14 | 21.57 | **21.13** | 9.61 |
| walk back `S`, units/s of a 2 s hold | 25.25 | 25.61 | 25.03 | **25.30** | 0.59 | 0.24 |
| strafe `A`, units/s of a 2 s hold | 43.94 | 45.59 | 43.36 | **44.30** | 2.23 | 0.94 |
| strafe `D`, units/s of a 2 s hold | *12.99* | 40.25 | 39.60 | — | — | — |

*Italic = excluded as obstructed.* **The rule, stated because the first draft dropped the 12.99
silently:** a hold whose displacement is below **half the median of its own group** is treated as
having run into something and excluded from that group's mean. It excludes exactly two holds in this
schedule — `D` rep 1 (12.99 against a median of 39.60) and `W` rep 1 (8.01 against 27.55) — and it is
applied to the group means quoted here, not to the `W` row, which deliberately keeps all three
repeats so the failure to converge is visible.

Singles: `J` (look left) over 2 s = **-86.34 deg/s**, r = 24.91, residual 0.00 — symmetric with `L`
to within 1.1 deg/s, and the sign settles that **`L` sweeps positive** in the atan2(dz, dx) plane.
`L` over 4 s = 95.08 deg/s; `W` over 4 s = 39.99 units/s.

**What converged and what did not.** The look rate converged: three repeats within +-5% by the circle
fit and within +-1.5% by the walk-heading cross-check, two independent instruments agreeing to 5
deg/s, and a left/right symmetry check. The orbit radius converged, on the three zero-residual fits.
**The forward walk did not**: 8.01 / 27.55 / 29.14 units/s is a peak-to-peak of 21.1 on a mean of
21.6, and the 8.01 repeat is a hold that plainly walked into something (16 units in 2 s, while the
backward holds either side of it did their usual 50). Backward and lateral holds, which happened to
run along open ground, repeat to better than +-3%. So **the forward number is a property of where
the player was standing as much as of the controls**, and it is shipped as a burst-sizing heuristic,
not as a speed. Sustained forward speed is better estimated at **~40 units/s** from the single 4 s
hold, which agrees with §3.12's "28-38 units per 1 s sample on every LX/LY hold".

### The constants, as shipped

Module-level in `tools_py/parity/online_match_ours.py`, no magic numbers at the call sites:

```
LOOK_DEG_PER_S                    = 104.9   TURN_HOLD_LEAD_S      = 0.44
LOOK_RIGHT_SIGN                   = +1.0    CAMERA_ORBIT_RADIUS   = 24.9
WALK_UNITS_PER_S_LONG             = 40.0    WALK_BACK_UNITS_PER_S = 25.3
LATERAL_UNITS_PER_S               = 42.5
WALK_2S_HOLD_OBSERVED_NOT_A_SPEED = 21.6    # 8.01/27.55/29.14 -- kept only as a record of the
                                            # measurement that failed. No call site reads it.
```

`LOOK_DEG_PER_S` / `TURN_HOLD_LEAD_S` are the **19-hold least-squares fit above (104.86, 0.443)**,
not the 2 s-repeats-plus-one-4 s-hold fit (108.1 / 0.48) that this note quoted in its first draft and
that the first proving run then over-turned with. **`WALK_UNITS_PER_S_LONG` is the forward rate** —
burst sizing and the progress test both read it; there is no other forward speed constant.

**These are calibrated on one map, one spawn and one round** — mp51, the Medley first round, A's SEAL
spawn at (542.3, 1479.9) against B's terrorist spawn at (1144.8, 77.5), 1526 units apart. The look
rate and the orbit radius are properties of the camera and should carry; the translation rates are
the ones to re-measure somewhere else before believing them.

### The aim resolution this buys, and its floor

Worth stating because it decides what Task 8 can attempt. `PAD_AXIS` only ever injects **full stick
deflection** (0 or 255, never an intermediate) — so the *only* aim control is how long the stick is
held, and the response is affine with a 0.44 s lead. The shortest hold that turns at all therefore
already delivers **~35–40 deg** (measured: 0.71 s → 40.24, 0.72 s → 34.38, 0.84 s → 47.70), and the
fit's RMS of 18 deg puts a floor of roughly **±20 deg on any single open-loop aim**.

That **rules out** scoped or long-range shooting, which needs a couple of degrees, and **rules in**
close range, where a body subtends 15–20 deg. Aiming finer than that needs either partial stick
deflection (a change to the pad injection, not to the harness) or a closed loop that fires, observes
and corrects.

### `--walk-to-b`

`python -m tools_py.parity.online_match_ours --existing-b --hold 40 --walk-to-b --arrive 120`.
A reads **both** instances' records out of the two run logs, converts each to a player position with
`CAMERA_ORBIT_RADIUS`, and loops: bearing to B -> if the error exceeds `TURN_DEADBAND_DEG` (12) turn
by one timed hold of `turn_hold_seconds(error)` -> walk one burst sized at `WALK_STEP_FRACTION` (0.8)
of the remaining gap. B's facing comes from one forward tap at the start (without it B's position is
only known to within the orbit radius); A's comes from the burst it just walked, so the heading is
re-measured every step rather than dead-reckoned. A turn that reads as a rotation contributes its own
fitted sweep to the facing rather than the commanded angle.

A burst's heading replaces the facing **only if the burst is believed**: the scale held at 1.0, it
covered at least `WALK_PROGRESS_FRACTION` (0.25) of `WALK_UNITS_PER_S_LONG * (hold - lead)`, and its
straightness (net displacement / path length along the sampled rows) is at least
`WALK_STRAIGHT_MIN` (0.70). Otherwise the dead-reckoned facing is kept and the loop detours: step
back, sidestep `UNSTICK_LATERAL_UNITS` at the strafe rate above, and aim `DETOUR_DEG` (65) off the
bearing for `DETOUR_STEPS` (2) steps, flipping sides after three consecutive blocked bursts. There
is no `STUCK_UNITS` threshold — an earlier draft of this note described one, and the shipped
mechanism is the belief test.

Two hard caps, because a mis-calibration must not run the match forever: `WALK_TO_B_MAX_STEPS` (40)
and `WALK_TO_B_MAX_SECONDS` (**290** by default; the three proving runs passed `--max-walk-seconds
300`). Both are checked at the top of every step and the function returns the best distance reached
rather than claiming success.

The loop was proved against a simulated world before it was given a match (the simulation writes the
same `[peek]` / `MoveScale` lines into a file and the real `RunLogTail` reads them; in all three
scenarios the simulated world's turn response is deliberately mismatched against the constants, so
every correction overshoots and the loop has to recover by re-measuring):

| scenario | result |
|---|---|
| open ground | converges **857 → 71 units in 9 steps**; the distance the loop reports matches the simulated truth exactly, which is what validates the camera→player reconstruction |
| a wall across the direct line (the shape of the real failure) | converges **857 → 112 units in 14 steps** by detouring round it |
| that wall, with the caps tightened | stops on the cap, `ok=False`, reports the best distance |

(An earlier draft of this note described the second scenario as "mismatched turn response, 20 steps".
That was the *first* version of the wall run, before the detour sign-flip bug was fixed; 14 steps is
the shipped loop.)

### The proving runs — it steers, it does not arrive

**It does not reach B on mp51, and that is the honest headline.** Three matches drove `--walk-to-b`
with `--arrive 120`; none got inside 120 units. What they do show is that the loop's *steering* is
correct and that what stops it is the map, not the calibration.

| run | A start → A end (camera record) | distance to B, start → best | stopped by |
|---|---|---|---|
| `ours_task7_wtb1` | (537.1, 1393.0) → wandered | 1368 → **1251** | 300 s cap |
| `ours_task7_wtb2` | (542.2, 1479.8) → (1086.0, 744.9) | 1382 → **624** | 300 s cap |
| `ours_task7_wtb6` | (542.0, 1479.7) → (1148.2, 1018.6) | 1379 → **864** | 300 s cap |

`ours_task7_wtb2` is the run to read (`logs/parity/drive_task7_wtb2.txt`,
`logs/run_A_20260912_211009.log`: **1441 in-game `[peek] @416054` rows, 937 distinct x**, x spanning
491.07–1118.15 and z 742.61–1482.39; frames `A_wtb00.png`…`A_wtb24.png`; the per-step track in
`logs/parity/ours_task7_wtb2/walk_to_b.json`). A travelled **912 units** of net displacement across
the map toward B and **more than halved** the gap. B stayed at its spawn throughout — 56 distinct x
over 1441 rows, x 1113.02–1145.17 — which is what the loop assumes.

Three things limit it, in order of size:

1. **Steering churn first, map geometry second — and the first draft of this note had that
   backwards.** It is comfortable to say "the calibration is fine, the map is the problem". Half of
   that is false, and the false half is the half about my own loop. Over `wtb2`'s 24 step
   transitions **10 lost ground**, and the biggest losses were not walls: steps 11→12, 12→13, 13→14
   and 16→17 each walked **150–185 units at straightness 0.93–0.97** — clean, open-ground bursts —
   *away* from B, because the detour was aiming 65 deg off the bearing and then had to come back.
   Totals: **1960.7 units walked in bursts to close 757.8 — 38.6 % efficiency.** The `DETOUR_DEG` /
   `DETOUR_STEPS` policy commits to detours it does not need and does not unwind them cheaply, and
   that, not geometry, is where most of the 300 s went.

   Geometry is real, but it is the *second* effect and it shows in `wtb6` rather than `wtb2`: there
   A covered 1379 → 864 units in **five steps and 47 s**, then spent the remaining 250 s blocked
   around (1090–1200, 1000–1090) with the bearing to B due south and something in the way. A
   straight-line-with-detour policy is not a navigator, and the SEAL-spawn → terrorist-spawn route
   on this map needs one. **But the cheapest win available to the next task is not a route planner —
   it is a detour policy that stops throwing away three of every five units walked.**

2. **`wtb1` failed for a different reason, now fixed, and it is worth recording.** The loop adopted
   the heading of *every* burst, including bursts that slid along a wall. Those report headings up to
   86 deg off the direction the player is pointed (step 2: the turn left A facing −55.5 deg, the
   burst reported +30.8), the loop believed them, and every bearing after that was nonsense — it
   oscillated for 21 steps and closed 117 units. With the belief test (progress fraction and
   straightness) added, the next run closed 758.
3. **The movement scale decays when A is STUCK — not because the approach is long.** The first
   draft of this note said "over a 300 s approach", which mislocates the cause. In the calibration
   run all 623 `f12` rows on A were 1.0. In `wtb2` **19 of A's 821 rows are not 1.0** (fifteen 0.0,
   two 0.1, one 0.5, one 0.9) and all nineteen fall inside two windows in which A was pinned —
   steps 19 and 20 moved **2.6 and 2.5 units**. **B's 701 rows are 1.0 throughout, none excepted.**
   The asymmetry gives the mechanism: A's activity counter is fed by what it *receives*; A blocked
   ⇒ A sends little; B parked ⇒ B sends nothing; the peer channel goes quiet for longer than the
   5500 ms of §3.12 and A's scale decays — which keeps A stuck. A feedback trap, not a distance or
   duration effect, and honest console behaviour (§3.12) rather than a defect. What it forbids is
   **"stall against geometry while the target is parked"**; a long approach that keeps moving is
   fine, and **keeping B moving removes it either way.**

**So:** the calibration is good enough to steer with — A turns to the right bearing and walks along
it — and `--walk-to-b` is worth having on the spawn it was calibrated against, as a "close the
distance and keep facing B" primitive. It is **not** a general "go to the other player" and should
not be described as one until something route-plans.

### Three more harness defects found and fixed (all of which silently cost whole runs)

§3.10's list needs these:

- **The on-screen keyboard was driven by posted keys.** `osk_type` dead-reckons the keyboard cursor
  from `OSK_START`, so one dropped press mistypes every character after it and, on the last one,
  presses the key *next to* ENTER. Run 1 of this task typed the game name as `test;` and left the
  keyboard open; every later press went into the keyboard, the game lobby was never created
  (`B_teams` read `(0, 0)` instead of `(143, 144)`) and the match never launched. Same failure as the
  `eq4P--` run in §3.10. `Shell.type` now types through the **injected pad file**.
- **Nothing checked that the keyboard was open before typing into it.** In one run the CROSS that
  enters CREATE GAME landed a screen late, so the CROSS meant to open the game-name keyboard entered
  CREATE GAME instead and `type("test")` hammered the CREATE GAME menu — it set ROUND COUNT to 1 and
  ROUND TIME to 20 minutes, left GAME NAME empty, and the lobby refused with "You must create a
  playlist before game creation can occur". In another, a **"SELECT A CONTROLLER CONFIGURATION"**
  screen appeared mid-login and swallowed both persona presses. `Shell.wait_osk` now waits for the
  keyboard, escalates CROSS then BACK+CROSS, and otherwise aborts with a screenshot. It **recovered**
  the controller-configuration case on the last run (`on-screen keyboard up after recovery 1`), which
  would otherwise have been another twelve minutes. (Incidentally that screen confirms §3.13's
  Finding 2 from the other side: PRECISION SHOOTER is the highlighted preset.)
- **Nothing checked that CREATE GAME / JOIN GAME actually reached the game lobby.** `require_game_lobby`
  now does, using the existing `game_lobby` reference, which separates the two outcomes exactly:
  **0.287** on every run that launched a match (`ours_task6_ab`, `ours_task7_cal3/wtb1/wtb2`) against
  **0.506–0.509** on every run that did not (`ours_task7_cal1/wtb3/wtb5`), threshold 0.45. A lobby
  flake now costs four minutes and says what happened, instead of twelve and a liveness failure.
- **`write_pad_file` could not survive its own press rate**: the atomic `os.replace` fails with
  `WinError 5` while the exe has the pad file open for its 60 Hz poll. Rare at hold rates, routine at
  keyboard rates — it crashed a run outright. It now retries for up to 200 ms.

Even with all four, the lobby flow reached gameplay in only **4 of 10** launches in this task. It is
the single biggest tax on any two-instance work and the next task should budget for it.

### Two conventions, and one thing this task got wrong about its own evidence

- **"Distinct x" means distinct as the exe prints it** — the `%g` float in the `[peek]` line, six
  significant figures — which is how §3.12 and §3.12a counted. The same 1441 `wtb2` rows give 937
  that way, 882 if you round to two decimals and 1001 on the exact binary value. Quote 937.
- **The run scripts under `logs/` were rewritten in place** (`sed -i` over `s4_task7_wtb1.sh` to make
  `wtb2.sh`, and so on), so `s4_task7_cal2.sh`, `wtb1.sh` and `wtb2.sh` no longer exist even though
  the runs they produced are cited throughout this section — **the exact command line of the headline
  run is unrecoverable.** Only the surviving scripts and the drive logs under `logs/parity/` remain.
  Every one of these runs costs twelve minutes; write a new script per run and never overwrite one.

---

## 4. S3 — where the kill state lives, the mined corridor, and `--until-kill` (2026-09-12)

Task 7 left the acceptance test one thing short of runnable: A could be steered across the map but
could not arrive, and nothing in the harness could say that a player had died. This section is the
route to the player's own record in guest memory, what the Horizon logs do and do not carry, the
corridor mined out of Task 7's own position rows, and what the loop does differently because of it.

### 4.1 The player actor: `*0x408c58` — and the route STATUS's 01:30 entry is read as is wrong

> **RETRACTION for close-out — and the attribution matters.** The wrong route is
> `*0x488de8+0xbc`, and it comes from **`STATUS.md`'s 2026-09-09 01:30 entry**, where it is written
> as a warning ("Gotcha: the camera's follow pointer (`*0x488de8+0xbc`) is null in the spawn
> images") and has since been read as a route. **It was never in `HANDOFF.md`** — `git log -S` over
> that file matches only the close-out's own retraction commit — and `HANDOFF`'s
> `*0x488de8+0x320` is the **camera position**, which is correct and stays. An earlier draft of
> this section blamed `HANDOFF.md:311` and `:80`; that was wrong, and it was wrong *because* it
> cited line numbers, which had already moved under the retractions inserted above them. **Cite the
> dated entry or the item name, never `file:NN`.**
>
> The route does not reach the player: measured over 1162 sampler rows it resolved **24 times**,
> every one of them to `0xd9d9d9d9` (the allocator's fill pattern). The route that works is the
> static **`0x408c58`** (equivalently `0x40d744`, `0x440c38`, or `*0x415ff0+0xbc` — note
> `0x415ff0`, not `0x488de8`), verified in five of our RDRAM images, **in the PCSX2 console
> image**, and live in an online match.

`STATUS.md`'s 2026-09-09 01:30 entry names the camera's follow pointer `*0x488de8+0xbc`, and it has
been read since as the way to the player. **It is not, and a run was spent finding that out.** `logs/run_t8probe1.log`
(single instance, `scripts/parity/gameplay_damage.txt`, 1162 sampler rows) peeked
`*0x488de8+0xbc*` all the way into gameplay: the chain resolved **24 times out of 1162**, and to
`0xd9d9d9d9` — the allocator's fill pattern — at that. The rest of the time `PS2X_PEEK` skipped the
item silently, which is why the run script now peeks the raw static **last**, so an unresolved
chain shows up as missing items rather than as a silent index shift in the rows that did resolve.

The route that works was found **offline, in RDRAM images this repo already had**, at the cost of no
runs at all. Scan an image for the actor vtable `0x6691a0`; there are 37 actors; exactly one of them
has a mover (`actor+0xc0`) whose vtable is the **player's** `0x6694b0` rather than the AI movers'
`0x6693f0` (STATUS's **02:10 update inside the 01:30 entry** — that part is correctly attributed;
it is the `*0x488de8+0xbc` gotcha in the 01:30 body above it that has been misread as a route).
Then scan for words equal to that actor's address. Three
statics hold it outright:

| static | holds |
|---|---|
| **`0x408c58`** | the local player's actor |
| `0x40d744` | the same |
| `0x440c38` | the same |
| `0x415ff0` | a camera-ish object whose `+0xbc` IS the same actor — the working version of that chain, `0x415ff0` rather than `0x488de8` |

All four resolve to the player actor in **five of our RDRAM images** (`spawn_ours3`, `postload_ours`,
`rest_ours`, `rest_ours_gq`, `s4rand_ours`) **and in the PCSX2 console image** (`spawn_pcsx2`, where
the actor is `0x1713ce0` instead of our `0x1a5e4b0`). Working on both sides of the comparison is what
makes them game statics rather than an artefact of our heap. `tools_py/parity/` has no scanner for
this; the two throwaway scripts that produced it are quoted in the task report.

So the peek spec for a gameplay run is

```
PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0x200:32,*0x408c58+0xc0*:32,0x408c58:4"
```

`0x416054:3` stays first because `PS2X_TRIGGER` only ever tests the first word of the first item,
and because the liveness rule of §3.10 counts its rows.

### 4.2 The health candidates, and what is NOT yet confirmed

Diffing the actor block across the images (fresh spawn vs 400 s at rest) leaves two words that look
like a health pair, and they are the same in every image including PCSX2's:

| offset | value | why it is a candidate |
|---|---|---|
| `actor+0x204` | `1.0` | a fraction, the shape of "health remaining" |
| `actor+0x208` | `100000.0` (`0x47c35000`) | a round maximum, the shape of "max health" |

**They are candidates and nothing more, and they are weaker candidates than they look.** The word
immediately before them, `actor+0x200`, is `0000ff00` — which reads as much like a packed RGBA as
like a header, and in that reading `1.0` and `100000.0` are a scale and a far clip distance rather
than health and max health. The brief's rule is that an offset is not believed until it has been
watched across **two separate kills**, and this task got none.

`--until-kill` therefore ships with the health signal **disarmed**, and the knob is
`--health-offset` — a **byte offset from the actor base**, not an item index.

> **A defect worth recording, because it was the zero-rows hazard hiding inside the instrument that
> is supposed to certify the kill.** The first version of the arming path took `--health-item` /
> `--health-word` and guarded on word 0 of the **health** item. The documented
> `--health-item 2 --health-word 2` would therefore have checked `items[2][0] == 0x6691a0` — but
> item 2 is `actor+0x200`, whose word 0 is `0000ff00`. The guard could never be true, the watch
> would never have read anything, and a future run would have reported "health never moved" from
> an instrument that never looked. The tail now finds the actor block by its **vtable**, keeps that
> block's address, and resolves a health offset against `actor_addr + offset` across whichever
> peeked item contains it — index-proof by construction.

### 4.3 What the Horizon logs actually carry — and it is not a death

§1 already measured that a playing match and a frozen one produce **byte-identical** DME TCP
profiles, so the DME log cannot see a death. Checking what it *can* see: over the whole of Task 7's
runs `server/logs/console-DME.log` contains only `RT_MSG_CLIENT_ECHO`, `MediusServerConnectNotification`
(CONNECT / DISCONNECT), `MediusServerCreateGameWithAttributesRequest`, `MediusServerJoinGameRequest`
and `MediusServerEndGameRequest`. No per-player events of any kind — the kill is peer-to-peer and
the DME only relays it.

`server/logs/console-Medius.log` is better and is what the harness reads: a client sends
**`MediusPlayerReport`** with a `Stats:` blob at each round boundary, and its fourth dword steps
`1 → 3 → 5 → 7` across a match. That is a **round-end** signal, not a kill: it says the round is
over, not what ended it. The harness reads it, names it `server`, and the note says so rather than
calling it a kill.

### 4.4 The third signal: the position record itself

A one-life round ends when someone dies, and both players are then put back at their spawns. That is
visible in the instrument the harness already trusts: `[peek] @416054` jumps by more than any walk
can cover between two samples (`TELEPORT_UNITS` 250 against ~10 units at 4 Hz and 40 units/s), and
lands within `RESPAWN_RADIUS` of the spawn it left. `KillWatch` fires `respawn` on either, but only
after that player got `MOVED_AWAY_UNITS` (250) from its spawn in the first place, so the first steps
out of the spawn cannot trigger it.

**This signal says "the round ended", not "A shot B".** A round also ends on its timer, so the run
prints the time the signal fired relative to the start of the approach, and the two screens, and
leaves the reader to judge. Naming the signal is the point: `RESULT PASS signal=respawn` and
`RESULT PASS signal=health` are different claims and the line says which.

### 4.5 The corridor, mined rather than planned

Task 7's 38.6 % closure efficiency was lost to steering churn **in open ground**, not to walls
(§3.13), so the cheapest win available was never a route planner. Two things were done instead, and
the first cost no runs at all.

**Mining.** `logs/run_A_20260912_211009.log` (the `wtb2` run) holds 1441 in-game position rows of A
actually walking from the SEAL spawn to (1086, 745). Keeping a row when it is at least 70 units from
the last kept row **and** closer to the terrorist spawn than any row before it gives a
progress-monotone chain of 16 points — every one of them a place the player's camera record
provably was:

```
(542.2,1479.8) (529.8,1407.2) (619.3,1378.2) (693.2,1348.9) (748.1,1297.8) (795.4,1232.7)
(737.6,1192.2) (746.7,1119.7) (742.7,1044.5) (720.6, 977.1) (755.7, 912.1) (843.4, 903.9)
(911.6, 879.0) (950.3, 814.1) (1033.8, 800.5) (1096.4, 750.6)
```

**1167.5 units of path to close 851.4 units of gap — a ratio of 73 %.** That is the geometry of an
idealised polyline and therefore an **upper bound**, not a closure efficiency: it is what a player
would achieve walking the corridor perfectly, with no steering, no turns and no re-measurement. It
is not comparable with the 38.6 % a real run achieved, and the first draft of this note compared
them. What the corridor actually bought in the match is in §4.8. The `y` of those rows falls
184.8 → −4.5: the route is a descent out of a bowl, which is why a straight line out of the SEAL
spawn does not work. `MP51_SEAL_ROUTE` in the harness is that list, with the rule that produced it
written next to it so it can be re-mined.

The second gameplay run over the same ground (`run_A_20260912_220017.log`, `wtb6`) is the
counter-example that says the mining rule matters: it branched east at (817, 1275), climbed back to
y ≈ 100–118 and spent 250 s stuck around (1060–1180, 1025–1100). Mining that run would have produced
a corridor into a dead end. The rule keeps only monotone progress, which is what excludes it.

### 4.6 What the loop does differently

`walk_to_b` is no longer its own loop: it is `approach()` with no corridor, no engagement and a
partner that is not walking back, so the simulation exercises the code a match runs.

1. **Both sides walk.** One mover cannot close 1382 units inside a round and a parked opponent
   starves a stuck mover (KNOWN.md). `--converge` runs `approach()` on both instances in threads
   against a shared `Duel` that carries each side's **measured** facing, so each side reconstructs
   the other's player position from its camera record rather than guessing it to within the orbit
   radius.
2. **A full burst is only spent on a measured facing.** This is the efficiency fix and it is a fix
   to the loop, not to the map. Over `wtb2`'s 24 transitions the four biggest losses were 150–185
   unit bursts at straightness 0.93–0.97 — clean open-ground walking, in the wrong direction,
   because the burst followed an open-loop turn whose delivery the loop had assumed. Now a burst
   that follows a turn is a **1.5 s probe (~42 units)** whose only job is to measure the facing; the
   full burst is spent on the next step, when the facing is measured and the bearing error is inside
   the deadband. The worst case costs 42 units instead of 185.
3. **The turn has a measured gain.** `wtb2`'s step 15 asked for −72.3° and delivered −16.3°; step 17
   asked for +134.4° and delivered +184.3°. Each turn is now scored against the facing the next
   believed burst measures, and an EMA of delivered/commanded (clamped to 0.35–2.5) scales the next
   request. It is the same closed loop the sweep measurement already was, applied to the thing that
   was open.
4. **A believed burst ends the detour.** `wtb2` decremented `detour_left` and kept walking 65° off
   the bearing for another step or two; it now clears it outright.

### 4.7 The simulation, which now lives in the tree

`tools_py/parity/sim_walk_to_b.py` — Task 7 wrote this in a scratch directory and lost it, and the
note that cited it could not be checked. It writes the same `[peek]` / `MoveScale` lines the exe
writes into temp logs at 4 Hz, the **real** `RunLogTail` reads them, and a fake `Shell.pad` drives a
simulated player. Every scenario deliberately mismatches the world's turn response against the
harness constants, so every correction overshoots or undershoots and the loop has to recover by
re-measuring.

Run as shipped (`python -m tools_py.parity.sim_walk_to_b all`). **The step counts and wall
times below are ILLUSTRATIVE, not constants** -- the simulation is wall-clock timed and one
`maze` took 14 steps / 102 s where another took 29 / 206 s on identical code. What is
asserted is the OUTCOME (arrival, the cap, the signal) and, for `converge`, that the distance
the loop REPORTS tracks the simulated truth:

| scenario | result |
|---|---|
| `open` — one mover, parked target | arrives, 5 steps, 39 s |
| `maze` — a wall across the direct line | arrives by detouring, 14 steps, 102 s |
| `caps` — a deliberately wrong walk rate and a wall | stops on the cap, `ok=False`, best distance reported |
| `converge` — **both** movers from the real mp51 spawns | **1526.3 → 64.3 units in 56 s**, A walking 1110 and B 700 to close 1462 — **80.8 % efficiency** |
| `route` — the same with the mined corridor, a spawn-bowl wall and a wall in B's half | **1526.3 → 40.9 units**, 15 steps a side, 78 s, 65.1 % |
| `stack` — A's ground falls away as it walks while B stays at one height (the kill2 failure, as a test) | the loop refuses contact and climbs its own breadcrumb trail back to B's height |
| `watch` — a player walked 360 units away and teleported back | `KillWatch` fires `respawn` |

**One property of the honest gate that Sprint 5 should know.** With the distance now measured
rather than reconstructed, the `converge` endgame is genuinely variable: across four runs of the
same code it reached contact in 16 steps (99 s), reached it in 38 (230 s), and **ran out its
40-step budget circling at 25–31 units** of a 22-unit gate. The reconstruction used to hide this by
reporting a flattering distance and stopping. The scenario now asserts the outcome that is actually
guaranteed — the 1526-unit map closed to within two engage radii — and that the last reported range
tracks the truth to within one burst, rather than asserting contact.

**And one false alarm the simulation manufactured about itself.** During the final review round,
`open` — green three times running at 5 steps, reported 85.24 against truth 85.24 — suddenly timed
out having walked **1240 units away** from its target. Nothing in the code under test had changed
along that path. The cause was the harness: the previous suite had not been killed (`pkill` is a
no-op in Git Bash, and its `2>/dev/null` hid that), and the simulation wrote its worlds to fixed
names in the shared temp directory, so **two suites interleaved two simulated worlds into one
log** and the loop steered on rows from both. The logs are now named per process. Worth recording
because the failure was indistinguishable from a regression in the loop, and the first instinct was
to go looking for one.

**And a second one, inside the simulated world itself.** With the logs isolated, `maze` then spent a
whole 40-step budget pinned at x≈720, z≈1300 — a position **inside** its own wall
(`z < 1400 and x < 750`). The simulated `World` only checked the wall for the forward walk `W`; back
(`S`) and strafe (`A`/`D`) passed straight through it. So the loop's own unstick manoeuvre — a step
back and a sidestep — could put the player inside solid geometry, and from there every forward move
was blocked for good. That is what made `maze` flaky across the whole task (14, 18, 23 and 29 steps
on four runs), and it had nothing to do with the loop. Every translation is now wall-checked.
**Neither defect was in the code under test, and both looked exactly like it was.**

**And one race that WAS in the code under test, fixed rather than tolerated.** The reviewer's own
run of the suite failed `converge` with the loop reporting a best of **11.2** while the two
simulated players ended **87.35** apart. The cause was already written down beside `route`'s
assertion, which had been loosened for it: when one side calls contact, the other side is usually
in the middle of a walk burst — up to `WALK_STEP_MAX_S`, ~240 units — and it finished that burst,
straight through the engagement. That is not a simulator artefact. In a live match it is exactly
the overshoot this whole task has been fighting: a player still walking after contact is called.
**Every hold `approach()` makes — turns, walk bursts, facing probes, unstick moves, and the waits
between them — is now released the moment either side sets `duel.contact`**, via an `abort` event
that `Shell.pad` (and the simulated shell) honours, and a burst cut short that way is neither
scored nor unstuck from. `route` and `stack` had their assertions put back to the tight
`d <= 45.0` that `converge` always had.

**The evidence, including what did not pass.** The race is fixed; the suite is **not** yet reliably
green, and the two are different claims.

*Fail before, pass after, identical command* (`python -m tools_py.parity.sim_walk_to_b converge`,
one process at a time; "before" is `git archive 2eafed8`):

| code | run | outcome | loop's reported best | true final distance |
|---|---|---|---|---|
| before | 1 | **FAIL** — contact called, other side finished its burst | 5.0 | **75.01** |
| before | 2 | **FAIL** — the same | 9.4 | **53.84** |
| after | 1 | pass | 5.2 | 5.17 |
| after | 2 | **FAIL — a different defect**: no contact was ever called, zero holds released; both sides spent all 40 steps orbiting each other at 60–98 units | 26.7 | 53.69 |

*Five full suites, sequential, alone, no retries* (after):

| run | result | converge truth | route truth | stack truth |
|---|---|---|---|---|
| 1 | **FAIL in `stack`** — both sides step-capped; A cycled 21 of 40 steps between "walk to B, drop 14 below it on the ramp" and "retreat ~140 units to a level breadcrumb" | 15.74 | 5.06 | 70.23 |
| 2 | SIM OK | 7.28 | 19.11 | 9.47 |
| 3 | SIM OK | 18.65 | 6.45 | 5.04 |
| 4 | SIM OK | 20.40 | 15.03 | 16.63 |
| 5 | SIM OK | 6.36 | 10.94 | 18.19 |

So: across the seven post-fix `converge` runs the contact-then-overshoot race **never recurred**
(true distance tracked the reported one every time contact was called, and route's re-tightened
bound held 5 of 5), against 2 of 2 before. **Two other loop defects remain, and both are real, not
simulator artefacts**: (1) **mutual-pursuit orbiting** — two movers each steering at the other's
latest position can circle indefinitely just outside the 3-D gate (1 of 7 converge runs); and
(2) **an anti-stack limit cycle** — when the only same-height ground is *away* from the target, "go
to a level breadcrumb" and "approach the player" undo each other forever (1 of 5 stack runs). Both
want the same kind of fix — hysteresis or a role split (one side holds while the other closes) —
and neither is done. The suite is 4 of 5 green, and it is recorded that way.

The `converge` number is the one that decided the match was worth launching: it is not a measurement
of the game, it is a measurement of the loop's own arithmetic against a world where the turn
response is deliberately wrong.

### 4.8 The runs

Three launches, **all three reached gameplay** — against the 4-in-10 rate Task 7 measured. Nothing
was changed in the lobby flow, so this is luck, not an improvement, and the next task should still
budget 2.5 launches per usable match.

| run | what it was for | outcome |
|---|---|---|
| `logs/run_t8probe1.log` | single instance, no match: does `*0x488de8+0xbc*` reach the player? | **no** — 24 resolutions in 1162 rows, all `0xd9d9d9d9` |
| `logs/run_t8probe2.log` | the same with `*0x408c58` | **void** — the previous run's `drive.py` reached its own cleanup and ran `taskkill /F /IM socom2.exe`, which killed *this* run's exe 66 s in. The log froze at 127 sampler rows while `drive.py` kept screenshotting a dead game: §3.10's trap, from the other end |
| `ours_task8_kill1` | the acceptance test, attempt 1 | reached contact-range arithmetic but was **stopped early by a false signal** |
| `ours_task8_kill2` | attempt 2 | ~~closed 1392 → 33 units~~ **closed 1485.5 → 50.0 units true 3-D** (struck figure was the camera+facing reconstruction — see the correction below this table and §4.11), fired 24 bursts, **no hit** |
| `ours_task8_kill3` | attempt 3, with a pitch sweep | reached gameplay, ~~**lost instance B before its first step**~~ B was controllable; the camera record froze (retracted 2026-09-13, `736193c`) |
| `ours_task8_kill4` / `kill6` / `kill7` | attempts 4, 6 and 7 | never reached gameplay (lobby band 0.521, 0.521, and the on-screen keyboard never opened) |
| `ours_task8_kill5` | attempt 5 | reached the lobby, both READY, **match never launched** — 0 in-game rows of 2514 |

**`ours_task8_kill1`** (`logs/s4_task8_kill1.sh`, `logs/parity/drive_task8_kill1.txt`,
`logs/run_A_20260912_230022.log` / `run_B_…`, 805 in-game rows each). Liveness checked before any
hold: A 160 / B 161 in-game rows at the check, 803 / 802 by the end.

**Both players moved.** Every Task 7 run had B parked inside 48 units of its spawn; here B walked
its camera record from (1144.9, 77.8) to (869.1, 347.1). A walked (540.8, 1480.4) → (784.8, 973.9).

**The efficiency figures have to be team-level, and the first draft of this note got that wrong.**
Two movers close the *same* gap, so quoting each side's closure against its own walking
double-counts it: per-side, `kill2` comes out at 107.6 % and 119.2 %, which is impossible for one
mover. The comparable quantity is **team-closed over team-walked**, measured on the actors' own
positions:

| | movers | walked (team) | true 3-D gap closed | efficiency | rate |
|---|---|---|---|---|---|
| Task 7 `wtb2` | 1 (B parked) | 1960.7 | 757.8 over 300 s | **38.6 %** | 2.5 units/s |
| `kill1` | 2 | 2437.1 | 888.5 (1485.1 → 596.6) over 157 s | **36.5 %** | 5.7 units/s |
| `kill2` | 2 | 2352.6 | 1435.5 (1485.5 → 50.0) over 127 s | **61.0 %** | **11.3 units/s** |

So `kill1` was **not** an efficiency win — at 36.5 % it is marginally *worse* than the one-mover
baseline it was quoted against, and the deadband defect below is why. `kill2` is a real one, and
**the defensible headline is rate, not efficiency**: 1435 units of gap closed in 127 s against 758
in 300 s, four and a half times faster, which is what turns "cannot finish inside a round" into
"finishes in two minutes".

Per-side detail, which is where the deadband defect shows:

| | steps | turns | probe bursts | believed | walked |
|---|---|---|---|---|---|
| `kill1` A | 30 | 28 | **29 of 30** | 24 | 1371.9 |
| `kill1` B | 27 | 24 | 25 of 27 | 18 | 1065.2 |

Two things came out of it, and both were defects in this task's own work:

- **29 of A's 30 bursts were probes and exactly one was a full burst.** `TURN_DEADBAND_DEG` is 12°,
  and no single open-loop aim is better than about ±20°, so every step turned, and every step that
  turned walked a probe. Fixed by a separate `APPROACH_DEADBAND_DEG` of 30°: walking 30° off the
  bearing still closes cos 30° = 87 % of the distance, which beats turning again.
- **The run printed `RESULT PASS signal=server` for a round that had not ended.** One
  `MediusPlayerReport` arrived at T+156.7 s with the players 603 units apart, both still walking and
  no respawn in either position record. The server mark is now recorded and **never fires** (§4.3).
  It is exactly the flattering positive the sprint has been warning about, and it was in the harness
  for one run.

Also confirmed live: `*0x408c58` resolves **in an online match** — actor `0x17941d0`, word 0
`006691a0`, 804 rows on A and 802 on B — and `actor+0x204` = 1.0 with `actor+0x208` = 100000.0
throughout, unchanged, because nobody was shot. And the peek indices **do** shift: A's item 1 holds
2502 rows, 1698 of them the raw `0x408c58:4` static from before the actor existed and 804 the actor
block. The health watch now checks word 0 against `0x6691a0` before reading anything.

**`ours_task8_kill2`** (`logs/s4_task8_kill2.sh`, `logs/parity/drive_task8_kill2.txt`,
`logs/run_A_20260912_231341.log` / `run_B_…`, **1172 in-game position rows on A and 1055 on B**
(the first draft of this note quoted 1172 for both; the actor blocks give 1173 and 1056). With the
deadband, the gain EMA at 0.3 and the 2.0 s probe:

**~~A closed 1392 → 33.04 units in 23 steps and about 127 s, and B stopped at 70.8.~~**
> **SUPERSEDED FIGURE — kept visible on purpose.** "1392 → 33.04" and "70.8" were produced by the
> camera + facing reconstruction, which is wrong by up to two orbit radii (~50 units; §4.11 proves
> it in a flat simulated world). On the actors' own positions the headline run closed **1485.5 →
> 50.0 units true 3-D** in about 127 s; over the last 400 rows the 3-D separation had a median of
> **67.9**, and **0 %** of those rows were inside any contact gate (the table further down).
> Nothing below this box should be read as "the players reached 33 units".

The run took 23 steps. The two
instances met in the middle of mp51 — A's record ran (541.8, 1479.7) → (903.7, 893.6) and B's
(1144.8, 78.2) → (927.4, 867.1). That is the first time in this project that two online players
have been ~~in the same place~~ near each other — 50 units apart at best, true 3-D.

**Then 24 bursts hit nothing, and it is worth being exact about why.** The first reading was
measured on the camera
records and was both too kind and too narrow**; the actors' own positions (§4.1, words 7/8/9) are
the honest version, and they change the conclusion:

| measurement, on the ACTOR rows | value |
|---|---|
| minimum true **3-D** separation, whole run | **50.0 units** |
| minimum true **2-D** separation, whole run | 17.6 units |
| 3-D separation over the last 400 rows | median **67.9**, min 50.0, max 112.4 |
| vertical separation over the last 400 rows | median **+44.0** (A below B) |
| elevation angle over the last 400 rows | median **43.3°**, max 70.0° |
| rows inside 45 units in 3-D / inside 25 / with `\|dy\|` ≤ 10 | **0 % / 0 % / 0 %** |

**Range and elevation are co-equal causes.** The 77° figure the first draft led with is the single
worst row, not the condition, and a fix aimed only at elevation would have failed again: the two
players were never once inside the engagement range at all, in three dimensions. They swept from a
median of 68 units away, and sweeping from out of range is not an aim problem.

At 10 units of ground range a 45-unit height difference is **77° of elevation**, and the engagement
swept yaw only. `actor+0x204` and `actor+0x208` are unchanged on **both** instances for all 1172
rows, so neither player took a single point of damage: this is not "the kill did not register", it
is "nothing was hit".

**And the loop's own distance was wrong, not merely two-dimensional.** It reconstructed each player
as `camera + CAMERA_ORBIT_RADIUS * facing`, so a facing estimate that is wrong by tens of degrees
misplaces a player by up to two orbit radii — about **50 units**, which is larger than the whole
engagement range. It also needed the *other* side's facing to place the other player, the exact
dependency that `kill3` could not satisfy. The simulation reproduces the pathology in a world with
**no vertical dimension at all**: on the committed code `converge` reported a best separation of
**40.3 against a ground truth of 64.3**, `route` **23.4 against 30.7** and `caps` **157.6 against
204.7** — a consistent 25–47 unit under-report that can only be the orbit reconstruction.

That is now fixed at the root: `true_pos()` reads the actor's own x/y/z and the reconstruction is
a labelled fallback. After the change the same simulated scenario reports **18.1 against a ground
truth of 18.1**. So "contact at 33 units" was never a measurement of anything.

**And the shots were real.** This matters, because "the bursts did nothing" has two very different
explanations and the frames settle which. The injected pad state carries `buttons=0800` — bit 11,
R1 — **96 times** in A's run log, and the HUD ammo counters follow: `A_fight04.png` reads
**30/30, 2 MAGS**, `A_fight07.png` reads **0/30** with a spray of bullet impacts across the stone
wall a metre in front of the muzzle, `B_fight05.png` reads **4/30** with muzzle smoke, and
`B_final.png` reads **13/30, 1 MAG** — about 47 rounds out of B alone. Both players emptied
magazines; the rounds went into the geometry between them. The round clock in those frames runs
02:09 → 01:06, so the engagement was nowhere near the round's end either.

**`ours_task8_kill3`, `kill4`, `kill5` — the three that taught something and produced nothing.**

> **Retracted 2026-09-13 (Sprint 5 Task 3 Step 0, `736193c`):** the kill3 B "0.00 units" below
> measured the camera record `0x416054`, which froze while B's actor walked ~65 units on the first
> hold. B was controllable; see `docs/KNOWN.md` standing hazards. Kept as written for the record.

- `kill3` reached gameplay and then **lost one of its two movers before the first step**: instance
  B's facing probe measured **0.00 units** of travel across a 1.5 s forward hold, a 1.3 s turn and a
  second 1.5 s hold, with 161 in-game rows and the movement scale at 1.0 the whole time. The player
  was in-game and not yet controllable, and the loop gave up after two probes in ten seconds. A then
  walked alone and stopped 587 units short — the one-mover arithmetic, reproduced by accident.
  **The liveness rule cannot catch this**: it counts non-zero position rows, not *distinct* ones.
  The probe now retries six times over ~40 s and, failing that, starts with the facing marked
  untrusted and lets the first believed burst measure it, because a side that cannot measure its
  heading can still walk.
- `kill4` never reached the game lobby (`game_lobby` band distance **0.521** against the 0.45
  threshold) and Task 7's guard ended it in four minutes instead of twelve.
- `kill5` reached the lobby, pressed READY on both sides, and the match still did not launch:
  **0 in-game peek rows of 2514**, caught by the liveness rule of §3.10.

`kill6` never got the on-screen keyboard up for the game name (Task 7's `wait_osk` guard, five
minutes), and `kill7` repeated `kill4`'s **0.521** lobby-band miss.

So of **seven** two-instance launches, **three reached gameplay and two produced a usable
approach** — the 4-in-10 rate this note has been quoting, and nothing in this task touched the
lobby flow. Every one of the four failures was caught by a Task 7 guard in four to five minutes
instead of twelve, which is the only reason seven launches fitted in the session at all.

### 4.9 The exact commands, because `logs/` is gitignored

Task 7 lost the command line of its headline run by rewriting its scripts in place; `logs/` is also
**gitignored**, so a per-run script there does not survive the workspace either. The two that matter:

```bash
# ours_task8_kill1 -- the first two-mover approach
export PS2X_SOCOM2_SERVER=192.168.2.10 PS2X_SOCOM2_RSA_KEY_B=b PS2X_SOCOM2_INPUT_TRACE=1 \
       PS2X_CALL_TRACE="0x553dc0:MoveScale" PS2X_CALL_TRACE_EVERY=10 PS2X_PC_SAMPLER=0.25 \
       PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0x200:32,*0x408c58+0xc0*:32,0x408c58:4"
python -m tools_py.parity.online_match_ours --existing-b --hold 30 --until-kill \
       --arrive 60 --engage 45 --max-steps 60 --max-walk-seconds 250 \
       --fight-seconds 120 --kill-timeout 400 \
       --out logs/parity/ours_task8_kill1 --seconds 1200 > logs/parity/drive_task8_kill1.txt 2>&1

# ours_task8_kill2 -- THE HEADLINE RUN, the same environment as above.
#   SUPERSEDED FIGURE: this line used to say "1392 -> 33.04 units". That was the camera+facing
#   reconstruction (wrong by up to ~50 units, 4.11). True 3-D on the actor rows: 1485.5 -> 50.0.
#   Also note --engage meant a GROUND distance when this ran; it is now a TRUE 3-D range.
python -m tools_py.parity.online_match_ours --existing-b --hold 30 --until-kill \
       --arrive 60 --engage 45 --max-steps 60 --max-walk-seconds 300 \
       --fight-seconds 120 --kill-timeout 460 \
       --out logs/parity/ours_task8_kill2 --seconds 1200 > logs/parity/drive_task8_kill2.txt 2>&1
```

The pitch sweep of §4.6 has **never been in front of a landed engagement**: the run that reached
contact (`kill2`) predates it, and the four launches after it either lost a mover before the first
step or never reached gameplay. It is shipped and simulated, not proven.

The single-instance actor probe, which needs no match at all and is the cheapest way to re-check the
peek route after any heap change:

```bash
PS2X_PC_SAMPLER=0.5 PS2X_RUN_LOG=$PWD/logs/run_t8probe.log \
PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0x200:64,*0x408c58+0xc0*:64,0x408c58:4" \
python -m tools_py.parity.drive --target ours --script scripts/parity/gameplay_damage.txt \
       --out logs/parity/ours_task8_probe --seconds 760 --tail 120
```

### 4.10 What Sprint 5 should do, in order (rewritten 2026-09-13)

> The first version of this section is superseded and was wrong in two places by the time it was
> written down: it prescribed `--health-item 2 --health-word 2`, an index path that has since been
> **removed** because its guard could never fire, and it said "sweep pitch (done)", which has since
> been **retired on arithmetic**. Both are corrected below. This is the section that gets read
> first, so it is the one that must not rot.

1. **Settle Frostfire movement before anything else.** One run showed the move path entered for
   0.6 s and never again (§4.12). Re-launch Frostfire; if it reproduces, this is a bigger finding
   than the kill, because §3.12's movement fix was measured on mp51 and only on mp51. The threads
   to pull are the call count of `FUN_00553dc0` and the `0x200` idle counter of §3.12.
2. **Confirm the health offset across two kills, then arm it** with
   ~~`--until-kill --health-offset 0x208`~~ `--until-kill --health-offset 0x1044` (a BYTE OFFSET FROM
   THE ACTOR BASE — never an item index). **The candidate changed:** research/19 F1 puts health at
   the float `actor+0x1044` (1.0 = full, `<= 0.0` = dead) with the alive byte at `actor+0xF7A`,
   from two r0001 community tools cross-checked against 17 decomp sites and all eight actor images.
   It is research-sourced and **not yet read live in an online match**, so it is not the default.
   The `+0x204`/`+0x208` pair this item used to name is retracted. `--health-range` now defaults to
   `-1e9:0.0` — it used to be `-0.5:0.5`, which on a 1.0-full float would have called a player at
   40 % health dead. Make sure `PS2X_PEEK` covers the offset (e.g. `*0x408c58+0x1040:4`, which none
   of Task 8's run scripts did): the run prints `reads=` and `misses=` per instance on the RESULT
   line and **fails outright** if an armed watch read nothing.
3. **Until then, `--until-kill` cannot print `PASS`, by design.** `respawn` is a round-end detector
   and a round ends on its clock, so it prints `ROUND-END (unattributed -- NOT a kill)` and exits
   non-zero. That is the instrument being honest, not broken.
4. **The engagement is still the open problem, and it is a geometry problem.** In the one run that
   reached contact the players were never inside 45 units in 3-D, let alone 22. The gate is now 3-D
   plus a height tolerance, and both the approach and the engagement steer to a same-height
   breadcrumb rather than converging into a stack — but see §4.13: none of that has run live.
5. **If elevation ever has to be solved rather than avoided, measure pitch first**, and it costs no
   match: camera-minus-actor is itself a pitch readout (kill2: ground radius 20.65, height 19.73,
   i.e. ~44° above the player), so one timed `I` hold and one timed `K` hold in **any**
   single-instance run give both the sign and the deg/s.
6. **The lobby is still the tax**: two usable approaches out of eight match launches.
   `host_game`/`join_game` still navigate by fixed presses — `choose_map` shows the shape a fix
   takes (verify, then act; abort with a capture otherwise).

### 4.13 What has NEVER run live, and must be treated as untested

Sprint 5's first run will be testing all of this at once, so it should expect the first one to be
diagnostic rather than decisive:

| mechanism | status |
|---|---|
| the 3-D + `\|dy\|` contact gate | simulated only — `kill2` predates it, `frost1` never moved |
| `level_target` / anti-stack steering in the **approach** | 13 of 26 steps in the `stack` simulation, **zero live** |
| the same steering inside the **engagement** | added after `frost1`; never run at all |
| `engage_fight`'s keep-closing step | never run |
| the `--health-offset` watch, in any arming | unit-tested offline (4 reads / 3 changes covered, 4 misses uncovered); never armed in a match |
| `choose_map` on any map but Frostfire | one live map, one reference image |
| the `stack` scenario's premise | a synthetic ramp, not a real floor; the real failure was geometry we cannot simulate faithfully |
| releasing the other side's in-flight hold at contact (`abort=duel.contact`) | five simulated suites; never run live -- and in the real harness it also has to beat the pad file's 60 Hz poll |
| **mutual-pursuit orbiting** at the 3-D gate | a KNOWN FAILURE, 1 of 7 simulated converge runs; unfixed |
| **anti-stack limit cycle** when level ground lies away from the target | a KNOWN FAILURE, 1 of 5 simulated stack runs; unfixed |
| `--health-offset 0x1044` with the `-1e9:0.0` dead range | offline unit test only (0.4 does not fire, 0.0 does); never armed live |

## 4.11 What the review changed, and the map switch (2026-09-13)

Four corrections landed after §4.8 was written. Three of them were defects in this task's own work
and none of them cost a match launch to find.

### The measurement was wrong, and the simulation proves it in a world with no height

`Duel` placed each player at `camera + CAMERA_ORBIT_RADIUS * facing`. A facing wrong by tens of
degrees misplaces a player by up to **two orbit radii, ~50 units** — larger than the whole
engagement range — and placing the *other* player needed the *other* side's facing, which is the
dependency `kill3` could not satisfy. Reproduced offline, in a simulated world that is perfectly
flat:

| scenario | reported best | simulated truth | error |
|---|---|---|---|
| `converge` (before) | 40.3 | 64.3 | −24.0 |
| `route` (before) | 23.4 | 30.7 | −7.3 |
| `caps` (before) | 157.6 | 204.7 | −47.1 |
| **`converge` (after)** | **18.1** | **18.1** | **0.0** |

The fix is `true_pos()`: read the actor's own x/y/z from words 7/8/9 of the peeked block
(`+0x1c/+0x20/+0x24`) and treat the reconstruction as a labelled fallback. Measured over kill2's
1172 paired rows, the camera orbits the actor at a **ground radius of 20.65 (sd 5.17)** and sits
**19.73 above** it — which is also, incidentally, a free pitch readout: the camera looks down on the
player from about **44°**.

### The pitch sweep is retired, on arithmetic rather than on a run

The look response has a **0.44 s dead time**, so `ENGAGE_PITCH_HOLD_S = 0.5` delivers ~0.06 s of
deflection — of the order of **6°** — while §3.x's own probe table records a 2 s `RUP` hold pitching
"to the sky", i.e. saturation. Full-deflection-only injection therefore leaves almost nothing usable
between ~6° and the clamp, and the level-again loop **counted holds**, so the first clamp would
desynchronise the pitch from the facing probe and the forward tap that follow. `ENGAGE_SWEEP_PITCH`
is `False`. Meeting at the same height is the calibrated fix, and the `|dy|` gate plus the
breadcrumb rendezvous is what enforces it. Anyone who wants pitch properly: one timed `I` and one
timed `K` hold in **any single-instance run**, read against the camera-minus-actor elevation above,
gives both the sign and the deg/s without spending a match.

### `RESULT PASS` is now reserved for a kill

`respawn` is a **round-end** detector, and a round ends on its clock too — so with a 470 s timeout
against a round of a few minutes, the acceptance test could have printed `RESULT PASS
signal=respawn` for a test whose acceptance is a kill. That is the same defect as the
`MediusPlayerReport` one, one level down. The verdict is now: `PASS` only when the firing signal is
`health`; `PASS (round end corroborated by a health transition)` when both fired; otherwise
**`ROUND-END (unattributed -- NOT a kill)`**, and `--until-kill` exits non-zero. With the health
offsets unconfirmed, that means **`--until-kill` cannot currently print PASS at all**, which is the
honest state of the instrument rather than a bug in it.

### The map is now chosen, not accepted

`host_game` used to take whatever was highlighted: `sh.press("cross", 4.0)  # Medley`. The owner
asked for **Frostfire**, and the AVAILABLE MAPS box holds six visible rows and **scrolls**, so no
fixed number of presses is knowable in advance.

One single-instance scan (`--only A --map-scan 26`, `logs/parity/ours_task8_mapscan`, **no match
created**) walked the list capturing every screen. The list, in order:

> Medley, Random, VIGILANCE, THE MIXER, FOXHUNT, SUJO, ENOWAPI, SHADOW FALLS, FISH HOOK,
> CROSSROADS, SANDSTORM, CHAIN REACTION, GUIDANCE, REQUIEM, BLIZZARD, **FROSTFIRE**, ABANDONED,
> DESERT GLORY, NIGHT STALKER, RAT'S NEST, BITTER JUNGLE, BLOOD LAKE, DEATH TRAP, THE RUINS.

`choose_map` verifies before it accepts, in two independent steps, both measured off those captures:

1. **Which row is highlighted**, from an absolute luminance band and no reference image at all: the
   highlighted row's peak luminance is **123–125** in all 27 captures, an ordinary row's pale text
   **168–174**, an empty row **99–110**. Rows are at y = 117 + 20·i, height 12, x 78–292.
2. **Whether that row is the map asked for**, by a **text-mask distance** (symmetric difference over
   union of the binarised rows, best over ±3 px of shift) against `scripts/parity/refs/map_*.png`.
   The contrast-normalised band distance `Shell.diff` uses was **not good enough** — it scored
   ENOWAPI at 0.317 against a 0.42 threshold, i.e. it would have accepted the wrong map.

Offline acceptance over all 28 CHOOSE GAMES captures this repo has: **cursor found on 28 of 28,
FROSTFIRE matched on exactly 1**, distance **0.005** against a nearest rival of **0.510** and a
threshold of 0.30. A map with no reference, or a map never highlighted in 30 presses, **aborts with
a capture** — it never accepts whatever happens to be there.

**And the mined corridor is dropped on any map it was not mined for.** `MINED_ROUTE_MAP` is
`medley`; on anything else the banner reads `route=direct`, because a corridor that does not exist
is worse than no corridor — the loop believes it.

### 4.12 Frostfire — the map switch worked, and the players could not move (2026-09-13)

`logs/s4_task8_frost1.sh`, `logs/parity/drive_task8_frost1.txt`,
`logs/run_A_20260913_004754.log` / `run_B_…`, `logs/parity/ours_task8_frost1/`.

**Everything upstream of gameplay worked, first launch.** The verified map selection found
FROSTFIRE at row 4 after 15 DOWN presses with a text-mask distance of **0.005** against a 0.30
threshold — the offline prediction exactly — the lobby launched, and the banner read
`map=frostfire route=direct engage3d=22.0 dy_tol=10.0 pos=actor health=disarmed`. Liveness passed
on both instances (163 / 162 in-game rows at the check, **1152 / 1151 actor rows** by the end), and
`src=actor/actor` in every step line: the actor read was live on both sides.

**The first thing to measure on a new map, as asked, and it is good news:**

| | mp51 / Medley | Frostfire |
|---|---|---|
| spawn separation (actors, 3-D) | 1485.5 | **692.1** |
| spawn separation (ground) | — | 690.8 |
| height difference at spawn | — | **+41.9** (A below B) |
| A spawn | (542.3, 1479.9) | (795.7, 613.6) |
| B spawn | (1144.8, 77.5) | (535.7, 1253.6) |

Less than half the gap — two movers would have had ~350 units each — but a 42-unit height
difference is there from the spawn, so the vertical problem is not specific to where kill2 happened
to meet.

**And then neither player moved at all.** Over 240 s of approach and 1152 position rows, A's camera
record spanned **2.5 units of x** (793.2–795.7) and B's spanned **0.0** (511.7 throughout). Both
sides ran all six facing probes and every one measured **0.00 units**; both then fell back to an
untrusted facing — which is the only reason the run produced any data at all, since the previous
code would have aborted both sides — and every burst after that also moved nothing. Final result:
`time-cap`, `contact=False`, `closest_3d=692.07`, i.e. the starting separation.

**This is not an instrumentation failure, and the run says so four ways:**

- The injected pad state reached the guest: `ly=00` (full forward) on 31 polls, `lx=00` on 11,
  `rx=00` on 4, against 338 neutral.
- The movement scale was **live, not frozen**: every `f12` row read `1.0`, so this is not §3.12's
  lag freeze.
- The match was really in gameplay: `A_hold02.png` shows the HUD, the round clock counting down
  from **05:19**, `30/30 5 MAGS` and a squad marker.
- The actor chain resolved on both instances for the whole run.

**And the movement routine was not "slow" — it stopped.** The first draft of this section read
`PS2X_CALL_TRACE_EVERY=10` off the environment and divided, giving "about 360 calls, roughly one a
second". That is wrong by a factor of twenty, and the tracer's own rule says why:
`callTraceShouldLog(n)` is `n < 300u || (n % every) == 0u` — **the first 300 calls of a slot are
logged unconditionally**, and `EVERY` only begins to thin after that. Frostfire never got near 300,
so every call was logged:

| | `[call]` lines | `[ret]` lines | actual calls | window | rate |
|---|---|---|---|---|---|
| `frost1` | 18 | 18 | **18** (`#0`–`#17`) | **t = 371.4 s → 372.0 s** | — |
| `kill2` A | 826 | — | 300 + 10·526 ≈ **5560** | t = 418.5 s → 712.1 s | **18.9 / s** |

So the honest shape is not a slow map. **The local move path was entered for 0.6 seconds at round
start and then never ticked again**, while 2634 sampler rows kept arriving and the round clock kept
running. That reads as **control never being handed to the client** — the round starts, the actor
exists and is sampled, and the routine that would consume the stick is simply not called — rather
than as movement being throttled. It is the same sentence §3.8 had to retract and restate once
already, arriving on a different map.

**What this is, honestly, is one run.** It has the shape of the defect this entire note exists
about — the round runs and the local player cannot move — reappearing on a map the movement fix was
never tested on; §3.12's fix was measured on mp51 and only on mp51. But a single match cannot
separate "Frostfire-specific movement defect" from "this particular match never handed control to
either client". The cheap next step is another Frostfire launch: if it reproduces, the call rate of
`FUN_00553dc0` is the thread to pull, and `PS2X_SOCOM2_NET_STATS` / the `0x200` idle counter of
§3.12 are where to look. **It should not be assumed that movement works on any map but mp51.**
