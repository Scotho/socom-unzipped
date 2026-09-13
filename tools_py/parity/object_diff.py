"""Object-keyed uninitialised-field diff -- Sprint 5 Task 4 Step 1 (Leg 0, zero game runs).

Two modes, one contract: never key a diff by absolute address, because our heap (`guestMalloc`
in `ps2_runtime.cpp`) places objects at different addresses than the console (`research/19` F3/F4:
the `CZNetGame` block sits at `0x869360` on ours and `0xC496B0` on the console). Key every diff by
STATIC POINTER -> BLOCK -> OFFSET instead.

Mode 1 -- RDRAM image diff (this is the contract Task 4's brief gives verbatim)::

    python -m tools_py.parity.object_diff \\
        --static 0x437ce8:0x14c --static 0x408c58:0x1100 --static 0x415ff0:0x200 \\
        <our images...> -- <console images...>

For each `--static ADDR:SIZE`, the word at `ADDR` (PS2 KSEG address, masked with `& 0x1FFFFFF`
against each image, same convention as `tools_py/rdr_tree.py`) is followed as a pointer to a
`SIZE`-byte block, independently in every image on both sides of the bare `--`. It prints the
resolved block address in every image, then walks the block byte by byte and prints every offset
where the two sides disagree, flagging any offset that is a single nonzero constant on every
`ours` image and zero on every `console` image (the uninitialised-heap-memory signature: `0xAF`
recycled bytes on ours, zeroed pages on the console). A static that resolves to NULL or to a block
that runs past the image (an unresolved chain) is a hard failure: exit 2. So is being asked to
diff zero images, or an image that produced zero read bytes: exit 2, "NO-DATA" -- every instrument
here counts what it actually read and refuses to report success over nothing.

Mode 2 -- peek-log diff (`--peek-log NAME=path ...`), for the runtime's `PS2X_PEEK` text logs
(`[peek] @<addr>: <hex>(<float>) ... @<addr>: ...` rows, one `@addr: words...` block per resolved
pointer in the `PS2X_PEEK` spec). The catch the handoff notes flag: item indices SHIFT when a
chain does not resolve (an unresolved `*static` item is dropped from the row entirely, not
printed as zeros), and the block addresses themselves are per-instance heap addresses that differ
run to run. So this mode never reads "the Nth block on the row" -- it finds the actor block by
its vtable word (`0x6691a0` for the local player, `KNOWN.md`) and reads each requested field
offset from whichever block on that row (there can be several, from different `*static+off` peek
items) actually covers that absolute address. If no block on a row covers a requested offset, that
row is reported as NOT COVERED for that field rather than guessed at.
"""
import re
import struct
import sys
from dataclasses import dataclass, field as dc_field
from typing import Dict, List, Optional, Tuple

RDRAM_MASK = 0x1FFFFFF  # tools_py/rdr_tree.py's `a & 0x1ffffff` convention

USAGE = __doc__


# --------------------------------------------------------------------------------------------
# Mode 1: RDRAM image diff -- pure logic first, IO second.
# --------------------------------------------------------------------------------------------


class ResolveError(Exception):
    """A static pointer did not resolve (NULL, or its block runs past the image) in some image."""


@dataclass
class StaticSpec:
    raw: str
    addr: int
    size: int

    @classmethod
    def parse(cls, text: str) -> "StaticSpec":
        try:
            addr_s, size_s = text.split(":", 1)
            addr = int(addr_s, 16)
            size = int(size_s, 16)
        except ValueError as exc:
            raise ValueError(f"bad --static spec {text!r}, want ADDR:SIZE in hex") from exc
        if size <= 0:
            raise ValueError(f"bad --static spec {text!r}: size must be > 0")
        return cls(text, addr, size)


def read_u32(image: bytes, addr: int) -> int:
    p = addr & RDRAM_MASK
    if p + 4 > len(image):
        raise ResolveError(f"address {addr:#x} (phys {p:#x}) is out of range for a "
                            f"{len(image)}-byte image")
    return struct.unpack_from("<I", image, p)[0]


