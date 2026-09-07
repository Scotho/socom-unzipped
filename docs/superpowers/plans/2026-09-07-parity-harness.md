# Parity Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the autonomous loop a per-screen visual parity score against PCSX2 running the same ISO, so sessions grade themselves on "looks like the original", not "navigated further".

**Architecture:** One screen-keyed input script drives both our exe (runtime script runner fed by a SwitchMenu hook) and PCSX2 (Python driver: PINE memory reads for the current dialog, posted key messages for input). Both sides are captured per screen with a focus-free PrintWindow capture; a comparer scores each screen and writes `docs/parity/REPORT.md`.

**Tech Stack:** Python 3.13 (Pillow, numpy, ctypes), PCSX2 2.8.1 with PINE (TCP 28011), the existing C++ runtime (`socom2_host_input.cpp`, `game_overrides_socom2.cpp`).

**Spec:** `docs/superpowers/specs/2026-09-07-parity-harness-design.md`

## Global Constraints
- Never run two game instances at once (our exe or PCSX2); never rebuild while a run is active.
- Do not steal desktop focus or screenshot the desktop; capture windows with PrintWindow only.
- Screenshots (golden and runs) stay under `logs/parity/` and out of git; only `docs/parity/REPORT.md` is committed.
- Git root is `C:\projects`; stage explicit `socom_pc/...` paths, never `git add -A`.
- Runtime-only changes: `./build.sh runtime` (3-10 min). Do not touch `recomp/`.
- Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Python files LF; C++ edits via the Edit tool (heredocs mangle backslashes).

---

### Task 1: Python deps and focus-free window capture

**Files:**
- Create: `tools_py/parity/__init__.py` (empty)
- Create: `tools_py/parity/requirements.txt`
- Create: `tools_py/parity/winshot.py`
- Test: `tools_py/parity/test_winshot.py`

**Interfaces:**
- Produces: `winshot.find_window(title_substring: str) -> int | None` (HWND), `winshot.capture(hwnd: int) -> PIL.Image.Image` (client area, RGB), `winshot.capture_by_title(title_substring, path) -> str` (saves PNG, returns path).

- [ ] **Step 1: Install deps and record them**

```
pip install pillow numpy
```
`tools_py/parity/requirements.txt`:
```
pillow
numpy
```

- [ ] **Step 2: Write the failing test**

```python
# tools_py/parity/test_winshot.py
import threading, time, tkinter as tk
from tools_py.parity import winshot

def test_capture_tk_window():
    root = tk.Tk(); root.title("winshot-test-window"); root.geometry("300x200")
    root.update()
    hwnd = winshot.find_window("winshot-test-window")
    assert hwnd
    img = winshot.capture(hwnd)
    root.destroy()
    assert img.size[0] >= 290 and img.size[1] >= 190
    assert img.getbbox() is not None
```

- [ ] **Step 3: Run it, expect ImportError**

Run from `socom_pc/`: `python -m pytest tools_py/parity/test_winshot.py -q` (install pytest if missing: `pip install pytest`). Expected: FAIL, no module `winshot`.

- [ ] **Step 4: Implement winshot.py**

```python
"""Focus-free capture of a top-level window's client area (PrintWindow, PW_RENDERFULLCONTENT)."""
import ctypes, ctypes.wintypes as wt
from PIL import Image
user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 2

def find_window(title_substring):
    found = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if title_substring.lower() in buf.value.lower():
                    found.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None

def capture(hwnd):
    rect = wt.RECT(); user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetDC(hwnd); mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h); gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT | 1)   # 1 = PW_CLIENTONLY
    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)

def capture_by_title(title_substring, path):
    hwnd = find_window(title_substring)
    if not hwnd:
        raise RuntimeError(f"no window matching '{title_substring}'")
    capture(hwnd).save(path)
    return path
```

- [ ] **Step 5: Run the test, expect PASS** — `python -m pytest tools_py/parity/test_winshot.py -q`

- [ ] **Step 6: Commit** — `git add socom_pc/tools_py/parity` ; message `parity: focus-free window capture (winshot) + deps`.

---

### Task 2: PINE client for PCSX2

**Files:**
- Create: `tools_py/parity/pine.py`
- Test: `tools_py/parity/test_pine.py` (integration; skipped when PCSX2 is not running)

