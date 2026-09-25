# Sprint 1 — Hygiene, Freeze, First Native VU1 Program: Implementation Plan

> **ARCHIVED 2026-09-23 — Sprint 1's plan, closed 2026-09-11. Cited by `docs/archive/HANDOFF-reference-to-2026-09-13.md`; kept verbatim.**
> Moved here from `docs/superpowers/plans/` in Sprint 11; nothing below it was edited except those
> citations that pointed at this block's own old paths. It is a record, not an instruction.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project testable (unit tests build and run, one PASS/FAIL gate command), freeze emulator speed work, and land the first hand-written native replacement of a VU1 program (entry point 0 of the game's single microcode image, the 2D/UI path) verified packet-for-packet against the interpreter.

**Architecture:** Tasks 1-4 add a test target to `build.sh`, a `--verify` mode to the existing offline VU1 replay tool with committed fixture dumps, and a `gate` Python command that drives the three existing screenshot scripts and scores them numerically. Tasks 5-8 add a native-program registry keyed by (microcode hash, entry pc) in front of the existing generated-code dispatch, then implement the entry-0 command interpreter natively, handler by handler, handing anything unimplemented back to the existing code, until the title-screen dumps run 100 % native with zero GIF mismatches.

**Tech Stack:** C++20 under llvm-mingw clang (portable toolchain in `tools/`, driven by `build.sh`), CMake + Ninja, the fork's hand-rolled MiniTest framework, Python 3 (numpy, Pillow) for the parity tooling, Git Bash for scripts.

**Spec:** `docs/archive/sprints-1-6/2026-09-10-sprint-1-hygiene-and-native-render-design.md`

## Global Constraints

- Repo root is `C:\projects\socom_pc` (its own git repo, remote `github.com/Scotho/socom-unzipped`). Commit from the root with explicit paths, never `git add -A`; leave `server/config/simulated.db` unstaged; push after each commit. Commit trailers: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: <session url>`.
- Builds and game runs are serial: `scripts/loop_lock.sh take <owner>` before any `./build.sh`, `run.sh` or `drive.py`; `release <owner>` after. Offline tools (`vu1_replay`, `ps2x_tests`, Python analysis) need no lock.
- `./build.sh runtime` takes ~3 min for a .cpp change, ~10 min after a header change. Never edit a header mid-build.
- Long game runs must be launched detached (a bash script under `logs/`, started with PowerShell `Start-Process bash.exe <script>`, polled through a `.done` marker): the harness kills long background shells.
- Shell and Python files stay LF. C++ edits go through the Edit tool or a Python patch script (bash heredocs mangle backslashes).
- **Frozen this sprint:** no commits that change VU1/VU0 interpreter speed, scheduler batching, GS/GL caching or upload paths for performance. Accuracy fixes found by the gate are allowed.
- Sprint 1 native code must emit the *same GIF packets* as the microprogram. Host-resolution drawing is Sprint 2.
- Every sprint-1 native VU1 program uses the arithmetic helpers in `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_ops.h` for FMAC/FDIV/EFU maths so results are bit-identical to the interpreter.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xTest/CMakeLists.txt` | fix the mingw stack flag; add the SOCOM link-stub TU |
| `third_party/ps2recomp/ps2xTest/src/socom2_link_stubs.cpp` | (new) definitions of the four SOCOM-runner symbols the runtime library references |
| `third_party/ps2recomp/ps2xTest/src/main.cpp` | register the new suites |
| `third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp` | (new) unit tests for the native-program registry and hand-back contract |
| `build.sh` | new `test` step: build `ps2x_tests` + `vu1_replay`, run both, run fixture verification |
| `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` | `--verify <golden state.txt>`, `--regs`, `--native` |
| `tests/fixtures/vu1/title/*.bin`, `tests/fixtures/vu1/title/golden.txt` | (new) 12 title-screen VU1 dumps + exact-interpreter golden |
| `tools_py/parity/gate.py` | (new) runs the three gates, scores them, prints PASS/FAIL, exit code |
| `tools_py/tests/test_gate.py` | (new) unittest for the scorers on stored run directories |
| `docs/LOOP_PROMPT.md`, `docs/HANDOFF.md`, `docs/STATUS.md` | freeze rules, gate requirement, "Current state" section |
| `docs/research/12-vu1-entry0-ui-path.md` | (new) what entry 0 of the VU1 image does on the title screen |
| `third_party/ps2recomp/ps2xRuntime/include/runtime/ps2_vu1.h` | `Vu1NativeProgram` struct, test override hook |
| `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp` | native dispatch before the generated-code dispatch; counters |
| `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/vu1_native_programs.cpp` | (new) the registry table |
| `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_entry0.cpp` | (new) the native entry-0 program |
| `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` | glob `src/lib/vu/native/*.cpp` into `ps2_runtime` |

---

### Task 1: Make `ps2x_tests` build and run under the project toolchain

**Files:**
- Modify: `third_party/ps2recomp/ps2xTest/CMakeLists.txt:123-127`
- Create: `third_party/ps2recomp/ps2xTest/src/socom2_link_stubs.cpp`
- Modify: `build.sh`

**Interfaces:**
- Consumes: the existing target `ps2x_tests` (`ps2xTest/CMakeLists.txt:94`), `MiniTest::Run()` returning the failed count (`ps2xTest/include/MiniTest.h:123`), `std::_Exit(res)` in `ps2xTest/src/main.cpp:43-46`.
- Produces: `./build.sh test` → exit 0 when every test passes; `third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe`.

Background: the link currently fails twice (documented at `docs/STATUS.md:333-336`): the mingw branch passes `--stack,8388608` without `-Wl,`, and `libps2_runtime.a` references four symbols that only exist in `game_overrides_socom2.cpp`, which is attached to the `ps2EntryRunner` executable, not the library (`ps2xRuntime/CMakeLists.txt:491-497` explains why: static self-registration objects would be dropped from a static lib).

- [x] **Step 1: Reproduce the link failure**

Run (from repo root, Git Bash):
```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests 2>&1 | tail -20
```
Expected: FAIL. First `clang-23: error: unknown argument: '--stack,8388608'`; after fixing that, `undefined reference to ps2HostProfStart`, `ps2_stubs::sceVibGetProfile`, `ps2_stubs::socom2_RsaGenerateKeyPair`, `ps2_stubs::scePad2GetState`.

- [x] **Step 2: Fix the stack flag**

In `third_party/ps2recomp/ps2xTest/CMakeLists.txt` replace
```cmake
elseif(MINGW)
    target_link_options(ps2x_tests PRIVATE "--stack,8388608")
```
with
```cmake
elseif(MINGW)
    target_link_options(ps2x_tests PRIVATE "-Wl,--stack,8388608")
```

- [x] **Step 3: Add the link-stub translation unit**

Create `third_party/ps2recomp/ps2xTest/src/socom2_link_stubs.cpp`:
```cpp
// The runtime library references a few symbols that the SOCOM II runner defines in
// game_overrides_socom2.cpp (attached to ps2EntryRunner only, see ps2xRuntime/CMakeLists.txt).
// The unit tests never run SOCOM code, so inert definitions satisfy the link.
#include "ps2_runtime.h"
#include "ps2_stubs.h"
#include <cstdint>

void ps2HostProfStart(void *) {}

namespace ps2_stubs
{
    void sceVibGetProfile(uint8_t *, R5900Context *ctx, PS2Runtime *) { ctx->pc = GPR_U32(ctx, 31); }
    void socom2_RsaGenerateKeyPair(uint8_t *, R5900Context *ctx, PS2Runtime *) { ctx->pc = GPR_U32(ctx, 31); }
    void scePad2GetState(uint8_t *, R5900Context *ctx, PS2Runtime *) { ctx->pc = GPR_U32(ctx, 31); }
}
```
If `GPR_U32` is not visible, add `#include "ps2_runtime_macros.h"`. Check each signature against `third_party/ps2recomp/ps2xRuntime/include/ps2_call_list.h` and `game_overrides_socom2.cpp:50,232-376` before building; the parameter list must match exactly or the symbol will not resolve.

In `third_party/ps2recomp/ps2xTest/CMakeLists.txt`, after the `add_executable(ps2x_tests ...)` line (line 94), add:
```cmake
target_sources(ps2x_tests PRIVATE src/socom2_link_stubs.cpp)
```

