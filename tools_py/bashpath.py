"""Where `bash` is, for Python that runs the repository's shell scripts (the tests, and the PreToolUse hook).

On Windows a bare "bash" can resolve to WSL's `System32\\bash.exe` -- it does on a GitHub Windows runner, where
Python's PATH puts System32 ahead of Git's `usr/bin`, and every script-driving test then fails with "Windows Subsystem
for Linux has no installed distributions" (Sprint 10 H3's first CI run, 2026-09-21). test_loop_lock.py had its own
finder for the same trap; this is that finder, shared. Git Bash first, by `git --exec-path` and then the usual
install paths; a bare `bash` only when nothing better exists. Moved here from tools_py/tests/shell.py (which
re-exports it) in Sprint 14 G2, so tools_py/hooks/pretool.py does not import the tests package.
"""
import os
import shutil
import subprocess
import sys


def find_bash():
    if sys.platform != "win32":
        return shutil.which("bash")
    if os.environ.get("SOCOM_BASH") and os.path.exists(os.environ["SOCOM_BASH"]):
        return os.environ["SOCOM_BASH"]
    candidates = []
    try:
        exec_path = subprocess.run(["git", "--exec-path"], capture_output=True, text=True, check=True).stdout.strip()
        root = os.path.abspath(os.path.join(exec_path, "..", "..", ".."))       # <git>/mingw64/libexec/git-core
        candidates += [os.path.join(root, "bin", "bash.exe"), os.path.join(root, "usr", "bin", "bash.exe")]
    except (OSError, subprocess.CalledProcessError):
        pass
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", ""),
                 os.environ.get("LOCALAPPDATA", "") + r"\Programs"):
        if base:
            candidates += [os.path.join(base, "Git", "bin", "bash.exe"), os.path.join(base, "Git", "usr", "bin", "bash.exe")]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    found = shutil.which("bash")
    if found and "system32" in found.lower():
        return None                      # WSL's launcher is not a shell the scripts can run in
    return found


BASH = find_bash()
