"""Sprint 13 V7 (#34) -- pause the PEER of a running online round for a while, and record A through it.

#34's closing bar is a round in which the peer stops sending mid-round: then A's `sceInetRecv` with a timeout waits on
a quiet socket, which before V7 held the EE executor for up to 10 s (research/29 shape 2). A harness cannot make a
peer quiet by pressing buttons, so the peer PROCESS is suspended -- every thread stopped, its sockets open and silent,
exactly a console whose owner paused it -- and resumed afterwards:

  * Windows: NtSuspendProcess / NtResumeProcess on a handle opened with PROCESS_SUSPEND_RESUME (what Sysinternals'
    pssuspend does; the tree had no suspend of its own, and pssuspend is not installed on the machine);
  * elsewhere: SIGSTOP / SIGCONT.

The peer is instance B of our two-instance driver (its window title SOCOM-B, online_login_ours.INSTANCES), or the
console: PCSX2 instance B, whose pid pcsx2_ctl records in logs/s4_instances.json when it launches it.

`run` waits until A's round clock (the peeked guest_clock float, tools_py/parity/control_round_readout.peek_clock)
reaches --at-clock seconds, captures A's frame (the runtime's own logs/parity/latest_frame_A.png, which every harness
capture reads) every --every s for --pre-s, suspends the peer (so the suspend lands at about --at-clock + --pre-s of
round clock, 40 s by default) after checking its image is socom2 / pcsx2 and writing the pid to pause.json, keeps
capturing for --pause-s, resumes it (always, first thing in a finally), captures --post-s more, and writes <out>/pause.json: A's run log, the peer's pid, the host times of the
suspend and the resume, A's log SIZE at each (the byte range control_round_readout reads as the pause window -- the
game flushes every sampler line, so the size is where the log stood), the round clock at the suspend, and the frames.

Run: python -m tools_py.parity.peer_pause run --out <round dir> --peer ours|console [--pause-s 30] [--at-clock 30]
     python -m tools_py.parity.peer_pause suspend|resume --pid <n>        (by hand, e.g. after a killed run)
"""
import argparse
import glob
import json
import os
import shutil
import signal
import sys
import time

from tools_py.parity import control_round_readout as R

PROCESS_SUSPEND_RESUME = 0x0800
PEER_TITLE = "SOCOM-B"                                   # online_login_ours.INSTANCES["B"]["PS2X_WINDOW_TITLE"]
PCSX2_STATE = os.path.join("logs", "s4_instances.json")  # pcsx2_ctl.STATE, relative to the repository root
FRAME_A = os.path.join("logs", "parity", "latest_frame_A.png")
TAIL_BYTES = 256 * 1024
# POSIX's numbers (Linux 19 / 18) where the signal module has none (Windows), so the non-Windows branch is testable.
SIGSTOP = getattr(signal, "SIGSTOP", 19)
SIGCONT = getattr(signal, "SIGCONT", 18)


def _nt_call(fn_name, pid):
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(PROCESS_SUSPEND_RESUME, False, int(pid))
    if not h:
        raise OSError("OpenProcess(%d) failed: error %d" % (pid, ctypes.get_last_error()))
    try:
        fn = getattr(ntdll, fn_name)
        fn.argtypes = [ctypes.c_void_p]
        status = fn(ctypes.c_void_p(h)) & 0xFFFFFFFF
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))
    if status != 0:
        raise OSError("%s(%d) returned NTSTATUS %#x" % (fn_name, pid, status))


def suspend(pid, platform=None):
    if (platform or sys.platform) == "win32":
        _nt_call("NtSuspendProcess", pid)
    else:
        os.kill(int(pid), SIGSTOP)


def resume(pid, platform=None):
    if (platform or sys.platform) == "win32":
        _nt_call("NtResumeProcess", pid)
    else:
        os.kill(int(pid), SIGCONT)


PEER_IMAGES = {"ours": ("socom2",), "console": ("pcsx2",)}   # the executable's base name must start with one


