# 10 — libnetb RPC contract (EE `libnet` ⇄ IOP `LIBNETB.IRX` over msifrpc)

Purpose: everything needed to HLE the msifrpc service `0x80001201` on the host so the
game's SCE-RT network layer (Medius client, rt_udp/rt_tcp, DNS, DNAS) runs without
INET.IRX/LIBNETB.IRX. Read-only reverse engineering of:

- EE: `game/analysis/socom2_game.elf.decomp.c` (libnet EE wrappers 0x245690..0x2484a0,
  libmrpc 0x1bcd80..0x1bd5c8, BSD-socket shim "mp_net" 0x1c1cd0..0x1c4c98, SCE-RT PS2
  platform layer 0x62da90..0x62ebf8).
- IOP: `game/disc/RUN/IRX/LIBNETB.IRX` decompiled with Ghidra 12.1.3 headless
  (`tools/ghidra`, script `ghidra_scripts/ExportAll.java`) into
  `game/analysis/LIBNETB.IRX.{decomp.c,functions.txt,strings.txt}` (103 functions; the three
  Ghidra missed — event callback at 0x0000 and the two TCP/UDP send threads at 0x171c/0x194c —
  were added with `MakeFunctionsFromFile.java`). INETCTL.IRX / EZNETCTL.IRX were decompiled to
  the scratchpad only, to pin down the inetctl export ordinals and event/state constants.
