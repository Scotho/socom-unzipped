# Sprint 10 Q6 (Goal 11) -- a latched stall must not eat the machine

*Record of the work on branch `agent/stall` (worktree `C:\projects\wt-stall`, off `sprint-10`), 2026-09-21. The
numbers below are the ones the tests print; the gate on the rebuilt exe and a look at a real stall run are the
controller's (section 6).*

## 1. What was true before

Three things bound the GL backend's command queue (`gs_gl_backend.cpp`, `gs_frame_backpressure.h`):

1. **Frames** (R35, Sprint 5): `GsFrameBackpressure` makes the recorder wait when more than N=3 guest frames are
   recorded ahead of the replay. When the replay makes no progress for 2 s (a title-bar drag holds the GL thread in
   the modal size-move loop; a hang; llvmpipe under a blocked audio thread on the VM) the wait **latches
   "stalled"** and frames stop waiting, so the game keeps running while the window is stuck.
2. **Bytes** (Sprint 7 Task 1b): once latched, `GsPendingCap::admit` drops draw work (`Submit`, `Clear`, the
   fire-and-forget `Readback`) past `PS2X_GS_PENDING_CAP_MB` (64 MB) -- the next guest frame records it again.
   It admitted every **state-carrying** command without bound, because dropping an upload, a transfer, a CLUT
   snapshot or a VRAM write corrupts every frame drawn after the stall.
3. **A ceiling** (R124, Sprint 8 Goal 5): at `PS2X_GS_PENDING_HARD_CAP_MB` (1024 MB) the recorder waits for the
   replay in 50 ms slices, **5 s at most per command, then admits anyway**. It moved the wall from "the allocator
   gives up" to "one gigabyte, then the game thread crawls"; `admit` itself stayed unbounded, and the
   `postAndGetToken` path (`Present`, once per frame) never waited at all. The 8 GB VM with no swap died of
   `std::bad_alloc` on a GS-register store before R124 (`s8_vm_title_audio3`: the title movie under a hung GL
   thread); R124 was never measured on that machine.

