#!/usr/bin/env python3
"""Sprint 8 Goal 1 Task 7: which shared libraries the Linux portable folder carries in lib/.

Reads `ldd` output on stdin (one run per binary, concatenated is fine) and prints one absolute
path per line -- the libraries scripts/make_portable.sh copies next to the runner, found at run
time through the RPATH $ORIGIN/lib. Everything the binaries link is carried EXCEPT the host's
own stack: glibc and the loader, libgcc_s and libstdc++ (every distro ships them, and a copied
libstdc++ is the classic way to break a newer host's GL driver), the GL/GLX/EGL dispatch, X11
and xcb and xkbcommon and wayland, and ALSA/PulseAudio/dbus/systemd/udev -- those must come from
the machine whose driver and sound server they talk to. What is left is the FFmpeg family
(libavcodec/libavformat/libavutil/libswscale/libswresample/libavfilter/libavdevice) and whatever
it pulls in (libvpx, libx264, libopus, libvorbis, ...), which the distro may not have.

Sprint 9 Goal 2: `ldd` prints a FLAT list -- everything the process will map, including what only a HOST
library needs. libXau is the example: nothing we carry imports it, only libxcb does, and libxcb is the
host's. Carrying it made the folder audit (tools_py/portable_audit.py) refuse the tarball, rightly. So the
list is walked instead of filtered: starting at the shipped executables, follow DT_NEEDED through the
libraries we carry ourselves and stop at a host one, because whatever lies behind it is the host's too.
ldd still provides the name -> path resolution, and --missing still reports what it could not resolve.

  python3 scripts/portable_libs.py <exe>... < ldd.txt   paths to copy, one per line (the closure walk)
  python3 scripts/portable_libs.py  < ldd.txt           every non-host path ldd named (the flat view)
  python3 scripts/portable_libs.py --missing < ldd.txt   names ldd could not resolve; exit 1 if any
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A dependency whose SONAME starts with one of these comes from the host, never the tarball.
HOST_PREFIXES = (
    # glibc and the dynamic loader
    "libc.", "libm.", "libpthread.", "libdl.", "librt.", "libresolv.",
    "ld-linux", "linux-vdso",
    # the compiler runtime the distro already ships
    "libgcc_s.", "libstdc++.",
    # the graphics stack: it belongs to the installed driver
    "libGL.", "libGLX.", "libEGL.", "libGLdispatch.",
    # X, xcb, wayland: the running display server's own libraries
    "libX11.", "libXext.", "libXrandr.", "libXinerama.", "libXcursor.", "libXi.",
    "libxcb", "libxkbcommon", "libwayland",
    # sound and the session bus
    "libasound.", "libpulse", "libdbus", "libsystemd", "libudev",
    # hardware video decode: each of these talks to the installed GPU driver over a private
    # interface, so a copied one is a mismatch with the driver on the player's machine.
    "libva",        # VA-API, and its libva-drm/libva-x11/libva-wayland backends
    "libvdpau",     # VDPAU, the NVIDIA-side decode dispatch, which dlopens the driver's backend
    "libdrm",       # the kernel DRM ioctl wrapper: it must match the running kernel, not ours
    "libgbm",       # buffer allocation through the same kernel driver
    "libvulkan",    # the Vulkan loader, which reads the host's own ICD manifests
    # windowing and audio servers the host owns, which FFmpeg's avdevice closure pulls in
    "libSDL2",      # avdevice's SDL output; the host's SDL is the one wired to its video stack
    "libjack",      # the JACK client library must match the JACK server that is running
    "libpipewire",  # likewise PipeWire: the client and the session manager are a matched pair
    "libsndio",     # sndio's client library talks to the host's sndiod socket
)


def _entries(ldd_text):
    """Yield (soname, path_or_None) for each dependency line of ldd output."""
    for raw in ldd_text.splitlines():
        line = raw.strip()
        if not line or line == "statically linked":
            continue
        if "=>" in line:
            name, _, rest = line.partition("=>")
            name, rest = name.strip(), rest.strip()
            if rest == "not found":
                yield name, None
                continue
            path = rest.split(" (")[0].strip()
        else:
            # "linux-vdso.so.1 (0x...)" and "/lib64/ld-linux-x86-64.so.2 (0x...)"
            path = line.split(" (")[0].strip()
            name = path.rsplit("/", 1)[-1]
        if not (path.startswith("/") or os.path.isabs(path)):
            continue
        yield name, path


def is_host_library(soname):
    """True when the host must provide this library and the tarball must not carry it."""
    return soname.startswith(HOST_PREFIXES)


_audit = None


def _elf_needed(path):
    """DT_NEEDED of one ELF file, through tools_py/portable_audit.py's pure-Python reader (no objdump)."""
    global _audit
    if _audit is None:
        spec = importlib.util.spec_from_file_location(
            "portable_audit_reader", os.path.join(ROOT, "tools_py", "portable_audit.py"))
        _audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_audit)
    return _audit.elf_needed(path)


def reachable(ldd_text, exes):
    """The absolute paths to copy into lib/: the libraries `exes` reach through a chain of libraries we
    carry ourselves. A host library ends the walk -- what only it needs is the host's problem, not ours.
    A name ldd could not resolve is skipped here and reported by missing()."""
    resolved = {}
    for name, path in _entries(ldd_text):
        if path is not None:
            resolved.setdefault(name, path)
    out, seen, todo = [], set(), list(exes)
    while todo:
        for name in _elf_needed(todo.pop(0)):
            if name in seen or is_host_library(name):
                continue
            seen.add(name)
            path = resolved.get(name)
            if path is None or path in out:
                continue
            out.append(path)
            todo.append(path)
    return out


def select(ldd_text):
    """The flat view: every absolute path ldd named that is not the host's, input order, no duplicates."""
    out, seen = [], set()
    for name, path in _entries(ldd_text):
        if path is None or is_host_library(name) or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def missing(ldd_text):
    """The sonames ldd could not resolve, input order, no duplicates."""
    out, seen = [], set()
    for name, path in _entries(ldd_text):
        if path is None and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def main(argv):
    args = argv[1:]
    text = sys.stdin.read()
    if "--missing" in args:
        names = missing(text)
        for n in names:
            print(n)
        return 1 if names else 0
    exes = [a for a in args if not a.startswith("-")]
    for p in (reachable(text, exes) if exes else select(text)):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
