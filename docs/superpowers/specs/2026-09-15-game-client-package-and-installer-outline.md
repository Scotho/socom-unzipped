# The shippable game client, its launcher, and an installer: outline

Status: outline written 2026-09-15 on the owner's request ("partition out tasks that don't need the lock:
the game client, installer outline"), lock-free, no code. It sharpens the original design's M6 ("portable
zip: exe + runtime + an install.bat-free first run that asks for the ISO path; README, GPL sources",
`docs/superpowers/specs/2026-09-04-socom2-pc-recompilation-design.md` §M6) against what the runtime
actually needs today. Nothing here is scheduled before Sprint 8 (`docs/superpowers/specs/2026-09-15-sprint-6-…-design.md`
§7) except where marked **[Sprint 6/7]**; it exists so the product shape is known while the correctness
work proceeds. Every "today" statement was read from the tree on 2026-09-15.

## 1. What the client is, today

`dist/socom2.exe` is the recompiled game plus the runtime (raylib window, GL backend, IOP services,
Horizon-facing netcode). It is launched as `socom2.exe <path-to-socom2_game.elf>` (`run.sh`). At start it
needs, in this order:

| Need | Today | Source |
|---|---|---|
| The merged game ELF (`socom2_game.elf`, loader + two decrypted overlays) | `game/disc/socom2_game.elf`, built by `tools_py/make_overlay_elf.py` from the user's disc after `tools_py/decrypt_apache.py` recovered the overlays (Unicorn-driven) | `build.sh recomp`; README "How it works" |
| The disc as a raw image (the game opens `RUN/*.ZAR` by LBN) | an `.iso` next to the ELF or one directory up, else `PS2X_CD_IMAGE=<path>` | `game_overrides_socom2.cpp` `configureCdImage` |
| Memory cards | `PS2X_MC_DIR=<dir>` (default under the ELF directory; a second instance needs its own) | `ps2_runtime.cpp` |
| Runtime DLLs | 32 files, ~45 MB, next to the exe (SDL2, ffmpeg 61, OpenEXR, jxl, brotli, freetype, harfbuzz, libc++, libunwind, winpthread) | `dist/` |
| A server to log into | `PS2X_SOCOM2_SERVER=<ip>` (else the exe advertises 127.0.0.1); the local Horizon stack under `server/` | `socom2_hostnet.cpp`; `server/README.md` |
| Input | raylib gamepad 0 when present (`ps2_pad.cpp`); keyboard/mouse host input is the harness path, opt-in via `PS2X_SOCOM2_PAD`, mouse look via `PS2X_SOCOM2_MOUSE=1` | `socom2_host_input.cpp` |
| Window | 640×448 resizable, aspect-fit presentation, `PS2X_PRESENT_FILTER`, `PS2X_GS_SCALE=1..4` | `ps2_runtime.cpp`, README |

Two facts shape everything below. **The recompiled code inside `socom2.exe` is derived from the game's
own binary**, so the exe is not a clean-room artefact the way an emulator is; whether it can be
distributed at all, or must be *built on the user's machine from their disc*, is the owner's call and a
legal one, not an engineering one. **The exe is 236 MB** (recompiled C++ for ~3.6 MB of MIPS text plus the
runtime, LTO off, `-O1` generated code); that is a download-size and antivirus-heuristics concern before
it is a performance one.

## 2. Two packaging shapes, and the recommendation

**A. Portable folder (the M6 target).** `socom2/` with `socom2.exe`, the DLLs, `launcher.exe` (or a
`.ps1`/`.bat` first), `README.txt`, `LICENSES/` (GPL-3.0 for the PS2Recomp fork, raylib zlib, ffmpeg LGPL,
the rest), and empty `cards/`, `logs/`. The user points it at their ISO once. No registry, no admin,
uninstall = delete the folder. **Recommended**: it matches how the community runs emulators, it is what
the design chose, and it needs nothing the project does not already have.

