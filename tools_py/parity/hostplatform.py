"""Which host are we driving the game on -- and the two things the harness does to the OS.

Sprint 8 Goal 1 Task 9. The gate's capture, key and process paths were Windows-only (winshot's
ctypes user32/gdi32, `tasklist`, `taskkill /F /IM x.exe`). The Linux VM is the second verification
ring, so each of those grew a Linux half and every caller asks here which half to use.

Pure and testable: every function takes an optional `system=` override (`platform.system()` by
default) and the process helpers are split into a command builder that returns the argv list and a
thin `run` that does the subprocess -- so both branches are exercised on a Windows host without
launching or killing anything.

The Linux game binary is `socom2`, no `.exe` (spec item 4: "The child is `./socom2`, no `.exe`"),
so callers pass the BASE name everywhere and `exe_name` adds the suffix when there is one.
"""
import os
import platform
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_windows(system=None):
    return (system or platform.system()) == "Windows"


def exe_name(base, system=None):
    """'socom2' -> 'socom2.exe' on Windows, 'socom2' on Linux."""
    return base + ".exe" if is_windows(system) else base


def runtime_exe(system=None):
    """The game binary this host launches, relative to the repo root: the Windows build writes
    `dist/socom2.exe` and the Linux build `dist-linux/socom2` (Sprint 8 Task 1), and the two never
    overwrite each other -- so the gate's drive must ask which one it is looking at."""
    if is_windows(system):
        return os.path.join("dist", "socom2.exe")
    return os.path.join("dist-linux", "socom2")


def free_space_path(system=None):
    """The path whose free space a launch checks before it starts (gate.py's disk refusal). On
    Windows that is the system drive the runs are written to; on Linux the C: drive is not a path,
    so the question is asked of the filesystem the repo itself lives on."""
    if is_windows(system):
        return "C:\\"
    return ROOT


def shot_module(system=None):
    """The window-capture primitive for this host: winshot (ctypes user32/gdi32) on Windows,
    x11shot (xdotool + ImageMagick `import`) on Linux. Imported lazily -- winshot's
    `ctypes.windll` does not exist on Linux, and x11shot must not touch X to be imported."""
    if is_windows(system):
        from tools_py.parity import winshot
        return winshot
    from tools_py.parity import x11shot
    return x11shot


def kill_argv(base, system=None):
    """argv that takes the game down by name. Windows goes through `cmd` because Git Bash mangles
    a bare "/F" (drive.py has carried that note since Sprint 5). Linux matches the process NAME
    exactly (`-x`), the way `taskkill /IM` matches an image name: `-f` matches whole command lines,
    so a concurrent `clang ... game_overrides_socom2.cpp` in the same VM is "socom2 running" (it
    refused the second VM gate run of Task 10) and, worse, `pkill -f` would have killed it."""
    if is_windows(system):
        return ["cmd", "/c", "taskkill /F /IM " + exe_name(base, system)]
    return ["pkill", "-x", base]


def running_argv(base, system=None):
    """argv that lists (Windows) or matches (Linux) the process."""
    if is_windows(system):
        return ["tasklist"]
    return ["pgrep", "-x", base]


def running_from_output(base, stdout, returncode, system=None):
    """Read `running_argv`'s result: `tasklist` prints every process, so look for the image name;
    `pgrep` answers with its exit code."""
    if is_windows(system):
        return exe_name(base, system).lower() in (stdout or "").lower()
    return returncode == 0


def run(argv):
    """The one place the harness shells out for process control."""
    return subprocess.run(argv, capture_output=True, text=True)


def kill_process_by_name(base, system=None):
    """taskkill /F /IM <base>.exe | pkill -f <base>. Best effort: a missing process is not an error."""
    return run(kill_argv(base, system))


def process_running(base, system=None):
    """True when a process of that name is up (the 'already running' guard of every drive)."""
    p = run(running_argv(base, system))
    return running_from_output(base, p.stdout, p.returncode, system)


# ---------------------------------------------------------------------------
# The disc image (Sprint 8 Task 10 follow-up (a)).
#
# The harness resolved the disc by ONE fixed relative path (drive.ISO) while the runtime resolved
# it by its own directory scan (`configureCdImage`, game_overrides_socom2.cpp:551-581: the ELF's
# directory, then its parent, first `*.iso` wins). Two answers to one question: in the VM, where
# the repo's `game/` carries no image, the drive was content and the runtime found nothing, so the
# title stage booted BLACK and was scored as a freeze (docs/KNOWN.md, the falsified AUDIO_DUMP row).
# One resolver, asked before the launch, and the answer exported as PS2X_CD_IMAGE so the runtime
# stops guessing.
ISO_NAME = "SOCOM II - U.S. Navy SEALs (USA).iso"
LINUX_HOME_ISO = "~/socom2.iso"           # where scripts/vm_sync.sh iso puts it in the VM


def iso_candidates(env=None, root=None, system=None):
    """The places a disc image is looked for, in order, as (where, path, consulted) triples.

    `consulted` is False for a place this host does not use -- the VM's `~/socom2.iso` is a Linux
    fallback (`vm_sync.sh iso` writes it there and the VM's repo has no image of its own), and
    consulting it on Windows would be a new way for the daily gate to pick up a stray file. It is
    still reported, so the error names all three places wherever it is raised."""
    env = os.environ if env is None else env
    root = root or ROOT
    return [
        ("SOCOM_ISO", env.get("SOCOM_ISO") or None, True),
        ("the repo's game/", os.path.join(root, "game", ISO_NAME), True),
        (LINUX_HOME_ISO, os.path.expanduser(LINUX_HOME_ISO), not is_windows(system)),
    ]


def iso_path(env=None, root=None, system=None):
    """The disc image this run drives, absolute: $SOCOM_ISO if it is set and exists, else the
    repo's own `game/<ISO_NAME>`, else (Linux only) `~/socom2.iso`. Raises FileNotFoundError
    naming all three places -- a run with no disc must fail at the launch, with the reason, rather
    than boot to a black screen that every scorer then has to interpret."""
    tried = []
    for where, path, consulted in iso_candidates(env, root, system):
        if path is None:
            tried.append("%s (not set)" % where)
            continue
        if not consulted:
            tried.append("%s -> %s (Linux only)" % (where, path))
            continue
        tried.append("%s -> %s" % (where, path))
        if os.path.isfile(path):
            return os.path.abspath(path)
    raise FileNotFoundError("no SOCOM II disc image; looked at: " + "; ".join(tried))