**What the working set is made of during a latched stall, per guest frame** (read from `GS::loadClutIfNeeded`,
`GSGlBackend::UploadImage/BeginTransfer/LoadClut/Present`, research/16 section 9, KNOWN's decodes row):

| stream | per frame | a `Cmd` record is **656 bytes** (`GSGlBackend::kCommandBytes`) |
|---|---|---|
| the title movie | ~1040 `BeginTransfer` + `Upload` pairs, one 16x16 CT32 tile of 1 KB each | 1040 x (2 x 656 + 1024) = 2,429,440 bytes; with two 2 KB palette loads and the Present, 2,435,504 (the test's frame) |
| gameplay / menus | streamed texture uploads (the menus: 7-11k 1 KB tiles a second) | of the same shape |
| palettes | one `ClutLoad` (a 2 KB+ `GSClutLoad` snapshot) per palette *alternation* -- SOCOM II alternates palettes on consecutive draws | thousands a second in a round |
| presents | one `Present` through `postAndGetToken` | 656 bytes |
| draw work | ~500-2000 `Submit`/`Clear` | dropped since Sprint 7 |

600 frames of the title movie (10 s of a hung GL thread) offer **1,461,302,400 bytes** of state to the queue. Every
one of those commands is a write into a memory whose **final state the game thread already holds**: the
game-thread `GSCpuBackend` (`m_cpu`) applies each upload, transfer and VRAM write to the real VRAM *before* the
command is recorded, and a palette snapshot is keyed by its content (`loadClutIfNeeded`: the same bytes get the
same id). Replaying the stream after the stall reproduces exactly the state the game thread has now.

## 2. The policy chosen: absorb and re-anchor

While the replay is latched and the byte cap is reached, `GsPendingCap::admit` now **refuses** a state-carrying
command too, and stays "absorbing" until the latch clears. A refused state command is handed to the new
`GsStallCoalescer` (`gs_stall_coalescer.h/.cpp`), which remembers **where** it wrote and nothing else:

- a destination rectangle per `(dbp, dbw, dpsm)` -- the bounding box only where two rectangles tile exactly (the
  movie's 16x16 blocks growing a row, a completed row joining the rows above it), otherwise separate pieces, at
  most 8 per key before they collapse to their box; at most 512 pieces in all;
- the touched pages (a 64-byte mask);
- the newest snapshot per palette id, at most 256 (the replay's own eviction window is 256 loads);
- past 512 pieces, past 4 MB of rectangle bytes, or on a format the packer cannot read: **one 64x32 CT32 rectangle
  per touched page** -- still the exact bytes (every PSM shares the page's 8 KB), a coarser render-target refresh.

When the latch clears (`GsPendingCap::reanchorDue`), `GSGlBackend::reanchorLocked` pushes, ahead of the next
command: one `ClutLoad` per remembered palette (oldest first); one 4 MB `SnapshotVram` of the game thread's VRAM
under the CPU backend's own lock; one synthesized `BeginTransfer` + `Upload` per rectangle carrying the rectangle's
bytes **as they are now**, packed exactly as the IMAGE stream packs them (`packRect`: 4/3/2/1 bytes per pixel,
4-bit formats two per byte in one continuous nibble stream); then, if a host->local transfer is still open on the
game thread, its `BeginTransfer` plus the prefix already taken (`packPrefix`), so the receiver's transfer state
equals the game thread's and the game's next chunk lands in its own row. The synthesized commands go through the
ordinary render-thread path (`executeTransfer`/`executeUpload`: the shadow VRAM, the page generations the R123
texture cache revalidates by, `refreshRenderTargetsFromShadow` with the transfer's exact rows when it is in the
target's layout). **The frame after the stall is drawn from exactly the VRAM the game has -- correct by
construction, not by replaying history.**

What is dropped, coalesced or re-anchored, and why each is safe:

| command | while absorbing | why |
|---|---|---|
| `Submit`, `Clear`, fire-and-forget `Readback` | dropped (as since Sprint 7) | the next guest frame records it again; the stalled window could not show it |
| `Present` | dropped; its token resolves with the last command issued | the next Present carries the display registers again; the only waiter is `PS2X_FRAME_DUMP`'s 2 s wait, which a latched stall already cost it |
| `BeginTransfer` (host->local, local->local), `Upload`, `WriteVram` | coalesced into rectangles; re-anchored from the game VRAM | the game VRAM holds their final effect; every synthesized rectangle writes the truth, so overlapping rectangles agree byte for byte and their order does not matter |
| `BeginTransfer` local->host | counted only | it reads; the game thread served it from `m_cpu` already |
| `ClutLoad` | coalesced by id, newest 256 | ids are content-keyed; the replay only needs each id once |
| `Reset`, blocking `Readback` (token-waited) | admitted, never refused | waited on for their effect; a Reset also blanks what the coalescer remembered (both VRAMs are blank after it) |

The **alternative** considered and not chosen: make R124's ceiling honest (no 5 s escape, wait until the replay
drains). It bounds memory at the ceiling (two buffers: up to 2 GB on the VM), freezes the game thread for the
whole drag after the first ~4 s (the title movie fills 1 GB in about that), makes a long stall cost a
gigabyte-sized replay to catch up on, and keeps the online connection's fate tied to the window being dragged.
Absorb-and-re-anchor keeps the queue at the cap plus one command for as long as the stall lasts, the game running,
and the catch-up at one VRAM's worth of uploads.

What is *not* exact, plainly: a merged rectangle's bounding box can cover pixels the stall never wrote, and the
per-page fallback refreshes whole page rows. Both write bytes the game VRAM holds, which equal the shadow's except
where the GPU drew and only the shadow was refreshed (`downloadRenderTargetToShadow`); for a frame buffer that is
one frame's difference (it is redrawn), for a draw-once render target that a stall's upload also lands in it could
persist until the target is next drawn. This is the same class of assumption Sprint 7's draw drop already makes
(the frames after a stall rely on the game redrawing), narrowed by the tiling rule and the 8-pieces-per-key limit.

## 3. The tests (`gs_frame_backpressure_tests.cpp`)

- **Rewritten:** "a latched queue drops guest frames and keeps uploads" (line ~422) asserted
  `cap.bytes() <= 1024 + 200 * 64` -- "only uploads may exceed the cap" -- and so codified the unbounded state
  stream. It now asserts `cap.bytes() <= 1024 + 64` (the cap plus one command) and that uploads are admitted up to
  the cap and refused past it.
- **New, RED before / GREEN after, on the existing seam (`GsPendingCap::admit` only):** "across N frames of a
  latched stall the pending bytes stay under the cap plus one command" -- 600 title-movie frames (1040 tile pairs,
  2 palettes, 500 draws, 1 present each) against a 64 MB cap.
- **New, on the new seam:** the absorbing verdict outliving the byte count until the latch clears; the movie's
  tiles becoming one 640x416 rectangle and two palettes over 600 frames with the tables under 16 KB; the packed
  rectangle reproducing the upload's bytes and the VRAM byte for byte for all 13 storage formats (odd sizes and
  origin, three chunks) plus the per-page CT32 view; an in-flight CT16 transfer restored to the game thread's
  position with the next chunk landing in the same rows on both sides; the hostile stall (4000 distinct
  destinations -> per-page plan under 4 MB, 1000 palettes -> the newest 256, an unreadable format -> pages, a Reset
  forgetting what preceded it).

RED (implementation parked, tests in): ps2x_tests 702 run, 700 passed, 2 failed --
`Q6: across N frames of a latched stall ...   [Failed] peak pending bytes over 600 stalled frames must stay under the cap plus one command: peak 1448985600 > 67111552 (the state stream offered 1441305600 bytes)` (the RED build used a 640-byte stand-in for the record; the GREEN build measures the real 656) and `a latched queue drops guest frames and, past the cap, refuses uploads ...   [Failed] the queue stays at the cap plus one command, was 13312`.

GREEN: `./build.sh test --no-runner` exit 0 -- Python `Ran 1571 tests ... OK (skipped=96)`, ps2x_tests `Total Tests: 707 Passed: 707 Failed: 0` (702 before: the two rewritten/new bound cases plus five new-seam cases), the VU1 verify runs `PASS: 0 mismatching field(s)`. The N-frames case prints `a command record is 656 bytes; one title frame offers 2435504 bytes of state, 600 of them 1461302400`.

## 4. The instrument

- `[gs-gl] stall bound (Q6): ...` at init names the bounds and `sizeof(Cmd)`.
- `[gs-gl] stall bound engaged: the replay is latched stalled with <n> MB of commands pending; uploads, transfers,
  CLUT loads and VRAM writes are absorbed into the game VRAM until it drains (engagement <k>)` -- once per stall
  that reaches the cap.
- `[gs-gl] stall bound released: <c> commands (<m> MB) absorbed over the stall, re-anchored as <p> palettes + <r>
  rectangles[ (per page)][ + the open transfer] (<kb> KB pushed)` -- when the latch clears.
- The `[gs-gl stats] backpressure ...` line (`PS2X_GS_STATS=1`, every 60 presents) gains
  `stall_engaged= stall_absorbed_cmds= stall_absorbed_bytes= stall_reanchor_bytes=`.

## 5. Rulings (numbered by the controller 2026-09-21: R189-R192)

- **R189 -- the state stream is absorbed, not waited on.** Decided 2026-09-21 by the stall agent. A latched stall
  keeps the game running (Sprint 7's intent) and the queue at the cap plus one command, at the cost of a re-anchor
  of at most 4 MB plus 512 + 256 commands when the window comes back, and the inexactness named in section 2's
  last paragraph. R124's ceiling stays as the last line for an unlatched-but-slow replay and for
  `PS2X_GS_PENDING_CAP_MB=0`. Overturnable: `PS2X_GS_PENDING_CAP_MB=0` restores the pre-Q6 path exactly.
- **R190 -- `Present` is droppable at the cap on a latched stall.** Before Q6 it was "accounted, never dropped".
  Its only waiter is the frame dump (2 s timeout, already paid on a stall); the next Present carries the display
  registers again. Cost if wrong: a frame-dump run under a drag misses frames it could not have shown.
- **R191 -- the bounds: 512 rectangle pieces, 8 per key, 256 palettes, 4 MB.** 256 is the replay's own CLUT
  eviction window (a re-anchor of more would evict its own first entries); 4 MB is VRAM's size (the page plan can
  never exceed it); 512 and 8 are the point where a rectangle table stops being cheaper than the page mask. None
  was measured against a real stall; the stats line's `stall_reanchor_bytes=` will say what a real one costs.
- **R192 -- no launch from this branch.** The gate on the rebuilt exe and the stall run are the controller's
  (section 6); this agent built and ran `./build.sh test --no-runner` only.

## 6. For the controller

Rebuild, gate, then one real stall (Windows; the VM stays off):

```bash
export LOOP_LOCK_PATH=/c/projects/socom_pc/logs/.loop_lock
bash scripts/loop_lock.sh run main --purpose "Q6: runtime" -- ./build.sh runtime
bash scripts/loop_lock.sh run main --purpose "Q6: test" -- ./build.sh test
python -m tools_py.parity.gate --stamp s10_q6_gate --owner gate          # expected 3/3
# the stall: a title-stage launch with the stats on, and a 30 s title-bar drag 90 s in (Sprint 7's recipe)
PS2X_GS_STATS=1 python -m tools_py.parity.gate --only title --stamp s10_q6_drag --owner gate &
sleep 90; powershell.exe -NoProfile -File scripts/parity/drag_window.ps1 -Title "PS2-Recomp" -Seconds 30; wait
grep -a "stall bound\|stall_engaged" logs/parity/gate/s10_q6_drag/title.run.log | tail -5
```

Expected in the run log, if the drag latches (on this host Sprint 7's 30 s drag did not: the Windows size-move
loop kept pumping and the cap never engaged, R93 -- a longer drag or the VM's hung GL thread does):

```
[gs-gl] stall bound engaged: the replay is latched stalled with 64 MB of commands pending; uploads, transfers, CLUT loads and VRAM writes are absorbed into the game VRAM until it drains (engagement 1)
[gs-gl] stall bound released: <c> commands (<m> MB) absorbed over the stall, re-anchored as <p> palettes + 1 rectangles (1040 KB pushed)
[gs-gl stats] backpressure ... stall_engaged=1 stall_absorbed_cmds=<c> stall_absorbed_bytes=<b> stall_reanchor_bytes=<r>
```

and `pending_bytes=` flat at the cap for the drag's duration. If the drag never latches, the line to look for is
its absence together with `timeouts=0` on the stats line: the bound had nothing to do.