**Interfaces:**
- Produces: `pine.Pine(port=28011)` with `.read8/16/32/64(addr) -> int`, `.write8/32(addr, value)`, `.status() -> int` (0 running, 1 paused, 2 shutdown), `.title() -> str`, `.cstring(addr, max=64) -> str`.
- Protocol: request = `u32 total_len` + `u8 opcode` + args (little-endian); reply = `u32 total_len` + `u8 result (0 ok)` + data. Opcodes: 0 read8, 1 read16, 2 read32, 3 read64, 4 write8, 5 write16, 6 write32, 7 write64, 8 version, 0xB title, 0xF status. TCP `127.0.0.1:port` on Windows.

- [ ] **Step 1: Write the test**

```python
# tools_py/parity/test_pine.py
import socket, pytest
from tools_py.parity.pine import Pine

def pcsx2_up():
    try:
        socket.create_connection(("127.0.0.1", 28011), timeout=0.5).close(); return True
    except OSError:
        return False

@pytest.mark.skipif(not pcsx2_up(), reason="PCSX2 with PINE not running")
def test_status_and_title():
    p = Pine()
    assert p.status() in (0, 1, 2)
    assert "SOCOM" in p.title().upper()
    # ELF header of the loaded game sits at the ELF load address; 0x100000 holds "\x7fELF" for the loader
    assert p.read32(0x00100000) == 0x464c457f
```

- [ ] **Step 2: Implement pine.py**

```python
import socket, struct

class Pine:
    def __init__(self, port=28011, host="127.0.0.1"):
        self.s = socket.create_connection((host, port), timeout=5)
    def _call(self, op, payload=b""):
        msg = struct.pack("<IB", 5 + len(payload), op) + payload
        self.s.sendall(msg)
        hdr = self._recv(5)
        total, res = struct.unpack("<IB", hdr)
        data = self._recv(total - 5) if total > 5 else b""
        if res != 0:
            raise RuntimeError(f"PINE op {op:#x} failed")
        return data
    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("PINE closed")
            buf += chunk
        return buf
    def read8(self, a):  return self._call(0, struct.pack("<I", a))[0]
    def read16(self, a): return struct.unpack("<H", self._call(1, struct.pack("<I", a)))[0]
    def read32(self, a): return struct.unpack("<I", self._call(2, struct.pack("<I", a)))[0]
    def read64(self, a): return struct.unpack("<Q", self._call(3, struct.pack("<I", a)))[0]
    def write8(self, a, v):  self._call(4, struct.pack("<IB", a, v & 0xff))
    def write32(self, a, v): self._call(6, struct.pack("<II", a, v & 0xffffffff))
    def status(self): return struct.unpack("<I", self._call(0xF))[0]
    def title(self):  return self._call(0xB)[:-1].decode("utf-8", "replace")
    def cstring(self, a, max=64):
        out = bytearray()
        for i in range(max):
            b = self.read8(a + i)
            if b == 0: break
            out.append(b)
        return out.decode("ascii", "replace")
```

- [ ] **Step 3: Launch PCSX2 headless and run the test**

Launch (detached, from `socom_pc/`): `start "" tools\pcsx2\pcsx2-qt.exe -batch -nogui -fastboot "<iso path from game/>"` (find the ISO: `ls game/*.iso`). Wait ~20 s, then `python -m pytest tools_py/parity/test_pine.py -q`. Expected: PASS (not skipped). Note the window title PCSX2 uses (`winshot.find_window("PCSX2")`) for later tasks. Leave PCSX2 running for Task 3.

- [ ] **Step 4: Commit** — `parity: PINE client (read/write guest RAM, status, title)`.

---

### Task 3: Spike — key injection into PCSX2 without focus

**Files:**
- Create: `tools_py/parity/pcsx2_keys.py`
- Create: `docs/parity/NOTES.md` (spike result)

**Interfaces:**
- Produces: `pcsx2_keys.press(hwnd, button: str, hold_s=0.1)` mapping PS2 button names (`CROSS, CIRCLE, SQUARE, TRIANGLE, UP, DOWN, LEFT, RIGHT, START, SELECT, L1, R1, L2, R2`) to the `[Pad1]` keys in `tools/pcsx2/inis/PCSX2.ini` (Cross=K, Circle=L, Square=J, Triangle=I, arrows, Return, Backspace, Q, E, 1, 3). Returns True if PCSX2 reacted.

- [ ] **Step 1: Implement posting keys**