- Names: sizes of the EE functions were matched against the SDK symbol database shipped with
  ps2recomp (`third_party/ps2recomp/ps2xAnalyzer/include/ps2recomp/sce_symbol_database_data.h`,
  libraries `libnet` and `libmrpc`); every libmrpc function matched exactly, and the libnet
  wrappers matched exactly or within one instruction pair (this build is libnetb 1.10.0000,
  slightly newer than the DB's). IOP import ordinals were named from usage inside INETCTL.IRX
  (which prints the sceInet* name next to each call) and EZNETCTL.IRX (which carries the
  `sceInetCtl*` names as strings next to its stubs).

Version strings: EE `$Header: /projects/rtime/CVS/libnetb/src/ee/libnetb_ex.c,v 1.31` and
`libnetb version: 1.10.0000`; IOP `/usr1/dev/150_0915/libnetb/src/iop/libnetb.c` (SDK 1.50
libnetb) plus `libnetb/src/iop/libnetb_ex.c,v 1.26` (the SCE-RT "ex" fast path).

Conventions in this file: `p[n]` = 32-bit word `n` of the RPC buffer (byte offset `4n`);
all integers are little-endian native EE/IOP words. "SEND" = bytes the EE DMAs to the IOP,
"RECV" = bytes the IOP DMAs back; both go through the *same* EE buffer (libnet always passes
one buffer for both directions).

---------------------------------------------------------------------------------------------

## 1. Transport: msifrpc (`libmrpc`) as used by libnet

### 1.1 EE functions (all matched by size to the SDK `libmrpc` symbols)

| EE address | Name | Notes |
|---|---|---|
| 0x001bcd80 | `sceSifMInitRpc` | once; `sceSifAddCmdHandler(0x80000018, handler=0x1bcf20, pool=0x1e0e40)`; packet pool: 32 × 0x40 at 0x201e0640; sends SIF cmd `0x80000001` (0x18 bytes @0x1e0680) and spins on `sceSifDmaStat`-style poll until the IOP acks |
| 0x001bce48 | `sceSifMExitRpc` | clears the init flag only |
| 0x001bce58 | (internal) allocate packet from pool | marks pkt+0x10 in-use, stores pkt id at pkt+0x18 |
| 0x001bcf20 | SIF cmd handler for `0x80000018` | dispatch on pkt+0x20 (see 1.3) |
| 0x001bd028 | `sceSifMBindRpc` | thunk → `sceSifMBindRpcParam` |
| 0x001bd050 | `sceSifMBindRpcParam(cd, sid, mode, bufsize, param5, param6)` | mode must be 0 ("mode must be 0 in this version.") |
| 0x001bd200 | `sceSifMUnBindRpc(cd, mode)` | cmd `0x8000001d` |
| 0x001bd320 | `sceSifMCallRpc(cd, fno, mode, send, sendsize, recv, recvsize, endfunc, endarg)` | cmd `0x8000001a`; send/recv addresses must be 64-byte aligned (`%s: send buffer addr is not 64 byte align`), sizes are checked `& 0x3f == 0`; synchronous when `endfunc == 0` |

### 1.2 Client descriptor (`sceSifMClientData`, 0x3c bytes, `int cd[15]`)

Offsets as written by `sceSifMBindRpcParam` / `sceSifMCallRpc` / the cmd handler:

| Offset | Set by | Meaning |
|---|---|---|
| 0x00 | bind/call/unbind | current SIF packet pointer (from the pool) |
| 0x04 | bind/call/unbind | packet id (`pkt+0x18`) |
| 0x08 | bind/call/unbind | completion semaphore id of the in-flight operation (created per call, deleted after) |
| 0x0c | – | not touched by libmrpc (padding) |
| 0x10 | bind | `sid` = **0x80001201** for libnetb |
| 0x14 | bind reply (`pkt+0x28`) | IOP-side address of the server's receive buffer; `sceSifMCallRpc` passes it as the DMA destination for the send data (`sceSifSendCmd(0x8000001a, pkt, 0x40, send, cd[5], sendsize)`) |
| 0x18 | bind reply (`pkt+0x2c`) | second IOP value returned by bind (probably the IOP-side reply/DMA buffer or server handle; not used by the EE afterwards) |
| 0x1c | call | `endfunc` |
| 0x20 | call | `endarg` |
| 0x24 | bind reply (`pkt+0x24`) | IOP client handle; non-zero ⇒ bound. `sceLibnetInitialize` loops re-binding until this is non-zero. Copied into every call packet at `pkt+0x34` |
| 0x28 | bind | serialisation semaphore (init count 1, max 1); `WaitSema` at the start of call/unbind, `iSignalSema` by the handler when the reply for `0x8000001a` arrives |
| 0x2c | unbind reply (`pkt+0x24`) | unbind result (`sceSifMUnBindRpc` returns it; libnet loops until it equals 1) |
| 0x30 | bind | **buffer size** (`bufsize`) — libnet's maximum for `sendsize`/`recvsize` and for its pack/unpack helpers |
| 0x34 | bind | `param5` (libnet passes 0x2000; likely IOP thread stack size) |
| 0x38 | bind | `param6` (libnet passes 0x20; likely IOP thread priority) |

`sceLibnetInitialize(cd, bufsize, 0x2000, 0x20)` requires `bufsize >= 0x80` and
`bufsize % 64 == 0` (else "sceLibnetInitialize() buffersize", returns -0x21f). Observed
instances: the mp_net socket shim creates one client per EE thread (`ctx+0x14`, bufsize
`(0x800+99)&~63 = 0x840`, RPC buffer `ctx+0x58` 64-aligned); global clients at
0x456780 (buffer 0x455f80, used by the network-config UI and DNAS/DNS resolve) and 0x672200
(buffer 0x672240, used by the SCE-RT platform layer) both with `bufsize = 0x800`.

### 1.3 SIF packets (0x40 bytes, standard SIF cmd header in the first 0x10)

Common: `pkt+0x14 = pkt` (self), `pkt+0x1c = cd`.

| Cmd id (EE→IOP) | Fields | Reply handling (cmd `0x80000018` back to the EE, `pkt+0x20` = original id) |
|---|---|---|
| `0x80000019` bind | `+0x20 sid`, `+0x24 bufsize`, `+0x28 param5`, `+0x2c param6` | `cd[9]=pkt+0x24`, `cd[5]=pkt+0x28`, `cd[6]=pkt+0x2c`; signal `cd[10]` |
| `0x8000001a` call | `+0x20 fno`, `+0x24 sendsize`, `+0x28 recvbuf (EE)`, `+0x2c recvsize`, `+0x30 = 1`, `+0x34 = cd[9]`; data DMA: `send → cd[5]` on the IOP, `sendsize` bytes | calls `endfunc(endarg)` if set, `iSignalSema(cd[10])`. The IOP has already DMA'd `recvsize` bytes into `recvbuf` before this arrives |
| `0x8000001d` unbind | `+0x20 sid`, `+0x24 = cd[9]` | `cd[11]=pkt+0x24`; signal `cd[10]` |
| `0x8000001c` | – | handled (no-op) |

In all cases the handler then signals the completion semaphore `cd[2]` and frees the packet.
The EE `SyncDCache`s the send range before the call (and the recv range if it differs).

### 1.4 IOP side of the service

`LIBNETB.IRX` module entry `FUN_00000afc`: parses `-verbose` / `-send_delay=N` (ms, clamped
1..10, default 10 → the send-thread poll interval), calls sifcmd#14, then creates a thread
(`FUN_00000974`) that does `msifrpc#4()` and
`msifrpc#17(&queue, 0x80001201, dispatcher=FUN_000003f8, 0)`. The dispatcher is
`void *dispatch(int fno, int *buf)` and **returns the buffer pointer**; the reply DMA is done by
msifrpc from that pointer, `recvsize` bytes. Unknown `fno` → `p[0] = 0xfffffde3` ("UNHANDLED
CASE"). `fno >= 100` is routed to the libnetb_ex handler `FUN_00000d08`.

Imports used by LIBNETB.IRX (ordinal → name; names verified via INETCTL/EZNETCTL usage or
by exact EE-wrapper correspondence):

- `inet` 1.01: 4 sceInetName2Address, 5 sceInetAddress2String, 6 sceInetCreate, 7 sceInetOpen,
  8 sceInetClose, 9 sceInetRecv, 10 sceInetSend, 11 sceInetRecvFrom, 12 sceInetSendTo,
  13 sceInetAbort, 14 sceInetAddress2Name, 15 sceInetControl, 16 sceInetPoll,
  24 sceInetGetInterfaceList, 25 sceInetInterfaceControl, 27 sceInetGetRoutingTable,
  30 sceInetGetNameServers, 36 sceInetChangeThreadPriority, 38 sceInetGetLog, 41 sceInetAbortLog.
  (13/14/15/16/27/36/38/41 are inferred from the EE wrapper that maps onto them; 24/25/4/5
  are confirmed by INETCTL.IRX's own log strings.)
- `inetctl` 1.01: 4 sceInetCtlSetConfiguration, 5 sceInetCtlUpInterface, 6 sceInetCtlDownInterface,
  7 sceInetCtlSetAutoMode, 8 sceInetCtlRegisterEventHandler, 9 sceInetCtlUnregisterEventHandler,
  10 sceInetCtlGetState (all confirmed by EZNETCTL.IRX).
- `msifrpc` 1.02: 4 (init), 17 (register server).
- sifman 7/8 (`sceSifSetDma`/`sceSifDmaStat`) for the ex fast path, thbase/thsemap/intrman/sysmem/sysclib/stdio.

---------------------------------------------------------------------------------------------

## 2. libnet EE wrappers: common machinery

| EE address | Role |
|---|---|
| 0x00245ad8 | `CallRpc(cd, fno, buf, sendSize, recvSize)`: rounds both sizes up to 64; if either exceeds `cd[0x30/4]` prints `CallRpc() in Libnet send:%d, recv:%d, max:%d` and returns -0x21f; else `sceSifMCallRpc(cd, fno, 0, buf, send64, buf, recv64, 0)` |
| 0x00245b58 | `PackIn(cd, buf, slot, src, len)`: `memcpy(buf + slot*4, src, len)`; -0x21f if `len > bufsize - slot*4` or `len < 0`; no-op (0) if `src == NULL` |
| 0x00245bb0 | `UnpackOut(cd, dst, buf, slot, len)`: `memcpy(dst, buf + slot*4, len)` with the same checks |
| 0x00245c08 | `PackString(cd, buf, slot, str)`: `strcpy(buf + slot*4, str)`; returns `strlen+1` (or -0x21f if it does not fit; 0 if `str == NULL`) |
| 0x00245c98 | `UnpackString(cd, dst, buf, slot)`: `strcpy(dst, buf + slot*4)` |

Return-value convention of every wrapper: RPC transport failure → **-0x21e** (0xfffffde2)
(or -0x21f for a pack failure); otherwise the wrapper returns **`p[0]`**, which is whatever
the IOP function returned (a cid/count/byte-count `>= 0`, or a negative `sceINETE_*` code —
see §5). `sceInetCreate` additionally maps a returned 0 to -0x21c.

### 2.1 Structures (exact bytes)

`sceInetAddress_t` (16 bytes) — as produced/consumed by the EE helpers 0x1c2410/0x1c2458,
0x247aa0 (string→addr) and 0x247b38 (addr→string), and by IOP `FUN_00002d20`:

| Offset | Size | Content |
|---|---|---|
| 0x00 | 4 | reserved, always 0 |
| 0x04 | 4 | IPv4 address as a **native (little-endian) u32 in host order**: value = `a<<24 | b<<16 | c<<8 | d` for dotted `a.b.c.d`, i.e. bytes in memory are `d, c, b, a` (byte +7 = `a`, byte +4 = `d`) |
| 0x08 | 8 | zero (unused by IPv4 code; memset to 0 by every producer) |

Conversions in the mp_net shim: BSD `sin_addr` (network order) → `bswap32` → store at +4;
`sin_port` → `bswap16` → **int port in host order**, with `sin_port == 0` mapped to **-1**
(= "any port", used as `local_port` in `sceInetCreate`).

`sceInetParam_t` (0x40 bytes, argument of `sceInetCreate`; bytes 0x1c..0x3f were always 0 in
every caller — meaning of those fields unknown):

| Offset | Content |
|---|---|
| 0x00 | `type`: 0 `sceINETT_DGRAM` (UDP), 1 `sceINETT_CONNECT` (TCP active), 2 `sceINETT_LISTEN` (TCP passive), 3 `sceINETT_RAW` (raw IP) |
| 0x04 | `local_port` (int, host order; -1 = any) |
| 0x08 | `remote_addr` (`sceInetAddress_t`, 16 bytes) |
| 0x18 | `remote_port` (int, host order; -1/0 = unspecified) |
| 0x1c..0x3f | zero (unknown; probably flags/queue sizes) |

`sceInetInfo_t` (0x4c bytes, returned by `sceInetControl(cid, 1, ...)`; field names from the
IOP's own state dump `FUN_000024c4`):

| Offset | Content |
|---|---|
| 0x00 | `cid` |
| 0x04 | `proto`: 1 `sceINETI_PROTO_TCP`, 2 `sceINETI_PROTO_UDP`, 3 `sceINETI_PROTO_IP` |
| 0x08 | `recv_queue_length` (bytes) |
| 0x0c | `send_queue_length` (bytes) |
| 0x10 | `local_adr` (`sceInetAddress_t`) |
| 0x20 | `local_port` |
| 0x24 | `remote_adr` (`sceInetAddress_t`) |
| 0x34 | `remote_port` |
| 0x38 | `state`: 0 UNKNOWN, 1 CLOSED, 2 CREATED (UDP), 3 OPENED (UDP/raw), 4 LISTEN, 5 SYN_SENT, 6 SYN_RECEIVED, 7 ESTABLISHED, 8 FIN_WAIT_1, 9 FIN_WAIT_2, 10 CLOSE_WAIT, 11 CLOSING, 12 LAST_ACK, 13 TIME_WAIT |
| 0x3c..0x4b | unknown (never read by the EE) |

`sceInetPollFd_t` (8 bytes): word 0 = `cid`; word 1 = events/revents (the shim copies the
caller's second word through untouched and passes it back; exact bit layout of
`events`/`revents` not observed — treat as opaque 32 bits, likely `events` low 16 /
`revents` high 16).

Recv/send `flags` word: bit 0x2 = "peek"? (mp_net `recv()` with `MSG_PEEK`-like `flags & 1`
sets IOP flags = 2), bit 0x4 in the returned flags = **connection closed by peer** (TCP recv
loop stops; ex-path returns error 0xd); the ex path also passes `inet_flag` verbatim.

---------------------------------------------------------------------------------------------

## 3. Function numbers (service 0x80001201)

For each: EE wrapper, IOP call, SEND layout, RECV layout, callers.

### fno 1 — `sceInetCreate(cd, buf, const sceInetParam_t *param)` — EE 0x00245ff0
IOP: `p[0] = sceInetCreate(&p[1])`.
- SEND 0x44: `p[0]` unused, `p[1..16]` = `sceInetParam_t` (0x40 bytes, §2.1).
- RECV 4: `p[0]` = **cid** (> 0) or negative error. EE maps 0 → -0x21c.
- Callers: mp_net `socket()`+`bind()`/`connect()` path (0x1c2dd0 connect, 0x1c35a0 lazy-create for UDP, 0x1c2f38 listen/accept pre-create), ex-path open 0x2471a8.

### fno 2 — `sceInetOpen(cd, buf, int cid, int timeout_ms)` — EE 0x00246068
IOP: `p[0] = sceInetOpen(p[0], p[1])`.
- SEND 8: `p[0]` cid, `p[1]` timeout (ms; -1 = infinite, 0 = non-blocking/poll).
- RECV 4: `p[0]` 0 or error. Semantics: UDP/raw → bind & make usable; CONNECT → TCP connect (mp_net treats -500 `TIMEOUT` as "in progress" for non-blocking connects, and -0x1fb `ALREADY_EXISTS` as success on `accept()`); LISTEN → wait for an incoming connection on that cid (accept happens by opening a pre-created LISTEN cid).
- Callers: connect 0x1c2dd0 (timeout -1), accept 0x1c32a8 (-1), listen slot 0x1c2f38 (0), UDP lazy open 0x1c35a0 (-1), ex-path 0x2472c8 (10000 for TCP connect).

### fno 3 — `sceInetClose(cd, buf, int cid, int timeout_ms)` — EE 0x002460b0
IOP: `p[0] = sceInetClose(p[0], p[1])`. SEND 8 (`cid`, `timeout`), RECV 4 (`p[0]` result).
Callers: mp_net `close()` 0x1c3ce8 (timeout = socket's linger field, default -1), accept cleanup (0), ex-path close via fno 0x66.

### fno 4 — `sceInetRecv(cd, buf, int cid, void *dst, int len, u32 *flags, int timeout_ms)` — EE 0x002460f8
IOP: `p[0] = sceInetRecv(cid=p[0], buf=&p[2], len=p[2], flags=&p[1], timeout=p[3])`.
- SEND 0x10: `p[0]` cid, `p[1]` flags in (0 or `*flags`), `p[2]` len, `p[3]` timeout.
- RECV `len+8`: `p[0]` = bytes received (≥0) or error; `p[1]` = flags out (bit 4 = closed); data at **`p[2]` (byte 8)**, `p[0]` bytes. EE copies `p[0]` bytes out and writes `p[1]` back to `*flags`.
- Caller: mp_net `recv()` 0x1c3810 — loops in chunks of `min(len, 0x800)` (the per-thread bufsize), timeout = socket recv-timeout field (+0x60, default 0 → non-blocking semantics; returns errno 0xb EAGAIN when nothing arrived).

### fno 5 — `sceInetSend(cd, buf, int cid, const void *src, int len, u32 *flags, int timeout_ms)` — EE 0x002462d0
IOP: `p[0] = sceInetSend(cid=p[0], buf=&p[4], len=p[2], flags=&p[1], timeout=p[3])`.
- SEND `len+0x10`: `p[0]` cid, `p[1]` flags, `p[2]` len, `p[3]` timeout, data at **`p[4]` (byte 0x10)**.
- RECV 8: `p[0]` bytes sent or error, `p[1]` flags out.
- Caller: mp_net `send()` 0x1c3660 (chunks ≤ 0x800; `flags & 1` → IOP flags 2).

### fno 6 — `sceInetName2Address(cd, buf, u32 flags, sceInetAddress_t *out, const char *name, int timeout_ms, int retries, u32 extra)` — EE 0x00245d78
IOP: `p[0] = sceInetName2Address(flags=p[0], addr=&p[1], name=(p[4]>0 ? (char*)&p[5] : NULL), p[1], p[2], p[3])` (the IOP passes the raw words `p[1..3]` as extra args; `p[1]` is *also* the start of the output address — the address is only written on success).
- SEND `strlen+1+0x14`: `p[0]` flags, `p[1]` timeout (ms), `p[2]` retries, `p[3]` = 0, or `extra` when `flags & 0x80`; `p[4]` = strlen(name)+1; NUL-terminated name at **`p[5]` (byte 0x14)**.
- RECV 0x14: `p[0]` result (0 ok), `p[1..4]` = resolved `sceInetAddress_t`.
- Flags seen: `0x41` (mp_net `gethostbyname` 0x1c48a0), `0` (DNAS/network-config resolve 0x30de30 with timeout 6000, retries 4; SCE-RT platform resolve 0x62e5c8 / 0x62dbd8 with 0,0). The mp_net wrapper maps errors -500/-0x203 → h_errno 1, -0x204 → 2, -0x205 → 3, -0x206 → 4 (so the resolver also returns -0x203..-0x206 "DNS" errors). Meaning of flag bits 0x01/0x40/0x80 unknown (0x80 = "extra parameter present", likely a name-server address override).

### fno 7 — `sceInetAddress2String(cd, buf, char *out, int outlen, const sceInetAddress_t *addr)` — EE 0x00245e60
IOP: `p[0] = sceInetAddress2String(str=&p[5], len=p[0], addr=&p[1])`.
- SEND 0x14: `p[0]` outlen, `p[1..4]` address.
- RECV `outlen+0x14`: `p[0]` result, string at **`p[5]` (byte 0x14)** ("%u.%u.%u.%u").
- Callers: 0x30de30 (config UI), 0x62e5c8 / 0x62e678 (platform layer, outlen 0x10).

### fno 8 — `sceInetGetInterfaceList(cd, buf, int *ids, int max)` — EE 0x00246558
IOP: `p[0] = sceInetGetInterfaceList(&p[1], p[0])`.
- SEND 4: `p[0]` max entries. RECV `max*4+4`: `p[0]` = count (or error), interface ids at `p[1..]`.
- Callers: 0x30bd40 (UI, max 0x100), 0x62e7e0 (platform init, max 0x20), 0x246d10 (libnet internal, 0x100).

### fno 9 — `sceInetInterfaceControl(cd, buf, int if_id, int code, void *ptr, int len)` — EE 0x002465e8
IOP: `p[0] = sceInetInterfaceControl(p[0], p[1], (p[2] ? &p[3] : NULL), p[2])`.
- SEND `len+0xc`: `p[0]` if_id, `p[1]` code, `p[2]` len, payload at **`p[3]` (byte 0xc)** (for "set" codes).
- RECV `len+0xc`: `p[0]` result, payload at `p[3]` (for "get" codes; EE always copies `len` bytes back).
- Codes observed (all "get"): `2` → interface name string (len 0x100); `3` → vendor/description string (0x100); `8` → u32 flags (bit 0x1 and bit 0x2: libnet picks the first interface with `flags & 2`, the platform layer requires `(flags & 3) == 3` = attached+up; bit 0x200 = "secondary/PPP-type" interface — libnetb keeps such ids in a second slot); `9` → 16-byte `sceInetAddress_t` = the interface's IP address (used by `sceLibnetWaitGetAddress`; INETCTL logs it via Address2String); `0xb` → 16-byte address (platform layer reads it right after 9 as a second address string — netmask or gateway, uncertain); `0x200` → u32 (UI polls it and restarts a timer when it changes — probably link/DHCP status counter, uncertain). EZNETCTL additionally uses `8` (flags) and 0x8003xxxx/0x9000xxxx vendor codes (PPP); INETCTL uses `0x10000`/`0x10001` as down/up commands.

### fno 0xa — `sceInetGetRoutingTable` — no EE wrapper in this build
IOP: `p[0] = sceInetGetRoutingTable(&p[1], p[0])` (entries of unknown size). Never called.

### fno 0xb — `sceInetGetNameServers(cd, buf, sceInetAddress_t *out, int max)` — EE 0x00246738
IOP: `p[0] = sceInetGetNameServers(&p[1], p[0])`. SEND 4 (`max`), RECV `max*16+4`: `p[0]` count, 16-byte addresses at `p[1..]`. No callers in the game.

### fno 0xc — `sceInetChangeThreadPriority(cd, buf, int prio)` — EE 0x002467c8
IOP: `p[0] = inet#36(p[0])`. SEND 4 / RECV 4. No callers.

### fno 0xd — `sceInetRecvFrom(cd, buf, int cid, void *dst, int len, u32 *flags, sceInetAddress_t *from, int *fromport, int timeout_ms)` — EE 0x002461c0
IOP: `p[0] = sceInetRecvFrom(cid=p[0], buf=&p[7], len=p[2], flags=&p[1], from=&p[2], fromport=&p[6], timeout=p[3])`.
- SEND 0x10: `p[0]` cid, `p[1]` flags, `p[2]` len, `p[3]` timeout.
- RECV `len+0x1c`: `p[0]` bytes/error, `p[1]` flags out, `p[2..5]` source address (16 bytes, **overwrites len/timeout**), `p[6]` source port, data at **`p[7]` (byte 0x1c)**.
- Caller: mp_net `recvfrom()` 0x1c3b20.

### fno 0xe — `sceInetSendTo(cd, buf, int cid, const void *src, int len, u32 *flags, const sceInetAddress_t *to, int toport, int timeout_ms)` — EE 0x00246378
IOP: `p[0] = sceInetSendTo(cid=p[0], buf=&p[9], len=p[2], flags=&p[1], to=&p[5], toport=p[4], timeout=p[3])`.
- SEND `len+0x24`: `p[0]` cid, `p[1]` flags, `p[2]` len, `p[3]` timeout, `p[4]` dest port, `p[5..8]` dest address, data at **`p[9]` (byte 0x24)**.
- RECV 8: `p[0]` bytes/error, `p[1]` flags out.
- Caller: mp_net `sendto()` 0x1c39b0.

### fno 0xf — `sceInetAbort(cd, buf, int cid, u32 flags)` — EE 0x00246460
IOP: `p[0] = sceInetAbort(p[0], p[1])`. SEND 8 / RECV 4.
Callers: mp_net `shutdown()`-like 0x1c28f8 (aborts the socket and all its accept-queue cids with the caller's flags), `sceInetAbort(0, 0x52534c56 'RSLV')` from 0x1c4c20 = abort a pending resolver call.

### fno 0x10 — `sceInetAbortLog(cd, buf)` — EE 0x002468a8
IOP: `p[0] = inet#41()`. SEND 0 / RECV 4. No callers.

### fno 0x11 — `sceInetGetLog(cd, buf, void *out, int size, int mode)` — EE 0x00246810
IOP: `p[0] = inet#38(&p[1], p[0], p[1])`. SEND 8 (`size`, `mode`), RECV `size+4` (data at `p[1]`). No callers.

### fno 0x12 — `sceInetAddress2Name(cd, buf, u32 flags, char *name_out, int namelen, const sceInetAddress_t *addr, int timeout_ms, int retries, u32 extra)` — EE 0x00245f08
IOP: `p[0] = sceInetAddress2Name(flags=p[0], name=&p[8], namelen=p[1], addr=&p[4], p[2], p[3], p[8])`.
- SEND 0x24: `p[0]` flags, `p[1]` namelen, `p[2]` timeout, `p[3]` retries, `p[4..7]` address, `p[8]` = 0 or `extra` (if `flags & 0x80`).
- RECV `namelen+0x20`: `p[0]` result, name string at **`p[8]` (byte 0x20)**.
- Caller: mp_net `gethostbyaddr` 0x1c4a20 (flags 0x40, namelen 0x100).

### fno 0x13 — `sceInetControl(cd, buf, int cid, int code, void *ptr, int len)` — EE 0x002464a8
IOP: `p[0] = sceInetControl(p[0], p[1], (p[2] ? &p[3] : NULL), p[2])`. Same layout as fno 9: SEND/RECV `len+0xc`, payload at `p[3]`; EE copies `len` bytes back unconditionally.
- Codes (from the mp_net `getsockopt`/`setsockopt`/`getsockname`/`accept` shim 0x1c4140/0x1c43d0/0x1c46d0):
  `1` get `sceInetInfo_t` (0x4c); `2` get / `3` set TCP_NODELAY (u32, `IPPROTO_TCP`,1); `4` set / `5` get IP_MULTICAST_IF (16-byte address); `6` set / `7` get IP_MULTICAST_TTL (u32); `8` set / `9` get IP_MULTICAST_LOOP (u32); `10` set IP_ADD_MEMBERSHIP, `11` set IP_DROP_MEMBERSHIP (0x20 bytes = two `sceInetAddress_t`: group, interface); `0x10` set u32 (wrapper 0x1c4088, no callers — unknown).

### fno 0x14 — `sceInetPoll(cd, buf, sceInetPollFd_t *fds, int nfds, int timeout_ms)` — EE 0x00245cd0
IOP: `p[0] = sceInetPoll(&p[2], p[0], p[1])`.
- SEND `nfds*8+8`: `p[0]` nfds, `p[1]` timeout, fds at `p[2..]` (8 bytes each: cid, events).
- RECV `nfds*8+4`: `p[0]` = number of ready fds (or error), fds (with revents) at `p[2..]`.
- Caller: mp_net `poll()`/`select()` 0x1c3e60 (LISTEN sockets are polled on the cid of their pre-opened accept slot).

### fno 0x1e — `sceLibnetRegisterHandler(cd, buf)` — EE 0x00246b90
IOP: resets the interface-id slots (2 ids), the event ring index and flags; creates two semaphores (mutex; event-count sema max 16); `p[0] = sceInetCtlRegisterEventHandler(&handler)` where the handler callback is `FUN_00000000(id, type)`, which appends `(id, type)` to a 16-entry ring and signals the event semaphore. SEND 0 / RECV 4. Semaphore creation failure → `p[0] = -0x21c`.

### fno 0x1f — `sceLibnetUnregisterHandler(cd, buf)` — EE 0x00246bd0
IOP: `p[0] = sceInetCtlUnregisterEventHandler(&handler)`; deletes both semaphores (-0x21c on failure). SEND 0 / RECV 4.

### fno 0x20 — `sceLibnetSetConfiguration(cd, buf, u32 arg)` — EE 0x00246c10
IOP: `p[0] = sceInetCtlSetConfiguration(p[0])`. SEND 4 / RECV 4. `arg` is an IOP-side pointer to a netcnf config (or 0 = default); no callers in the game (the game runs NETCNF/INETCTL with `-no_auto` and lets EZNETCTL/netcnf bring the interface up).

### fno 0x21 / 0x22 — `sceLibnetWaitGetInterfaceID(cd, buf, int *ids, int n, fno)` — EE 0x00246c58 (thunks 0x00246ce0 = fno 0x21, 0x00246cf8 = fno 0x22)
IOP: loops: pop one event `(id, type)` from the ring (waiting up to 5 × 300 ms, see 0x23), then classify with `FUN_00000358(id, type)`:

| inetctl event `type` | INETCTL name | libnetb action |
|---|---|---|
| 1 | Attach | returns **1** if `id` is the registered primary interface (slot 0, not flag 0x200) → satisfies **0x21** |
| 2 | Detach | if `id` == slot 0 → **fatal** (0x100) |
| 3 | Start (interface configured/up) | returns **4** → satisfies **0x22** |
| 4 | Stop | ignored |
| 5 | Error | if `id` == slot 0 → fatal |
| 6 | configuration found (INETCTL emits it on Attach when a netcnf entry exists) | registers `id` (slot 0, or slot 1 if `InterfaceControl(id, 8)` flags has 0x200); keep waiting |
| 7 | "configuration for this I/F is not set yet" | fatal unless a primary id is already registered |
| 8 / 10 | Up request / Retry | ignored |
| 9 | Down | fatal |

- SEND 0. RECV `n*4+4`: on success `p[0]` = 1 (fno 0x21) or 4 (fno 0x22) and `p[1]`, `p[2]` = interface ids in slots 0 and 1 (0 = empty); the EE copies `p[1..n]` to `ids`. On failure `p[0] = -0x220` with `p[1]` = event type (fatal event) or `p[1]` = -1 / the pop error (no event within ~1.5 s: `p[0] = -0x220`, `p[1] = id` as popped so far), `p[2]` = id.
- EE usage: 0x00246f10 (`sceLibnetWaitGetInterfaceID`-style: first tries `FUN_00246d10` = "any listed interface with flags bit 2 already set", else waits fno 0x21); 0x00246e10 (already-up check, else wait 0x22, then `InterfaceControl(id, 9, addr, 16)`); 0x00246ea8 (wait 0x22 then address).

### fno 0x23 — `sceLibnetGetEvent(cd, buf, int *id, int *type)` (name inferred) — EE 0x00246f90
IOP: `p[0] = PopEvent(&p[1], &p[2])`: waits up to 5 × 300 ms for the event semaphore, `p[1]` = id, `p[2]` = type; `p[0]` = 0 ok, `-0x220` no event, `-0x21c` semaphore error; if the callback ever failed to signal (flag bit 1) → `p[1] = -1`, `p[0] = -0x220`. SEND 0 / RECV 0xc. No direct callers in the game.

### fno 0x32 / 0x33 / 0x34 — `sceInetCtlUpInterface` / `sceInetCtlDownInterface` / `sceInetCtlSetAutoMode(cd, buf, int if_id_or_mode)` — EE 0x002468e8 / 0x00246930 / 0x00246978
IOP: `p[0] = inetctl#5/6/7(p[0])`. SEND 4 / RECV 4 (INETCTL: `if_id == 0` = all interfaces). No callers.

### fno 0x35 — `sceInetCtlGetState(cd, buf, int if_id, int *state)` — EE 0x002469c0
IOP: `p[0] = sceInetCtlGetState(p[0], &p[1])`. SEND 8 (`p[0]` if_id, `p[1]` = `*state` in), RECV 8 (`p[0]` 0 / -1 unknown id, `p[1]` state: 0 DETACHED, 1 STARTING, 2 RETRYING, 3 STARTED, 4 STOPPING, 5 STOPPED). No callers.

### `sceLibnetWaitGetAddress(cd, buf, int *ids, int n, sceInetAddress_t *addr, u32 flags)` — EE 0x00247008 (symbol in `recomp/socom2.toml`)
Not an RPC itself: `flags & 2` → 0x00246e10, else 0x00246ea8 (i.e. fno 0x22 then fno 9 code 9). Called once by the platform layer 0x62e940 with `n = 1`, `flags = 2`.

### `sceLibnetInitialize` 0x00246a38 / `sceLibnetTerminate` 0x00246b10
Bind/unbind only (§1.2); Terminate loops `sceSifMUnBindRpc` until it returns 1 (-0x21c on error).

---------------------------------------------------------------------------------------------

## 4. libnetb_ex fast path (fno 100, 0x65, 0x66, 0x67) — used by the SCE-RT platform layer

The SCE-RT platform layer (0x62da90..0x62ebf8; thunk table 0x62ea58.. = the `rt_platform`
socket API used by rt_udp/rt_tcp/Medius) does **not** use fno 4/5/0xd/0xe for data. It opens
each socket through `FUN_002471a8` + `FUN_002472c8`, after which all data moves through two
8 KB ring buffers in EE memory that the IOP fills/drains with **raw `sceSifSetDma`**, and
16/64-byte headers that each side DMAs to the other's copy of the descriptor. An HLE must
therefore also intercept SIF DMA writes to the fake IOP addresses it hands out in the fno
100/0x65 replies. The ring/descriptor protocol is fully specified below.

### 4.1 EE handle (`FUN_002471a8`, 0x28 bytes, allocated with 0x632340)
| Offset | Content |
|---|---|
| 0x00 | type (`sceInetParam.type`) |
| 0x04 | remote port |
| 0x08 | cid (from fno 1) |
| 0x0c | max datagram size (UDP: caller's; raw: 4; TCP: 0) |
| 0x10/0x14 | raw/aligned pointer of the **recv descriptor+ring** (0x2040 bytes, 64-aligned; descriptor = first 0x40, ring = 0x2000 after) |
| 0x18/0x1c | same for the **send descriptor+ring** |
| 0x20 | recv descriptor (EE address, = aligned 0x14) |
| 0x24 | send descriptor (EE address) |

### 4.2 Descriptor `sceaInetSimpleAsyncInfo` (0x40 bytes; identical layout on both CPUs, each side keeps its own copy)
| Offset | EE meaning | IOP meaning |
|---|---|---|
| 0x00 | `data_waiting_size` (TCP: bytes pending in ring / error code) | same |
| 0x04 | `last_returned_flag` (TCP recv flags) | same |
| 0x08 | max datagram size (UDP/raw) | same (checked: must be ≤ buffer_size-0x40) |
| 0x0c | state: 0 ok, 1 opening, 2 = LISTEN (IOP send thread will `sceInetOpen` it), 3 error | same |
| 0x10 | `cid` | same |
| 0x14 | `inet_flag` (flags passed to recv/send) | same |
| 0x18 | `buffer_size` = 0x2000 | same |
| 0x1c | `buffer_start` (EE ring address = desc+0x40) | IOP ring address (IOP copy) |
| 0x20 | `other_processors_info` = **IOP descriptor address** (from reply `p[8]`) | EE descriptor address |
| 0x24 | – | list link |
| 0x28 | – | async thread id |
| 0x2c | `other_write_loc` = IOP ring address (send side only, reply `p[0xb]`) | EE ring address (recv side: from EE's 0x1c) |
| 0x30 | – | close request (1 = threads must exit) |
| 0x34 | `type` (0 UDP, 1 TCP connect, 2 TCP listen, 3 raw) | same |
| 0x38 | remote port | same |
| 0x3c | ring read offset (EE) | ring write/read offset (IOP) |

### fno 100 (0x64) — start async **receive** — EE 0x00248350
- SEND 0x50: the EE descriptor (0x40 bytes, with `p[0]=0`, `p[1]=0`, `p[8]=EE descriptor address`, `p[9]=0`) + 4 spare words.
- IOP: allocates `0x40 + buffer_size` (`AllocSysMemory`), copies the 0x40-byte descriptor, sets its own `0x1c` = IOP ring, `0x2c` = EE `buffer_start`, `0x24/0x28 = 0`, `0x30 = 0`, links it in `gASyncReadList`, and starts thread `libnet_asyncread` (prio 0x42, stack 0x800): `FUN_000012c4` for TCP, `FUN_00001640` (UDP/raw block loop) otherwise. Reply: **`p[8]` = IOP descriptor address** (0 on failure), `p[10]` = thread id, `p[0xb]` = IOP ring address. `p[0]` is *not* set (EE ignores it; it checks `p[8]`/`p[13]` instead).
- RECV 0x50.

### fno 0x65 — start async **send** — EE 0x002483f8
Same request; IOP additionally sets its `0x2c` = EE ring (`p[7]` of the request) and starts `libnet_asyncsend` (prio 0x41): `FUN_0000171c` (TCP) or `FUN_0000194c` (UDP/raw). Reply `p[8]` = IOP descriptor, `p[0xb]` = **IOP ring address** (the EE writes outgoing data there), `p[10]` = thread id.

After both RPCs, `FUN_002472c8` (for non-LISTEN types) calls fno 2 `sceInetOpen(cid, timeout)`, sets state 0x0c = 0 (or 3 on failure) in both EE descriptors and DMAs the first 0x10 bytes of each to the IOP descriptor (`other_processors_info`). For LISTEN (state 2) the IOP TCP **send** thread performs `sceInetOpen(cid, 10000)` itself, sets state 0/3 and DMAs 0x10 bytes back to the EE descriptor.

### fno 0x66 — close — EE 0x00247460 (direct `sceSifMCallRpc(cd, 0x66, 0, buf, 0x10, buf, 0x10, 0)`)
- SEND 0x10: `p[0]` cid, `p[1]` timeout (platform layer passes 500).
- IOP: if the cid has no async descriptor → `p[0] = sceInetClose(cid, p[1])`. Otherwise waits until the send ring drains (poll every 100 ms, up to `p[1]*1000` ms, forever if `p[1] < 0`), sets close=1 in both descriptors, `p[0] = sceInetClose(cid, p[1])`, then deletes both threads and frees the descriptors.
- RECV 0x10: `p[0]` close result.

### fno 0x67 — debug dump — EE 0x00247b88 (`sceSifMCallRpc(cd, 0x67, 0, 0,0, 0,0, 0)`)
Prints "Displaying LIBNETB's State" with both lists, thread states and `sceInetControl(cid,1)` info. No data.

### 4.3 TCP data protocol (types 1/2)
- **Recv** (IOP thread): waits while EE state ≠ 0; `sceInetRecv(cid, IOP ring, 0x2000, &flags(=inet_flag), -1)`; if `n > 0`: waits until EE `data_waiting_size == 0` (polls its own copy, which the EE updates by DMA), DMAs `n` bytes to the EE ring, then sets `0x00 = n`, `0x04 = flags` and DMAs the **first 0x10 bytes** of its descriptor to the EE descriptor. `flags & 4` ⇒ peer closed, thread exits. On error: `0x00 = error`, DMAs 8 bytes, exits.
- **EE consumer** (`FUN_002474f8`, "recv"): copies `min(len, 0x00)` bytes from `ring + 0x24`(read offset), decrements `0x00`, advances `0x24`; when it hits 0 it resets the offset and DMAs its first 0x10 bytes to the IOP descriptor (`0x20`), which unblocks the IOP thread. `0x04` is returned as flags (platform layer treats bit 4 as "disconnected" → error 0xd).
- **Send** (EE `FUN_00247738`): only when `0x00 <= 0` and state ok; copies ≤ `buffer_size` bytes into the EE ring, DMAs them to the IOP ring (`0x2c`), sets `0x00 = n` and DMAs 0x10 header bytes to the IOP. IOP send thread loops `sceInetSend(cid, ring+done, n-done, &flags, 500)` until all sent, then sets `0x00 = 0` (or the error) and DMAs 0x10 bytes back.

### 4.4 UDP / raw datagram protocol (types 0/3): 64-byte slot headers in the ring
Each datagram occupies `0x40` header + data padded to 64 bytes, placed sequentially from ring
offset `0x3c`, wrapping at `buffer_size`; a header with word1 = 1 is a "skip to start" marker.

| Word | Offset | Content |
|---|---|---|
| 0 | 0x00 | 1 = slot holds data (consumer clears to 0) |
| 1 | 0x04 | 1 = wrap marker (skip), else 0 |
| 2 | 0x08 | slot data capacity (bytes after the header, multiple of 64) |
| 3 | 0x0c | data length |
| 4..7 | 0x10 | `sceInetAddress_t` (source for recv, destination for send) |
| 8 | 0x20 | port (source / destination) |
| 9 | 0x24 | flags (recv: flags out; send: flags in) |
| 10 | 0x28 | send result (IOP writes) |
| 11 | 0x2c | address of this header on the producer's CPU (used as DMA target for the header write-back) |
| 15 | 0x3c | 1 = ready for the consumer |

- IOP recv thread (`FUN_00002a40`): finds a free slot ≥ `0x08`+0x40 bytes (`FUN_0000362c`), `sceInetRecvFrom(cid, slot+0x40, maxsize, &flags, &addr, &port, -1)` (UDP) — for **raw** sockets it instead parses ICMP echo replies (see 4.5) into a 2-byte payload = port — fills the header, DMAs data then header to the EE ring, advances. EE consumer (`FUN_00247d30`): reads the slot at its `0x3c` offset when word0==1 && word15==1, copies data + addr/port/flags out, zeroes word0/word1/word15, restores word3 = word2, DMAs the 0x40 header back to the IOP copy (word 11), advances by `word2+0x40`.
- EE send (`FUN_00247fe8`): writes header+data into its send ring at `0x3c`, DMAs data then header to the IOP ring (`0x2c`+offset), sets word0=1, word15=1. IOP send thread (`FUN_00002804`): `sceInetSendTo(cid, data, len, &flags, addr, port, 500)` (raw: sends an ICMP probe, 4.5); on error/-0x1f8(no resources → retried as 0) writes word10/word9, clears word0/word15/word1, DMAs the header back to the EE copy, and if an error occurred DMAs its own descriptor (0x10 bytes) so the EE sees `0x00 = error`.
- The IOP send thread polls every `send_delay` ms (default 10 ms) and sleeps 1 s between consecutive datagrams (!): `FUN_0000194c` calls `DelayThread(1000)` after each `FUN_00002804`. (Bulk UDP throughput on real hardware was therefore ≤ 1 datagram/s per socket on this path; an HLE need not replicate the delay.)

### 4.5 Raw-socket "probe" (type 3 = sceINETT_RAW)
The platform functions 0x62e128 (send probe, `FUN_00247920`) / 0x62e3d0 (recv probe,
`FUN_002476d0`) exchange 2-byte payloads = a port number. On the IOP this becomes an **ICMP
echo request** built by `FUN_00003044`: IP header 20 bytes (TTL 0x40, proto 1, dst = address),
ICMP type 8, code 0, checksum, identifier **0xa5a5**, sequence = port (big-endian). The receiver
`FUN_00002d20` reads 0x1c-byte raw packets and accepts ICMP type 0 (echo reply) with identifier
0xa5a5, returning the source address and the sequence as the port. SCE-RT uses this for NAT /
reachability probing. An HLE can implement it with a real ICMP echo where permitted, or answer
it locally.

### 4.6 Platform-layer callers (0x672200 client) — for naming the thunks at 0x62ea58..
0x62da90 init (`sceLibnetInitialize`, fno 0x1e, interface list → first with `(flags&3)==3`
within 95 s, `sceLibnetWaitGetAddress` → local IP string @0x6555d0, `InterfaceControl(0xb)`
→ second string @0x6555e8); 0x62db58 shutdown (fno 0x1f, Terminate); 0x62dbd8 socket open
(type/port/host → fno 6 resolve, fno 1, fno 100, 0x65, fno 2 with timeout 10000 for TCP
connect, 0 for listen); 0x62df50 close (fno 0x66, 500); 0x62dfa0 TCP send; 0x62e038 UDP sendto
(host string); 0x62e128 send probe; 0x62e1e8 TCP recv (≤ 0x1000); 0x62e2b8 UDP recvfrom;
0x62e3d0 recv probe; 0x62e4a0 bytes available / accept status (`FUN_002479b8`); 0x62e5c8
resolve → string; 0x62e678 remote address of a cid (fno 0x13 code 1, offset 0x24);
0x62e728 debug dump; 0x62e760 is-connected (`FUN_00247bd8` state check).

---------------------------------------------------------------------------------------------

## 5. Error codes

libnet/libnetb layer (EE and IOP share them):

| Value | Meaning |
|---|---|
| -0x21f (0xfffffde1) | invalid argument / buffer too small for bufsize (EE), `sceLibnetInitialize` bad bufsize |
| -0x21e (0xfffffde2) | `sceSifMCallRpc` failed |
| -0x21d (0xfffffde3) | IOP: unknown function number |
| -0x21c (0xfffffde4) | bind/unbind/semaphore failure; IOP: semaphore create/delete failure in 0x1e/0x1f; EE: `sceInetCreate` returned 0 |
| -0x220 (0xfffffde0) | no event / fatal interface event (fno 0x21/0x22/0x23) |
| -0x200 (0xfffffe00) | ex-path: NULL argument (`sceINETE_INVALID_ARGUMENT`) |
| -0x1f5 (0xfffffe0b) | ex-path: generic failure (`sceINETE_ABORT` value reused) |

`sceINETE_*` codes returned in `p[0]` by INET (from the IOP's own error printer):
-500 TIMEOUT, -0x1f5 ABORT, -0x1f6 BUSY, -0x1f7 LINK_DOWN, -0x1f8 INSUFFICIENT_RESOURCES,
-0x1f9 LOCAL_SOCKET_UNSPECIFIED, -0x1fa FOREIGN_SOCKET_UNSPECIFIED, -0x1fb
CONNECTION_ALREADY_EXISTS, -0x1fc CONNECTION_DOES_NOT_EXIST, -0x1fd CONNECTION_CLOSING,
-0x1fe CONNECTION_RESET, -0x1ff CONNECTION_REFUSED, -0x200 INVALID_ARGUMENT, -0x201
INVALID_CALL, -0x202 NO_ROUTE. Resolver failures additionally use -0x203..-0x206.

mp_net errno mapping (`FUN_001c24d0`, values as the game's errno): -500→0x74, -0x1f5→0x71,
-0x1f6→0x10, -0x1f7→0x73, -0x1f8→0xc, -0x1f9/-0x1fa→0x7d, -0x1fb→0x7f, -0x1fc→0x80,
-0x1fd→0x6e, -0x1fe→0x68, -0x1ff→0x6f, -0x202→0x76, -0x200/-0x201→0x16, other→-1.
Non-blocking recv with nothing pending → errno 0xb.

---------------------------------------------------------------------------------------------

## 6. Confidence summary

| fno | Name | Confidence |
|---|---|---|
| 1 sceInetCreate, 2 sceInetOpen, 3 sceInetClose | layouts exact (EE+IOP); `sceInetParam_t` bytes 0x1c..0x3f unknown | high |
| 4 sceInetRecv, 5 sceInetSend, 0xd sceInetRecvFrom, 0xe sceInetSendTo | exact | high |
| 6 sceInetName2Address, 0x12 sceInetAddress2Name | layout exact; meaning of flag bits (0x01/0x40/0x80) and of `p[1]`/`p[2]` (timeout ms / retries — inferred from caller values 6000, 4) medium | high/medium |
| 7 sceInetAddress2String | exact | high |
| 8 sceInetGetInterfaceList, 9 sceInetInterfaceControl | layout exact; codes 2/3/8/9 solid, 0xb/0x200 semantics uncertain | high/medium |
| 0xa sceInetGetRoutingTable, 0xb sceInetGetNameServers, 0xc sceInetChangeThreadPriority, 0x10 sceInetAbortLog, 0x11 sceInetGetLog | layout exact, names from size-matching + ordinal, unused by the game | medium |
| 0xf sceInetAbort | exact; 'RSLV' flag for resolver abort | high |
| 0x13 sceInetControl | layout exact; codes 1..11 mapped from the sockopt shim; `sceInetInfo_t` 0x3c..0x4b unknown | high |
| 0x14 sceInetPoll | layout exact; pollfd second word opaque | high/medium |
| 0x1e/0x1f/0x20 sceLibnetRegister/UnregisterHandler/SetConfiguration | exact | high |
| 0x21/0x22 sceLibnetWaitGetInterfaceID, 0x23 GetEvent | exact; inetctl event names for 6/7/8/9 partly inferred | high/medium |
| 0x32..0x35 sceInetCtl Up/Down/SetAutoMode/GetState | exact, unused | high |
| 100/0x65/0x66/0x67 libnetb_ex | descriptor and ring protocol exact from both sides; thread timing noted | high |
| msifrpc client struct / packets | exact from libmrpc; meaning of cd+0x18 and bind params 5/6 inferred | high/medium |
