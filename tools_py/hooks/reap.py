"""The SessionEnd/Stop reaper (Sprint 14 G3): kill orphaned watcher processes, never a shell.

On 2026-09-25 the host carried 213 orphaned `tail`/`grep` watchers left by dead monitors (the oldest from 09-17) and
every bash start took seconds (docs/audits/2026-09-26 note 02 section 4.5; the memory rule "kill orphans only, never
bash.exe"). Claude Code runs this at SessionEnd and at every Stop through scripts/hooks/claude_session_end.sh.

A pid is killed when its command's basename is a watcher (tail, grep, sleep, inotifywait) AND it is orphaned: its
ppid is not a pid in the `ps -ef` table (the parent shell is gone) or is 1. Never a bash/sh/python/git process,
never pid 1 or our own pids, never a watcher whose parent is a live loop_lock.sh holder's shell.

The kill is `kill -9` through subprocess, never os.kill: Git Bash's `ps` prints MSYS pids, and a Windows-native
Python's os.kill takes a WINDOWS pid -- measured 2026-09-26, os.kill(<msys pid>, 9) raised WinError 87 and the
sleep lived, and on a luckier number it would terminate an unrelated Windows process. MSYS `kill -9` killed it.

main() prints ONE line and exits 0 always: a Stop hook's exit 2 would stop Claude from stopping.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

WATCHERS = frozenset({"tail", "grep", "sleep", "inotifywait"})
NEVER = frozenset({"bash", "sh", "dash", "zsh", "python", "python3", "py", "git"})

# UID PID PPID TTY STIME COMMAND; STIME is hh:mm:ss today, else two tokens ("Sep 21"); COMMAND may hold spaces.
_ROW = re.compile(r"^\s*\S+\s+(\d+)\s+(\d+)\s+\S+\s+(?:\d\d:\d\d:\d\d|[A-Za-z]{3}\s+\d{1,2}|\d{4})\s+(\S.*?)\s*$")


def parse_ps(text):
    """`ps -ef` text -> [(pid, ppid, command)]; the header and anything unparseable are skipped."""
    table = []
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            table.append((int(m.group(1)), int(m.group(2)), m.group(3)))
    return table


def _name(command):
    """The executable's basename, lower case, without .exe. MSYS ps prints the path with no arguments, and the path
    may hold spaces ("/c/Program Files/Git/usr/bin/sleep"); a command line with arguments starts with the path."""
    def base(word):
        word = word.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()
        return word[:-4] if word.endswith(".exe") else word

    command = command.strip()
    if not command:
        return ""
    name = base(command.split()[0])
    if name not in WATCHERS | NEVER and command.startswith("/"):
        # a path with a space: the whole string up to its first " -" is the path (MSYS ps prints no arguments)
        name = base(command.split(" -", 1)[0])
    return name


def kill_list(table, protect=(), self_pids=None):
    """The pids to kill: orphaned watchers only. `protect` holds live loop_lock.sh holder pids; `self_pids` defaults
    to this process and its parent."""
    if self_pids is None:
        self_pids = (os.getpid(), os.getppid())
    self_pids = set(self_pids)
    protect = set(protect)
    live = {pid for pid, _, _ in table}
    parent = {pid: ppid for pid, ppid, _ in table}
    out = []
    for pid, ppid, command in table:
        name = _name(command)
        if name in NEVER or name not in WATCHERS or pid <= 1 or pid in self_pids:
            continue
        if ppid in live and ppid != 1:
            continue  # its parent is alive: a live watcher
        # an orphan -- unless its parent (or an ancestor still in the table) is a lock holder
        chain, p, seen = set(), ppid, set()
        while p not in seen:
            seen.add(p)
            chain.add(p)
            p = parent.get(p, p)
        if chain & protect:
            continue
        out.append(pid)
    return out


def read_table():
    r = subprocess.run(["ps", "-ef"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise OSError("ps -ef exit %d" % r.returncode)
    return parse_ps(r.stdout)


def _git_common_dir(root):
    git = root / ".git"
    if git.is_dir():
        return git
    if git.is_file():
        m = re.match(r"gitdir:\s*(.+)", git.read_text().strip())
        if m:
            gitdir = Path(m.group(1).strip())
            common = gitdir / "commondir"
            if common.is_file():
                return (gitdir / common.read_text().strip()).resolve()
            return gitdir
    return None


def lock_holder_pids():
    """The pid inside the live loop_lock record's take_id (<epoch>-<pid>x<rand>), as scripts/loop_lock.sh finds it
    (LOOP_LOCK_PATH, else <main tree>/logs/.loop_lock). Best effort: nothing readable -> ()."""
    lock = os.environ.get("LOOP_LOCK_PATH")
    if not lock:
        root = Path(__file__).resolve().parents[2]
        common = _git_common_dir(root)
        lock = str((common.parent if common else root) / "logs" / ".loop_lock")
    try:
        fields = Path(lock + ".d", "record").read_text().split()
    except OSError:
        return ()
    m = re.match(r"\d+-(\d+)x", fields[1]) if len(fields) > 1 else None
    return (int(m.group(1)),) if m else ()


def kill_pids(pids):
    """`kill -9` (MSYS) on the list; returns the pids that are gone. One re-read of ps only when kill complains."""
    r = subprocess.run(["kill", "-9"] + [str(p) for p in pids], capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        return list(pids)
    still = {pid for pid, _, _ in read_table()}
    return [p for p in pids if p not in still]


def main(read_table=None, kill=None, protect=None):
    mod = sys.modules[__name__]
    read_table = read_table or mod.read_table
    kill = kill or mod.kill_pids
    protect = protect or mod.lock_holder_pids
    try:
        pids = kill_list(read_table(), protect=protect())
        if not pids:
            print("reap: nothing to kill")
            return 0
        killed = kill(pids)
        print("reap: killed %d watchers (pids %s)" % (len(killed), " ".join(str(p) for p in killed)))
    except BaseException as e:  # a Stop hook must never block: any failure is one line and exit 0
        print("reap: skipped: %s" % (str(e) or type(e).__name__))
    return 0


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
