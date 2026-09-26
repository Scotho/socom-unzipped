"""The SessionEnd/Stop reaper (Sprint 14 G3): kill orphaned watcher processes, never a shell.

On 2026-09-25 the host carried 213 orphaned `tail`/`grep` watchers left by dead monitors (the oldest from 09-17) and
every bash start took seconds (docs/audits/2026-09-26 note 02 section 4.5; the memory rule "kill orphans only, never
bash.exe"). Claude Code runs this at SessionEnd and at every Stop through scripts/hooks/claude_session_end.sh.

The table is `ps -W` (PID PPID PGID WINPID TTY UID STIME COMMAND), which carries the process group. A pid is killed
when its command is an MSYS path (it starts with "/"; `ps -W` also lists native Windows processes, with a C:\\ path,
and those are never judged) whose basename is a watcher (tail, grep, sleep, inotifywait), AND it is orphaned: its
ppid is not a pid in the table (the parent shell is gone), or its ppid is 1 and it does NOT lead its own process
group. A watcher whose bash exited normally shows ppid 1 and keeps the dead shell's group (pgid != pid); a watcher
started directly by a Windows program (PowerShell's Start-Process) also shows ppid 1 but is its own group leader
(pgid == pid) -- kept (review, 2026-09-26). Never a bash/sh/python/git process, never pid 1 or our own pids.

Why no live session's process is on the list (the review's walk): every live Monitor watcher sits under a live bash;
the loop lock's renewer `sleep 1` lives under a live subshell; run_detached.sh's child is a `nohup bash`, which the
reaper never kills; the parity scripts' background jobs are python/powershell, never watchers.

The kill is `kill -9` through subprocess, never os.kill: Git Bash's `ps` prints MSYS pids, and a Windows-native
Python's os.kill takes a WINDOWS pid -- measured 2026-09-26, os.kill(<msys pid>, 9) raised WinError 87 and the
sleep lived, and on a luckier number it would terminate an unrelated Windows process. MSYS `kill -9` killed it.
`kill -9` with one pid already dead returns rc 1 while the live ones still die, so on a non-zero rc kill_pids
re-reads ps and reports only the pids that are really gone.

main() prints ONE line and exits 0 always: a Stop hook's exit 2 would stop Claude from stopping.
"""

import os
import re
import subprocess
import sys

WATCHERS = frozenset({"tail", "grep", "sleep", "inotifywait"})
NEVER = frozenset({"bash", "sh", "dash", "zsh", "python", "python3", "py", "git"})

# [status letter] PID PPID PGID WINPID TTY UID STIME COMMAND; STIME is hh:mm:ss today, else two tokens ("Sep 21");
# COMMAND may hold spaces.
_ROW = re.compile(r"^\s*(?:[A-Z]\s+)?(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+\S+\s+\d+\s+"
                  r"(?:\d\d:\d\d:\d\d|[A-Za-z]{3}\s+\d{1,2}|\d{4})\s+(\S.*?)\s*$")


def parse_ps(text):
    """`ps -W` text -> [(pid, ppid, pgid, command)]; the header and anything unparseable are skipped."""
    table = []
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            table.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)))
    return table


def _name(command):
    """The executable's basename, lower case, without .exe -- for an MSYS path only (it starts with "/"); anything
    else (a native C:\\ path, a bare name) is "". MSYS ps prints the path with no arguments, and the path may hold
    spaces ("/c/Program Files/Git/usr/bin/sleep"); a command line with arguments starts with the path."""
    def base(word):
        word = word.rsplit("/", 1)[-1].strip().lower()
        return word[:-4] if word.endswith(".exe") else word

    command = command.strip()
    if not command.startswith("/"):
        return ""
    name = base(command.split()[0])
    if name not in WATCHERS | NEVER:
        # a path with a space: the whole string up to its first " -" is the path
        name = base(command.split(" -", 1)[0])
    return name


def kill_list(table, self_pids=None):
    """The pids to kill: orphaned watchers only. `self_pids` defaults to this process and its parent."""
    if self_pids is None:
        self_pids = (os.getpid(), os.getppid())
    self_pids = set(self_pids)
    live = {row[0] for row in table}
    out = []
    for pid, ppid, pgid, command in table:
        name = _name(command)
        if name in NEVER or name not in WATCHERS or pid <= 1 or pid in self_pids:
            continue
        if ppid == 1:
            if pgid == pid:
                continue  # started directly by a Windows program: its own group leader, not a bash orphan
        elif ppid in live:
            continue  # its parent is alive: a live watcher
        out.append(pid)
    return out


def read_table():
    r = subprocess.run(["ps", "-W"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise OSError("ps -W exit %d" % r.returncode)
    return parse_ps(r.stdout)


def kill_pids(pids):
    """`kill -9` (MSYS) on the list; returns the pids that are gone. One re-read of ps only when kill complains."""
    r = subprocess.run(["kill", "-9"] + [str(p) for p in pids], capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        return list(pids)
    still = {row[0] for row in read_table()}
    return [p for p in pids if p not in still]


def main(read_table=None, kill=None):
    mod = sys.modules[__name__]
    read_table = read_table or mod.read_table
    kill = kill or mod.kill_pids
    try:
        pids = kill_list(read_table())
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
