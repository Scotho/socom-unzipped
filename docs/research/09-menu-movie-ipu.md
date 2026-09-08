# 09 — Main-menu background movie (MENULOOP.PSS) through the sceMpeg HLE

Branch `feat/menu-movie`. Goal: the main menu plays `RUN/MOVIES/COMMON/MENULOOP.PSS`
behind the roller, as on the console. This note records how the game drives libmpeg,
why nothing played on our exe, and what the runtime now does.

## What the runtime already had
`third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/MPEG.cpp` is a full FFmpeg-backed
HLE of the EE libmpeg entry points (PSS demux → MPEG-2 ES → libavcodec → RGBA → the
IPU/CSC output layout in guest RAM). `recomp/socom2.toml` already routes the 13 sceMpeg*
symbols of the game to it, and the Windows build links the prebuilt FFmpeg 7.1 DLLs
(`PS2X_ENABLE_FFMPEG`, `dist/avcodec-61.dll` …). `Kernel/Stubs/IPU.cpp` (sceIpu*) is
irrelevant for playback: with the HLE the IPU is never programmed. So "the IPU/MPEG path
is a placeholder" was wrong — the decoder was there, the protocol around it was not.

## How SOCOM II plays a movie (decomp addresses, `game/analysis/socom2_game.elf.decomp.c`)
- `FUN_003098e0(name, 1, blocking, audio)` = open. `FUN_0030bb60` resolves the file to an
  LBN (`FUN_0039def0`), `sceCdStInit(0x50, 5, buf)`, `sceCdStStart(lbn)`. `DAT_0049e2cd`
  selects CD streaming (real disc/ISO) over `sceOpen/sceRead`.
- `FUN_0030b4d0(mp, readCb=0x30b9d0, bufs=0x451cc0, fb1, fb2, audioStreams)` = player create:
  `sceMpegInit`, `sceMpegCreate(mp, work, size)`, `sceMpegAddStrCallback(mp, M2V=0, 0,
  0x30add0)`, `(…, ADPCM=2, id, 0x30aca0)`, `sceMpegAddCallback(mp, STOPDMA=1, 0x30aaa0)`,
  `(…, TIMESTAMP=4, 0x30a970)`, `(…, NODATA=0, 0x30a940)`, then a priming loop
  `do { n = readCb(0x451e00, 0x4000) while n==0; consumed = sceMpegDemuxPss(mp, buf, n) }
  while (consumed)`.
- `readCb` = `sceCdStRead(len>>11, buf, STMNBLK, &err) << 11` — non-blocking; the game
  busy-waits on 0 (the runtime's stream model produces sectors on the vsync tick, so the
  spin terminates).
- M2V stream callback `0x30add0` copies each video PES payload into the game's own IPU ring
  (`DAT_00455e10/e18/e20/e28/e30`) and returns 0 when the ring is full (real DemuxPss stops
  there). STOPDMA `0x30aaa0` kicks DMA ch4 (IPU_TO, `CHCR=0x101`) with up to 0x1000 bytes
  from that ring, demuxing more first when the ring holds < 0x1000. TIMESTAMP `0x30a970`
  only sets a flag in non-blocking mode. NODATA `0x30a940` = `longjmp(0x455e50, 1)`: the
  per-frame function `FUN_0030b1d0` does `setjmp` before `sceMpegGetPicture(mp, image,
  (h/16)*40)` and closes the player if the library reports no data.
- Shell: `FUN_00366940` runs every shell tick (60 Hz): `FUN_003096c0` → `FUN_0030b180` =
  `DAT_00455e38 || sceMpegIsEnd(mp)`; not ended → `FUN_00309850` → `FUN_0030b1d0` (GetPicture,
  first frame builds the GIF packet `FUN_0030b770`, `FUN_0030b740` kicks it); ended and
  loop flag (+0x27a) → `FUN_00309560` (Reset, `sceCdStSeek(start)`, Create again). The vsync
  path `FUN_00309780` feeds `sceMpegDemuxPss` for a RCNT0-timed window each frame.
- Picture layout expected by `FUN_0030b770`: TRXREG 16×16, inner loop over MB rows
  (DSAY += 16), outer over MB columns (DSAX += 16), source advancing 0x400 per MB → the
  image is **16-px-wide column strips of full height**, exactly what
  `writeDecodedFrameToGuest` emits (no change needed).
- `MENULOOP.PSS`: 640×448, frame-rate code 5 (30 fps), 3790 pictures (~126 s), single
  sequence header, ends with sequence_end + program_end.

## Why nothing played (evidence: `PS2X_CALL_TRACE` runs, logs/run_20260907_2138*.log)
1. `sceMpegIsEnd` is **not** HLE'd for this game (0x1bbab8 is recompiled: `return work[0]`)
   and the HLE `sceMpegCreate` never wrote `work+0`. The real `sceMpegCreate` memsets the
   whole work buffer. On our side the first `IsEnd` after every open returned stale bytes
   (`0x654d4955` = "UIMe" from a previous `.rdr`, `0x80716717` for MENULOOP) → the shell
   closed the player on its first tick. Every movie (sony448, intro, MENULOOP, cinematics)
   died this way; INTRO_2 only "played" because the previous Reset had zeroed the buffer.
2. Even with that fixed, the HLE `sceMpegGetPicture` parks the thread (`waitExternal`)
   when no picture is queued. SOCOM's only feeders are the game's own thread (the vsync
   feed loop and the STOPDMA callback, which the real library calls from inside
   GetPicture) — parking the caller could deadlock, and the STOPDMA/NODATA protocol was
   never exercised (control callbacks were registered but never dispatched).

## Changes (MPEG.cpp)
- `sceMpegCreate`: zero `[work, work+size)` before initialising (mirrors libmpeg) and log
  under `PS2X_MPEG_TRACE`.
- `sceMpegGetPicture`: when no decoded picture is queued and the stream is not over, run
  the game's SCE_MPEG_CBSTOPDMA callback synchronously on the calling thread
  (`EeScheduler::invokeCurrent`, HleCall) and re-enter GetPicture when it returns; a
  callback result of 0 or `kMaxStarveInvocations` rounds without a picture ends the stream.
  Games without a STOPDMA callback keep the old `waitExternal` path.
- Guest-visible end flag: every GetPicture writes `work+0` (what the recompiled
  `sceMpegIsEnd` reads) = 1 when the queue is drained and the stream ended
  (program_end / sequence_end seen, decoder failure, or CD stream EOF), so the shell's
  loop restart (`FUN_00309560`) fires at the end of MENULOOP.
- `PS2X_MPEG_TRACE=1`: runtime-gated trace of create / demux / picture / end events
  (independent of the compile-time AGRESSIVE_LOGS).

## Verification
(filled in below as runs complete)
