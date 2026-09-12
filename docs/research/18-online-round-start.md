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