- [x] **Step 4: Build and run the tests**

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests 2>&1 | tail -3
(cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe; echo "exit=$?")
```
Expected: a `[Passed]`/`[Failed]` list, a Total/Passed/Failed block, `exit=0`. The working directory matters: `code_generator_tests.cpp:1141-1149` reads `../../ps2xRecomp/include/ps2recomp/instructions.h` relative to CWD. If `exit` is non-zero, the failures are pre-existing upstream or fork regressions: record each failing test name in the commit message, then fix the ones caused by fork changes (grep the test name, read the assertion, compare with `git log -p -- <file under test>`); do not delete or skip tests.

- [x] **Step 5: Add the `test` step to `build.sh`**

In `build.sh`, after the `runtime()` function add:
```bash
test_step() {
  cmake --build "$RTBUILD" --target ps2x_tests vu1_replay -j "$(nproc)"
  ( cd "$RTBUILD/ps2xTest" && ./ps2x_tests.exe )
  cp "$RTBUILD/ps2xRuntime/vu1_replay.exe" "$ROOT/dist/vu1_replay.exe"
  echo "tests: ok"
}
```
and in the `case` add `test)    test_step ;;` before `all)`. (`set -euo pipefail` at the top makes a non-zero test exit abort the script.) Task 2 appends the fixture verification to this function.

- [x] **Step 6: Run and commit**

```bash
scripts/loop_lock.sh take hygiene && ./build.sh test; echo "exit=$?"; scripts/loop_lock.sh release hygiene
git add build.sh third_party/ps2recomp/ps2xTest/CMakeLists.txt third_party/ps2recomp/ps2xTest/src/socom2_link_stubs.cpp
git commit -m "test: ps2x_tests links and runs under llvm-mingw (-Wl,--stack; SOCOM runner link stubs); ./build.sh test"
git push
```
Expected: `exit=0`.

---

### Task 2: `vu1_replay --verify` and committed title-screen fixtures

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (arg parse at 150-176, `printState` at 99-131, batch loop at 300-360)
- Create: `tests/fixtures/vu1/title/vu1_prog_*.bin` (12 files), `tests/fixtures/vu1/title/golden.txt`
- Modify: `build.sh` (`test_step`)

**Interfaces:**
- Consumes: dump format (`vu1_replay.cpp:8-11`: 16-byte header `startPc, top, itop, codeSize`, 16 KB code, 16 KB data, `int32 vi[16]`, `float vf[32][4]`); `VU1Interpreter::execute(...)`; `memory.setGifPacketCallback`.
- Produces: `vu1_replay --verify <golden.txt> [--regs all|none] [--native] <dump>...` → prints `OK <name>` / `MISMATCH <name> <field> golden=<v> got=<v>` per dump, exit 0 iff all OK. `--native` sets `PS2X_VU1_NATIVE=1` before the first run (Task 6 reads it).

- [x] **Step 1: Pick and commit the fixtures**

```bash
mkdir -p tests/fixtures/vu1/title
for n in 0 12 24 36 48 60 72 84 96 108 120 132; do cp logs/vu1dump_title/vu1_prog_$n.bin tests/fixtures/vu1/title/; done
ls -la tests/fixtures/vu1/title | wc -l   # expect 14 lines (., .., 12 files)
```
Each dump is 33,360 bytes; the set is ~385 KB. `logs/vu1dump_title` holds 150 dumps of the title screen, all entry pc 0, image FNV `d418194495c25213`, alternating `top` 424/724 (verified 2026-09-10). If `logs/vu1dump_title` is missing, regenerate it: `mkdir -p logs/vu1dump_title` then a title run with `PS2X_VU1_DUMP=logs/vu1dump_title:150 PS2X_VU1_DUMP_AFTER=60` through `drive.py --script scripts/parity/title_only.txt` (lock required).

- [x] **Step 2: Refactor `printState` into a string builder**

In `vu1_replay.cpp` replace `void printState(FILE *out, ...)` with a function that returns the line, and a thin wrapper that prints it:
```cpp
    std::string stateLine(const char *name, const VU1Interpreter &vu, uint32_t packetCount,
                          const std::vector<uint8_t> &packets, uint64_t cycles, const std::vector<uint8_t> &data)
    {
        const VU1State &s = vu.m_state;
        std::string out;
        char buf[128];
        auto add = [&](const char *fmt, auto... args) { std::snprintf(buf, sizeof(buf), fmt, args...); out += buf; };
        add("%s packets=%u bytes=%zu hash=%016llx cycles=%llu endpc=0x%x", name, packetCount, packets.size(),
            (unsigned long long)fnv1a(packets.data(), packets.size()), (unsigned long long)cycles, s.pc);
        add(" mac=%03x status=%03x clip=%06x r=%08x", s.mac, s.status, s.clip, s.r);
        uint32_t w = 0;
        std::memcpy(&w, &s.q, 4); add(" q=%08x", w);
        std::memcpy(&w, &s.p, 4); add(" p=%08x", w);
        std::memcpy(&w, &s.i, 4); add(" i=%08x", w);
        out += " vi=";
        for (int r = 0; r < 16; ++r) add("%s%04x", r ? "," : "", (unsigned)(s.vi[r] & 0xFFFF));
        out += " acc=";
        for (int c = 0; c < 4; ++c) { std::memcpy(&w, &s.acc[c], 4); add("%s%08x", c ? "," : "", w); }
        out += " vf=";
        for (int r = 0; r < 32; ++r)
            for (int c = 0; c < 4; ++c) { std::memcpy(&w, &s.vf[r][c], 4); add("%s%08x", (r || c) ? "," : "", w); }
        add(" data=%016llx\n", (unsigned long long)fnv1a(data.data(), data.size()));
        return out;
    }

    void printState(FILE *out, const char *name, const VU1Interpreter &vu, uint32_t packetCount,
                    const std::vector<uint8_t> &packets, uint64_t cycles, const std::vector<uint8_t> &data)
    {
        const std::string line = stateLine(name, vu, packetCount, packets, cycles, data);
        std::fputs(line.c_str(), out);
    }