```python
import ctypes, time
from ctypes import wintypes as wt
user32 = ctypes.windll.user32
VK = {"UP":0x26,"DOWN":0x28,"LEFT":0x25,"RIGHT":0x27,"CROSS":0x4B,"CIRCLE":0x4C,"SQUARE":0x4A,
      "TRIANGLE":0x49,"START":0x0D,"SELECT":0x08,"L1":0x51,"R1":0x45,"L2":0x31,"R2":0x33}
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101

def target_windows(main_hwnd):
    """The main window plus every child (Qt puts the render surface in a child widget)."""
    out = [main_hwnd]
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _): out.append(h); return True
    user32.EnumChildWindows(main_hwnd, cb, 0)
    return out

def press(main_hwnd, button, hold_s=0.1):
    vk = VK[button.upper()]
    scan = user32.MapVirtualKeyW(vk, 0)
    for h in target_windows(main_hwnd):
        user32.PostMessageW(h, WM_KEYDOWN, vk, (scan << 16) | 1)
    time.sleep(hold_s)
    for h in target_windows(main_hwnd):
        user32.PostMessageW(h, WM_KEYUP, vk, (scan << 16) | 0xC0000001)
```

- [ ] **Step 2: Probe it against the running PCSX2**

With PCSX2 at the first popup (memory-card notice, ~10 s after boot): capture `before.png` with winshot, `press(hwnd, "CROSS")`, wait 2 s, capture `after.png`, compare mean pixel difference (`numpy.abs(a-b).mean()`); a reaction is > 2.0. Also try `SendInput`-free alternative if PostMessage fails: `user32.SendMessageW` to the child with focus (`GetGUIThreadInfo`). Record which worked.

- [ ] **Step 3: Record the outcome in `docs/parity/NOTES.md`**

Either "PostMessage to <child class> works" with the child window class name, or "no reaction; fallback = assisted golden capture (Task 6 fallback path)". If fallback: Task 6's driver only labels and captures; the user plays once.

- [ ] **Step 4: Commit** — `parity: PCSX2 key injection spike (<result>)`.

---

### Task 4: Current-dialog probe address

**Files:**
- Create: `tools_py/parity/addresses.py`
- Create: `tools_py/parity/find_dialog_ptr.py`

**Interfaces:**
- Produces: `addresses.DIALOG_NAME_PTR` (guest address of a pointer to the current dialog record) and `addresses.DIALOG_NAME_OFFSET` (offset of the name C-string inside that record), plus `addresses.current_dialog(read32, cstring) -> str` usable with both a PINE client and a RAM-dump reader.

- [ ] **Step 1: Dump our guest RAM at dlgMenu**

Run (90 s max): `PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT="8:CROSS,12:CROSS,16:CROSS,20:CROSS,24:CROSS" PS2X_CALL_TRACE="0x27e720:SwitchMenu" PS2X_RDRAM_DUMP="logs/parity/menu.rdram:40" ./run.sh 45`. Check the log's `SwitchMenu` lines show the dialog name as a text argument (the tracer prints `aN="..."`). If SwitchMenu's args are not the name, trace `0x27c9f0:SetMenuState` and the ZAR lookup instead and pick the one whose a0 is the name.

- [ ] **Step 2: Find static pointers to the dialog record**

`find_dialog_ptr.py`: load the 32 MB dump; find every occurrence of the bytes `dlgMenu\0`; for each string address S, find every 32-bit word equal to S (a record field holding the name pointer) → record candidates R; for each R find words equal to R located in the static data range `0x400000..0x4c0000` (the shell/state globals). Print `static addr -> record -> name`. Choose the static one; if the record holds the name inline instead, DIALOG_NAME_OFFSET is the inline offset.

- [ ] **Step 3: Verify on PCSX2 over PINE**

With PCSX2 sitting on its main menu (drive it there with `pcsx2_keys.press` or, in fallback mode, by hand once): `python -c "from tools_py.parity import pine, addresses as A; p=pine.Pine(); print(A.current_dialog(p.read32, p.cstring))"` → prints `dlgMenu`.

- [ ] **Step 4: Commit** — `parity: current-dialog probe address (static ptr → record → name)`.

---

### Task 5: Screen-keyed script — parser (Python) and runtime support

**Files:**
- Create: `tools_py/parity/script.py`
- Test: `tools_py/parity/test_script.py`
- Create: `scripts/parity/launch_to_mission.txt`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp` (parseScript, initialise, the poll loop's event firing)
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` (SwitchMenu hook)
- Modify: `third_party/ps2recomp/ps2xRuntime/include/socom2_host_input.h` (declare `socom2InputNotifyDialog`)