def resolve_block(image: bytes, static_addr: int, size: int) -> Tuple[int, bytes]:
    """Follow the pointer word at `static_addr` in `image` and return (block_addr, block_bytes).
    Raises ResolveError on a NULL pointer or a block that would run past the image -- the two
    "does not resolve" cases the contract calls out."""
    ptr = read_u32(image, static_addr)
    if ptr == 0:
        raise ResolveError(f"static {static_addr:#x} is NULL in this image")
    p = ptr & RDRAM_MASK
    if p + size > len(image):
        raise ResolveError(f"static {static_addr:#x} -> {ptr:#x}: a {size:#x}-byte block there "
                            f"runs past the {len(image)}-byte image")
    return ptr, image[p:p + size]


@dataclass
class FieldRow:
    offset: int
    our_bytes: List[int]
    console_bytes: List[int]
    flagged: bool


def diff_blocks(our_blocks: List[bytes], console_blocks: List[bytes]) -> List[FieldRow]:
    """Pure diff over already-resolved, same-size blocks (no file IO, unit-testable on its own).
    Returns one row per BYTE offset where the two sides do not read the same value everywhere,
    flagging offsets that are a single nonzero constant on every `ours` block and zero on every
    `console` block."""
    if not our_blocks or not console_blocks:
        return []
    size = len(our_blocks[0])
    rows: List[FieldRow] = []
    for off in range(size):
        our_vals = [b[off] for b in our_blocks]
        con_vals = [b[off] for b in console_blocks]
        if len(set(our_vals)) == 1 and len(set(con_vals)) == 1 and our_vals[0] == con_vals[0]:
            continue
        flagged = (len(set(our_vals)) == 1 and our_vals[0] != 0
                   and len(set(con_vals)) == 1 and con_vals[0] == 0)
        rows.append(FieldRow(off, our_vals, con_vals, flagged))
    return rows


def fmt_byteset(vals: List[int]) -> str:
    uniq = sorted(set(vals))
    if len(uniq) == 1:
        return f"{uniq[0]:02x}"
    return "[" + ",".join(f"{v:02x}" for v in vals) + "]"


def format_ranges(offsets: List[int]) -> str:
    if not offsets:
        return ""
    offsets = sorted(offsets)
    ranges = []
    start = prev = offsets[0]
    for o in offsets[1:]:
        if o == prev + 1:
            prev = o
            continue
        ranges.append((start, prev))
        start = prev = o
    ranges.append((start, prev))
    return ", ".join(f"+{a:#x}" if a == b else f"+{a:#x}..+{b:#x}" for a, b in ranges)


