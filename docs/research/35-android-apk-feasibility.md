# 35 — Android: what a native APK would actually take (feasibility, 2026-09-20)

A scoping question from the owner: can this be packaged as an APK and played on a phone? The answer is
further along than expected. Upstream PS2Recomp already carries an Android target and an ARM SIMD path that
nobody in this tree has ever compiled; the CPU half of the port is close to done and is **measured** below,
not assumed. The graphics half is the real work, and it has one requirement that will decide which phones
can run it at all.

Everything in §2 was cross-compiled in this session with `aarch64-linux-gnu-g++ 13.3` and `sse2neon v1.9.1`.
No NDK was available, so nothing here was linked or run on a device; §7 says exactly what that leaves open.

## 1. What already exists, unbuilt

| Where | What |
|---|---|
| `third_party/ps2recomp/CMakeLists.txt:22-27` | `if(ANDROID)` — builds the runtime only, drops recomp/analyzer/test/studio |
| `:29-79` | ARM target detection, fetches `sse2neon` v1.9.1, defines `USE_SSE2NEON`, `-march=armv8-a+fp+simd` |
| `third_party/ps2recomp/android/` | A Gradle project: `build.gradle`, `app/build.gradle`, `settings.gradle`, `gradle.properties` |
| `android/app/src/main/AndroidManifest.xml` | `android.app.NativeActivity`, `hasCode=false`, landscape, `android.app.lib_name=ps2EntryRunner` |
| `ps2xRuntime/CMakeLists.txt:44-47, 74-76` | `PS2X_IS_ANDROID`, raylib built with `PLATFORM=Android` |
| `:488-494` | `ps2EntryRunner` becomes a **shared** library with `-Wl,--undefined=ANativeActivity_onCreate` |
| `:240-242, 245-249` | links `log` and `android`; FFmpeg **off** by default on Android |
| `:610, 693-695, 724` | debug UI, `vu1_replay` and the launcher excluded; `ps2_android_runtime.cpp` added |
| `ps2xRuntime/src/main.cpp:18-40` | stdout/stderr redirected into logcat — implemented |

Two notes on that table. The boot path has no file picker: `main.cpp:150-160` falls back to
`PS2X_DEFAULT_BOOT_ELF`, a **compile-time** string set from a Gradle property. And `android/README.md` says
logcat redirection is "not yet" wired — stale, `main.cpp` does it.

None of this is in CI (`.github/workflows/linux.yml` is the only workflow) and nothing in this tree has ever
targeted it.

## 2. The CPU half — measured

### 2.1 The generated code is full of SSE, as text

The recompiler does not emit portable C++ for the PS2's 128-bit paths. It emits x86 intrinsics as literal
strings: `mmi_translation_helpers.cpp:50-268`, `vu_translation_helpers.cpp:188`, `vu_translator.cpp:305`,
`instruction_translator.cpp:233`. So all 14,880 generated functions (`recomp/socom2_ghidra.csv`) carry
`_mm_*` and `__m128`.

**54 distinct intrinsics** are emitted. All 54, plus the SSE4.1 set the runtime uses
(`_mm_blendv_epi8`, `_mm_min_epi32`, `_mm_max_epi32`, `_mm_mullo_epi32`, `_mm_extract_epi32`), plus
`_mm_getcsr`/`_mm_setcsr`, **compile clean for aarch64 under sse2neon**. `_mm_setcsr` lowers to a real
`msr fpcr` (and `_mm_getcsr` to `mrs x, fpcr`), so the VU's round-toward-zero control has somewhere to go.

### 2.2 The runtime: 61 of 62 files compile for aarch64

A syntax-only sweep of every `.cpp` under `ps2xRuntime/src/lib`, after the two fixes in §2.3:

```
aarch64 syntax check: OK=61 FAIL=1
```

The single failure is `Kernel/Stubs/MPEG.cpp`, which needs `libavcodec/avcodec.h`. The Android branch
already turns FFmpeg off (`ps2xRuntime/CMakeLists.txt:245-249`), so it compiles there — at the price of
MPEG video falling back to stub frames. **The intro and any FMV would not play.**

### 2.3 Two real blockers, both small, both fixed here

1. **Four files include x86 intrinsic headers unguarded**, bypassing the `USE_SSE2NEON` branch the other
   headers use: `include/runtime/ps2_vu1.h:8`, `src/lib/vu/ps2_vu1_ops.h:15`,
   `src/lib/vu/ps2_vu1_upper.cpp:9` (`<emmintrin.h>`) and `src/lib/vu/ps2_vu1_core.cpp:16`
   (`<xmmintrin.h>`). Each now takes the same `#if defined(USE_SSE2NEON)` guard as `ps2_runtime.h:9-16`.

2. **Three lines of x86 inline assembly** — the only inline asm in the whole tree.
   `ps2_vu1_core.cpp:2054-2062`, `VuRoundingScope`, saves and sets the x87 control word with
   `fnstcw`/`fldcw` alongside MXCSR, as a measured 142 ns/call replacement for `fesetround`. There is no
   x87 on aarch64; `_mm_setcsr`'s FPCR write already governs both the SIMD and the scalar paths there, so
   the x87 pair is now under `#if defined(__i386__) || defined(__x86_64__)`.