**B. Installer (Inno Setup or NSIS).** Adds Start-menu entries, a per-user data directory
(`%LOCALAPPDATA%\socom2\` for cards, logs, config), file association for `.iso` is *not* wanted, an
uninstaller. Worth doing only after A is stable; the script is ~100 lines over A's folder and can be
generated in CI. Sketch in §6.

**Not** a shape: an in-place "build from your disc" flow that runs the recompiler on the user's machine.
It needs clang, CMake, Ninja, Python + Unicorn and ~15 minutes, and the generated C++ is deterministic
from the ELF, so there is no benefit over shipping the exe *if* shipping the exe is permitted. If it is
not permitted, that flow is the only option and becomes its own project (a "recomp kit" download that
produces the exe from the disc; PS2Recomp upstream's model).

## 3. The launcher

A small window (raylib itself, or a PowerShell/WinForms script for the first cut) that owns the
configuration the exe reads from environment variables, so no user ever sets a `PS2X_*` variable by hand:

- **First run:** ask for the ISO path; verify it is SCUS_972.75 r0001 by hashing `SCUS_972.75` out of
  the image (the project already parses the ISO directory in Python — port the ~40 lines or ship
  `tools_py` under an embedded Python only if the launcher is Python); write `config.json`.
- **Server:** a text field for the server address (default: the project's public server once one
  exists, else `127.0.0.1` with a "start local server" button that runs `server/start-servers.ps1`
  when the Horizon stack is installed alongside); maps to `PS2X_SOCOM2_SERVER`.
- **Cards:** one memory-card directory per profile (`cards/<profile>/`), maps to `PS2X_MC_DIR`.
- **Video:** window size (native, 2×, fullscreen borderless), presentation filter, render scale (1 or
  2 — 3 and 4 are untested and cost 67 MB per target); maps to `PS2X_PRESENT_FILTER`, `PS2X_GS_SCALE`,
  and a window-size argument the runtime does not yet take (**[Sprint 8]**: today the window opens at
  640×448 and only an external resize changes it).
- **Input:** gamepad (default when present) or keyboard+mouse (`PS2X_SOCOM2_PAD=1`,
  `PS2X_SOCOM2_MOUSE=1`, `PS2X_SOCOM2_MOUSE_SENS`); a bindings page is **[Sprint 8]** — today the
  keyboard map is the harness's (W/A/S/D, I/J/K/L, R1 on a fixed key).
- **Launch:** `socom2.exe <elf>` with the environment set, stdout/stderr to `logs/run_<stamp>.log`,
  and a "copy diagnostics" button that zips the last log, `config.json` and the DLL hashes.
- **Second instance** (for testing on one machine): a checkbox that sets `PS2X_SOCOM2_UDP_SHIFT=2`,
  `PS2X_SOCOM2_RSA_KEY=b` and a second card directory, exactly what `online_match_ours.py` does.

## 4. What must change in the runtime before a stranger can run it

Ordered by how much each blocks a first outside user; none is scheduled before Sprint 6 closes.

1. **Defaults that assume the developer tree.** The ELF path argument, the ISO search "next to the ELF
   or one up", and the memory-card default should all resolve from `config.json` or from the exe's own
   directory; the launcher hides this, but a bare `socom2.exe` double-click should also work
   (`socom2.exe` with no argument → read `config.json` next to it). **[Sprint 8]**
2. **The merged ELF is built from the disc.** Either ship `socom2_game.elf` (it is the game's code,
   same question as the exe) or build it on first run: `decrypt_apache.py` needs Unicorn, which means an
   embedded Python (~30 MB) or a C++ port of the decrypt (the loader's libdnas2 path run under a MIPS
   interpreter — the runtime already has one). The owner's distribution ruling decides which.
3. **Knob retirement.** 80+ `PS2X_*` variables, most diagnostic; a shipped client should read a config
   file for the dozen a user may touch and ignore the rest unless a `--dev` flag is present.
   **[Sprint 6 Goal 8 starts this; Sprint 8 finishes]**
4. **Crash and hang reporting.** Today a stall or crash is diagnosed from `[peek]` rows and the
   pc-sampler; a user needs a one-file diagnostic (the launcher's "copy diagnostics") and an exit code
   that distinguishes "ISO not found" from "shader compile failed" from a guest crash.
5. **Size.** Try `GENOPT=-Os` for the generated code and `LTO=ON` on a release build, measure the exe
   and the frame rate; strip symbols; drop the OpenEXR/jxl/brotli DLLs if the screenshot path is the only
   user (it is the harness's PNG export — a release build can compile it out). Target under 100 MB
   total. **[Sprint 7, alongside the two-instance speed work — same build flags]**
6. **Antivirus.** A 236 MB unsigned exe that opens sockets and reads a disc image will be flagged. Code
   signing costs money and a legal identity; at minimum publish SHA-256 sums and build in CI so the
   binary is reproducible from a tagged commit.

## 5. The online system as shipped

The client talks to a Horizon Private Server configured for app id 10472 (`server/README.md`). For
players, someone must host that stack on a reachable address; the client's server field is the whole
client-side story. What the *server* package needs, in order:

1. A `server/` zip: the built .NET 9 Horizon binaries, the four configs, `start-servers.ps1`, and the
   simulated database seeded with `CreateAccountOnNotFound=True` so any name self-registers. This exists
   for the developer machine; it needs the advertised address made configurable (today 127.0.0.1) and
   the ports documented for a router (10070 UDP, 10071/10073/10075/10077/10078 TCP, plus the DME and
   peer UDP ranges).
2. **Two machines, not two instances**, as the first real online test **[Sprint 7]** — everything so
   far is two exes on one host, which never exercised NAT, the advertised address, or clock skew.
3. A real database (SQL Server via the middleware) only when stats, clans and bans across restarts are
   wanted; simulated mode is enough for matches.
4. PCSX2 interoperability (Sprint 6 Goal 7): a mixed lobby is the acceptance that "fully functional
   online" means the same server for console players.

## 6. Installer sketch (Inno Setup)

```
[Setup]
AppName=SOCOM Unzipped         AppVersion={#GitTag}     DefaultDirName={autopf}\SOCOM Unzipped
PrivilegesRequired=lowest      OutputBaseFilename=socom-unzipped-setup-{#GitTag}
LicenseFile=LICENSES\GPL-3.0.txt

[Files]
Source: "dist\socom2.exe";        DestDir: "{app}"
Source: "dist\*.dll";             DestDir: "{app}"
Source: "dist\socom2_game.elf";   DestDir: "{app}"
Source: "launcher\*";             DestDir: "{app}"
Source: "LICENSES\*";             DestDir: "{app}\LICENSES"

[Dirs]
Name: "{localappdata}\SOCOM Unzipped\cards";  Name: "{localappdata}\SOCOM Unzipped\logs"

[Icons]
Name: "{autoprograms}\SOCOM Unzipped"; Filename: "{app}\launcher.exe"

[Run]
Filename: "{app}\launcher.exe"; Parameters: "--first-run"; Flags: postinstall nowait
```

The installer never touches the ISO; the launcher's first run asks for it. Uninstall removes `{app}`
and leaves `{localappdata}\SOCOM Unzipped` (cards are saves). A CI job builds the folder (§2 A), the installer
(§6), and `SHA256SUMS`, from a tag.

## 7. Owner decisions (2026-09-15)

1. **Distribution: ship the exe and the merged ELF.** The portable folder (§2 A) carries `socom2.exe`, the
   DLLs and `socom2_game.elf`; the player supplies only their ISO, which the launcher's first run asks for.
   Consequence: §4.2's "build the ELF on first run" path is dropped; no embedded Python, no decrypt port.
   The owner takes the distribution risk knowingly; the README and installer license page say plainly
   that the code is derived from the retail game and that the player must own the disc.
2. **Online: a project-hosted Horizon server**, its address the launcher's default, with a custom
   address still allowed (so "bring your own server" remains possible for LAN groups, and community
   instances can be tried without a build). Follow-ups it creates: a host machine and its router/port
   plan (§5.1), the advertised address made configurable in `server/config`, and the two-machine test
   (§5.2) as Sprint 7's first online item.
3. **Name: SOCOM Unzipped** for the launcher, the installer and the folder (`SOCOM Unzipped/`,
   `socom-unzipped-setup-<tag>.exe`); the installer sketch in §6 is updated accordingly.