**Interfaces:**
- Script line: `<key>+<seconds>:<BTN>[+<BTN>][:<hold>]` where `<key>` is `boot` or `<dialog>[#<n>]`. Comments `#`. Blank lines ignored.
- Produces (Python): `script.parse(text) -> list[Step]` with `Step(key: str, ordinal: int, delay: float, buttons: list[str], hold: float)`.
- Produces (runtime): env `PS2X_SOCOM2_INPUT_SCRIPT_FILE=<path>`; log line `[socom2-ui] dialog=<name> n=<k> t=<sec>` on every SwitchMenu; `void socom2InputNotifyDialog(const char *name)`.

- [ ] **Step 1: Parser test**

```python
from tools_py.parity.script import parse
def test_parse_forms():
    steps = parse("# c\nboot+8:CROSS\ndlgMenu+1.5:CROSS\ndlg_Brief_Alb51#1+2:DOWN+DOWN:0.2\n")
    assert [s.key for s in steps] == ["boot", "dlgMenu", "dlg_Brief_Alb51"]
    assert steps[1].ordinal == 1 and steps[1].delay == 1.5 and steps[1].buttons == ["CROSS"]
    assert steps[2].buttons == ["DOWN", "DOWN"] and steps[2].hold == 0.2
```

- [ ] **Step 2: Implement script.py**

```python
from dataclasses import dataclass
@dataclass
class Step:
    key: str; ordinal: int; delay: float; buttons: list; hold: float = 0.1
def parse(text):
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip() if not raw.strip().startswith("#") else ""
        # allow '#<n>' inside the key: re-split carefully
        if raw.strip().startswith("#") or not raw.strip():
            continue
        line = raw.strip()
        keypart, rest = line.split(":", 1)
        key, delay = keypart.rsplit("+", 1)
        ordinal = 1
        if "#" in key:
            key, o = key.split("#", 1); ordinal = int(o)
        fields = rest.split(":")
        buttons = [b.strip().upper() for b in fields[0].split("+") if b.strip()]
        hold = float(fields[1]) if len(fields) > 1 else 0.1
        out.append(Step(key, ordinal, float(delay), buttons, hold))
    return out
```
(Trailing `# comment` after a step is not supported; comments are whole lines.)

- [ ] **Step 3: Run test, PASS; write the script**

