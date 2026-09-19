#!/usr/bin/env python3
"""Sprint 9 Goal 2: what the portable folder carries is decided from import tables, and checked.

  closure  the local libraries the shipped executables reach -- scripts/make_portable.sh copies these
           and nothing else (it used to copy dist/*.dll: 31 files, of which the executables reach 16);
  audit    a finished folder: `missing` = imported, not in the folder, not the operating system's;
           `orphans` = carried, imported by nothing;
  sha256sums / verify   the SHA256SUMS file beside each archive.

Pure Python (struct): no objdump, no ldd -- so a Windows folder is audited in CI and a Linux one on the
host. The Linux "host provides it" list is scripts/portable_libs.py's, the one the tarball is built with.

  python tools_py/portable_audit.py closure --dir <folder> <exe>...
  python tools_py/portable_audit.py audit <folder> [--system Windows|Linux]
  python tools_py/portable_audit.py sha256sums <out dir> <archive name>...
  python tools_py/portable_audit.py verify <out dir>
"""
import argparse
import hashlib
import importlib.util
import os
import platform
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# What Windows itself provides, as imported today by the two executables and the sixteen DLLs they reach
# (llvm-objdump -p over dist/, 2026-09-19), plus the four FFmpeg's import libraries name. Anything else that
# is imported and absent -- VCRUNTIME140.dll is the classic -- is a finding, because a stranger's machine
# may not have it.
WINDOWS_SYSTEM = frozenset((
    "kernel32.dll", "user32.dll", "gdi32.dll", "shell32.dll", "winmm.dll", "ws2_32.dll", "comdlg32.dll",
    "ole32.dll", "bcrypt.dll", "advapi32.dll", "secur32.dll", "oleaut32.dll",
))
WINDOWS_SYSTEM_PREFIXES = ("api-ms-win-",)
SHIPPED = {"Windows": ("socom2.exe", "socom_unzipped_launcher.exe"), "Linux": ("socom2", "socom_unzipped_launcher")}
SUMS_NAME = "SHA256SUMS"


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _cstr(data, offset):
    return data[offset:data.index(b"\0", offset)].decode("ascii", "replace")


def pe_imports(path):
    """DLL names a PE32/PE32+ file imports: the import directory, then the delay-import directory."""
    data = _read(path)
    try:
        if data[:2] != b"MZ":
            raise ValueError("no MZ header")
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("no PE signature")
        section_count, = struct.unpack_from("<H", data, pe + 6)
        optional_size, = struct.unpack_from("<H", data, pe + 20)
        optional = pe + 24
        magic, = struct.unpack_from("<H", data, optional)
        if magic not in (0x10B, 0x20B):
            raise ValueError("optional header magic 0x%x" % magic)
        directories = optional + (112 if magic == 0x20B else 96)
        directory_count, = struct.unpack_from("<I", data, directories - 4)
        sections = []
        for i in range(section_count):
            at = optional + optional_size + 40 * i
            sections.append(struct.unpack_from("<IIII", data, at + 8))   # vsize, vaddr, rawsize, rawptr

        def offset_of(rva):
            for vsize, vaddr, rawsize, rawptr in sections:
                if vaddr <= rva < vaddr + max(vsize, rawsize):
                    return rawptr + (rva - vaddr)
            raise ValueError("rva 0x%x is in no section" % rva)

        names = []
        for index, entry_size, name_at in ((1, 20, 12), (13, 32, 4)):
            if index >= directory_count:
                continue
            rva, _size = struct.unpack_from("<II", data, directories + 8 * index)
            if not rva:
                continue
            at = offset_of(rva)
            while at + entry_size <= len(data):
                name_rva, = struct.unpack_from("<I", data, at + name_at)
                if not name_rva:
                    break
                names.append(_cstr(data, offset_of(name_rva)))
                at += entry_size
        return names
    except (struct.error, ValueError) as e:
        raise ValueError("%s: not a PE file this reader understands (%s)" % (path, e))


def elf_needed(path):
    """DT_NEEDED names of a 64-bit little-endian ELF; [] when it has no dynamic section."""
    data = _read(path)
    try:
        if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
            raise ValueError("not a 64-bit little-endian ELF")
        section_table, = struct.unpack_from("<Q", data, 0x28)
        entry_size, count = struct.unpack_from("<HH", data, 0x3A)

        def section(i):
            _name, kind, _flags, _addr, offset, size, link = struct.unpack_from(
                "<IIQQQQI", data, section_table + i * entry_size)
            return kind, offset, size, link

        for i in range(count):
            kind, offset, size, link = section(i)
            if kind != 6:                      # SHT_DYNAMIC
                continue
            _kind, strings, _size, _link = section(link)
            names = []
            for at in range(offset, offset + size, 16):
                tag, value = struct.unpack_from("<qQ", data, at)
                if tag == 0:
                    break
                if tag == 1:                   # DT_NEEDED
                    names.append(_cstr(data, strings + value))
            return names
        return []
    except (struct.error, ValueError) as e:
        raise ValueError("%s: not an ELF file this reader understands (%s)" % (path, e))