With those, `ps2_vu1_core.cpp` — the densest SIMD file in the project — compiles for aarch64.

### 2.4 Memory needs no porting

`ps2_memory.cpp:380` is `new uint8_t[]`, and every guest access goes through a bounds-checked software
translation (`:685-925`). 32 MB RAM + 4 MB VRAM (`ps2_memory.h:26-51`). No fixed `mmap`, no host page-table
tricks, nothing platform-specific to port — but that same design is where the EE's CPU cost lives, which
matters in §5.

## 3. The graphics half — the actual work, and the phone-dependent part

`gs_gl_backend.cpp` is desktop GL 3.3 core. The gap to GLES 3.x, in order of difficulty:

**Dual-source blending is a hard requirement, and it is not core GLES.** `gs_gl_caps.h:86-87` fails the
machine without it, and a failed probe means the CPU rasterizer. It is not decorative: the second output
`oBlendAlpha` (`gs_gl_backend.cpp:332-333`) carries the PS2 ALPHA register's `C` coefficient — the
fragment's `As` — independently of the colour's alpha, and `:3669` feeds it in as `GL_SRC1_ALPHA`. That is
how the PS2's programmable `A,B,C,D` blend is reproduced.

On GLES this needs `EXT_blend_func_extended`. Adreno generally has it; Mali historically does not. On a
phone without it the caps probe drops to the software GS, which will not be playable.

There is a better mobile answer than porting the dual-source path as-is: **`EXT_shader_framebuffer_fetch`**
is well supported on tile-based mobile GPUs (Adreno and Mali both), and it lets the PS2 blend equation be
evaluated *exactly*, in the shader, with the destination colour in hand — more faithful than the
dual-source encoding, not less. If this is built, that is the route to take.

The rest is ordinary:

- Five shaders at `#version 330 core` → GLSL ES 300 (precision qualifiers, `layout(index=1)` via the
  extension). `texelFetch` (`:654`) and `gl_FragDepth` (`:349`) are both fine in GLES 3.0.
- `glClipControl` — absent on GLES, and already has a documented fallback (`gs_gl_caps.h:88-91`,
  fragment-depth mapping). A note, not a blocker; `gs_gl_backend.cpp:16` already skips the GLFW lookup
  under `__ANDROID__`.
- `glGetTexImage` — not in GLES at all. Used for readback; becomes FBO + `glReadPixels`.
- The whole backend uses **74 distinct `gl*` calls**. A small surface.

## 4. Everything else

- **Touch controls do not exist.** `ps2_android_runtime.cpp` is three lines: a `TODO` for the on-screen
  stick and buttons. A Bluetooth pad would sidestep this for a first run.
- **No launcher on Android** (`CMakeLists.txt:91` excludes it), so no ISO picker and no settings UI. The
  boot ELF is a compile-time constant. A stranger's first run is a different problem here than on desktop.
- **Storage.** `android/README.md` expects the game tree pushed to
  `Android/data/com.ps2x.runner/files` over `adb`. A real build needs an import flow under scoped storage.
- **Online** is plain sockets against Horizon; nothing Android-specific is expected.
- **Size.** The Linux runner is 224 MB unstripped and the tarball 109 MB (`docs/CURRENT_SPRINT.md:40`).
  Sprint 9 Goal 2's release-and-strip work applies here directly.

## 5. Performance — the honest unknown

No measurement exists and none can be made from here. What is known: the EE does software address
translation on every guest access (§2.4); after Goal 2b the login screen still costs 46-92 ms/s in
`transfer=` on a desktop GPU (`docs/CURRENT_SPRINT.md`, R117-R125); and the desktop bar is 58-60 fps under
a four-core load. A phone's big core is well short of a desktop core and is thermally limited besides.

Nothing in that says a phone will or will not hold a playable rate. It says the only way to find out is to
build it and measure it, and that the measurement should come early — before the GLES backend is polished,
not after.

## 6. If it were done, in this order

1. The two CPU fixes of §2.3. **Done in this investigation**, and the x86-64 build and C++ suite still pass.
2. Get the NDK build to *link* — never attempted; the first genuine unknown.
3. Stand up a GLES backend, taking the framebuffer-fetch route for blending rather than dual-source.
4. Touch overlay, or pad-only for a first run; a boot/import flow.
5. Measure on a real device, early.

Steps 1-2 are small. Step 3 is the sprint-sized piece. Step 5 decides whether any of it was worth it.

## 7. What this does NOT establish

- **Nothing was linked or run.** No NDK in the session; §2 is compile evidence only.
- Whether it reaches a playable frame rate on any device (§5).
- Whether sse2neon's `_mm_setcsr` gives **bit-identical** VU rounding. It compiles and reaches FPCR; it was
  not verified numerically, and the VU float path is where parity defects would show first. Before trusting
  an ARM build, `vu1_replay` against the existing goldens is the check — and it is currently excluded from
  Android/Vita builds (`ps2xRuntime/CMakeLists.txt:724`), which would need undoing for a host-side ARM run.
- Real-device extension support for `EXT_blend_func_extended` / `EXT_shader_framebuffer_fetch`: stated from
  general knowledge of the vendors, not surveyed.
- Distribution. An APK carries the recompiled game code, exactly as `socom2.exe` does; the posture is the
  owner's existing one and no better or worse for being on a phone.
