# SOCOM II technical facts (research + local verification, 2026-09-02)

## Disc
- redump disc 5230: "SOCOM II - U.S. Navy SEALs (USA)", SCUS-97275 / SCUS-97275GH (same image), v1.02, EXE date 2003-10-11, 4,380,753,920 bytes, CRC32 9E40EA01, MD5 2591f0aaaa58ca0eb9bcf1f33f1e3be2, SHA1 ef56534ff346679f88aff78bad4d73facf43590b. **Local ISO verified identical (MD5/SHA1 match).**
- `SYSTEM.CNF`: `BOOT2 = cdrom0:\SCUS_972.75;1`, VER 1.02, NTSC. PCSX2 ELF CRC 0F6FC6CF.
- Prototypes on Hidden Palace: Aug 18 2003 demo (SCUS-973.68), Aug 28 2003 (SCES-973.66 beta), Nov 25 2003; SOCOM 1 May 13 2002 demo **with debug symbols** (SCUS_972.05, basis of reCOM).

## Layout (local analysis)
- 349 files. Code: `SCUS_972.75` (874,792 B; only ~350 KB of real code at 0x180000+, rest zero padding; entry 0x180008; Metrowerks "MW MIPS C Compiler 2.4.1.01"; **.symtab empty**), `OVERLAY/REL/DNAS.BIN` (667 KB, Metrowerks `MWo3` overlay: header words = magic, version 2, load addr 0x4c5380, text 0x840c0, data 0x1ed00, bss 0x91f80, ctor start/end; name at +0x20; file loaded verbatim so code starts at load+0x80), `RUN/RAW/APACHE00.ZDB` (1.5 MB) = the **game code package** (r0001): two DNAS-encrypted + zlib blobs `ftscore` (855,920 B → overlay @0x1e7000, PH1 region memsz 0x2ce380) and `zsealetc` (691,792 B → overlay @0x4c5380, PH3 memsz 0x1c1c00). Boot main checks memory cards for `BASCUS-97275SOCOMII/APACHE00.ZDB` (the r0004 update) first, else loads from disc, then jumps to 0x4c53c0.
- ELF program headers: PH0 0x100000 (0xd5600 file / 0xe6680 mem), PH1 0x1e7000 memsz 0x2ce380 (ftscore), PH2 0x4c5380 memsz 0x134d80 (DNAS), PH3 0x4c5380 memsz 0x1c1c00 (zsealetc), PH4 0x686f80 (0).
- Data: 35 `.ZDB` pack files (12 SP missions M51–M83 at 15–17 MB, 23 MP maps MP1–MP9x at 8–13 MB) each a TOC (count @0x98, 0x5c-byte entries from 0xa0: size, name[64], offset, length) of ZAR/ZED/MPS inner files — **not encrypted**; `RUN/SOUNDS/VAGSTORE.ZAR` 577 MB, `BNKSTORE.ZAR` 67 MB; 69 `.PSS` movies; `RUN/IRX/*` Sony SDK 2.7.1 modules (sio2man, dbcman, ds2u_s1, mcman/mcserv, cdvdstm, libsd, sdrdrv, 989snd/989dstrm, usbd/usbkb, lgaud, headseto, dev9, smap, inet, inetctl, netcnf, eznetcnf/eznetctl, libnetb, msifrpc, ppp, pppoe, hdd/atad/pfs, DNAS271.IMG); `NETGUI/` network config utility (SCUSNGUI.ELF, 4.2 MB, with symbols? unchecked).
- DNAS.BIN contains libdnas2 2.7.1 ("PsIIdnas2no 271", libhttp 2710) with an OpenSSL-derived crypto lib (RSA, 3DES, MD5, X.509). It **self-decrypts/re-encrypts 34 code blocks at runtime** (FUN_005412a0(start, size^key, key, flags)); flag word at block-0x14.
- Decompression of overlays: zlib 1.1.4 inflate (FUN_001ca2a0 = inflateInit_/inflate(Z_FINISH)/inflateEnd).

## Engine
- Zipper in-house **GameZ** engine (reCOM symbols: zAI, zAnim, zArchive, zAssetLib, zBody, zBone, zCamera, zEntity, zFTS, zGame, zGraph, zGrid, zInput, zIntersect, zMath, zMPEG, zNetwork, zNode, zParticle, zReader, zRender, zSave, zSeal, zSound, zSystem, zTexture, zTwoD, zUI, zUtil, zValve, zVehicle, zVideo, zVisual, zWeapon; app layer "FTS"). Wikipedia's "Kinetica" claim conflicts.
- Formats: ZAR archives (versions 0x20001/0x20002, string table + hierarchical keys, optional byte-NOT "secure" mode), zReader `.rdr` LISP-like S-expressions, ZED containers (_TXR/_PAL/_GEO/_MDL), OpenFlight-derived meshes, VAG audio, PSS video. Tools: socom-cc/socom-archive-manager (Go), TylerDev905/ZDBArchive, mbacker80/SOCOM-Archives-Manager.

## PCSX2 status
- GameIndex: compat 5 (Playable), gameFixes `VIF1StallHack`, `InstantDMAHack`. Wiki: supports headset, keyboard, HDD, widescreen, progressive; CPU intensive; crouch needs DS2 pressure buttons. MP maps (Crossroads) slow; render-fix codes 2035A2F8 100000DB / 2035A320 00000000 (r0004).
- Widescreen pnach: 001c0474 3c013f40, 001c0478 4481e800, 001c0480 461dbdc3, 20291450 461d0002, 20291688 461d0002.

## Community RE
- r0005 patch (Zero1UP / harry6two): kernel hooks at 0xD0000, vars 0xF6000, password keys at 0x30D278/0x2BC7D0/0x30D43C, hashed pw 0x45A1A8.
- gamehacking.org SCUS_972.75 codes; NightFyre/SOCOM-ARCHIVES; Zero1UP/Socom2StreamData (PCSX2 memory reader).
- SCE-RT SDK / LibDNAS on archive.org "ps2_sdks"; GDC talk "SOCOM: Bringing a Console Game Online".
