"""What scripts/vm_sync.sh tree must delete in the guest: files under the source roots that the host no
longer has. Reads the guest's list on stdin, prints the stale paths; the host's list comes from the tree."""
import os
import sys

ROOTS = ("third_party/ps2recomp/ps2xLauncher/", "third_party/ps2recomp/ps2xShared/",
         "third_party/ps2recomp/ps2xRuntime/", "third_party/ps2recomp/ps2xTest/",
         "third_party/ps2recomp/ps2xIOP/", "tools_py/", "scripts/", "src/")
SKIP_PARTS = ("__pycache__",)


def _norm(path):
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _prunable(path):
    parts = path.split("/")
    if path.startswith("/") or ".." in parts or any(p in SKIP_PARTS for p in parts):
        return False
    return path.startswith(ROOTS)


def stale(host_files, guest_files):
    host = {_norm(p) for p in host_files}
    return sorted(p for p in {_norm(g) for g in guest_files} if p and _prunable(p) and p not in host)


def host_files(root):
    out = []
    for base in ROOTS:
        for dirpath, _dirs, files in os.walk(os.path.join(root, base)):
            out.extend(os.path.relpath(os.path.join(dirpath, f), root) for f in files)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(newline="
")   # the list goes to a Linux xargs: no CR
    for path in stale(host_files(sys.argv[1]), sys.stdin.read().splitlines()):
        print(path)
