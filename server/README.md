# Local Horizon Private Server for SOCOM II (app id 10472)

This folder is a self-contained, Docker-free bring-up of the
[Horizon Private Server](https://github.com/Horizon-Private-Server/horizon-server)
(Medius/DME/NAT/MUIS emulator, C#/.NET 9, MIT) configured for SOCOM II NTSC
(Medius app id **10472**, "Medius Client Library Version 1.50.0013", DME client 1.32.0070).

Status as of 2026-09-19: **hosted on Linux at 3.143.65.100 and played on** (see "Hosting it on Linux"). Status as of 2026-09-04: **builds and runs**; all listeners verified; DME authenticates with MPS;
a scripted client completes the MAS RT handshake for app id 10472. No SOCOM II client has been
connected yet.

## Layout

| Path | What |
|---|---|
| `horizon-server/` | Plain copy of `research/horizon-server` (no `.git`), built in place. Two tiny local fixes, see below. |
| `horizon-server-database-middleware/` | Shallow clone, **reference only** (SQL scripts, DTO shapes). Not needed to run. |
| `horizon-docker/` | Shallow clone, reference only (upstream sample `medius.json`/`dme.json`/`muis.json`). |
| `config/` | The live configuration: `nat.json`, `muis.json`, `medius.json`, `dme.json`, `db.config.json`, `simulated.db`. |
| `logs/` | Console captures (`console-<component>.log`) and the servers' own rolling logs (`medius.log`, `dme.log`, `muis.log`). |
| `medius-plugins/`, `dme-plugins/`, `files/` | Empty dirs the servers expect relative to the working directory. |
| `start-servers.ps1` | Start / `-Stop` / `-Status` / `-Build` the stack; `-PublicIp` / `-ShowIp` set and show the advertised address. |
| `seed-simulated-db.ps1` | Write (or `-Show`) the encrypted `config/simulated.db` (test account + per-app settings). |
| `build-release.log` | Output of the first full `dotnet build` (0 errors, 16 warnings, 17 s). |

## Quick start

```powershell
cd C:\projects\socom_pc\server
.\start-servers.ps1            # Separate mode (default): NAT, MUIS, Medius, DME as four processes
.\start-servers.ps1 -Status    # which ports are listening
.\start-servers.ps1 -Stop
.\start-servers.ps1 -Build     # rebuild horizon-server\Horizon.Server.sln (Release) first
.\start-servers.ps1 -ShowIp    # what address will clients be told to connect back to?
.\start-servers.ps1 -PublicIp 203.0.113.7    # advertise that address, then start
```

Prerequisite: .NET SDK 9.x (9.0.204 and 10.0.400 are installed; every project targets `net9.0`, no retargeting was needed).

### Ports (all bind 0.0.0.0)

| Port | Proto | Component | Config key |
|---|---|---|---|
| 10071 | TCP | MUIS (Medius Universe Information Server) | `muis.json: Ports` |
| 10075 | TCP | MAS (authentication) | `medius.json: MASPort` |
| 10078 | TCP | MLS (lobby) | `medius.json: MLSPort` |
| 10077 | TCP | MPS (proxy; DME servers register here) | `medius.json: MPSPort`, `dme.json: MPS.Port` |
| 10073 | TCP | DME TCP (game/world data) | `dme.json: TCPPort` |
| 10070 | UDP | NAT (address echo) | `nat.json: Port`, `medius.json: NATPort` |
| 50000+ | UDP | DME UDP, one socket per connected client, bound on demand | `dme.json: UDPPort` |

### Advertised address (what clients are told to connect back to)

Binding and advertising are two different things. Everything binds `0.0.0.0`, but Medius/MUIS also *hand the
client an address* in their replies, and the client dials that. It must therefore be an address the client can
reach: the host's LAN IP for a PS2/emulator on the same LAN, the host's public IP for a hosted server. With
`"UsePublicIp": true` that address comes from the config; with `false` Horizon picks the first LAN adapter IP
(`Utils.GetLocalIPAddress`), which is also the only way to get loopback advertised as something else.

Six fields carry it, and `start-servers.ps1` sets all six at once:

```powershell
.\start-servers.ps1 -ShowIp                    # print the six fields and their current values
.\start-servers.ps1 -PublicIp 203.0.113.7      # rewrite them, then start
.\start-servers.ps1 -PublicIp 192.0.2.50 -NoStart     # rewrite only (also takes -ConfigDir <dir>)
```

| File | Field | What reads it |
|---|---|---|
| `medius.json` | `PublicIpOverride` | MAS/MLS tell the client where MLS and the DME game server live |
| `medius.json` | `NATIp` | address of the NAT/address-echo service handed to the client |
| `dme.json` | `PublicIpOverride` | DME's own address, registered with MPS and passed to joining clients |
| `muis.json` | `Universes["10472"][0].Endpoint` | the universe MUIS points SOCOM II at |
| `muis.json` | `Universes["0"][0].Endpoint` | same, fallback universe for unknown app ids |

`-PublicIp` accepts an IP or a hostname, rewrites only those fields (formatting and every other key preserved),
prints one `<file>: <field> -> <ip>` line per change, and refuses to write anything that would not parse back as
JSON. Without it the config files are left exactly as they are. **`dme.json: MPS.Ip` stays `127.0.0.1`** - that is
DME reaching Medius on the same machine, not an address any client sees; `-PublicIp` never touches it and `-ShowIp`
prints it greyed out so nobody "fixes" it.

**The advertised address is a required value.** The tracked configs carry `192.0.2.1`, a documentation address
(RFC 5737) that no client can reach and nobody's own network, in all six fields. Both launch scripts refuse to
start while any field still holds an RFC 5737 address -- `start-servers.ps1` and `linux/horizon-ctl.sh start` /
`restart` exit 2 with one sentence naming the fields and the step that sets them (`-PublicIp`, `public-ip`) -- so the
first run anywhere is `-PublicIp <this machine's LAN or public address>`; no hand-editing of JSON is needed.
`-CheckOnly` (Linux: `check`) runs that check alone, after any rewrite, and starts nothing. The addresses in the
examples above (`203.0.113.7`, `192.0.2.50`) are documentation addresses too: use your own.

**A developer in a clone** should not rewrite the tracked configs: copy `config/` to a git-ignored folder (`logs/`
is ignored) and pass it every time, e.g. `.\start-servers.ps1 -ConfigDir logs\my-config -PublicIp <address>` (the default Separate mode; Unified always reads `config\`). A
rewritten tracked config must not be committed -- the leak check's `tree` and `staged` modes report any private
address in a tracked file (`tracked-private-ip`, Sprint 13 S6). The vendored
servers' own initial `SERVER_IP` (`Server.Dme/Program.cs`, `Server.Medius/Program.cs`) is the same placeholder,
replaced as soon as the config loads.

### Hosting it on another machine: ports to forward

Advertise the public address (`-PublicIp`), open the Windows firewall for the five server processes, and forward
these from the router to the host. Ports are as listed in the table above and verified by `-Status`:

| Forward | Proto | Why |
|---|---|---|
| 10070 | UDP | NAT / address echo - the client asks it "what address do you see me on?"; NAT traversal fails without it |
| 10071 | TCP | MUIS - the first connection the game makes (universe lookup) |
| 10075 | TCP | MAS - authentication |
| 10078 | TCP | MLS - lobby |
| 10073 | TCP | DME TCP - game/world data |
| 50000+ | UDP | DME UDP game data, one socket per connected client, bound on demand from `dme.json: UDPPort` upward. Forward a range (e.g. 50000-50100) sized for the player count; a single 50000 rule only covers the first client. |

Checked against what the stack actually binds (Sprint 7 Task 4 Step 4, 2026-09-17, four processes running):
`Get-NetTCPConnection -State Listen` owned by the server processes reports **10071, 10073, 10075, 10077, 10078**
and `Get-NetUDPEndpoint` reports **10070** on `0.0.0.0`; nothing else. Every one of them is in the two tables
above, so the forward list is complete. The 50000+ DME UDP sockets are bound per client on demand and so show up
only while a client is connected - none were, which is why they are absent from that capture rather than from the
list.

### Hosting it on Linux (Sprint 8 Goal 12, 2026-09-19)

The binaries are framework-dependent `net9.0` and run unchanged under the .NET 9 runtime (`dotnet <Proj>.dll <config dir>`);
only the glue is per-platform. `linux/` is that glue for Ubuntu 24.04:

| File | What |
|---|---|
| `linux/install.sh` | As root, from the unpacked server folder: the runtime, a `horizon` user, the folder under `/opt/socom-unzipped-server`, the units, a logrotate rule. Idempotent; never overwrites an installed `config/`. |
| `linux/horizon-{nat,muis,medius,dme}.service`, `horizon.target` | The Separate mode as four units (the unified launcher's race applies on Linux too). DME waits for MPS on 10077 (`wait-for-port.sh`). Consoles go to the journal: `journalctl -u horizon-medius`. |
| `linux/horizon-ctl.sh` | `start`, `stop`, `restart`, `status`, `show-ip`, `public-ip <ip or hostname>`, `check` -- `start-servers.ps1`'s verbs, with the same six-field rewrite, the same refusal to start on an RFC 5737 placeholder, the same untouched `MPS.Ip`, the same refusal to write JSON that does not parse (`tools_py/tests/test_horizon_ctl.py`). |

`seed-simulated-db.ps1` stays PowerShell: seed on a Windows machine (inside the package folder, so the repo's own
database is not involved) and copy `config/simulated.db` up. On a cloud box the advertised address is the public
(static) one, never the private address the interface carries; open the same ports in the provider's firewall
(the table above, the UDP range included) and leave 10077 closed.

**Verified on the project's hosted box (3.143.65.100, 2 vCPU / 2 GB, 2026-09-19):** from outside, 10071, 10073, 10075 and
10078 accept and 10077 does not; any datagram to 10070/udp is answered with the sender's public address and port;
`Server.Test` completes the MAS handshake for app id 10472 against the public address; the four processes hold about
335 MB resident between them; a reboot brings every listener back unattended. **And played on (same day):** two instances of the PC client behind one home NAT logged in (a first login on a
new server address is a create-persona login: the game saves personas per server address, so moving the address
orphans them), hosted and joined on Frostfire, played a full five-minute control round (`s8_hosted_control2`) and a
four-round ladder with two kills (`s8_hosted_kill`); two 50000+ sockets bound per round, 537 MB resident after it.
Ubuntu's `needrestart` restarted the units during an unattended upgrade once; `install.sh` now excludes them.

### Message of the day, channel name, live stats (Sprint 8 Goal 13, 2026-09-19)

`config/db.config.json` carries what simulated mode tells the game: `SimulatedAnnouncementTitle` and
`SimulatedAnnouncementBody` (the game asks for it with `MediusGetAnnouncements` at login; title and body are sent
as `title\nbody\n`), `SimulatedChannelName` (the lobby channel the game lists; upstream's is "Channel 1") and
`SimulatedLocationName`. The tracked config sets the announcement ("Welcome to the SOCOM Unzipped Project", then
upstream's own two lines kept as the credit); the channel and location are the box's own
("US East (Ohio)", "AWS us-east-2 (Ohio)") and live only in the hosted box's config.

`config/medius.json` on the hosted box adds `"StatsPrefix": "http://+:10080/"`, `StatsServerName` and
`StatsLocation`: Medius then answers `GET /stats` with one JSON snapshot (status, server, location, uptime, players
online / in game / in lobby with names, open games with name, host, slots, level, status and roster, lobby channels,
and since-start counters: games created, distinct players, peak players). The provider's firewall opens 10080 to the
website's box only; s2u.scotho.com's nginx proxies and micro-caches it as `/api/stats` (`../scotho/apps/s2u`). On
Windows use `"http://127.0.0.1:10080/"` (a `+` prefix needs a URL ACL there). Empty or absent = off, which is the
tracked config.

Packaging this folder for the hosting machine: `bash scripts/make_server_zip.sh [out dir]` (default `dist/server`)
writes `socom-unzipped-server/` and `socom-unzipped-server.zip` -- `horizon-server/` with its Release binaries (no
`obj/`, no `bin/Debug/`), the empty `dme-plugins/`, `medius-plugins/`, `files/`, `logs/`, `config/` **without
`simulated.db`** (the host seeds their own; `config/README.txt` in the zip says how), plus `start-servers.ps1`,
`seed-simulated-db.ps1`, `linux/` and this README.

**10077/TCP (MPS) does not need forwarding** as long as DME runs on the same machine as Medius: `dme.json` has
`"MPS": { "Ip": "127.0.0.1" }`, so that connection never leaves the host. It only becomes an external port if DME
is split onto a separate box, and then it should be restricted to that box, not exposed to the internet.

Unverified on a real hosted machine: nothing here has been run outside the LAN yet (see Status above - no SOCOM II
client has connected). Expect the NAT/UDP path (10070 and the 50000+ range) to be where a hosted bring-up first
bites, since that is the part that depends on the advertised address being reachable from the client's side.

App ids: MUIS has a `Universes` entry keyed `"10472"` (plus a `"0"` fallback, which MUIS uses for
unknown app ids). DME has `"ApplicationIds": [10472]`. Medius has **no** app-id list of its own; the set of
accepted app ids comes from the database (`Database.GetAppIds()`), which in simulated mode returns 0..99999,
so 10472 is accepted (`MAS.cs` rejects and closes the socket on `RT_MSG_CLIENT_CONNECT_TCP` for unknown ids).

## Database: none required (simulated mode)

`Server.Database.DbController` has two backends selected by `config/db.config.json`:

* `"SimulatedMode": true` (what we use, and also the upstream default) - everything in memory; accounts/clans/
  per-app settings are persisted to `config/simulated.db` when `SimulatedEncryptionKey` is set
  (AES-256-CBC, key = SHA256(passphrase), 16-byte IV prefix; see `DbSimulated.cs`).
* `"SimulatedMode": false` - REST calls to the **horizon-server-database-middleware** (ASP.NET Core, EF Core,
  `UseSqlServer`), which itself needs SQL Server. Stats, ladders, announcements, ban lists, clans across restarts
  etc. only really work in this mode.

Simulated-mode limitations that matter here:
* `SetServerSettings()` is a no-op and `GetServerSettings()` only returns what was loaded from `simulated.db`.
  The per-app `AppSettings` (`EnableEncryption`, `CreateAccountOnNotFound`, text filters, timeouts...) therefore
  can only be set by seeding the file: `.\seed-simulated-db.ps1 [-EnableEncryption True] [-CreateAccountOnNotFound True]`.
  Current seed: account **socom / socom** for app id 10472, `EnableEncryption=False`, `CreateAccountOnNotFound=True`
  (so any name the game logs in with is auto-created). Run it with the servers stopped; verify with `-Show`.
* Announcements/policies return canned values, stats are not persisted, `GetPlayerList` returns `[]`.

### If/when a real database is wanted

This machine has SQL Server 2022 (`MSSQL$SQL2022`, service **stopped**) and SQL Server LocalDB 2019 + 2025
(`sqllocaldb info` -> `MSSQLLocalDB`), `sqlcmd` (ODBC 17) is on PATH. Nothing needed installing. Steps (not executed):

1. Start an instance: `Start-Service 'MSSQL$SQL2022'` (needs admin) or `sqllocaldb start MSSQLLocalDB`
   (connect as `(localdb)\MSSQLLocalDB`, Windows auth).
2. Run `horizon-server-database-middleware\Horizon.Database\scripts\CREATE_DATABASE.sql` then `CREATE_TABLES.sql`
   (creates `Medius_Database`, schemas `ACCOUNTS`, `KEYS`, ..., seeds `KEYS.roles`).
3. `INSERT INTO KEYS.dim_app_ids (app_id, app_name, group_id) VALUES (10472, 'SOCOM II NTSC', NULL);`
   (or list it under `AppIds` in the middleware's `appsettings.json`, which imports app ids/locations/channels at start).
4. Run the middleware (`dotnet run` in `Horizon.Database`, env `HORIZON_DB_SERVER`, `HORIZON_DB_NAME`,
   `HORIZON_DB_USER`, `HORIZON_MSSQL_SA_PASSWORD`, `HORIZON_MIDDLEWARE_SERVER=http://0.0.0.0:10000`,
   `HORIZON_MIDDLEWARE_USER/PASSWORD`). Note it uses SQL auth env vars; LocalDB would need a SQL login enabled.
5. Set `db.config.json` to `"SimulatedMode": false, "DatabaseUrl": "http://127.0.0.1:10000"` with the middleware
   admin user (it needs the `database` role - see upstream README).

## What was verified

1. `dotnet build Horizon.Server.sln -c Release`: 0 errors on the unmodified copy (`build-release.log`).
2. `Server.Unified.Launcher` (one process): all of 10071/10075/10078/10077/10073 TCP + 10070 UDP listening,
   DME -> MPS: `RT_MSG_CLIENT_HELLO Version:110` ... `MediusServerSetAttributesResponse MGCL_SUCCESS`,
   "Successfully authenticated with MPS".
3. Separate mode: same listeners across four processes, DME authenticated with MPS, empty stderr.
4. Handshake smoke test with the repo's `Server.Test` client (after the harness fixes below), app id 10472,
   hello version 108 (PS2-era path):
   `CLIENT_HELLO -> SERVER_HELLO -> CLIENT_CRYPTKEY_PUBLIC -> SERVER_CRYPTKEY_PEER -> CLIENT_CONNECT_TCP(AppId 0x28E8)
   -> SERVER_CRYPTKEY_GAME + SERVER_CONNECT_ACCEPT_TCP + SERVER_CONNECT_COMPLETE`. (The `fail: ScertEncoder ...
   10054` line that follows in the server log is just the test client being killed.)
5. `seed-simulated-db.ps1` output decrypts back to the intended JSON (`-Show`).
6. **RSA key check against the game**: Horizon's default RSA modulus
   `N = 0xc4f75716ec835d2325689f91ff85ed9bfc3211db9c164f41852e264e569d2802008054a0ef459e7e3eabb87fae576e735434d1d124b30b11bd6de09814860155`
   (512-bit, e = 17) is present **little-endian in `game/disc/socom2_game.elf` at file offset 0x488A28**,
   immediately followed by `E8 28 00 00` (= 10472) at 0x488A68, i.e. it is the client's baked-in Medius server key.
   Horizon's `DefaultKey` therefore carries the matching private exponent and can decrypt SOCOM II's RSA-encrypted
   `CLIENT_CONNECT_TCP`. Another 64-byte blob follows at 0x488A70 (unidentified - possibly a second key).

## Local source changes (all marked `LOCAL FIX (socom_pc)` in code)

No build fixes were needed. Runtime/harness fixes:

| File | Change | Why |
|---|---|---|
| `Server.NAT/Program.cs` | `await Task.Delay(Timeout.Infinite)` after `NATServer.Start()` | Standalone `Server.NAT.exe` exited right after binding (event-loop threads are background threads); only worked inside the unified launcher. |
| `Server.Test/Program.cs` | Set `ScertClientAttribute.DefaultRsaAuthKey` from `config.json` key | Test harness NRE'd in `ScertClientAttribute` ctor before sending anything. |
| `Server.Test/Test/ClientLoginLogout.cs` | `ApplicationId` from `config.json` (was hard-coded 11184) | Test with 10472. |
| `Server.Test/Medius/BaseClientConnect.cs` | Hello version 110 -> 108 | 110 makes the server answer `CONNECT_REQUIRE`, which the harness never handled; 108 is the PS2-era path. |
| `Server.Database/Config/DbSettings.cs`, `Server.Database/DbController.cs` | `SimulatedAnnouncementTitle`/`Body`, `SimulatedChannelName`, `SimulatedLocationName` in `db.config.json`; null keeps upstream's canned value | Simulated mode hard-coded the message of the day ("Horizon Medius Server / Source available on GitHub"), the lobby channel ("Channel 1") and the location (Sprint 8 Goal 13). |
| `Server.Medius/StatsServer.cs` (new), `Program.cs`, `Medius/MediusManager.cs`, `Config/ServerSettings.cs` | `GET /stats` JSON on `medius.json: StatsPrefix` (empty = off), snapshot built on the tick thread every 2 s | Live server stats for s2u.scotho.com: players, games, channels, uptime, since-start counters; names and counts only, never an address or a key. |

Known upstream issues found (not fixed, worked around by the script):
* **Unified launcher race**: `LogSettings.Singleton` is one static shared by all four components in the process and
  rewritten by each on its 5 s config refresh. DME (started 5 s later) can read another component's `LogPath`, fail to
  open the already-open file (`NReco` opens with `FileShare.Read`) and die silently inside an unobserved `Task.Run`
  (symptom: 10073 never listens; happened on the 2nd unified launch). `Separate` mode avoids it.
* `NReco.Logging.File` rolling logger globs `<basename>*.log` in `logs\` and reopens the newest match: any foreign
  file named `dme*.log`/`medius*.log`/`muis*.log` that is held open crashes that server at start. Console captures are
  therefore named `console-<component>.log`.
* Simulated `GetAppIds()` returns 0..99999, so Medius and DME allocate 100 000 `AppSettings` objects and re-walk them
  every 5 s. Harmless locally.

## What remains / risks for SOCOM II (Medius 1.50 client)

Horizon was built from Insomniac titles (Ratchet: UYA/Deadlocked, app ids 10683/10684/11184, "MediusVersion"
108-109 for PS2, 112/113 for PS3 UYA HD). SOCOM II is a 2003 Medius 1.50 title, older than anything Horizon targets.
Things to expect, roughly in order of likelihood of biting:

1. **RT version negotiation.** `ScertClientAttribute` derives `MediusVersion` from `RT_MSG_CLIENT_HELLO.Parameters[1]`
   and defaults to 108 if the first message is `CLIENT_CONNECT_TCP`. The <109 code paths (`CONNECT_TCP` has an extra
   `UNK0` byte, `CONNECT_ACCEPT_TCP`/`CONNECT_NOTIFY`/`DISCONNECT_NOTIFY`/`SET_RECV_FLAG`/`CONNECT_AUX_UDP` have
   short forms when `<= 108`) are the ones SOCOM II will hit. If SOCOM II sends a HELLO with a smaller version
   number nothing breaks numerically (all checks are `> 108`, `>= 109`, `>= 112`), but field layouts for genuinely
   pre-108 messages are unverified. Capture the first packets from the game and compare against `RT.Models/RT/*.cs`.
2. **Encryption.** Per-app `EnableEncryption` defaults to **false** (Horizon's own titles run unencrypted, sample
   middleware settings use `"EnableEncryption": "False"`). With it false the server sends `SERVER_HELLO` with a zero
   RSA key and all replies in plaintext, while it still *decrypts* anything the client encrypts (the decoder does not
   check the flag). Whether a retail 1.50 client tolerates plaintext replies is unknown; if it stalls after
   `CONNECT_TCP`, re-seed with `-EnableEncryption True`. The RSA modulus itself matches (see above), so the encrypted
   path is viable.
3. **Medius lobby message IDs / layouts.** `RT_MSG_CLIENT_APP_TOSERVER` payloads are dispatched by
   `(NetMessageTypes class, byte type)` through `MediusLobbyMessageIds`/`MediusLobbyExtMessageIds`/`MediusMGCLMessageIds`
   (`RT.Common/Types.cs`). Unknown ids become raw messages and are logged, not fatal, but every SessionBegin /
   AccountLogin / SetLocalizationParams / GetPolicy / CreateGame / JoinGame variant SOCOM II uses must exist with the
   1.50 field layout. Horizon has several `...Request0/1` legacy variants (e.g. `MediusSessionBegin1Request`,
   `MediusSetLocalizationParamsRequest1`, `MediusSetGameListFilterResponse0`) which suggests partial coverage of older
   clients; expect to add or adjust some. `Server.Medius/Medius/MAS.cs` (1.2k lines) and `MLS.cs` (4.2k lines) are the
   handlers; `Logging.LogLevel = 1` (Debug) in all configs prints every RT and Medius message.
4. **App-id gated behaviour.** Very little is hard-coded per app id: MAS/MLS gate only on
   `Manager.IsAppIdSupported()`; MPS pairs DME servers to clients by app id (`x.ApplicationId == appId || == 0`);
   `GetAppSettingsOrDefault(appId)` supplies filters/timeouts. Game-specific behaviour upstream lives in plugins
   (`medius-plugins/`, `dme-plugins/`), none of which apply to SOCOM II.
5. **DME 1.32 client vs Horizon DME.** `RT_MSG_CLIENT_CONNECT_AUX_UDP`/`CONNECT_TCP_AUX_UDP` have `<= 108` short forms;
   SOCOM II's peer-to-peer/relay model (host migration, its own UDP game protocol on 50000+) is untested.
6. **MUIS.** Responds to `MediusGetUniverseInformationRequest` with `Universes["10472"]`; if SOCOM II's 1.50 client
   uses an older universe-info request/response shape, adjust `Server.UniverseInformation/MUIS.cs`.
7. **DNAS / SCE-RT extras.** `MediusDnasSignaturePost` is accepted and ignored. Anything the game expects around
   `MediusGetPolicy` (usage/privacy text) is served from simulated defaults.

Suggested next step: point the game (or an emulator with the network plugin) at the server host - the same address
`-ShowIp` reports - via a DNS/hosts override for the SOCOM II MUIS hostname, watch `logs\console-MUIS.log` then
`console-Medius.log` at Debug level, and diff the first `RT_MSG_CLIENT_*` frames against the message classes in `horizon-server\RT.Models\RT\`.