def system_of(path):
    """"Windows" or "Linux", from the file's own magic (MZ / \\x7fELF). The reader is chosen by what the
    FILE is, never by what the host is: CI (Linux) audits a Windows folder, and the Windows host a Linux one."""
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic[:2] == b"MZ":
        return "Windows"
    if magic == b"\x7fELF":
        return "Linux"
    raise ValueError("%s: neither a PE (MZ) nor an ELF file" % path)


def folder_system(folder):
    """The platform a portable folder was built for, from the first shipped executable found in it."""
    for system, names in SHIPPED.items():
        for name in names:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return system_of(path)
    return platform.system()


def imports_of(path):
    """The libraries `path` imports, read by the reader its magic calls for."""
    return pe_imports(path) if system_of(path) == "Windows" else elf_needed(path)


def is_windows_system(name):
    lowered = name.lower()
    return lowered in WINDOWS_SYSTEM or lowered.startswith(WINDOWS_SYSTEM_PREFIXES)


_portable_libs = None


def is_linux_host(name):
    """scripts/portable_libs.py:is_host_library -- glibc, libstdc++, GL, X11, the sound servers."""
    global _portable_libs
    if _portable_libs is None:
        spec = importlib.util.spec_from_file_location("portable_libs", os.path.join(ROOT, "scripts", "portable_libs.py"))
        _portable_libs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_portable_libs)
    return _portable_libs.is_host_library(name)


def closure(exes, folder, system):
    """(needed, missing): needed = {file name in `folder`: first importer}, missing = {imported name: importer}
    for names that are neither in `folder` nor provided by the operating system. Windows matches names without
    regard to case, as its loader does."""
    windows = system == "Windows"
    provided = is_windows_system if windows else is_linux_host
    fold = (lambda s: s.lower()) if windows else (lambda s: s)
    local = {fold(n): n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n))}
    needed, missing, todo = {}, {}, list(exes)
    while todo:
        path = todo.pop(0)
        importer = os.path.basename(path)
        for name in imports_of(path):
            if fold(name) in local:
                found = local[fold(name)]
                if found not in needed:
                    needed[found] = importer
                    todo.append(os.path.join(folder, found))
            elif not provided(name):
                missing.setdefault(name, importer)
    return needed, missing


def audit(folder, system=None):
    system = system or folder_system(folder)
    windows = system == "Windows"
    libs = folder if windows else os.path.join(folder, "lib")
    exes = [os.path.join(folder, n) for n in SHIPPED["Windows" if windows else "Linux"]]
    needed, missing = closure(exes, libs, system) if os.path.isdir(libs) else ({}, {})
    if windows:
        carried = [n for n in os.listdir(folder) if n.lower().endswith(".dll")]
    else:
        carried = [n for n in os.listdir(libs)] if os.path.isdir(libs) else []
    return {"needed": sorted(needed), "missing": missing, "orphans": sorted(set(carried) - set(needed))}


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256sums(out_dir, names):
    path = os.path.join(out_dir, SUMS_NAME)
    with open(path, "w", newline="\n", encoding="ascii") as fh:
        for name in sorted(names):
            fh.write("%s  %s\n" % (_sha256(os.path.join(out_dir, name)), name))
    return path


def verify_sha256sums(out_dir):
    path = os.path.join(out_dir, SUMS_NAME)
    if not os.path.isfile(path):
        return [SUMS_NAME + ": not found"]
    problems = []
    with open(path, encoding="ascii") as fh:
        for line in fh.read().splitlines():
            want, _, name = line.partition("  ")
            target = os.path.join(out_dir, name)
            if not os.path.isfile(target):
                problems.append(name + ": not found")
            elif _sha256(target) != want:
                problems.append(name + ": checksum differs")
    return problems


def _out(lines):
    sys.stdout.buffer.write("".join(line + "\n" for line in lines).encode())   # LF on Windows too: bash reads this


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("closure")
    c.add_argument("--dir", required=True)
    c.add_argument("--system", choices=("Windows", "Linux"))
    c.add_argument("exes", nargs="+")
    a = sub.add_parser("audit")
    a.add_argument("folder")
    a.add_argument("--system", choices=("Windows", "Linux"))
    s = sub.add_parser("sha256sums")
    s.add_argument("out_dir")
    s.add_argument("names", nargs="+")
    v = sub.add_parser("verify")
    v.add_argument("out_dir")
    args = ap.parse_args(argv)
    if args.cmd == "closure":
        needed, missing = closure(args.exes, args.dir, args.system or system_of(args.exes[0]))
        if missing:
            for name, importer in sorted(missing.items()):
                print("missing: %s (imported by %s)" % (name, importer), file=sys.stderr)
            return 3
        _out(sorted(needed))
        return 0
    if args.cmd == "audit":
        result = audit(args.folder, args.system)
        for name, importer in sorted(result["missing"].items()):
            print("missing: %s (imported by %s)" % (name, importer), file=sys.stderr)
        for name in result["orphans"]:
            print("orphan: %s (nothing imports it)" % name, file=sys.stderr)
        _out(["audit %s: %d needed, %d missing, %d orphans"
              % (args.folder, len(result["needed"]), len(result["missing"]), len(result["orphans"]))])
        return 4 if result["missing"] or result["orphans"] else 0
    if args.cmd == "sha256sums":
        _out([write_sha256sums(args.out_dir, args.names)])
        return 0
    problems = verify_sha256sums(args.out_dir)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 5 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
