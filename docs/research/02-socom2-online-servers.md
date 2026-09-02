# SOCOM II online revival — servers, client patches, protocol (research, 2026-09-02)

## Summary
- **PS Rewired** (https://psrewired.com, guide https://psrewired.com/guides/socom2) is the only live SOCOM II server. It absorbed "SOCOM Community" (Harry62). Its Medius server is **closed source**; auxiliary tools on GitHub (org PSRewired: Game-Information, SOCOM-Data-Dump, Memdusa, FragmentServer, RetroDNS, PCSX2-Custom-Installer).
- SOCOM II **Medius app IDs** (PS Rewired list): NTSC **10472**, NTSC beta 10202, PAL/AUS 10481, PAL beta 10540, JP 10501, KOR 10511. Player DNS 67.222.156.250.
- **No open-source Medius server lists SOCOM II.** Best open base: **Horizon Private Server** (C#/.NET, **MIT**): https://github.com/Horizon-Private-Server/horizon-server (projects Server.Medius = MAS+MLS+MPS+NAT, Server.Dme, Server.UniverseInformation = MUIS, RT.Common, RT.Cryptography, RT.Models, Server.Database, Server.Plugins). Also horizon-docker, horizon-dns (DNS + DNAS replacement on 443 with SSLv2), horizon-server-database(-middleware). App IDs are config (`dim_app_ids`, `APP_ID` env), but only Ratchet UYA/Deadlocked are tested; SOCOM II message coverage **unverified**.
- Horizon default ports: MAS 10075, MLS 10078, MPS 10077, NAT 10070/udp, DME 10073 tcp / 50000 udp, MUIS 10071. Docker compose: horizon-server + horizon-middleware (10000/10001) + MSSQL 1433.
- Alternatives: hashsploit/clank (Java, Medius 1.5–1.8; clank-dnas, medius-crypto, medius-wireshark, packet-captures — no SOCOM), GitHubProUser67/PSHome-MultiServer (C#, GPL-3, lists SOCOM FTB1/FTB2/Confrontation, not SOCOM II).

## Client identification
- NTSC-U SCUS-97275 (and SCUS-97275GH Greatest Hits, same disc), ELF `SCUS_972.75`, PCSX2 CRC **0F6FC6CF**, disc version 1.02 = code revision **r0001**; Sony pushed **r0004** to memory card on login (adds 3 HDD maps). Other: SCUS_973.66 (beta), SCES_523.06 / SCES-51904 (PAL), SCPS_150.65 (JP), SCKA_200.20 (KOR).

## DNAS bypass (published)
From PSRewired/Game-Information `PS2/SOCOM II US Navy Seals/SCUS_972.75`:
```
DNAS Bypass r0001:  202CC670 03E00008 / 202CC674 00000000   (jr ra; nop)
DNAS Bypass r0004:  203953C0 03E00008 / 203953C4 00000000
alt:                202CC798 24020001                        (li v0,1)
```
PS Rewired pnach (Harry62, https://psrewired.com/downloads/0F6FC6CF.pnach): code cave at 0x9F000 hooked by `jal` at 0x1E70CC; checks whether 0x2CF330 holds `addiu sp,sp,-0x40` (r0004 loaded) and stubs 0x2CF330, else stubs 0x2CC670 (r0001). PS2 hardware equivalents: `r0004v002.elf`, `r0004nodns.elf`.
Note: 0x2CC670 lies inside the `ftscore` overlay region (0x1e7000–0x4b5380).

## Hostnames the game resolves (redirect via DNS; no ELF patch needed)
- `socom2-prod.pdonline.scea.com`, `socom2-prod.svo.pdonline.scea.com` (MAS/MLS)
- `socom2-prod.muis.pdonline.scea.com` (MUIS NTSC); PAL `socom2-palmaster-muis.online.scee.com`; AUS `socom2-prod-muis.rt.au.playstation.com`
- `updates.pdonline.scea.com` — HTTP patch server, path `/_socom2-prod/currentpatch/APACHE00.ZDB` (how r0004 is delivered)
- `gate1.us.dnas.playstation.org` (DNAS, TCP 443)
- Ports for SOCOM II not published; Horizon defaults are the standard Sony scheme (unconfirmed).

## Topology
- SOCOM II is a Medius **P2P** title: lobby via MAS/MLS/MUIS over TCP, NAT server UDP for hole punching, match traffic host-based peer-to-peer over UDP (voice too). No DME game server expected (inferred: Horizon `NetConnectionTypePeerToPeerUDP`, hashsploit docs, DSLReports thread). A Bandwidth Probe Server picks hosts.

## PCSX2 networking
- DEV9 built in: PCAP Bridged/Switched, TAP, **Sockets** (PR #4944, 2022; hosting "not expected to work"). Internal DNS (PR #4220): PS2 DNS `192.0.2.1`; `DEV9Hosts.ini` maps hostnames, rewrites 127.0.0.1 to host adapter IP — designed for local revival servers.
- HDD optional (r0004 maps); community `SOCOM II HDD.raw`.

## Medius protocol references
- hashsploit wiki https://wiki.hashsploit.net/PlayStation_2#Medius (often down); Horizon `RT.Common/Types.cs` (`RT_MSG_TYPE`: CLIENT_CONNECT_TCP 0x00 … CLIENT_HELLO 0x24, SERVER_HELLO 0x25, MULTI_APP_TOSERVER 0x3B…), `RT.Models/`, `RT.Cryptography/` (512-bit RSA key exchange, RC4-like "RCQ" per message). Medius lobby ids: SessionBegin 0x03, AccountLogin 0x07, AccountRegistration 0x09, AnonymousLogin 0x19, CreateGameRequest0 0x1D, JoinGameRequest0 0x23 …
- Medius version used by SOCOM II (late 2003) unknown; expect version-specific struct differences.
- Wireshark dissector: hashsploit/medius-wireshark. SCE-RT SDK exists on archive.org ("PS2 SDKs" item: SCE-RT.rar, LibDNAS.7z).

## Practical path
1. Stand up Horizon (`APP_ID=10472`) + horizon-dns/DNAS stub. 2. Point the client at it via DNS/hosts. 3. Bake the DNAS stub into the rebuilt client. 4. Capture the MAS handshake and adapt Horizon message models where SOCOM II diverges. 5. Optionally serve r0004 via HTTP.

## Community
- PS Rewired Discord (hub), SOCOM HQ (https://socomhq.com/connect-socom-2), SOCOM Community Discord, Zero1UP/Socom2StreamData, Zero1UP/ps2disSharp, GO0dspeed/Socom2-SteamDeck, harry6two/SOCOM2_r0005_patch.
