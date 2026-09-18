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

  python3 scripts/portable_libs.py  < ldd.txt    paths to copy, one per line
  python3 scripts/portable_libs.py --missing < ldd.txt   names ldd could not resolve; exit 1 if any
"""
import sys

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
        if not path.startswith("/"):
            continue
        yield name, path


def is_host_library(soname):
    """True when the host must provide this library and the tarball must not carry it."""
    return soname.startswith(HOST_PREFIXES)


def select(ldd_text):
    """The absolute paths to copy into lib/, input order, no duplicates."""
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
    text = sys.stdin.read()
    if "--missing" in argv[1:]:
        names = missing(text)
        for n in names:
            print(n)
        return 1 if names else 0
    for p in select(text):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
