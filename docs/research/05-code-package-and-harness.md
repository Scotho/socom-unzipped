# SOCOM II code package, DNAS protection and the Unicorn harness (2026-09-04)

## What is actually the game
`SCUS_972.75` (874 KB, ~350 KB code) is only a **loader**: MSL crt0, libcdvd/libmc/libpad/libdma/libgraph/libipu/libdbc/libusbkb RPC clients, zlib 1.1.4, and `main()` at 0x1c4cc0. The game itself lives in `RUN/RAW/APACHE00.ZDB` (r0001; the r0004 update is the same container downloaded to memory card `BASCUS-97275SOCOMII/APACHE00.ZDB`):

| ZDB entry | encrypted+deflated | plain | Metrowerks `MWo3` overlay | load | text | data | bss | end |
|---|---|---|---|---|---|---|---|---|
| `ftscore`  | 855,920 B | 2,233,472 B | `FTSCore.bin` (v1)  | 0x1e7000 | 0x1f4fb8 | 0x2c3d0 | 0xacf00 | 0x4b5380 |
| `zsealetc` | 691,792 B | 1,723,520 B | `ZSealEtc.bin` (v3) | 0x4c5380 | 0x18a3b8 | 0x1a880 | 0x1cf80 | 0x686f80 |

Overlay header (0x80 bytes): `MWo3`, version, load address, text size, data size, bss size, ctor table start/end, name at +0x20. The file is loaded verbatim, so code starts at load+0x80. `OVERLAY/REL/DNAS.BIN` (libdnas2 2.7.1 + libhttp + OpenSSL-derived crypto) shares the 0x4c5380 slot and is only resident during authentication/decryption; ZSealEtc replaces it afterwards. Boot then jumps to **0x4c53c0** (ZSealEtc entry) with argc/argv.

Recovered build id: `SOCOM 2 r0001 17:22:21 Oct 11 2003`. Compiler: MW MIPS C 2.4.1.01 (CodeWarrior). No symbols, but Metrowerks RTTI class names survive (`CZSealBody`, `CZFTSWeapon`, ...), as do thousands of strings (rdr/zar names, UI events, Medius API names) matching the reCOM SOCOM 1 symbol set.

Network stack inside ZSealEtc: SCE-RT **DME client 1.32.0070**, `rt_udp 01.02.0048`, `rt_audio` (voice), `rt_crypt` (LargeInt RSA, MD5), **Medius Client Library 1.50.0013**; hostnames `socom2-prod.pdonline.scea.com` and `socom2-prod.muis.pdonline.scea.com`; sceHTTP for the patch download.

## DNAS protection (libdnas2 "content decryption")
Decryption sequence (mirrors `FUN_001c5da0` in the loader), all functions in DNAS.BIN:
```
0x534830()                              init (creates semaphores; needs sceSifInitRpc + sceCdInit first)
rc    = 0x539d00(size, buf, &out)       parse+verify 0x580-byte signed header, RSA/MD5; >= 0
size2 = 0x539d50(size, out, buf)        decrypt body in place (3DES-CBC-ish, chunked 0x80); > 0
rc    = 0x534848(size2, buf, &n)        second-layer decrypt (dnas "unique" layer);  == 0
rc    = 0x535018(size2, n, buf)         finalize;                                    == 0
inflate(buf[:n]) -> overlay             zlib
```
Step 2 asks the IOP CDVD S-command server (SIF RPC SID 0x80000593) for `sceCdReadConsoleID` (fno 0x24) and `sceCdMV` (fno 0x26). **Any values work** (the IDs feed a hash that is not verified against the content), so the package is not console-locked.

Anti-tamper: DNAS.BIN self-encrypts **131 code blocks** (0x7578 bytes). Each protected function begins `if (!flag) DECRYPT(start, size^key, key, flags)` and ends with the matching re-encrypt; four copies of the decryptor exist (0x4ee9e8, 0x52b9d0, 0x53a358, 0x5412a0). The cipher is a chain of ≤7 word-transforms (xor / rotate / byte-swap) selected by nibbles of a descriptor derived from `key`, skipping relocation words listed in a per-block table. `tools_py/dnas_selfdecrypt.py` decrypts all blocks statically by running each variant's core routine under Unicorn → `DNAS.dec.bin` (+ `DNAS.blocks.json`).

## The harness (`tools_py/ee_unicorn.py`)
Unicorn MIPS64 LE (cpu model MIPS64R2 generic; the default R4000 rejects `movn` etc.). R5900-only encodings (MMI, lq/sq, 3-op mult, mult1/div1, mtsab/mtsah, R5900 FPU adda/madd/max/min/rsqrt, cache/pref/sync.x, COP0) are trap-patched to `syscall` with an index and emulated in Python; 128-bit upper halves live Python-side. Lessons that cost time:
- A trapped instruction in a **branch delay slot** must be handled by trapping the *branch* instead (QEMU misreports the PC).
- Do **not** install memory-read hooks over code regions — it breaks Unicorn's translator (host access violations). A cheap global code hook is needed for stability when guest code writes to code pages.
- After an HLE-replaced function returns, resume with a fresh `emu_start` at `$ra` (writing PC inside the hook leaves stale branch state → spurious RI exceptions).
- Key/flag constants and re-encrypt trailer constants live *inside* `.text`; they must never be trap-patched.
- The overlay region is inside the loader ELF's bss: run crt0 first, then load overlays (as `main()` does).
- `ee_sema_t.init_count` is at +8. `t_SifClientData.server` is at +0x24.
- Map uncached mirrors 0x20000000/0x30000000 onto the same RAM buffer (`mem_map_ptr`).

HLE provided: kernel semaphores/threads (single-threaded), `SetupThread/SetupHeap`, `sceSifBindRpc/CallRpc/CheckStatRpc`, SIF regs/DMA, cdvd S-cmd server. `decrypt_apache.py` runs end-to-end in ~5 min (Python emulation of the 3DES layers dominates) and writes `game/overlays/{ftscore,zsealetc}.bin`; `make_overlay_elf.py` wraps loader + both overlays into `game/overlays/socom2_game.elf` (3 PT_LOADs, entry 0x180008).

## PS2Recomp with llvm-mingw
Builds except the final `ps2EntryRunner` link: raylib's `CloseWindow`/`ShowCursor` collide with user32 (MSVC gets `/FORCE:MULTIPLE`). Fix when forking: build raylib with `-DSUPPORT_...` renames or link with `-Wl,--allow-multiple-definition`. `ps2_analyzer.exe` and `ps2_recomp.exe` built fine.
