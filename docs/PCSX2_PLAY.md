# Playing SOCOM II online through PCSX2 -- the launcher's PCSX2 client

The launcher has two clients, NATIVE and PCSX2, switched in its top bar. NATIVE runs our recompiled game
(`docs/INSTALL.md`). PCSX2 runs **your own retail disc in the PCSX2 emulator**, pointed at our server: the same
SOCOM II a PlayStation 2 runs, set up from one window. Each client keeps its own settings; changing one never touches
the other. The files and the switches for developers: `docs/DEVELOPING.md` "The launcher".

**Status:** built and tested in parts; the run from a clean folder to our lobby is still owed (Sprint 18 T7).
`docs/KNOWN.md` records it when it lands.

## 1. What you need

- The launcher archive, unzipped into a folder of your own (`docs/INSTALL.md` sections 2 and 3).
- Your own ISO of the US retail disc, SOCOM II r0001, unpatched.
- Your own PS2 BIOS dump. None ships with SOCOM Unzipped, and PCSX2 cannot start a game without one.
- Windows 10 version 1803 or later (INSTALL unpacks PCSX2 with Windows' own `tar.exe`) and an internet connection.

PCSX2 is free software (GPL v3) by the PCSX2 team, github.com/PCSX2/pcsx2. INSTALL downloads their official release;
nothing of it ships with SOCOM Unzipped.

## 2. Six steps

The screenshot named in each step is the launcher's own (`socom_unzipped_launcher.exe --screenshot <dir>`).

1. **Switch to PCSX2.** Press PCSX2 in the top bar; the rail shows the PCSX2 client's pages. Open the PCSX2 page
   (`pcsx2_1100x700.png`). The switch waits while something runs: "an INSTALL is running: the client can change when
   it finishes", "the game is running: close it, then change the client".
2. **INSTALL, or SELECT your own.** INSTALL downloads the latest official release into the `pcsx2` folder beside
   the launcher, checks it against the release's checksum and size, and unpacks it: "fetching the release list",
   "downloading ...", "extracting", then "installed PCSX2 v2.x.y at ..." (`pcsx2_installing_1100x700.png`).
   VERSION then reads "PCSX2 v2.x.y (installed by the launcher)". Already have PCSX2? SELECT... picks your
   `pcsx2-qt.exe`, and VERSION reads "PCSX2 (your own copy)". A refused INSTALL says why after "NOT INSTALLED." and
   leaves an earlier install as it was; a later INSTALL updates it and keeps your BIOS, memory cards and settings.
   Closing the launcher during an INSTALL does not stop it: the launcher finishes the download and the unpacking
   without a window (up to about 15 minutes) before it exits. Started again in that time, INSTALL reads "another
   INSTALL is running in this folder; wait for it to finish": wait those minutes, then press INSTALL again.
3. **Your BIOS.** OPEN FOLDER opens the folder PCSX2 reads its BIOS from. Copy your dump there; the BIOS row then
   reads "1 file in ..." (`pcsx2_800x520.png`, the same page at the small window size).
4. **DISC.** BROWSE... to your ISO. It is checked as the native client's is, and LAUNCH stays off until it matches
   the r0001 disc (`disc_pcsx2_1100x700.png`).
5. **ONLINE.** SOCOM Unzipped is the server. The community server reads "coming soon"; GAME VERSION r0004 is greyed,
   "needs the card package -- later"; Custom takes an address or a host name you type (`online_pcsx2_1100x700.png`).
   "Personas are made in the game: CONNECT TO SOCOM II, then CREATE NEW on its own screen. PCSX2 keeps them on its
   memory card."
6. **LAUNCH.** PLAY reads "LAUNCH starts PCSX2 on your disc" (`play_pcsx2_1100x700.png`). PCSX2 opens and boots the
   game. The first time, make a network configuration in the game's own wizard: memory card slot 1, Ethernet,
   auto-detect, PPPoE not required, IP automatic, **DNS automatic** (never type a DNS there: the launcher has given
   PCSX2 our server's), save. Then CONNECT TO SOCOM II, CREATE NEW for a persona, and you are in our lobby. If the
   first start does not connect, LAUNCH again: the launcher re-applies its network settings every time. When
   PCSX2 closes, PLAY's LAST RUN reads "PCSX2 closed", or "PCSX2 exited with code N -- its log is ...".

When LAUNCH cannot start, the bar says why in one sentence, the first that applies:

- "no disc set yet: pick your SOCOM II image on the DISC page"
- the DISC page's own sentence, when the disc did not pass its check
- "no PCSX2 yet: SELECT or INSTALL one on the PCSX2 page"
- "no BIOS yet: put your PS2 BIOS dump in PCSX2's bios folder (the PCSX2 page)"
- "cannot resolve <server> -- check your connection", or "<server> is not an address or a host name" (the
  server's name is looked up at LAUNCH, because PCSX2 is given its address)

## 3. Hosting a game

Whoever creates the game is the host; the others send their game traffic straight to the host's address on UDP
3658; if joiners see *Disconnected from Game*, the host's router needs one UDP port forward to that PC, or pick the
player with the friendliest router as the standing host. Our server carries the lobby, the chat and the bookkeeping;
the match itself is between the players.

## 4. Everyone on the plain disc

Players on two game revisions cannot join each other's games. The PCSX2 client plays the plain r0001 disc, nothing
patched onto it, so everyone on the plain disc can join everyone. r0004 on PCSX2 needs a card package the launcher
does not write yet; until it does, GAME VERSION keeps r0004 greyed.

## 5. What the launcher writes into PCSX2, and what it never touches

At every LAUNCH, and only when the bytes differ:

- `inis/PCSX2.ini`, its `[DEV9/Eth]` section and two `[UI]` keys only, merged key by key: `EthEnable = true`,
  `EthApi = Sockets`, `EthDevice` (the adapter with your internet connection, or the one chosen under ADVANCED on the
  PCSX2 page), `InterceptDHCP = true`, `DNS1` and `DNS2` = the server's address (PCSX2 reads `DNS1` alone),
  `AutoMask = true`, `AutoGateway = true`, `ModeDNS1 = Manual`, `ModeDNS2 = Manual`; in `[UI]`, `SettingsVersion = 1`
  and `SetupWizardIncomplete = false`, so PCSX2's first-run wizard, which would rewrite the whole file, does not run.
  Every other key and section, your comments and your line endings stay.
- `patches/0F6FC6CF.pnach`, the SOCOM II patch that answers the console's online check (guarded: it changes nothing
  on any other disc).
- For a PCSX2 the launcher installed, also the `memcards/` and `bios/` folders, created empty when missing.

A file the launcher changes is first kept once as `<name>.bak-<stamp>` beside it: that copy is the way back. A PCSX2
you selected gets the two files above and nothing else. The launcher never writes your BIOS, your memory cards,
PCSX2's video, audio or controller settings, or any other patch file, and the PCSX2 client never writes the native
client's `config.json`. Beside the launcher it keeps `launcher.json` (which client is chosen) and `config.pcsx2.json`
(this client's disc, PCSX2, server and adapter).

## 6. Where PCSX2's own settings are

"PCSX2 keeps its own video, audio, controller and BIOS settings: open PCSX2 and use its Settings menu." Its data
folder (`inis`, `bios`, `memcards`, `patches`, `logs`) is beside `pcsx2-qt.exe` when a `portable.txt` or
`portable.ini` sits next to it -- every launcher INSTALL writes one, so that is the `pcsx2` folder beside the launcher
-- and otherwise `PCSX2` in your Documents folder, the one Windows names Documents (OneDrive can move it). The PCSX2
page shows the BIOS folder; `socom_unzipped_launcher.exe --pcsx2-status <path to pcsx2-qt.exe>` prints the data
folder without a window. PCSX2's own log is `logs\emulog.txt` in it.

## 7. A real PS2

Nothing is built for a console; the path is named, and we have not tried it. A console needs the same three things:
a DNS server on your own network that answers the six names SOCOM II looks up (`socom2-prod.pdonline.scea.com`,
`socom2-prod.muis.pdonline.scea.com`, `gate1.us.dnas.playstation.org`, `gate1.jp.dnas.playstation.org`,
`gate1.eu.dnas.playstation.org`, `www.playstation.org`) with 3.143.65.100; a way past the console's online check,
which on a console comes from the r0004 card package rather than the SOCOM II patch; and the console's network
configuration with its DNS set to that DNS server's address on your network.
