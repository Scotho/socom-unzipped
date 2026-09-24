"""What the SOCOM 1 demo's .debug section actually covers: source paths by directory, and how often
the engine class names occur in it. String extraction only, not a DWARF1 walk. (Task 7 review,
socom-pc-6c)

Run from the repo root:  python <this file>

The libpttclient directory holds libpttclient.c plus all 34 units of the LPC-10 reference vocoder
(analys.c ... vparms.c, with f2clib.c, the Fortran-to-C runtime that implementation carries): the
push-to-talk voice codec is LPC-10 at 2400 bit/s. (An earlier draft of this review said GSM 06.10
from the first five file names; that was wrong.)
"""
import collections
import os
import re
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
BS = chr(92)  # a backslash, kept out of the source so shell tooling cannot collapse it
CLASSES = [b"CZSealBody", b"CMission", b"CZNetwork", b"CSealCtrl", b"CZKit", b"CEntity",
           b"CPnt3D", b"CZAnimMain", b"CZOnlineLobby", b"CNetCnf"]


def main() -> None:
    data = open(DEMO, "rb").read()
    elf = read_elf(DEMO)
    debug = next(s for s in elf.sections if s.name == ".debug")
    d = data[debug.offset:debug.offset + debug.size]
    print(f".debug {debug.size} bytes; .line "
          f"{next((s.size for s in elf.sections if s.name == '.line'), 0)} bytes")

    path_re = re.compile(("[A-Za-z]:" + BS + BS + "[ -~]{2,200}").encode())
    paths = collections.Counter()
    for m in path_re.finditer(d):
        paths[m.group(0).decode("latin1").split(chr(0))[0]] += 1
    files = sorted(p for p in paths if p.lower().endswith((".cpp", ".c", ".h", ".s")))
    print(f"distinct path strings {len(paths)}, source files {len(files)}")
    dirs = collections.Counter(p.rsplit(BS, 1)[0] for p in files)
    for directory, n in dirs.most_common():
        print(f"  {n:3d}  {directory}")
    ptt = [p.rsplit(BS, 1)[1] for p in files if "libpttclient" in p]
    print("libpttclient units:", " ".join(sorted(ptt)))

    print("class-name occurrences (.debug / whole file):")
    for name in CLASSES:
        print(f"  {name.decode():14s} {d.count(name):5d} {data.count(name):5d}")


if __name__ == "__main__":
    main()