def image_name(pid, platform=None):
    """The base name of the process's executable (lower case), or None when it cannot be read."""
    if (platform or sys.platform) == "win32":
        import ctypes
        import ctypes.wintypes as wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        h = k32.OpenProcess(0x1000, False, int(pid))                 # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = wt.DWORD(len(buf))
            if not k32.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(n)):
                return None
            path = buf.value
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    else:
        try:
            with open("/proc/%d/comm" % int(pid), encoding="utf-8") as f:
                path = f.read().strip()
        except OSError:
            return None
    return os.path.basename(path.replace("\\", "/")).lower() or None


def image_matches(peer, image):
    return bool(image) and image.startswith(PEER_IMAGES[peer])


def peer_pid(peer, state_path=PCSX2_STATE, shot=None):
    """The pid to suspend: our instance B by its window title, or PCSX2's B from pcsx2_ctl's state file."""
    if peer == "console":
        with open(state_path, encoding="utf-8") as f:
            d = json.load(f)
        if "B" not in d:
            raise LookupError("no PCSX2 instance B in %s" % state_path)
        return int(d["B"]["pid"])
    if shot is None:
        from tools_py.parity import hostplatform
        shot = hostplatform.shot_module()
    hwnd = shot.find_window(PEER_TITLE)
    if not hwnd:
        raise LookupError("no window titled %s" % PEER_TITLE)
    return int(shot.window_pid(hwnd))


def newest_run_log(tag, after_mtime, pattern=os.path.join("logs", "run_%s_*.log")):
    """The newest logs/run_<tag>_*.log written after `after_mtime` (the round's start marker), or None."""
    cands = [p for p in glob.glob(pattern % tag) if os.path.getmtime(p) >= after_mtime]
    return max(cands, key=os.path.getmtime) if cands else None


