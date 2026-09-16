# Terrain-hole research tools (research/31 sections 15-16)

Offline scripts used on 2026-09-16 to compare the console's terrain draw list (a PCSX2 GS dump extracted to a
`[u32 path][u32 size][bytes]` packet stream) with ours (`PS2X_GIF_DUMP`) and with our VU1 program dumps
(`PS2X_VU1_DUMP`). They run from a directory holding `console_replay/packets.bin`, `our_replay3/packets.bin` and
`vu1dump_spawn/`, and some `exec()` the parsers of their siblings, so keep them together.

- `fan_sizes.py OURS CONSOLE` -- terrain (TEX0 block 0x36b1) fans per frame with the polygon-size histogram.
- `fan_detail.py NAME STREAM MB STOP LO HI` -- packet-level detail of fans LO..HI (vertices, A+D state).
- `terrain_dumps.py DUMPDIR PKDIR` -- which VU1 dumps hold the terrain texture, their header counts and cull flags.
- `clip_planes.py DUMP` -- the five clip planes (data qwords 30-36) and each primitive's signed distances.
- `patch_dump.py DUMP` -- a family-B dump's vertex block and index list with the cull dot products.
- `eye_experiment.py DUMPDIR` -- replay with the cull eye nudged.
- `unproject.py` -- fits the camera from dump 237 and unprojects console fans to world space.
- `classify2.py DUMPDIR CONSOLE LIMIT` -- replays every terrain program of the frame as-is and with the clip planes
  and cull normals zeroed, and labels each console fan KICKED / SENT-BUT-DROPPED / ABSENT.

`dist/vu1_replay.exe --batch <out> --no-native <dumps>` and `--pchist <hist.bin>` (execution counts per pc, e.g.
0x1f98 primitives, 0x2060 front-facing, 0x2090 survived the clipper) are the replay side.
- `cull_trace_scan.py TRACE [x,y,z]` -- reads a `PS2X_CULL_TRACE=<file>:t<seconds>[:<count>]` log (the object
  box-frustum cull FUN_00290c30: corners, matrix, guest result and mask, IEEE recomputation) and lists the calls
  whose box holds the world point, plus every guest-vs-IEEE mask disagreement.
