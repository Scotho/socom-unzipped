"""What scripts/vm_sync.sh tree must touch in the guest: the files the sync actually changed.

The tree travels as a tar stream, and tar carries the HOST's mtimes. A file edited before the guest's
last build but synced after it therefore arrives looking OLDER than the object ninja built from its
previous content, so ninja skips it -- the VM linked a launcher whose pad_render.cpp.o still defined
the old signature of ui::drawPad, and the link failed on a symbol the source no longer has. Content is
the only thing the two machines agree on, so the sync takes an md5 listing before and after the untar
and touches what differs (and what is new) with the guest's own clock: ninja then rebuilds exactly
those files and nothing else. Deleting is the other half, tools_py/vm_prune.py.

  <guest md5sum listing> | python -m tools_py.vm_restamp <before listing>   paths to touch, one per line
"""
import sys

SKIP_PARTS = ("__pycache__",)


def _norm(path):
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _safe(path):
    parts = path.split("/")
    return bool(path) and not path.startswith("/") and ".." not in parts \
        and not any(p in SKIP_PARTS for p in parts)


def _listing(lines):
    """{path: digest} from `md5sum` output ("<digest>  <path>"; a path may hold spaces)."""
    out = {}
    for line in lines:
        digest, sep, path = line.rstrip("\n").partition("  ")
        if not sep:
            continue
        path = _norm(path)
        if _safe(path):
            out[path] = digest.strip()
    return out


def changed(before_lines, after_lines):
    """The paths whose content the sync changed, plus the ones it added; sorted."""
    before = _listing(before_lines)
    after = _listing(after_lines)
    return sorted(path for path, digest in after.items() if before.get(path) != digest)


if __name__ == "__main__":
    sys.stdout.reconfigure(newline=chr(10))   # the list goes to a Linux xargs: no CR
    with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
        before = fh.read().splitlines()
    for path in changed(before, sys.stdin.read().splitlines()):
        print(path)