```
Build `vu1_replay` and confirm `--batch` output of one dump is byte-identical to before:
```bash
cmake --build third_party/ps2recomp/build-clang --target vu1_replay | tail -1
mkdir -p logs/vu1golden/t_before logs/vu1golden/t_after
git stash -q -- third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp   # only if you want a true before/after; otherwise use logs/vu1golden/d4/state.txt as "before"
third_party/ps2recomp/build-clang/ps2xRuntime/vu1_replay.exe --batch logs/vu1golden/t_after tests/fixtures/vu1/title/*.bin
head -c 200 logs/vu1golden/t_after/state.txt
```
Expected: one line per dump beginning `vu1_prog_0 packets=`.

- [x] **Step 3: Add the golden-comparison helpers**

Add to the anonymous namespace in `vu1_replay.cpp`:
```cpp
    // "name k=v k=v ..." -> map; the first token is the dump name.
    std::map<std::string, std::string> parseStateLine(const std::string &line, std::string &name)
    {
        std::map<std::string, std::string> kv;
        std::istringstream in(line);
        in >> name;
        std::string tok;
        while (in >> tok)
        {
            const size_t eq = tok.find('=');
            if (eq != std::string::npos)
                kv[tok.substr(0, eq)] = tok.substr(eq + 1);
        }
        return kv;
    }

    std::map<std::string, std::map<std::string, std::string>> loadGolden(const char *path)
    {
        std::map<std::string, std::map<std::string, std::string>> golden;
        std::ifstream in(path);
        std::string line, name;
        while (std::getline(in, line))
        {
            if (line.empty()) continue;
            auto kv = parseStateLine(line, name);
            golden[name] = std::move(kv);
        }
        return golden;
    }

    // Returns the number of mismatching fields; prints one MISMATCH line per field.
    int compareState(const std::string &name, const std::map<std::string, std::string> &golden,
                     const std::map<std::string, std::string> &got, bool regs)
    {
        std::vector<const char *> fields = {"packets", "bytes", "hash", "endpc", "data"};
        if (regs)
            for (const char *f : {"vi", "vf", "acc", "q", "p", "i", "mac", "status", "clip", "r"})
                fields.push_back(f);
        int bad = 0;
        for (const char *f : fields)
        {
            const auto g = golden.find(f), o = got.find(f);
            const std::string gv = g == golden.end() ? "<missing>" : g->second;
            const std::string ov = o == got.end() ? "<missing>" : o->second;
            if (gv != ov)
            {
                ++bad;
                std::printf("MISMATCH %s %s golden=%s got=%s\n", name.c_str(), f, gv.c_str(), ov.c_str());
            }
        }
        return bad;
    }
```
Add `#include <map>`, `#include <sstream>`, `#include <fstream>` at the top if absent. `cycles` is deliberately excluded: a native program does not count VU cycles.

- [x] **Step 4: Wire the flags and the verify loop**

In the argument loop add:
```cpp
        else if (!std::strcmp(argv[i], "--verify") && i + 1 < argc)
            verifyPath = argv[++i];
        else if (!std::strcmp(argv[i], "--regs") && i + 1 < argc)
            verifyRegs = std::strcmp(argv[++i], "none") != 0;
        else if (!std::strcmp(argv[i], "--native"))
            _putenv("PS2X_VU1_NATIVE=1");
```
with `std::string verifyPath; bool verifyRegs = true;` declared next to `batchDir`. Update the usage text to list `--verify <golden.txt> [--regs all|none] [--native]`.

After the `--gen` guard (`if (!genPath.empty() || !pcHistPath.empty())`) add:
```cpp
    std::map<std::string, std::map<std::string, std::string>> golden;
    int mismatches = 0;
    if (!verifyPath.empty())
    {
        golden = loadGolden(verifyPath.c_str());
        if (golden.empty())
        {
            std::fprintf(stderr, "--verify: no lines read from %s\n", verifyPath.c_str());
            return 2;
        }
    }
```
In the batch loop, where the code branches on `batchDir.empty()`, add a verify branch first:
```cpp
        if (!verifyPath.empty())
        {
            const std::string base = baseName(input);
            std::string gotName;
            auto got = parseStateLine(stateLine(base.c_str(), vu, packetCount, packets, cycles, data), gotName);
            const auto g = golden.find(base);
            if (g == golden.end())
            {
                std::printf("MISMATCH %s <no golden line>\n", base.c_str());
                ++mismatches;
            }
            else
            {
                const int bad = compareState(base, g->second, got, verifyRegs);
                mismatches += bad;
                if (bad == 0) std::printf("OK %s\n", base.c_str());
            }
            continue;
        }
```
And at the end of `main`, before the final `return 0;`:
```cpp
    if (!verifyPath.empty())
    {
        std::printf("%s: %d mismatching field(s)\n", mismatches ? "FAIL" : "PASS", mismatches);
        return mismatches ? 1 : 0;
    }
```

- [x] **Step 5: Produce the golden with the exact interpreter and verify**

```bash
cmake --build third_party/ps2recomp/build-clang --target vu1_replay | tail -1
cp third_party/ps2recomp/build-clang/ps2xRuntime/vu1_replay.exe dist/vu1_replay.exe
mkdir -p logs/vu1golden/title_exact
PS2X_VU1_FAST=0 PS2X_VU1_GEN=0 dist/vu1_replay.exe --batch logs/vu1golden/title_exact tests/fixtures/vu1/title/*.bin
cp logs/vu1golden/title_exact/state.txt tests/fixtures/vu1/title/golden.txt
dist/vu1_replay.exe --verify tests/fixtures/vu1/title/golden.txt tests/fixtures/vu1/title/*.bin; echo "exit=$?"
```
Expected: 12 `OK` lines, `PASS: 0 mismatching field(s)`, `exit=0`. This proves the default path (fast + generated) equals the exact interpreter on the fixtures.

Negative check, so the tool is known to fail when it should:
```bash
sed 's/hash=[0-9a-f]\{16\}/hash=0000000000000000/' tests/fixtures/vu1/title/golden.txt > logs/vu1golden/bad_golden.txt
dist/vu1_replay.exe --verify logs/vu1golden/bad_golden.txt tests/fixtures/vu1/title/*.bin | tail -1; echo "exit=$?"
```
Expected: `FAIL: 12 mismatching field(s)`, `exit=1`.

- [x] **Step 6: Add fixture verification to `build.sh test` and commit**

In `test_step()` in `build.sh`, before `echo "tests: ok"`:
```bash
  "$ROOT/dist/vu1_replay.exe" --verify "$ROOT/tests/fixtures/vu1/title/golden.txt" "$ROOT"/tests/fixtures/vu1/title/*.bin
```
Then:
```bash
scripts/loop_lock.sh take hygiene && ./build.sh test; echo "exit=$?"; scripts/loop_lock.sh release hygiene
git add build.sh third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp tests/fixtures/vu1/title
git commit -m "test(vu1): vu1_replay --verify against a golden state file; 12 title-screen dumps + exact-interpreter golden committed as fixtures; run by ./build.sh test"
git push
```

---

### Task 3: The `gate` command

**Files:**
- Create: `tools_py/parity/gate.py`
- Create: `tools_py/tests/__init__.py` (empty), `tools_py/tests/test_gate.py`

**Interfaces:**
- Consumes: `tools_py/parity/drive.py` CLI (`--target ours --script <txt> --out <dir> --seconds N --tail N`; prints one line per step and `untilref(...): N presses, matched=True|False`), `tools_py/parity/compare.py:score(golden_path, ours_path) -> (score, mad, block)` (check the exact return shape at `compare.py:19` before use and adapt `title_scores` below), `tools_py/parity/black_rows.py` (exit 1 on a non-black band), `scripts/loop_lock.sh`.
- Produces: `python -m tools_py.parity.gate [--only title,transition,mission] [--owner gate] [--stamp S]` → per gate one line `PASS title (17/23 menu captures >= 90.0)` or `FAIL ...`, a summary, exit 1 on any FAIL. Also `--score-title <run_dir>` and `--score-mission <drive_log>` to re-score existing runs without a game (used by the unit test and for threshold calibration).

- [x] **Step 1: Write the failing unit test against stored runs**

Create `tools_py/tests/__init__.py` (empty) and `tools_py/tests/test_gate.py`:
```python
import os
import unittest

from tools_py.parity import gate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOOD_TITLE_RUN = os.path.join(ROOT, "logs", "parity", "runs", "vr_title")          # known clean (STATUS 2026-09-10 17:40)
GOOD_MISSION_LOG = os.path.join(ROOT, "logs", "parity", "gameplay_probe5.log")     # known reached HUD (STATUS 2026-09-09 13:30)


@unittest.skipUnless(os.path.isdir(GOOD_TITLE_RUN), "needs logs/parity/runs/vr_title")
class TitleScoring(unittest.TestCase):
    def test_known_clean_run_passes(self):
        ok, detail = gate.score_title(GOOD_TITLE_RUN)
        self.assertTrue(ok, detail)

    def test_empty_dir_fails(self):
        ok, detail = gate.score_title(os.path.join(ROOT, "logs"))
        self.assertFalse(ok)


@unittest.skipUnless(os.path.isfile(GOOD_MISSION_LOG), "needs logs/parity/gameplay_probe5.log")
class MissionScoring(unittest.TestCase):
    def test_known_good_log_passes(self):
        ok, detail = gate.score_mission_log(GOOD_MISSION_LOG)
        self.assertTrue(ok, detail)

    def test_missing_hud_fails(self):
        ok, detail = gate.score_mission_log(os.path.join(ROOT, "README.md"))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
```
Check the two "known good" paths exist (`ls logs/parity/runs/vr_title | head`, `ls logs/parity/*.log`). If the mission drive log has a different name, use the newest `logs/parity/vr_gameplay.drive.log` from a run STATUS calls a pass, and note that the drive *log* (drive.py stdout) is what carries `matched=True`, not the game's `run_*.log`.

- [x] **Step 2: Run it to verify it fails**

Run: `python -m unittest tools_py.tests.test_gate -v`
Expected: `ImportError: cannot import name 'gate'` (or ModuleNotFoundError).

- [x] **Step 3: Write `gate.py`**

Create `tools_py/parity/gate.py`:
```python
"""One command for the three screenshot gates. PASS/FAIL per gate, exit 1 on any FAIL.

  python -m tools_py.parity.gate                     # all three (title ~3 min, transition ~3 min, mission ~11 min)
  python -m tools_py.parity.gate --only title,mission
  python -m tools_py.parity.gate --score-title logs/parity/runs/vr_title     # re-score, no game run
  python -m tools_py.parity.gate --score-mission logs/parity/vr_gameplay.drive.log

Runs go to logs/parity/gate/<stamp>/<gate>/ with the drive log beside them and a summary.txt.
Must be run from the repo root (drive.py uses relative paths). Takes scripts/loop_lock.sh.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

from tools_py.parity import compare

TITLE_REF = os.path.join("scripts", "parity", "ref_main_menu_ours.png")
TITLE_MIN_SCORE = 90.0      # compare.score of a capture vs the main-menu reference
TITLE_MIN_MATCHES = 16      # of the 23 captures s00..s22 (20 are at the menu on a clean run, then the attract movie)
HUD_REF_NAME = "ref_hud_ours.png"

GATES = {
    "title": dict(script="scripts/parity/title_menu.txt", seconds=170, tail=8),
    "transition": dict(script="scripts/parity/transition_probe.txt", seconds=170, tail=8),
    "mission": dict(script="scripts/parity/gameplay_probe.txt", seconds=480, tail=170),
}


def _score_value(golden, ours):
    """compare.score may return a float or a (score, mad, block) tuple; normalise to float."""
    r = compare.score(golden, ours)
    return float(r[0] if isinstance(r, (tuple, list)) else r)


def score_title(run_dir):
    caps = sorted(p for p in glob.glob(os.path.join(run_dir, "s[0-9][0-9]_*.png")) if "burst" not in p)
    if not caps:
        return False, "no captures in %s" % run_dir
    scores = [(os.path.basename(p), _score_value(TITLE_REF, p)) for p in caps]
    good = sum(1 for _, s in scores if s >= TITLE_MIN_SCORE)
    detail = "%d/%d menu captures >= %.1f; scores: %s" % (
        good, len(scores), TITLE_MIN_SCORE, " ".join("%s=%.1f" % (n[:3], s) for n, s in scores))
    return good >= TITLE_MIN_MATCHES, detail


def score_transition(run_dir):
    r = subprocess.run([sys.executable, "tools_py/parity/black_rows.py", run_dir], capture_output=True, text=True)
    bad = [ln for ln in r.stdout.splitlines() if "NOT BLACK" in ln]
    return r.returncode == 0, ("rows 396-447 black on every black-screen frame" if r.returncode == 0
                               else "non-black band: " + "; ".join(bad[:5]))


def score_mission_log(drive_log):
    try:
        text = open(drive_log, encoding="utf-8", errors="replace").read()
    except OSError as e:
        return False, str(e)
    m = re.search(r"untilref\([^)]*%s[^)]*\):.*matched=(True|False)" % re.escape(HUD_REF_NAME), text)
    if not m:
        return False, "no HUD untilref result in %s" % drive_log
    if m.group(1) != "True":
        return False, "HUD never matched (mission not reached)"
    holds = len(re.findall(r"^s\d\d_hold", text, re.M))
    return holds >= 3, "HUD reached; %d hold steps captured" % holds


def _lock(cmd, owner):
    return subprocess.run(["bash", "scripts/loop_lock.sh", cmd, owner], capture_output=True, text=True)


def run_gate(name, out_root):
    cfg = GATES[name]
    out_dir = os.path.join(out_root, name)
    os.makedirs(out_dir, exist_ok=True)
    for p in glob.glob(os.path.join("logs", "parity", "latest_frame.png*")):
        os.remove(p)
    drive_log = os.path.join(out_root, name + ".drive.log")
    with open(drive_log, "w", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-m", "tools_py.parity.drive", "--target", "ours",
                        "--script", cfg["script"], "--out", out_dir,
                        "--seconds", str(cfg["seconds"]), "--tail", str(cfg["tail"])],
                       stdout=log, stderr=subprocess.STDOUT)
    newest = sorted(glob.glob(os.path.join("logs", "run_*.log")), key=os.path.getmtime)
    if newest:
        subprocess.run(["cp", newest[-1], os.path.join(out_root, name + ".game.log")])
    subprocess.run([sys.executable, "-m", "tools_py.parity.montage", out_dir,
                    os.path.join(out_root, name + "_sheet.png")], capture_output=True)
    if name == "title":
        return score_title(out_dir)
    if name == "transition":
        return score_transition(out_dir)
    return score_mission_log(drive_log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="title,transition,mission")
    ap.add_argument("--owner", default="gate")
    ap.add_argument("--stamp", default=time.strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--score-title")
    ap.add_argument("--score-mission")
    args = ap.parse_args()

    if args.score_title:
        ok, detail = score_title(args.score_title)
        print("%s title (%s)" % ("PASS" if ok else "FAIL", detail))
        return 0 if ok else 1
    if args.score_mission:
        ok, detail = score_mission_log(args.score_mission)
        print("%s mission (%s)" % ("PASS" if ok else "FAIL", detail))
        return 0 if ok else 1

    take = _lock("take", args.owner)
    if take.returncode != 0:
        print("gate: lock busy: " + take.stdout.strip())
        return 2
    out_root = os.path.join("logs", "parity", "gate", args.stamp)
    os.makedirs(out_root, exist_ok=True)
    results = []
    try:
        for name in [g.strip() for g in args.only.split(",") if g.strip()]:
            ok, detail = run_gate(name, out_root)
            line = "%s %s (%s)" % ("PASS" if ok else "FAIL", name, detail)
            print(line, flush=True)
            results.append((ok, line))
    finally:
        _lock("release", args.owner)
    with open(os.path.join(out_root, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(line for _, line in results) + "\n")
    failed = [line for ok, line in results if not ok]
    print("GATE %s (%d/%d) -> %s" % ("FAIL" if failed else "PASS", len(results) - len(failed), len(results), out_root))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 4: Calibrate the title threshold on the stored clean run**

```bash
python -m tools_py.parity.gate --score-title logs/parity/runs/vr_title
```
Read the per-capture scores. On a clean run the 20 menu captures should score well above 90 and the last two or three (attract cinematic) well below. If the menu captures score in the 80s (the reference was captured on an older renderer state), set `TITLE_MIN_SCORE` to five points under the lowest menu capture and `TITLE_MIN_MATCHES` to two under the count of menu captures, and record both numbers and the run they came from in a comment next to the constants. Then, as a negative control, score a directory that is not a title run (any mission run under `logs/parity/runs/`) and confirm FAIL.

- [x] **Step 5: Run the unit test to verify it passes**

Run: `python -m unittest tools_py.tests.test_gate -v`
Expected: 4 tests, `OK`.

- [x] **Step 6: Run the full gate once on the current build**

Detached, because it takes ~17 minutes (Global Constraints). Write `logs/run_gate_first.sh`:
```bash
#!/usr/bin/env bash
cd /c/projects/socom_pc
python -m tools_py.parity.gate --stamp first > logs/parity/gate_first.out 2>&1
echo done > logs/parity/gate_first.done
```
Start it from PowerShell: `Start-Process bash.exe -ArgumentList "logs/run_gate_first.sh"`, poll `logs/parity/gate_first.done`, then `cat logs/parity/gate_first.out`.
Expected: three PASS lines and `GATE PASS (3/3)`. If the mission gate FAILs on the controller-configuration prompt drift (STATUS 2026-09-10 17:40), that is a known probe issue; re-run once. If a gate fails for a real reason, that is a pre-existing regression: record it in STATUS and fix it before Task 4 declares the gate mandatory.

- [x] **Step 7: Commit**

```bash
git add tools_py/parity/gate.py tools_py/tests/__init__.py tools_py/tests/test_gate.py
git commit -m "parity: gate command (title/transition/mission) with numeric PASS/FAIL and exit code; unit-tested scorers on stored runs"
git push
```

---

### Task 4: Freeze rules, gate requirement, readable current state

**Files:**
- Modify: `docs/LOOP_PROMPT.md`, `docs/HANDOFF.md`, `docs/STATUS.md`, `README.md`

**Interfaces:**
- Consumes: `./build.sh test` (Task 1-2), `python -m tools_py.parity.gate` (Task 3).
- Produces: the rules every later task and every loop firing follows.

- [x] **Step 1: Rewrite the goals block of `docs/LOOP_PROMPT.md`**

Replace the "Ordered goals" list (lines 3-12) with:
```markdown
Ordered goals (user, 2026-09-10, Sprint 1 — see
docs/archive/sprints-1-6/2026-09-10-sprint-1-hygiene-and-native-render-design.md and the plan in
docs/archive/sprints-1-6/2026-09-10-sprint-1-hygiene-and-native-render.md):

1. Hygiene: `./build.sh test` green, `python -m tools_py.parity.gate` green. Both are REQUIRED
   before any commit that touches third_party/ps2recomp/ or recomp/. A red gate is fixed first.
2. FROZEN: emulator speed work (VU1/VU0 interpreter, scheduler batching, GS/GL caching or upload
   performance). 36-42 fps single instance is enough for this sprint. The two-instance frame
   rate is a test-rig concern: run the second client of the acceptance test in PCSX2.
3. Native render path: the entry-0 (2D/UI) VU1 program hand-written in
   third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/, verified with
   `dist/vu1_replay.exe --verify --native` on tests/fixtures/vu1/title and by the title gate.
4. The first-kill acceptance test (tools_py/parity/online_match_ours.py) continues unchanged.
Long term: N64-recomp model — game logic stays recompiled, renderer/audio/input/network native.
```
And in "Every firing" step 3, after "commit ->", insert "`./build.sh test` and `gate` green ->".

- [x] **Step 2: Put a five-line "Current state" at the top of `docs/STATUS.md`**

Insert before the first dated entry:
```markdown
## Current state (keep to five lines; update when it changes, dated entries below are the log)
- Build: `./build.sh all`; tests `./build.sh test` (ps2x_tests + vu1 fixture verify); gates `python -m tools_py.parity.gate`.
- Plays: title/menus 59 fps, Albania 5-1 at 36-42 fps, two-instance online match reaches gameplay on local Horizon.
- Sprint 1 (2026-09-10 →): hygiene done up to Task N of docs/archive/sprints-1-6/2026-09-10-sprint-1-hygiene-and-native-render.md; emulator speed work frozen.
- Native VU1: entry-0 program status: <not started | hands back N of 12 fixtures | 12/12 native, gate green>.
- Open user reports: black 16x16 squares on the intro movie (goal-3 item, not a gate).
```

- [x] **Step 3: Collapse HANDOFF's stacked START HERE sections**

In `docs/HANDOFF.md`, replace the three "START HERE" headers and their state blocks with a single "START HERE" that says: read STATUS "Current state", then the sprint plan, then the run recipes below. Keep the run recipes, gotchas and the "Previous pick-up" material under a "Reference: run recipes and history" header. Do not delete any recipe.

- [x] **Step 4: Commit**

```bash
git add docs/LOOP_PROMPT.md docs/HANDOFF.md docs/STATUS.md
git commit -m "docs: sprint-1 rules — tests+gate required before runtime commits, emulator speed work frozen, STATUS current-state header, single START HERE"
git push
```

---

### Task 5: Characterise entry 0 of the VU1 image on the title screen

**Files:**
- Create: `docs/research/12-vu1-entry0-ui-path.md`

**Interfaces:**
- Consumes: `dist/vu1_replay.exe --pchist <hist.bin> <dumps>` (2048 `uint32` execution counts per instruction pair; `vu1_replay.cpp:163-170`), `python tools_py/vu1dis.py --start <pc> --count <n> <dump.bin>`, the generated C++ `third_party/ps2recomp/ps2xRuntime/src/lib/vu/generated/vu1_d418194495c25213.cpp` (labels `L_0x<pc>`), `docs/research/07-render-pipeline-diagnosis.md:123-127`.
- Produces: the handler list, register roles and hand-back points Task 7 implements; the register set Task 2's `--regs` must compare.

Facts already established (2026-09-10): the whole game runs one VU1 image (FNV `d418194495c25213`); the title screen runs only entry pc 0 (150/150 dumps), `top` alternates 424/724, `itop` 0. The dispatch at pc 0 reads the qword at `top`: `vi1 = top & 0x3ff; vi5 = word1(data[vi1]); vi3 = word3(data[vi1]); vi8 = 2; vi9 = vi5 & 2; if (vi9 == 0) goto 0x118; else { vi2 = 330; vi6 = 423; XGKICK vi6 at 0x50; ... }` (generated code lines 543-617). Research/07 names the UI-quad chain: `0xb20` int→float vertices, `0x1638` backface cull, `0xdf8` transform/divide, `0x5d8` template fill, `0x1440` lighting, `0x1780` build GIF packet + `XGKICK vi2` at `0x1920`, dispatched through a jump table at `0x1ba0` (`JR vi5+884`) over command words.

- [x] **Step 1: Execution histogram over all 150 title dumps**

```bash
mkdir -p logs/vu1entry0
dist/vu1_replay.exe --pchist logs/vu1entry0/title_hist.bin logs/vu1dump_title/*.bin > logs/vu1entry0/title_replay.txt
python - <<'EOF'
import struct
h = struct.unpack('<2048I', open('logs/vu1entry0/title_hist.bin','rb').read())
runs = [(pc*8, n) for pc, n in enumerate(h) if n]
print("executed pairs:", len(runs))
# contiguous ranges = handlers
start = prev = None
for pc, n in runs:
    if prev is None or pc != prev + 8:
        if start is not None: print("0x%04x-0x%04x" % (start, prev))
        start = pc
    prev = pc
print("0x%04x-0x%04x" % (start, prev))
EOF
```
Expected: a list of contiguous pc ranges. Each range is a handler (or the dispatcher). Record them.

- [x] **Step 2: Disassemble each range and name it**

For each range: `python tools_py/vu1dis.py --start 0x<lo> --count <pairs> logs/vu1dump_title/vu1_prog_0.bin`. Read it beside the generated C++ (`L_0x<lo>` in `vu1_d418194495c25213.cpp`, whose `setVi<n>`/`loadWord<k>`/`Vu1Gen::...` calls are easier to read than raw microcode). For each handler write down: inputs (which vi/vf registers and which VU data qwords it reads), outputs (registers, data qwords, XGKICK address), and the command word that selects it. Also decode the command list for one `top=424` dump and one `top=724` dump: dump the qwords the dispatcher reads (`data[top]`, then wherever the jump-table index comes from; research/07 says the list is at qword 340 relative to `vi14`) with:
```bash
python - <<'EOF'
import struct
b = open('logs/vu1dump_title/vu1_prog_0.bin','rb').read()
pc, top, itop, cs = struct.unpack('<4I', b[:16]); data = b[16+16384:16+32768]
vi = struct.unpack('<16i', b[16+32768:16+32768+64])
print("pc", pc, "top", top, "vi", vi)
for q in (top, top+1, top+2, 330, 340, 423):
    print(q, ["%08x" % w for w in struct.unpack('<4I', data[q*16:q*16+16])])
EOF
```

- [x] **Step 3: Live-in and live-out registers**

From the disassembly of the dispatcher (pc 0 to the first `JR`), list every register read before it is written (live-in, e.g. `vi14` if the command pointer comes from it). At every `E`-bit end of the program (search the generated code for `vu.m_state.ebit`/`goto ended` near the ranges found), list the registers the program leaves that the *next* run could read (the same live-in set). This set is what the native program must reproduce exactly; everything else is scratch. Note which vf registers hold constants across runs (the dumps show them: compare `vf` between `vu1_prog_0.bin` and `vu1_prog_12.bin`).

- [x] **Step 4: Write the note**

`docs/research/12-vu1-entry0-ui-path.md` with: (a) the histogram table (range, pairs executed, name, command word, XGKICK site), (b) the register-role table (vi1 = top pointer, vi2 = 330 output base, vi6 = 423 ..., with "[verified]" or "[guess]" per row, following research/11's convention), (c) the data-memory layout on the title screen (header qword at `top`, vertex/colour/uv arrays, matrices, GIF template at 330/423), (d) the live-in/live-out set from Step 3, (e) the hand-back rule: the native program must stop *only* at a dispatcher boundary (before reading the next command word) with all live registers set as the microprogram would have them, and `vu.m_state.pc` = the dispatcher pc.

- [x] **Step 5: Commit**

```bash
git add docs/research/12-vu1-entry0-ui-path.md
git commit -m "research: VU1 entry-0 (2D/UI) path on the title screen — handlers, register roles, data layout, live registers, hand-back rule"
git push
```

---

### Task 6: Native-program registry and the `PS2X_VU1_NATIVE` knob

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/ps2_vu1.h` (near line 70, `KnownProgramFn`)
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp` (dispatch at 2393-2452; stats printing where `g_vu1GenEntered` is reported)
- Create: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/vu1_native_programs.cpp`
- Modify: `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` (line ~380, the `generated/*.cpp` glob)
- Create: `third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp`; modify `ps2xTest/src/main.cpp`, `ps2xTest/CMakeLists.txt`

**Interfaces:**
- Consumes: `typedef bool (*KnownProgramFn)(VU1Interpreter &vu, uint64_t budgetEnd);` (true = program ended; false = hand back with `m_state.pc` set), `m_knownHash` (FNV-1a over the 16 KB image, recomputed on `getVU1CodeGeneration()` change), `m_state.pc`.
- Produces:
```cpp
struct Vu1NativeProgram { uint64_t hash; uint32_t entryPc; VU1Interpreter::KnownProgramFn fn; };
extern const Vu1NativeProgram g_vu1NativePrograms[]; extern const uint32_t g_vu1NativeProgramCount;
// test hook (public on VU1Interpreter):
void setNativeProgramsOverride(const Vu1NativeProgram *table, uint32_t count);   // nullptr,0 restores the built-in table
```
Counters `g_vu1NativeEntered`, `g_vu1NativeEnded`, `g_vu1NativeHandBacks` (`std::atomic<uint64_t>`) printed in the `[vu1-stats]` line. Env `PS2X_VU1_NATIVE` (unset → default `kVu1NativeDefault`, initially `false`).

- [x] **Step 1: Write the failing unit test**

Create `third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp`. It builds a two-instruction synthetic program (NOP/NOP then NOP with E-bit), registers a native function for that image's hash at entry 0 that writes a marker into `vi[10]` and returns true, and checks that with the override installed and the env on, the marker is set; and that a native function returning false with `pc` pointing at the second pair hands back and the interpreter finishes the program.
```cpp
#include "MiniTest.h"
#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"
#include "runtime/ps2_vu1.h"
#include <cstdlib>
#include <cstring>

namespace
{
    struct Fx
    {
        PS2Memory mem; GS gs; uint8_t *code = nullptr; uint8_t *data = nullptr;
        bool init()
        {
            if (!mem.initialize()) return false;
            gs.init(mem.getGSVRAM(), static_cast<uint32_t>(PS2_GS_VRAM_SIZE), &mem.gs());
            code = mem.getVU1Code(); data = mem.getVU1Data();
            std::memset(code, 0, PS2_VU1_CODE_SIZE); std::memset(data, 0, PS2_VU1_DATA_SIZE);
            return true;
        }
    };
    constexpr uint32_t kNopUpper = 0x000002FFu; // NOP (upper)
    constexpr uint32_t kNopLower = 0x8000033Cu; // NOP (lower)
    constexpr uint32_t kEbit = 1u << 30;
    void put(uint8_t *code, uint32_t pc, uint32_t lower, uint32_t upper)
    {
        std::memcpy(code + pc, &lower, 4); std::memcpy(code + pc + 4, &upper, 4);
    }
    uint64_t fnv(const uint8_t *p, size_t n)
    {
        uint64_t h = 1469598103934665603ull;
        for (size_t i = 0; i < n; ++i) { h ^= p[i]; h *= 1099511628211ull; }
        return h;
    }
    bool nativeEnds(VU1Interpreter &vu, uint64_t) { vu.state().vi[10] = 0x1234; return true; }
    bool nativeHandsBack(VU1Interpreter &vu, uint64_t) { vu.state().vi[11] = 0x5678; vu.state().pc = 8u; return false; }
}

void register_vu1_native_tests()
{
    MiniTest::Case("VU1Native", [](TestCase &tc)
    {
        tc.Run("native program for (hash, entry pc) runs instead of the microcode", [](TestCase &t)
        {
            Fx fx; t.IsTrue(fx.init(), "fixture");
            put(fx.code, 0, kNopLower, kNopUpper);
            put(fx.code, 8, kNopLower, kNopUpper | kEbit);
            put(fx.code, 16, kNopLower, kNopUpper);
            fx.mem.markVU1CodeModified();
            const Vu1NativeProgram table[] = {{fnv(fx.code, PS2_VU1_CODE_SIZE), 0u, &nativeEnds}};
            _putenv("PS2X_VU1_NATIVE=1");
            VU1Interpreter vu;
            vu.setNativeProgramsOverride(table, 1u);
            vu.execute(fx.code, PS2_VU1_CODE_SIZE, fx.data, PS2_VU1_DATA_SIZE, fx.gs, &fx.mem, 0u, 0u, 0u, 64u);
            t.Equals(vu.state().vi[10], 0x1234, "native program ran");
            vu.setNativeProgramsOverride(nullptr, 0u);
        });
        tc.Run("hand-back resumes the microcode at the pc the native program set", [](TestCase &t)
        {
            Fx fx; t.IsTrue(fx.init(), "fixture");
            put(fx.code, 0, kNopLower, kNopUpper);
            put(fx.code, 8, kNopLower, kNopUpper | kEbit);
            put(fx.code, 16, kNopLower, kNopUpper);
            fx.mem.markVU1CodeModified();
            const Vu1NativeProgram table[] = {{fnv(fx.code, PS2_VU1_CODE_SIZE), 0u, &nativeHandsBack}};
            _putenv("PS2X_VU1_NATIVE=1");
            VU1Interpreter vu;
            vu.setNativeProgramsOverride(table, 1u);
            vu.execute(fx.code, PS2_VU1_CODE_SIZE, fx.data, PS2_VU1_DATA_SIZE, fx.gs, &fx.mem, 0u, 0u, 0u, 64u);
            t.Equals(vu.state().vi[11], 0x5678, "native ran first");
            t.IsFalse(vu.state().running, "microcode reached the E bit after the hand-back");
            vu.setNativeProgramsOverride(nullptr, 0u);
        });
        tc.Run("a different entry pc is not intercepted", [](TestCase &t)
        {
            Fx fx; t.IsTrue(fx.init(), "fixture");
            put(fx.code, 0, kNopLower, kNopUpper);
            put(fx.code, 8, kNopLower, kNopUpper | kEbit);
            put(fx.code, 16, kNopLower, kNopUpper);
            fx.mem.markVU1CodeModified();
            const Vu1NativeProgram table[] = {{fnv(fx.code, PS2_VU1_CODE_SIZE), 0u, &nativeEnds}};
            _putenv("PS2X_VU1_NATIVE=1");
            VU1Interpreter vu;
            vu.setNativeProgramsOverride(table, 1u);
            vu.execute(fx.code, PS2_VU1_CODE_SIZE, fx.data, PS2_VU1_DATA_SIZE, fx.gs, &fx.mem, 8u, 0u, 0u, 64u);
            t.Equals(vu.state().vi[10], 0, "native program must not run for entry pc 8");
            vu.setNativeProgramsOverride(nullptr, 0u);
        });
    });
}
```
Check three things against the real headers before building: the NOP encodings (take them from the `makeVuUpper`/`makeVuLowerSpecial` helpers in `ps2_vu1_tests.cpp:36-172` if they differ), the name of the "program finished" flag in `VU1State` (`running`, `ended` or similar, `ps2_vu1.h:15-40`), and whether `PS2X_VU1_NATIVE` is read once into a `static const` (then the test must set the env before the first `execute` in the process; put `_putenv` at the top of `register_vu1_native_tests` instead).

Register it: add `void register_vu1_native_tests();` and a call in `ps2xTest/src/main.cpp`; add `src/vu1_native_tests.cpp` to the `ps2_test_lib` source list in `ps2xTest/CMakeLists.txt`.

- [x] **Step 2: Run the test to verify it fails**

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests 2>&1 | grep -E "error" | head -5
```
Expected: compile errors — `Vu1NativeProgram` and `setNativeProgramsOverride` undeclared.

- [x] **Step 3: Declare the registry types and hook**

In `include/runtime/ps2_vu1.h`, after the `KnownProgramFn` typedef (line 70):
```cpp
    // Hand-written host replacement of one microprogram entry point: selected when the 16 KB
    // image hashes to `hash` and the program is entered at `entryPc`. Same contract as
    // KnownProgramFn: true = ended (E bit reached); false = hand back to the microcode at
    // m_state.pc with every live register set as the microcode would have them.
    struct Vu1NativeProgram
    {
        uint64_t hash;
        uint32_t entryPc;
        KnownProgramFn fn;
    };
    void setNativeProgramsOverride(const Vu1NativeProgram *table, uint32_t count);
```
and among the private members:
```cpp
    const Vu1NativeProgram *m_nativeTable = nullptr; // nullptr = built-in table
    uint32_t m_nativeCount = 0;
    KnownProgramFn m_nativeFn = nullptr;   // resolved for (m_knownHash, entry pc) on each run
```
Because `ps2_vu1.h` is a header, this is a 10-minute rebuild; batch it with nothing else.

- [x] **Step 4: The table and the dispatch**

Create `src/lib/vu/native/vu1_native_programs.cpp`:
```cpp
#include "runtime/ps2_vu1.h"

// Registry of hand-written VU1 program replacements (see docs/research/12-vu1-entry0-ui-path.md).
extern const Vu1NativeProgram g_vu1NativePrograms[] = {
    {0ull, 0u, nullptr}, // placeholder so the array is never empty; Task 7 adds socom2 entry 0
};
extern const uint32_t g_vu1NativeProgramCount = 0u;
```
In `ps2_vu1_core.cpp` next to the `g_vu1KnownPrograms` extern declarations (2030-2035):
```cpp
extern const Vu1NativeProgram g_vu1NativePrograms[];
extern const uint32_t g_vu1NativeProgramCount;
std::atomic<uint64_t> g_vu1NativeEntered{0}, g_vu1NativeEnded{0}, g_vu1NativeHandBacks{0};
constexpr bool kVu1NativeDefault = false;

void VU1Interpreter::setNativeProgramsOverride(const Vu1NativeProgram *table, uint32_t count)
{
    m_nativeTable = table; m_nativeCount = count; m_knownGeneration = ~0ull; // force re-resolve
}
```
Inside `run()`, in the `if (m_fast)` block after the known-program resolution (`m_knownHash = hash;`) add the resolution of the native fn, and before the `if (m_knownFn && ...)` call add the native call:
```cpp
        static const bool s_nativeEnv = std::getenv("PS2X_VU1_NATIVE") ? std::atoi(std::getenv("PS2X_VU1_NATIVE")) != 0 : kVu1NativeDefault;
        m_nativeFn = nullptr;
        if (s_nativeEnv)
        {
            const Vu1NativeProgram *tbl = m_nativeTable ? m_nativeTable : g_vu1NativePrograms;
            const uint32_t cnt = m_nativeTable ? m_nativeCount : g_vu1NativeProgramCount;
            for (uint32_t i = 0; i < cnt; ++i)
                if (tbl[i].hash == m_knownHash && tbl[i].entryPc == m_state.pc && tbl[i].fn)
                    m_nativeFn = tbl[i].fn;
        }
        if (m_nativeFn && !m_state.dBitEnabled && !m_state.tBitEnabled && !m_state.ebit &&
            !m_state.haltAfterDelaySlot && !m_state.branchPending)
        {
            ++g_vu1NativeEntered;
            programEnded = m_nativeFn(*this, budgetEnd);
            if (programEnded) ++g_vu1NativeEnded; else ++g_vu1NativeHandBacks;
        }
```
Important: the hash must be computed even when `g_vu1KnownProgramCount == 0` (the test override case) — move the hash computation out from under the `g_vu1KnownProgramCount != 0u` condition so it runs whenever `s_genEnv || s_nativeEnv`. Then the existing generated-code call runs only `if (!programEnded && m_knownFn && ...)`.

Where `[vu1-stats]` prints `gen entered/ended/handbacks`, add `native entered/ended/handbacks` from the three new counters.

In `ps2xRuntime/CMakeLists.txt`, next to the `generated/*.cpp` glob (line ~380), add `file(GLOB PS2X_VU1_NATIVE_SOURCES src/lib/vu/native/*.cpp)` and append it to the `ps2_runtime` sources the same way.

- [x] **Step 5: Run the unit tests and the fixture verify**

```bash
scripts/loop_lock.sh take native && ./build.sh test; echo "exit=$?"
PS2X_VU1_NATIVE=1 dist/vu1_replay.exe --verify tests/fixtures/vu1/title/golden.txt tests/fixtures/vu1/title/*.bin | tail -1
scripts/loop_lock.sh release native
```
Expected: `exit=0` (three new VU1Native tests pass), and `PASS: 0 mismatching field(s)` with the knob on (the table is empty, so nothing changes yet).

- [x] **Step 6: Commit**

```bash
git add third_party/ps2recomp/ps2xRuntime/include/runtime/ps2_vu1.h third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/vu1_native_programs.cpp third_party/ps2recomp/ps2xRuntime/CMakeLists.txt third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp third_party/ps2recomp/ps2xTest/src/main.cpp third_party/ps2recomp/ps2xTest/CMakeLists.txt
git commit -m "vu1: native-program registry keyed by (image hash, entry pc) ahead of the generated-code dispatch; PS2X_VU1_NATIVE knob (default off); unit tests for run/hand-back/entry filtering"
git push
```

---

### Task 7: The native entry-0 program, handler by handler

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_entry0.cpp`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/vu1_native_programs.cpp`

**Interfaces:**
- Consumes: `docs/research/12-vu1-entry0-ui-path.md` (Task 5), `VU1Interpreter` internals via `#define private public` + `#include "../ps2_vu1_ops.h"` exactly as the generated file does (`vu1_d418194495c25213.cpp:3-5`): `vu.m_state.vi[]`, `vu.m_state.vf[][]`, `vu.m_state.top`, `Vu1Gen::dataAddress(addr)` → pointer into VU data memory, `vu.startXgkick(uint32_t qwordAddress)`, the FMAC helpers in `ps2_vu1_ops.h` (add/mul/madd with the VU's flush-to-zero and rounding rules), `vu.m_state.pc`.
- Produces: `bool vu1native_socom2_entry0(VU1Interpreter &vu, uint64_t budgetEnd);` registered as `{0xd418194495c25213ull, 0u, &vu1native_socom2_entry0}`.

The rule for this task: **every step ends with `--verify --native` green on the 12 fixtures**, because an unimplemented command hands back to the generated code, which is already verified. The program becomes "native" one handler at a time, in the order of Task 5's histogram (most-executed first), and the finish line is zero hand-backs.

- [x] **Step 1: Skeleton that hands back immediately**

Create `src/lib/vu/native/socom2_entry0.cpp`:
```cpp
// SOCOM II VU1 image d418194495c25213, entry pc 0: the 2D/UI command interpreter.
// Structure and register roles: docs/research/12-vu1-entry0-ui-path.md. Sprint-1 contract: emit
// exactly the GIF packets the microcode emits (verified by vu1_replay --verify --native).
#define private public
#include "../ps2_vu1_ops.h"
#undef private
#include <atomic>
#include <cstdint>
#include <cstring>

namespace
{
    // Dispatcher pc: the only legal hand-back point (research/12 §e).
    constexpr uint32_t kDispatchPc = 0x0u; // replace with the pc of the command-word read from research/12

    struct Ctx
    {
        VU1Interpreter &vu;
        uint8_t *data;                 // VU1 data memory (16 KB)
        uint32_t top;                  // qword index of the double buffer this run reads
        int32_t &vi(int r) { return vu.m_state.vi[r]; }
        float *vf(int r) { return vu.m_state.vf[r]; }
        const uint32_t *qw(uint32_t q) { return reinterpret_cast<const uint32_t *>(Vu1Gen::dataAddress(q)); }
        uint32_t *qwMut(uint32_t q) { return reinterpret_cast<uint32_t *>(Vu1Gen::dataAddress(q)); }
    };

    // Returns true if the command was handled natively; false = not implemented (hand back).
    bool handleCommand(Ctx &c, uint32_t command)
    {
        switch (command)
        {
        default:
            return false;
        }
    }
}

bool vu1native_socom2_entry0(VU1Interpreter &vu, uint64_t /*budgetEnd*/)
{
    Ctx c{vu, vu.m_activeVuData, vu.m_state.top & 0x3FFu};
    // Sprint-1 step 1: nothing implemented; hand back at the entry so the microcode runs as before.
    vu.m_state.pc = 0u;
    return false;
}
```
Register it in `vu1_native_programs.cpp`:
```cpp
bool vu1native_socom2_entry0(VU1Interpreter &vu, uint64_t budgetEnd);
extern const Vu1NativeProgram g_vu1NativePrograms[] = {
    {0xd418194495c25213ull, 0u, &vu1native_socom2_entry0},
};
extern const uint32_t g_vu1NativeProgramCount = 1u;
```
Check `m_activeVuData` is the member name the interpreter uses for the data pointer during `run()` (`ps2_vu1_core.cpp:1118` uses `m_activeVuData + sourceAddress`); if `Vu1Gen::dataAddress` needs `vu` and `vf` arguments like the generated code's calls, mirror that signature.

Build (`./build.sh runtime`, .cpp only) and verify:
```bash
dist/vu1_replay.exe --verify tests/fixtures/vu1/title/golden.txt --native tests/fixtures/vu1/title/*.bin | tail -1
```
Expected: `PASS: 0 mismatching field(s)`; `[vu1-stats]`-style counters (print them at the end of `vu1_replay` in `--native` mode: `native entered=12 ended=0 handbacks=12`). Commit: `git commit -m "vu1(native): socom2 entry-0 skeleton registered; hands back immediately (verify green)"`.

- [x] **Step 2: Implement the dispatcher natively**

Using research/12 §a-b, implement in `vu1native_socom2_entry0` the loop the microcode runs at pc 0: read the header qword at `top`, evaluate the flag test (`vi9 = word1 & 2`), set the constant registers the dispatcher sets (`vi2 = 330`, `vi6 = 423`, and the others research/12 lists), perform the XGKICK the dispatcher does before the first command (`vu.startXgkick(423)` at `0x50` when the flag path is taken), then loop: read the command word, call `handleCommand`; on `false`, set every live register (research/12 §d) and `vu.m_state.pc = kDispatchPc`, return false. On the end command, set `vu.m_state.pc` to the pc after the E-bit pair as the interpreter would (compare `endpc` in the golden line) and return true.

Verify after this step exactly as in Step 1. The hand-back now happens at the first command instead of at entry, and the golden must still match. If `endpc`, `vi`, or `vf` mismatch on the "end command" path, the dispatcher's register bookkeeping is wrong: diff the `vi=` field of the MISMATCH line against the golden to see which register, then read that register's writes in the generated code between `L_0x0` and the dispatcher's `JR`.

Commit: `git commit -m "vu1(native): entry-0 dispatcher native (header flags, constants, pre-kick); commands still hand back"`.

- [x] **Step 3: One handler per commit, most-executed first**

For each handler in research/12's histogram order:
1. Read its pc range in `vu1dis.py` output and in the generated C++.
2. Write a `static bool cmd_<name>(Ctx &c)` that does the same work with loops over vertices and the `ps2_vu1_ops.h` helpers for every float op (`Vu1Gen::fadd`, `fmul`, `fmadd`, `fdiv`... use whichever names `ps2_vu1_ops.h` defines; do not use raw `+`/`*` on VU floats: the VU flushes denormals and has no NaN/inf, and the interpreter models that).
3. Add its `case` to `handleCommand`.
4. Build; run `--verify --native`; expect PASS and the `handbacks` count to drop. If a MISMATCH names `hash`/`bytes`, the packet differs: dump both packet streams (`vu1_replay <dump> --out a.pk` with and without `--native`) and compare with `python tools_py/gif_packets.py a.pk b.pk` to see the first differing qword. If it names `data`, a data-memory write is missing or misplaced.
5. Commit: `git commit -m "vu1(native): entry-0 <handler name> (0x<lo>-0x<hi>) native; handbacks 12 -> N"`.

The GIF-emitting handler (`0x1780` + `XGKICK vi2` at `0x1920`) is last; it builds the GIFtag + register qwords in data memory from the template at 330 and calls `vu.startXgkick(c.vi(2))`.

- [x] **Step 4: Finish line on the full title dump set**

```bash
PS2X_VU1_FAST=0 PS2X_VU1_GEN=0 dist/vu1_replay.exe --batch logs/vu1golden/title150_exact logs/vu1dump_title/*.bin
dist/vu1_replay.exe --verify --native logs/vu1golden/title150_exact/state.txt logs/vu1dump_title/*.bin | tail -2
```
Expected: `PASS: 0 mismatching field(s)` and `native entered=150 ended=150 handbacks=0`. If the 150-set exposes a command absent from the 12 fixtures, implement it (Step 3) and add one dump that uses it to `tests/fixtures/vu1/title/` plus its golden line.

Then the main menu and lobby: `logs/vu1dump_title` is the title only. Capture 150 dumps at the main menu (`PS2X_VU1_DUMP=logs/vu1dump_menu:150 PS2X_VU1_DUMP_AFTER=<seconds at the menu>` with `scripts/parity/title_menu.txt`, lock required), produce an exact golden, verify native. Same expectation. Do not proceed to gameplay dumps (entries `0x1b50`/`0x33c8`) — Sprint 2.

---

### Task 8: Gate the native program and flip the default

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp` (`kVu1NativeDefault`)
- Modify: `docs/STATUS.md` ("Current state"), `docs/archive/sprints-1-6/2026-09-10-sprint-1-hygiene-and-native-render.md` (tick boxes)

**Interfaces:**
- Consumes: `python -m tools_py.parity.gate` (Task 3), `PS2X_VU1_NATIVE` (Task 6).

- [x] **Step 1: Full gate with the native program on**

Detached (see Task 3 Step 6), with `export PS2X_VU1_NATIVE=1` at the top of the run script and `--stamp native_on`. Expected: `GATE PASS (3/3)`. The title gate is the one that exercises the native code; transition and mission prove no collateral damage (the mission runs the same image at other entry points, which still go through the generated code).

If the title FAILs: the offline verify was green, so the difference is in what the *game* feeds the program versus the dumps (a command or flag combination not in any dump). Capture dumps during the failing run (`PS2X_VU1_DUMP=logs/vu1dump_gatefail:300`), verify them offline, implement what hands back, re-gate.

- [x] **Step 2: Flip the default and re-gate**

Set `constexpr bool kVu1NativeDefault = true;` in `ps2_vu1_core.cpp`, rebuild, run `./build.sh test` (the fixture verify now runs native by default; also run it once with `PS2X_VU1_NATIVE=0` to keep the generated path honest), then the full gate again without the env var, `--stamp native_default`. Expected: both green.

- [x] **Step 3: Update docs and commit**

STATUS "Current state" line 4: `Native VU1: entry-0 program 150/150 title + 150/150 menu dumps native, gate green, default on (PS2X_VU1_NATIVE=0 reverts)`. Tick the plan's boxes. Commit:
```bash
git add third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp docs/STATUS.md docs/archive/sprints-1-6/2026-09-10-sprint-1-hygiene-and-native-render.md
git commit -m "vu1(native): entry-0 program on by default after a green gate (title/transition/mission); PS2X_VU1_NATIVE=0 reverts"
git push
```

---

## Sprint 2 preview (not part of this plan)

With the registry, the golden harness and a native 2D program in place, Sprint 2 adds a public `GS::submitHostBatch(const GSPrimitiveBatch&)` (today the only producer of `GSRasterBackend::Submit` is the private `GS::vertexKick`, `gs_frontend.cpp:1668`) so the native program can hand the GL backend float-precision vertices directly, at host resolution; then entry `0x1b50` (world geometry, the command list `FUN_003b5f20` builds) follows the same handler-by-handler recipe with mission dumps.

---

## Self-review

- **Spec coverage:** §2.1 hygiene → Tasks 1-4 (tests build/run, one gate command, loop rules). §2.2 freeze → Task 4 (rules) and Global Constraints. §2.3 native render → Tasks 5-8 (registry, program, verify, gate, default on). §2.4 acceptance test untouched → no task touches `online_match_ours.py`. §4 definition of done → Task 1-2 (`./build.sh test`), Task 3 (`gate` exit code), Task 4 (LOOP_PROMPT rule, STATUS current state), Task 8 (`PS2X_VU1_NATIVE` default, zero mismatches, title gate).
- **Placeholders:** Task 7 Step 3 necessarily describes a repeated procedure rather than the code of each handler, because the handler set is Task 5's output; every other step carries its code or exact command. `kDispatchPc` in Task 7 Step 1 is explicitly replaced from research/12 in Step 2.
- **Type consistency:** `Vu1NativeProgram{hash, entryPc, fn}` and `setNativeProgramsOverride(table, count)` are identical in Tasks 6 and 7; `vu1native_socom2_entry0` signature matches `KnownProgramFn`; `score_title`/`score_mission_log` names match between `gate.py` and `test_gate.py`; `--verify`/`--regs`/`--native` flags match between Task 2 and Tasks 6-8.