def last_round_clock(path, tail=TAIL_BYTES):
    """The last guest round clock float on a [peek] row in the tail of `path`, or None."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        if "[peek] " in line:
            val, _ = R.peek_clock(line)
            if val is not None:
                return val
    return None


class Pauser:
    """The orchestration, with its IO injectable for the tests."""

    def __init__(self, out, peer, pause_s=30.0, at_clock=30.0, pre_s=10.0, post_s=20.0, every_s=2.0,
                 timeout_s=900.0, stop_file=None, frame_src=FRAME_A, mode="after",
                 clock=time.time, sleep=time.sleep, find_log=None, round_clock=last_round_clock,
                 pid_of=None, do_suspend=suspend, do_resume=resume, size_of=os.path.getsize,
                 copy=shutil.copyfile, mtime_of=os.path.getmtime, image_of=image_name):
        self.out, self.peer, self.mode = out, peer, mode
        self.pause_s, self.at_clock, self.pre_s, self.post_s, self.every_s = pause_s, at_clock, pre_s, post_s, every_s
        self.timeout_s, self.stop_file, self.frame_src = timeout_s, stop_file, frame_src
        self.clock, self.sleep, self.round_clock = clock, sleep, round_clock
        self.find_log = find_log or (lambda: newest_run_log("A", self._t0_mtime()))
        self.pid_of = pid_of or (lambda: peer_pid(peer))
        self.do_suspend, self.do_resume, self.size_of, self.copy, self.mtime_of = \
            do_suspend, do_resume, size_of, copy, mtime_of
        self.image_of = image_of
        self.rec = {"peer": peer, "mode": mode, "pause_s": pause_s, "at_clock": at_clock, "every_s": every_s,
                    "a_log": None, "pid": None, "frames": [], "error": None}

    def _t0_mtime(self):
        t0 = os.path.join(self.out, ".t0")
        return os.path.getmtime(t0) if os.path.exists(t0) else 0.0

    def _stopped(self):
        return bool(self.stop_file) and os.path.exists(self.stop_file)

    def write(self):
        os.makedirs(self.out, exist_ok=True)
        with open(os.path.join(self.out, "pause.json"), "w", encoding="utf-8") as f:
            json.dump(self.rec, f, indent=1)

    def capture(self, phase, seconds):
        frames_dir = os.path.join(self.out, "pause_frames")
        os.makedirs(frames_dir, exist_ok=True)
        end = self.clock() + seconds
        while True:
            n = len(self.rec["frames"])
            dst = os.path.join(frames_dir, "A_%03d_%s.png" % (n, phase))
            entry = {"phase": phase, "t": self.clock(), "path": dst, "mtime": None}
            try:
                entry["mtime"] = self.mtime_of(self.frame_src)
                self.copy(self.frame_src, dst)
            except OSError as e:
                entry["path"], entry["error"] = None, str(e)
            self.rec["frames"].append(entry)
            if self.clock() + self.every_s > end:
                return
            self.sleep(self.every_s)

    def wait_round(self):
        t0 = self.clock()
        while True:
            if self.rec["a_log"] is None:
                self.rec["a_log"] = self.find_log()
            val = self.round_clock(self.rec["a_log"]) if self.rec["a_log"] else None
            if val is not None and val >= self.at_clock:
                self.rec["round_clock_at_start"] = val
                return True
            if self._stopped():
                self.rec["error"] = "the driver ended before A's round clock reached %.0f s (last %s)" % (
                    self.at_clock, val)
                return False
            if self.clock() - t0 > self.timeout_s:
                self.rec["error"] = "A's round clock did not reach %.0f s within %.0f s (last %s, log %s)" % (
                    self.at_clock, self.timeout_s, val, self.rec["a_log"])
                return False
            self.sleep(2.0)

    def run(self):
        try:
            if not self.wait_round():
                return self.rec
            self.rec["pid"] = self.pid_of()
            image = self.image_of(self.rec["pid"])
            self.rec["image"] = image
            if not image_matches(self.peer, image):
                raise LookupError("pid %s is %r, not the %s peer's image (%s) -- not suspending it" % (
                    self.rec["pid"], image, self.peer, " or ".join(PEER_IMAGES[self.peer])))
            self.capture("pre", self.pre_s)
            self.rec["a_log_bytes_at_suspend"] = self.size_of(self.rec["a_log"])
            self.rec["round_clock_at_suspend"] = self.round_clock(self.rec["a_log"])
            self.rec["t_suspend"] = self.clock()
            self.rec["suspended"] = True
            self.write()      # the pid is on disk before the suspend: a killed run leaves `peer_pause resume --pid`
            self.do_suspend(self.rec["pid"])
            try:
                self.capture("pause", self.pause_s)
            finally:
                # The resume FIRST: nothing that can fail (the log's size, the clock) may stand before it.
                self.do_resume(self.rec["pid"])
                self.rec["suspended"] = False
                self.rec["t_resume"] = self.clock()
                self.rec["a_log_bytes_at_resume"] = self.size_of(self.rec["a_log"])
            self.capture("post", self.post_s)
            self.rec["round_clock_after"] = self.round_clock(self.rec["a_log"])
        except Exception as e:  # noqa: BLE001 - recorded; the readout reports a round without a pause
            self.rec["error"] = "%s: %s" % (type(e).__name__, e)
        finally:
            self.write()
        return self.rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="pause the peer of a running round and record A through it")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--peer", choices=("ours", "console"), required=True)
    r.add_argument("--pause-s", type=float, default=30.0)
    r.add_argument("--at-clock", type=float, default=30.0)
    r.add_argument("--pre-s", type=float, default=10.0)
    r.add_argument("--post-s", type=float, default=20.0)
    r.add_argument("--every", type=float, default=2.0)
    r.add_argument("--timeout", type=float, default=900.0)
    r.add_argument("--stop-file", default=None, help="stop waiting once this file exists (the driver ended)")
    r.add_argument("--mode", choices=("after", "before"), default="after")
    for name in ("suspend", "resume"):
        s = sub.add_parser(name)
        s.add_argument("--pid", type=int, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "suspend":
        suspend(a.pid)
        return 0
    if a.cmd == "resume":
        resume(a.pid)
        return 0
    rec = Pauser(a.out, a.peer, pause_s=a.pause_s, at_clock=a.at_clock, pre_s=a.pre_s, post_s=a.post_s,
                 every_s=a.every, timeout_s=a.timeout, stop_file=a.stop_file, mode=a.mode).run()
    if rec.get("error"):
        print("PAUSE FAILED %s" % rec["error"], flush=True)
        return 1
    print("PAUSE DONE peer=%s pid=%s %.1fs at round clock %s, A's log bytes %s..%s, %d frames" % (
        rec["peer"], rec["pid"], rec["t_resume"] - rec["t_suspend"], rec.get("round_clock_at_suspend"),
        rec["a_log_bytes_at_suspend"], rec["a_log_bytes_at_resume"], len(rec["frames"])), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