`scripts/parity/launch_to_mission.txt` (from the proven time script, converted; dialog names for the popups come from Step 5's first run log — start with `boot` keys and refine):
```
# first boot popups (memory card notice, warnings) then Sony logo / intro
boot+8:CROSS
boot+12:CROSS
boot+16:CROSS
boot+20:CROSS
boot+24:CROSS
# main menu: NEW GAME is the initial selection
dlgMenu+2:CROSS
dlgSelectRank+2:CROSS
dlgControllerPresetsNewGame+2:CROSS
dlgControllerPresetsRG+2:CROSS
dlgAlbaniaCinematic+3:CROSS
dlg_Brief_Alb51+2:DOWN
dlg_Brief_Alb51+3:DOWN
dlg_Brief_Alb51+4:DOWN
dlg_Brief_Alb51+5:DOWN
dlg_Brief_Alb51+6:DOWN
dlg_Brief_Alb51+8:CROSS
```

- [ ] **Step 4: Runtime — SwitchMenu hook (Edit tool)**

In `game_overrides_socom2.cpp`, next to `installCallTrace`, add:
```cpp
    PS2Runtime::RecompiledFunction g_switchMenuOriginal = nullptr;
    void socom2_SwitchMenuHook(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const std::string name = callTraceGuestString(rdram, GPR_U32(ctx, 4));
        static std::map<std::string, int> counts;
        const int n = ++counts[name];
        const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_callTraceStart).count();
        std::cout << "[socom2-ui] dialog=" << name << " n=" << n << " t=" << std::fixed << std::setprecision(2) << t << std::endl;
        socom2InputNotifyDialog(name.c_str());
        if (g_switchMenuOriginal)
            g_switchMenuOriginal(rdram, ctx, runtime);
    }
```
and in the install function (where `installCallTrace(runtime)` is called), *after* it:
```cpp
        g_switchMenuOriginal = runtime.lookupFunction(0x0027e720u);   // use the same accessor installCallTrace uses to save the original
        runtime.replaceFunction(0x0027e720u, socom2_SwitchMenuHook);
```
If Task 4 found the name in a different function's a0, hook that address instead. Read `installCallTrace` for the accessor that returns the current table entry and reuse it.

- [ ] **Step 5: Runtime — script file + dialog events (Edit tool)**

In `socom2_host_input.cpp`: extend `ScriptEvent` with `std::string key; int ordinal = 1;` (empty key = boot-time event, i.e. the old format). In `parseScript`, if `fields[0]` contains `+`, split at the last `+`: left = key (`boot` → empty, `name#n` → key/ordinal), right = delay. Add a file loader in `initialise()`:
```cpp
            if (const char *file = std::getenv("PS2X_SOCOM2_INPUT_SCRIPT_FILE"))
            {
                std::ifstream in(file);
                std::string line, joined;
                while (std::getline(in, line))
                {
                    const size_t hash = line.find('#');
                    if (!line.empty() && line[0] == '#') continue;
                    if (line.find_first_not_of(" \t\r") == std::string::npos) continue;
                    joined += (joined.empty() ? "" : ",") + line;
                }
                parseScript(joined.c_str());
            }
```
(Note `#` is also the ordinal separator inside a key, so only a `#` at column 0 is a comment.)
Add the dialog event source:
```cpp
    struct DialogSeen { std::string name; int ordinal; std::chrono::steady_clock::time_point at; };
    std::vector<DialogSeen> g_dialogs; std::mutex g_dialogsMutex;
    void socom2InputNotifyDialog(const char *name)
    {
        std::lock_guard<std::mutex> lock(g_dialogsMutex);
        int n = 1;
        for (const DialogSeen &d : g_dialogs) if (d.name == name) ++n;
        g_dialogs.push_back({name, n, std::chrono::steady_clock::now()});
    }
```
In the poll loop where time events fire (`event.at <= elapsed`), compute the reference time: for a keyed event, find `g_dialogs` entry with matching name and ordinal; if none, skip this frame; else `elapsed = now - entry.at`. Fire when `elapsed >= event.at`, same hold logic as today.

- [ ] **Step 6: Build and verify**

`./build.sh runtime` (3-10 min; detached if needed). Then `PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT_FILE=scripts/parity/launch_to_mission.txt ./run.sh 90`. Expected in the log: `[socom2-ui] dialog=dlgMenu n=1`, … `dialog=dlg_Brief_Alb51`, then the `LOAD_SCREEN`/mission registration lines as before. Adjust delays in the script until the whole path runs; if the popups have dialog names in the log, key them by name instead of `boot`.

- [ ] **Step 7: Commit** — `parity: screen-keyed input script (runtime file loader + SwitchMenu dialog events; python parser)`.

---

### Task 6: PCSX2 driver and golden capture

**Files:**
- Create: `tools_py/parity/pcsx2_driver.py`

**Interfaces:**
- Consumes: `pine.Pine`, `addresses.current_dialog`, `pcsx2_keys.press`, `winshot`, `script.parse`.
- Produces: CLI `python -m tools_py.parity.pcsx2_driver --script scripts/parity/launch_to_mission.txt --out logs/parity/golden [--assist]`. Writes `<out>/<dialog>#<n>.png` per screen (captured `settle` seconds after the dialog first appears, default 1.5 s, before any press for that screen) and `<out>/manifest.json` (`{screen: {"t": seconds_since_boot, "file": ...}}`). `--assist` disables key injection (fallback path: the user plays; the driver only labels/captures).

- [ ] **Step 1: Implement**

```python
import argparse, json, os, subprocess, time
from tools_py.parity import pine, addresses, pcsx2_keys, winshot, script

ISO = next(p for p in os.listdir("game") if p.lower().endswith(".iso"))

def launch():
    return subprocess.Popen(["tools/pcsx2/pcsx2-qt.exe", "-batch", "-nogui", "-fastboot", os.path.join("game", ISO)])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--script", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--assist", action="store_true"); ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--timeout", type=float, default=240); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    steps = script.parse(open(a.script).read()); proc = launch(); t0 = time.time()
    for _ in range(60):
        try: p = pine.Pine(); break
        except OSError: time.sleep(1)
    hwnd = None
    while hwnd is None: hwnd = winshot.find_window("PCSX2"); time.sleep(0.5)
    seen, manifest, fired, last = {}, {}, set(), None
    while time.time() - t0 < a.timeout and fired != set(range(len(steps))):
        try: name = addresses.current_dialog(p.read32, p.cstring)
        except Exception: name = None
        now = time.time()
        if name and name != last:
            seen.setdefault(name, []).append(now); last = name
        for i, s in enumerate(steps):
            if i in fired: continue
            if s.key == "boot": ref = t0
            else:
                times = seen.get(s.key, [])
                if len(times) < s.ordinal: continue
                ref = times[s.ordinal - 1]
            key = f"{s.key}#{s.ordinal}"
            if key not in manifest and now - ref >= a.settle:
                path = os.path.join(a.out, key + ".png"); winshot.capture(hwnd).save(path)
                manifest[key] = {"t": ref - t0, "file": path}
            if now - ref >= s.delay:
                if not a.assist:
                    for b in s.buttons: pcsx2_keys.press(hwnd, b, s.hold)
                fired.add(i)
        time.sleep(0.1)
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)
    proc.terminate()

if __name__ == "__main__": main()
```

- [ ] **Step 2: Capture the golden set**

`python -m tools_py.parity.pcsx2_driver --script scripts/parity/launch_to_mission.txt --out logs/parity/golden` (add `--assist` if Task 3 chose the fallback; then the user plays the same path once). Expected: PNGs for dlgMenu#1 … dlg_Brief_Alb51#1 plus the boot screens, `manifest.json` listing them. Eyeball two of them with the Read tool: the real home screen with visible text.

- [ ] **Step 3: Commit** — `parity: PCSX2 driver (dialog-keyed script over PINE, golden capture)`. Golden PNGs stay untracked (`logs/` is ignored; verify with `git status`).

---

### Task 7: Comparer and report

**Files:**
- Create: `tools_py/parity/compare.py`
- Test: `tools_py/parity/test_compare.py`

**Interfaces:**
- Produces: `compare.score(golden: Image, ours: Image) -> dict(score: float, mad: float, block: float)`; `compare.side_by_side(golden, ours) -> Image`; `compare.report(golden_dir, run_dir, out_md, prev_md=None) -> list[dict]` writing `docs/parity/REPORT.md`.

- [ ] **Step 1: Tests**

```python
from PIL import Image, ImageDraw
from tools_py.parity import compare
def logo(x):
    im = Image.new("RGB", (640, 448), (10, 10, 40)); ImageDraw.Draw(im).rectangle([x, 45, x + 200, 120], fill=(230, 230, 230)); return im
def test_identical_is_100():
    assert compare.score(logo(70), logo(70))["score"] == 100
def test_shift_scores_lower():
    assert compare.score(logo(70), logo(300))["score"] < compare.score(logo(70), logo(80))["score"] < 100
```

- [ ] **Step 2: Implement**

```python
import os, json, re
import numpy as np
from PIL import Image
SIZE = (320, 224)
def _arr(im): return np.asarray(im.convert("RGB").resize(SIZE, Image.BOX), dtype=np.float32) / 255.0
def score(golden, ours, block_thresh=0.08):
    g, o = _arr(golden), _arr(ours)
    mad = float(np.abs(g - o).mean())
    gb = g.reshape(14, 16, 20, 16, 3).mean(axis=(1, 3)); ob = o.reshape(14, 16, 20, 16, 3).mean(axis=(1, 3))
    block = float((np.abs(gb - ob).mean(axis=2) > block_thresh).mean())
    return {"score": round(max(0.0, min(100.0, 100 * (1 - 0.5 * mad - 0.5 * block))), 1), "mad": round(mad, 4), "block": round(block, 4)}
def side_by_side(golden, ours):
    g, o = golden.convert("RGB").resize(SIZE), ours.convert("RGB").resize(SIZE)
    d = np.abs(_arr(g) - _arr(o)).mean(axis=2); heat = Image.fromarray((np.clip(d * 4, 0, 1) * 255).astype("uint8")).convert("RGB")
    out = Image.new("RGB", (SIZE[0] * 3, SIZE[1])); out.paste(g, (0, 0)); out.paste(o, (SIZE[0], 0)); out.paste(heat, (SIZE[0] * 2, 0)); return out
def _prev_scores(prev_md):
    if not prev_md or not os.path.exists(prev_md): return {}
    return {m.group(1): float(m.group(2)) for m in re.finditer(r"^\| ([^|]+?) \| ([0-9.]+) \|", open(prev_md).read(), re.M)}
def report(golden_dir, run_dir, out_md, prev_md=None, stamp=""):
    prev = _prev_scores(prev_md); rows = []
    for f in sorted(os.listdir(golden_dir)):
        if not f.endswith(".png"): continue
        name = f[:-4]; ours_p = os.path.join(run_dir, f)
        if not os.path.exists(ours_p):
            rows.append({"screen": name, "score": None, "note": "not reached"}); continue
        g, o = Image.open(os.path.join(golden_dir, f)), Image.open(ours_p)
        s = score(g, o); side_by_side(g, o).save(os.path.join(run_dir, name + ".diff.png"))
        rows.append({"screen": name, **s, "delta": (s["score"] - prev[name]) if name in prev else None, "note": ""})
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w") as w:
        w.write(f"# Parity report {stamp}\n\nGolden: PCSX2 2.8.1, `{golden_dir}`. Run: `{run_dir}`. Score = 100·(1 − 0.5·mad − 0.5·block) at 320x224.\n\n")
        w.write("| screen | score | delta | mad | block | note |\n|---|---|---|---|---|---|\n")
        for r in rows:
            sc = "—" if r["score"] is None else f"{r['score']}"
            dl = "" if r.get("delta") is None else f"{r['delta']:+.1f}"
            w.write(f"| {r['screen']} | {sc} | {dl} | {r.get('mad','')} | {r.get('block','')} | {r['note']} |\n")
    return rows
```

- [ ] **Step 3: Run tests, PASS; commit** — `parity: comparer (mad + block score, side-by-side diff, REPORT.md)`.

---

### Task 8: Our-side runner and end-to-end report

**Files:**
- Create: `tools_py/parity/run_parity.py`

**Interfaces:**
- Consumes: `script.parse`, `winshot`, `compare.report`.
- Produces: CLI `python -m tools_py.parity.run_parity [--script scripts/parity/launch_to_mission.txt] [--seconds 120] [--golden logs/parity/golden]`. Launches `dist/socom2.exe` via `./run.sh` with `PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT_FILE=<script>`, tails the run log for `[socom2-ui] dialog=<name> n=<k>` lines, captures our window (`winshot.find_window("socom2")` — check the actual title from the runner, fall back to the exe's process main window) `settle` seconds after each, into `logs/parity/runs/<stamp>/<name>#<k>.png`; boot screens keyed like the driver (`boot#1..` at the same `t` values as the golden manifest); then `compare.report(...)` to `docs/parity/REPORT.md` with `prev_md` = the previous report; prints the table.

- [ ] **Step 1: Implement**

```python
import argparse, json, os, subprocess, time, re, datetime, shutil
from tools_py.parity import winshot, compare

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--script", default="scripts/parity/launch_to_mission.txt")
    ap.add_argument("--seconds", type=int, default=120); ap.add_argument("--golden", default="logs/parity/golden")
    ap.add_argument("--settle", type=float, default=1.5); a = ap.parse_args()
    for exe in ("socom2.exe", "pcsx2-qt.exe"):
        if exe.lower() in subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower():
            raise SystemExit(f"{exe} is running; refusing to start a second instance")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); run_dir = f"logs/parity/runs/{stamp}"; os.makedirs(run_dir)
    env = dict(os.environ, PS2X_SOCOM2_PAD="1", PS2X_SOCOM2_INPUT_SCRIPT_FILE=a.script)
    proc = subprocess.Popen(["bash", "./run.sh", str(a.seconds)], env=env)
    time.sleep(3); log = "logs/latest.log"
    manifest = json.load(open(os.path.join(a.golden, "manifest.json")))
    boot_keys = {k: v["t"] for k, v in manifest.items() if k.startswith("boot")}
    t0 = time.time(); pending, done = {}, set(); pos = 0
    while proc.poll() is None:
        with open(log, errors="replace") as f:
            f.seek(pos); chunk = f.read(); pos = f.tell()
        for m in re.finditer(r"\[socom2-ui\] dialog=(\S+) n=(\d+)", chunk):
            pending.setdefault(f"{m.group(1)}#{m.group(2)}", time.time())
        for k, t in boot_keys.items():
            pending.setdefault(k, t0 + t)
        for k, t in list(pending.items()):
            if k not in done and time.time() - t >= a.settle:
                hwnd = winshot.find_window("socom2") or winshot.find_window("ps2")
                if hwnd: winshot.capture(hwnd).save(os.path.join(run_dir, k + ".png")); done.add(k)
        time.sleep(0.2)
    out = "docs/parity/REPORT.md"; prev = out + ".prev"
    if os.path.exists(out): shutil.copy(out, prev)
    rows = compare.report(a.golden, run_dir, out, prev_md=prev, stamp=stamp)
    for r in rows: print(r)

if __name__ == "__main__": main()
```
Boot-screen capture on our side keys off the golden manifest's `t` (seconds since PCSX2 boot); since boot pacing differs, the runner also accepts `--boot-offset <s>` added to those times (default 0); tune once by comparing the memory-card popup screenshot.

- [ ] **Step 2: Run end to end**

`python -m tools_py.parity.run_parity --seconds 120`. Expected: `logs/parity/runs/<stamp>/` has one PNG per reached screen plus `.diff.png`, `docs/parity/REPORT.md` has the table. Open two diff images with the Read tool and confirm they show golden | ours | heat.

- [ ] **Step 3: Commit** — `parity: our-side runner + first REPORT.md` (commit `docs/parity/REPORT.md`; nothing under `logs/`).

---

### Task 9: Escalation probe (option 2, minimal)

**Files:**
- Create: `tools_py/parity/probe.py`

**Interfaces:**
- Produces: CLI `python -m tools_py.parity.probe --dump logs/parity/<ours>.rdram --addrs "0x4085d0:16,0x12000080:4"` printing, for each `addr:words`, the words from our dump next to the words read from PCSX2 over PINE at the same screen, marking the first difference. Our dump comes from `PS2X_RDRAM_DUMP_AT="<path>:SwitchMenu#<n>"` (trace name from Task 5's hook is `SwitchMenu`; keep the call-trace name too).

- [ ] **Step 1: Implement**

```python
import argparse, struct
from tools_py.parity import pine
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dump", required=True); ap.add_argument("--addrs", required=True); a = ap.parse_args()
    d = open(a.dump, "rb").read(); p = pine.Pine(); first = None
    for spec in a.addrs.split(","):
        addr, n = spec.split(":"); addr, n = int(addr, 16), int(n)
        for i in range(n):
            at = addr + 4 * i; ours = struct.unpack_from("<I", d, at & 0x1ffffff)[0]; ref = p.read32(at)
            mark = "" if ours == ref else "   <-- differs"
            if mark and first is None: first = at
            print(f"{at:#010x}  ours={ours:#010x}  pcsx2={ref:#010x}{mark}")
    print("first difference:", f"{first:#x}" if first is not None else "none")
if __name__ == "__main__": main()
```

- [ ] **Step 2: Smoke test** on `0x4085d0:8` at dlgMenu on both sides; commit — `parity: memory probe (our dump vs PCSX2 over PINE)`.

---

### Task 10: Docs — grading rule, escalation triggers, loop changes

**Files:**
- Modify: `docs/HANDOFF.md` (top: "The grade", loop section, escalation triggers; task list re-ordered: shell screens by score, then the mission coverage bug)
- Modify: `docs/STATUS.md` (new dated section with the first report table and the harness usage)
- Modify: `docs/superpowers/plans/2026-09-04-implementation-plan.md` (M3 re-opened as "M3-parity: each shell screen ≥ target score"; targets: 90 for static screens, 75 for animated ones)

- [ ] **Step 1: HANDOFF additions**

Under "The vision", add: *"The grade is `docs/parity/REPORT.md`. A session's last act is `python -m tools_py.parity.run_parity`; the next task is the worst screen on the launch → mission path unless a hard blocker (thread death, no frame) stops the path earlier. Regressions in any screen's score are fixed before moving on. Escalate to `probe.py` when the diff image does not explain a low score; to a PCSX2 GS dump only when the same primitives land differently (renderer bug)."* Under "How to work", replace the "one hypothesis → one build → one run" loop's success criterion with the score. Under "Next tasks", put "shell screens by score" first, the 0x510978 escaping-branch merge second, then the mission renderer.

- [ ] **Step 2: STATUS section** with the report table pasted and the three commands (golden capture, run_parity, probe).

- [ ] **Step 3: Commit** — `docs: parity is the grade — HANDOFF loop, escalation triggers, STATUS report`.

---

## Self-review
- Spec coverage: §1 rule → Task 10; §2 script → Task 5; §3 probe address → Task 4; §4 capture → Task 1; §5 injection spike → Task 3; §6 PINE → Task 2; §7 compare/report → Task 7; §8 runner → Task 8; §9 escalation → Task 9 (option 2) + Task 10 (triggers; option 3 is documented, not built). Testing section: Tasks 1, 2, 5, 7 have tests; Task 8 is the end-to-end.
- Names used across tasks: `winshot.find_window/capture`, `pine.Pine.read32/cstring/status/title`, `pcsx2_keys.press`, `addresses.current_dialog(read32, cstring)`, `script.parse -> Step(key, ordinal, delay, buttons, hold)`, `compare.score/side_by_side/report`, log line `[socom2-ui] dialog=<name> n=<k> t=<s>`, env `PS2X_SOCOM2_INPUT_SCRIPT_FILE`.
- Open risk carried in the plan: SwitchMenu's a0 may not be the name (Task 4 step 1 verifies and Task 5 step 4 hooks whichever function is); PostMessage may not reach PCSX2 (Task 3 fallback = assisted capture).