def load_image(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def run_image_diff(statics: List[StaticSpec], our_paths: List[str],
                    console_paths: List[str], out=None, err=None) -> int:
    # `out`/`err` default to the CURRENT sys.stdout/sys.stderr at call time, not at import time
    # (a bare `out=sys.stdout` default would bind the stream object once, at module load, which
    # breaks under contextlib.redirect_stdout as used by the tests).
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    if not statics:
        print("error: need at least one --static ADDR:SIZE", file=err)
        return 2
    if not our_paths or not console_paths:
        print("NO-DATA: zero images given (need at least one image on each side of --)", file=err)
        return 2

    try:
        our_images = [(p, load_image(p)) for p in our_paths]
        console_images = [(p, load_image(p)) for p in console_paths]
    except OSError as exc:
        print(f"error: {exc}", file=err)
        return 2

    rows_read = len(our_images) + len(console_images)
    if rows_read == 0:
        print("NO-DATA: zero images read", file=err)
        return 2
    print(f"images read: {len(our_images)} ours, {len(console_images)} console", file=out)

    for spec in statics:
        print(f"\n=== static {spec.addr:#x} size {spec.size:#x} ===", file=out)
        try:
            our_blocks = []
            print("  ours:", file=out)
            for path, img in our_images:
                addr, block = resolve_block(img, spec.addr, spec.size)
                print(f"    {path} -> block @{addr:#x}", file=out)
                our_blocks.append(block)
            console_blocks = []
            print("  console:", file=out)
            for path, img in console_images:
                addr, block = resolve_block(img, spec.addr, spec.size)
                print(f"    {path} -> block @{addr:#x}", file=out)
                console_blocks.append(block)
        except ResolveError as exc:
            print(f"  ERROR: static {spec.raw} does not resolve: {exc}", file=err)
            return 2

        rows = diff_blocks(our_blocks, console_blocks)
        flagged_offsets = [r.offset for r in rows if r.flagged]
        for r in rows:
            tag = "  FLAGGED (uninitialised-heap signature)" if r.flagged else ""
            print(f"  +{r.offset:#06x}: ours={fmt_byteset(r.our_bytes)} "
                  f"console={fmt_byteset(r.console_bytes)}{tag}", file=out)
        print(f"  -- {len(rows)} differing byte(s), {len(flagged_offsets)} flagged", file=out)
        if flagged_offsets:
            print(f"  flagged ranges: {format_ranges(flagged_offsets)}", file=out)

    return 0


# --------------------------------------------------------------------------------------------
# Mode 2: peek-log diff -- pure logic first, IO second.
# --------------------------------------------------------------------------------------------

_BLOCK_RE = re.compile(r"@([0-9a-fA-F]+):\s*((?:[0-9a-fA-F]{8}\([^)]*\)\s*)+)")
_WORD_RE = re.compile(r"([0-9a-fA-F]{8})\(")


@dataclass
class PeekBlock:
    addr: int
    words: List[int]


def parse_peek_row(line: str) -> Optional[List[PeekBlock]]:
    """Parse one `[peek] @addr: word(float) word(float) ... @addr: ...` line into its blocks, in
    the order they were printed. Returns None for a line that carries no peek blocks at all (not
    a peek line, or every item in the spec was unresolved that frame)."""
    if "[peek]" not in line:
        return None
    blocks = [PeekBlock(int(m.group(1), 16), [int(w, 16) for w in _WORD_RE.findall(m.group(2))])
              for m in _BLOCK_RE.finditer(line)]
    return blocks or None


def find_block_by_vtable(blocks: List[PeekBlock], vtable: int) -> Optional[PeekBlock]:
    """The block whose first word is `vtable` -- this is how the actor is found, because its
    address (and the row's item order) both shift run to run and item to item (handoff notes)."""
    for b in blocks:
        if b.words and b.words[0] == vtable:
            return b
    return None


def read_field(blocks: List[PeekBlock], target_addr: int) -> Optional[int]:
    """The word at absolute address `target_addr`, from whichever peeked block on the row (there
    may be several, from different `*static+off` PS2X_PEEK items) actually covers it. None if no
    block on this row covers it -- the peek spec did not capture that word, so the caller must say
    so rather than guess."""
    if target_addr % 4:
        return None
    for b in blocks:
        lo, hi = b.addr, b.addr + 4 * len(b.words)
        if lo <= target_addr < hi:
            return b.words[(target_addr - lo) // 4]
    return None


@dataclass
class PeekSample:
    row_index: int
    actor_addr: int
    values: Dict[int, Optional[int]] = dc_field(default_factory=dict)


def extract_actor_fields(lines: List[str], vtable: int, field_offsets: List[int]) -> List[PeekSample]:
    """Pure extraction over already-read lines: one PeekSample per row where the actor (keyed by
    `vtable`) resolved, each holding this row's value for every requested field offset (or None
    when that offset was not covered by any peeked block on the row)."""
    samples = []
    for i, line in enumerate(lines):
        blocks = parse_peek_row(line)
        if not blocks:
            continue
        actor = find_block_by_vtable(blocks, vtable)
        if actor is None:
            continue
        values = {off: read_field(blocks, actor.addr + off) for off in field_offsets}
        samples.append(PeekSample(i, actor.addr, values))
    return samples


def fmt_hexset(vals: List[int], cap: int = 12) -> str:
    uniq = sorted(set(vals))
    shown = ", ".join(f"{v:#x}" for v in uniq[:cap])
    more = f", ... (+{len(uniq) - cap} more)" if len(uniq) > cap else ""
    return "{" + shown + more + "}"


def load_lines(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def run_peek_log(peek_logs: List[Tuple[str, str]], vtable: int, fields: List[int],
                  out=None, err=None) -> int:
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    if not peek_logs:
        print("NO-DATA: zero peek logs given", file=err)
        return 2
    if not fields:
        print("error: need at least one --field OFFSET", file=err)
        return 2

    rows_read = 0
    try:
        logs = [(name, path, load_lines(path)) for name, path in peek_logs]
    except OSError as exc:
        print(f"error: {exc}", file=err)
        return 2

    for name, path, lines in logs:
        samples = extract_actor_fields(lines, vtable, fields)
        rows_read += len(samples)
        print(f"\n=== {name}: {path} ===", file=out)
        print(f"  {len(lines)} log lines, {len(samples)} rows with actor vtable {vtable:#x} "
              f"resolved", file=out)
        for off in fields:
            vals = [s.values[off] for s in samples]
            covered = [v for v in vals if v is not None]
            uncovered = len(vals) - len(covered)
            if not covered:
                print(f"  +{off:#x}: NOT COVERED -- no peeked block on any resolved row reaches "
                      f"this offset", file=out)
                continue
            note = f", {uncovered} row(s) not covered" if uncovered else ""
            print(f"  +{off:#x}: {len(covered)} covered row(s), distinct={fmt_hexset(covered)} "
                  f"first={covered[0]:#x} last={covered[-1]:#x}{note}", file=out)

    if rows_read == 0:
        print("NO-DATA: zero peek rows with the actor resolved were read", file=err)
        return 2
    return 0


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def parse_argv(argv: List[str]) -> dict:
    """Deliberately hand-rolled instead of argparse: the image-diff contract needs a bare `--` to
    separate the ours-images from the console-images, and argparse eats/repositions a literal
    `--` in ways that make that split unreliable."""
    args = {
        "mode": "image",
        "statics": [],
        "our_images": [],
        "console_images": [],
        "peek_logs": [],
        "vtable": 0x6691a0,  # KNOWN.md: the local-player actor's vtable word
        "fields": [],
    }
    seen_sep = False
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in ("-h", "--help"):
            raise _HelpRequested()
        elif tok == "--static":
            i += 1
            if i >= len(argv):
                raise ValueError("--static needs an ADDR:SIZE argument")
            args["statics"].append(StaticSpec.parse(argv[i]))
        elif tok == "--peek-log":
            args["mode"] = "peek-log"
        elif tok == "--vtable":
            i += 1
            if i >= len(argv):
                raise ValueError("--vtable needs a hex argument")
            args["vtable"] = int(argv[i], 16)
        elif tok == "--field":
            i += 1
            if i >= len(argv):
                raise ValueError("--field needs a hex OFFSET argument")
            args["fields"].append(int(argv[i], 16))
        elif tok == "--":
            seen_sep = True
        else:
            if args["mode"] == "peek-log":
                if "=" not in tok:
                    raise ValueError(f"--peek-log arguments must be NAME=path, got {tok!r}")
                name, path = tok.split("=", 1)
                args["peek_logs"].append((name, path))
            else:
                (args["console_images"] if seen_sep else args["our_images"]).append(tok)
        i += 1
    return args


class _HelpRequested(Exception):
    pass


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = parse_argv(argv)
    except _HelpRequested:
        print(USAGE)
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args["mode"] == "peek-log":
        return run_peek_log(args["peek_logs"], args["vtable"], args["fields"])
    return run_image_diff(args["statics"], args["our_images"], args["console_images"])


if __name__ == "__main__":
    sys.exit(main())
