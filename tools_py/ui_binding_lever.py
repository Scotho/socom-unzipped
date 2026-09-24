"""The `ui-binding` lever: name r0001's UI script handlers from the demo's (Sprint 12 Task 14; research/55
sec 4.2; S12-R15).

Both builds carry a table the UI script interpreter dispatches through: rows of [id, command string pointer,
handler pointer] (stride 12 in the SOCOM 1 demo, [id, string, handler, 0] at stride 16 in r0001). The demo's
handlers carry symbols, mostly `UI<command>__FP13C2DAnimCmdHdrPf`; r0001's are all auto-named. The command
string is the join key, so a demo name reaches an r0001 handler by an exact table join rather than by any
body heuristic, and a command only r0001 has is named from its own string in the demo's own convention.

    python -m tools_py.ui_binding_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \\
        recomp/socom2_ghidra.csv game/demo_symbol_matches.json \\
        --out game/demo_symbol_renames_ui.csv --derived-out game/demo_symbol_renames_ui_derived.csv

PROPOSALS ONLY: nothing here edits `recomp/socom2_ghidra.csv` or the sidecar; the applier (Task 3) does.
Both outputs are git-ignored and hold names, addresses and command strings, no game bytes.
"""
import argparse
import bisect
import csv
import glob
import json
import os
import re
import struct
import sys
import textwrap
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py import ghidra_symbol_match as gsm
from tools_py import name_provenance
from tools_py.elf_symbols import read_elf
from tools_py.ghidra_symbol_match import c_identifier
from tools_py.name_provenance import is_placeholder
from tools_py.symbol_levers import anchors_from_details, proved_anchors

PASS = "ui-binding"
PASS_DERIVED = "ui-binding-derived"
SCORE = 0.90
SCORE_DERIVED = 0.80
MIN_ROWS = 8
STRIDES = (8, 12, 16)
MAX_STRING = 256
COLUMNS = ["Address", "Current", "Proposed", "Mangled", "Pass", "Score", "Evidence", "DemoAddr"]

# What research/55 sec 4.2 measured, CHECKED against what the shape finder locates, never used to locate it.
NOTE_TABLES = {"demo": (0x439540, 147), "r0001": (0x3dd4d0, 207)}

UI_BINDING_RULE = (
    "ui-binding: both builds' UI script-binding tables are located by their shape alone -- a run of at least "
    "%d rows at one stride (8, 12 or 16 bytes), each holding an aligned pointer to a NUL-terminated printable "
    "string followed by a pointer to a function start -- and the largest run in each image is the table "
    "(checked against research/55's demo 147 rows at 0x439540 and r0001 207 rows at 0x3dd4d0, not assumed). "
    "The two tables are joined by the command string's exact bytes; a command that occurs more than once in "
    "either table is refused. Where the command is in both, the demo handler's name is proposed for r0001's "
    "handler (pass %s, score %.2f: an exact string-keyed table join, not a body heuristic), anonymous-namespace "
    "(@unnamed@) demo handlers included and counted apart. Where the command is only in r0001, UI<command> "
    "(the demo's own convention, through c_identifier) is proposed under pass %s at score %.2f with the "
    "derivation in Evidence, in a separate file. Hurdles: r0001's handler must still carry a placeholder name "
    "(csv and sidecar); a handler bound to two commands is refused; a row that disagrees with a Task 7 pair "
    "on either address (a derived row: Task 7 pairs its handler with a demo name not UI<command>__) is "
    "refused and printed; Task 7's identifier hurdles apply (two proposals that sanitise "
    "alike are both refused; a name recomp/socom2_name_holds.csv holds at that address is refused, and a Task "
    "7 pair on a held address is no anchor for the disagreement check (S12-R20); an identifier another demo_symbol_renames*.csv file spends at another address is "
    "refused; another file naming the same handler differently is refused), and every refusal is counted."
    % (MIN_ROWS, PASS, SCORE, PASS_DERIVED, SCORE_DERIVED))


class Row(NamedTuple):
    addr: int          # the string-pointer word
    string: bytes      # the command, without its NUL
    function: int      # the handler (a function start)
    name: str          # the handler's name in its own image ("" when the image has none)


class Table(NamedTuple):
    addr: int          # the first row's start (the pair address minus `lead`)
    stride: int
    lead: int          # bytes of the row before the string pointer (4: the id word)
    rows: Tuple[Row, ...]


class Join(NamedTuple):
    rows: List[Dict]           # pass ui-binding
    derived: List[Dict]        # pass ui-binding-derived
    held: Dict[str, int]       # refusal reason -> rows
    census: Dict[str, int]
    findings: List[str]        # disagreements with Task 7, printed
    collisions: List[str]      # clashes with other proposals files, printed


# ---- the table finder -----------------------------------------------------------------------------

class _Reader:
    def __init__(self, segments):
        self.segs = sorted((int(v), bytes(d)) for v, d in segments)
        self.vas = [v for v, _d in self.segs]
        self._str: Dict[int, Optional[bytes]] = {}

    def _seg(self, addr):
        i = bisect.bisect_right(self.vas, addr) - 1
        if i >= 0:
            va, data = self.segs[i]
            if addr < va + len(data):
                return va, data
        return None

    def is_pointer(self, addr: int) -> bool:
        return self._seg(addr) is not None

    def word(self, addr: int) -> Optional[int]:
        seg = self._seg(addr)
        if seg is None or addr + 4 > seg[0] + len(seg[1]):
            return None
        return struct.unpack_from("<I", seg[1], addr - seg[0])[0]

    def cstr(self, addr: int) -> Optional[bytes]:
        """The NUL-terminated printable (0x20..0x7e) string at `addr`, or None."""
        if addr in self._str:
            return self._str[addr]
        out = None
        seg = self._seg(addr)
        if seg is not None:
            va, data = seg
            off = addr - va
            end = data.find(b"\x00", off, off + MAX_STRING + 1)
            if end > off and all(0x20 <= c < 0x7f for c in data[off:end]):
                out = data[off:end]
        self._str[addr] = out
        return out


def find_binding_tables(side, min_rows: int = MIN_ROWS, strides: Sequence[int] = STRIDES) -> List[Table]:
    """Every run of >= `min_rows` (string pointer, function pointer) rows in `side`'s image, by shape only.

    `side` is an `address_matcher.Side` (its `starts`, `name` and `image.segments` are read). A pair is two
    aligned words: a pointer to a NUL-terminated printable string that is not itself a function start (r0001
    has arrays of function pointers whose code bytes read as "g"), then a function start of `side`. A run is
    pairs at a fixed stride; the first row that is not a pair (a function word that is not a start, a string
    word that is not a string) ends it. Strides are tried shortest first and a run whose pairs a shorter
    stride already covered is dropped (a stride-8 table also reads as two stride-16 half-runs). A table's
    `addr` is its first row's start: when the stride leaves room for it and the word before every pair is not
    a pointer into the image (the row id), that word begins the row (`lead` = 4)."""
    rd = _Reader(side.image.segments)
    starts = side.starts
    pairs: Dict[int, Tuple[bytes, int]] = {}
    for va, data in rd.segs:
        skip = (-va) % 4
        n = (len(data) - skip) // 4
        if n < 2:
            continue
        ws = struct.unpack_from("<%dI" % n, data, skip)
        for i in range(n - 1):
            fn = ws[i + 1]
            if fn in starts and ws[i] not in starts:        # a function start is code, not a string
                s = rd.cstr(ws[i])
                if s is not None:
                    pairs[va + skip + 4 * i] = (s, fn)
    covered = set()
    tables = []
    ordered = sorted(pairs)
    for stride in sorted(strides):
        for p in ordered:
            if p - stride in pairs:
                continue
            run = [p]
            while run[-1] + stride in pairs:
                run.append(run[-1] + stride)
            if len(run) < min_rows or covered.issuperset(run):
                continue
            covered.update(run)
            lead = 0
            if stride >= 12:
                before = [rd.word(q - 4) for q in run]
                if all(w is not None and not rd.is_pointer(w) for w in before):
                    lead = 4
            rows = tuple(Row(q, pairs[q][0], pairs[q][1], side.name.get(pairs[q][1], "")) for q in run)
            tables.append(Table(run[0] - lead, stride, lead, rows))
    return sorted(tables)


# ---- the join -------------------------------------------------------------------------------------

def _text(command: bytes) -> str:
    return command.decode("latin1")


def join(demo_table: Table, our_table: Table, task7: Optional[Dict[int, Tuple[int, str]]] = None,
         named: Optional[Dict[int, str]] = None,
         others: Iterable[Tuple[int, str, str]] = (), holds: Optional[Dict[int, str]] = None) -> Join:
    """The proposals for `our_table`'s handlers, from `demo_table` by command string.

    `task7` is Task 7's pairs as {our address: (demo address, demo name)}; `named` is {our address: name}
    for addresses already named elsewhere (the sidecar); `others` is [(our address, identifier, file)] from
    the other proposals files; `holds` is recomp/socom2_name_holds.csv as {address: held name}: a Task 7 pair
    whose our or demo address is held is no anchor here (S12-R20), and a row it alone would have blocked is
    counted "Task 7 pair overridden by a hold"; a held (address, name) is never proposed. See UI_BINDING_RULE
    for the rule; every refusal is a `held` count."""
    holds = holds or {}
    named = named or {}
    released = {o: v for o, v in (task7 or {}).items() if o in holds or v[0] in holds}
    task7 = {o: v for o, v in (task7 or {}).items() if o not in released}
    by_demo = {d: o for o, (d, _n) in task7.items()}
    by_demo_released = {d: o for o, (d, _n) in released.items()}
    held: Dict[str, int] = {}
    census: Dict[str, int] = {}
    findings: List[str] = []
    collisions: List[str] = []

    def hold(reason: str) -> None:
        held[reason] = held.get(reason, 0) + 1

    def count(key: str, n: int = 1) -> None:
        census[key] = census.get(key, 0) + n

    demo_n: Dict[bytes, int] = {}
    for r in demo_table.rows:
        demo_n[r.string] = demo_n.get(r.string, 0) + 1
    our_n: Dict[bytes, int] = {}
    fn_n: Dict[int, int] = {}
    for r in our_table.rows:
        our_n[r.string] = our_n.get(r.string, 0) + 1
        fn_n[r.function] = fn_n.get(r.function, 0) + 1
    demo_by = {r.string: r for r in demo_table.rows if demo_n[r.string] == 1}
    count("demo table rows", len(demo_table.rows))
    count("our table rows", len(our_table.rows))
    count("demo handlers named UI<command>__",
          sum(1 for r in demo_table.rows if r.name.startswith("UI%s__" % _text(r.string))))

    cands = []   # (our Row, demo Row or None)
    for r in sorted(our_table.rows, key=lambda x: x.function):
        if our_n[r.string] > 1:
            hold("command not unique in our table")
            continue
        if demo_n.get(r.string, 0) > 1:
            hold("command not unique in the demo table")
            continue
        d = demo_by.get(r.string)
        count("joined" if d else "r0001-only commands")
        if fn_n[r.function] > 1:
            hold("our handler is bound to two commands")
            continue
        if not is_placeholder(r.name) or r.function in named:
            hold("our handler is already named")
            continue
        if d is not None:
            if not d.name or is_placeholder(d.name):
                hold("demo handler has no name")
                continue
            rel = released.get(r.function)
            rel_other = by_demo_released.get(d.function)
            if (rel is not None and rel[0] != d.function) or (rel_other is not None and rel_other != r.function):
                count("Task 7 pair overridden by a hold")
            t7 = task7.get(r.function)
            other = by_demo.get(d.function)
            if t7 is not None and t7[0] == d.function:
                count("Task 7 agrees")
            elif t7 is not None or (other is not None and other != r.function):
                count("Task 7 disagrees")
                hold("disagrees with a Task 7 pair")
                if t7 is not None:
                    findings.append("0x%08x command %s: binding says demo 0x%08x %s; Task 7 says demo 0x%08x %s"
                                    % (r.function, _text(r.string), d.function, d.name, t7[0], t7[1]))
                else:
                    findings.append("0x%08x command %s: binding says demo 0x%08x %s; Task 7 pairs that demo "
                                    "function with our 0x%08x" % (r.function, _text(r.string), d.function,
                                                                  d.name, other))
                continue
        elif r.function in released and not released[r.function][1].startswith("UI%s__" % _text(r.string)):
            count("Task 7 pair overridden by a hold")
        elif r.function in task7:
            t7 = task7[r.function]
            if t7[1].startswith("UI%s__" % _text(r.string)):
                count("Task 7 agrees")
            else:
                count("Task 7 disagrees")
                hold("disagrees with a Task 7 pair")
                findings.append("0x%08x command %s (r0001-only): derived UI%s; Task 7 says demo 0x%08x %s"
                                % (r.function, _text(r.string), _text(r.string), t7[0], t7[1]))
                continue
        cands.append((r, d))

    spelling: Dict[str, int] = {}
    for r, d in cands:
        ident = c_identifier(d.name if d else "UI" + _text(r.string))
        spelling[ident] = spelling.get(ident, 0) + 1
    by_ident: Dict[str, List[Tuple[int, str]]] = {}
    by_addr: Dict[int, List[Tuple[str, str]]] = {}
    for addr, ident, path in others:
        by_ident.setdefault(ident, []).append((addr, path))
        by_addr.setdefault(addr, []).append((ident, path))

    rows, derived = [], []
    for r, d in cands:
        ident = c_identifier(d.name if d else "UI" + _text(r.string))
        if spelling[ident] > 1:
            hold("identifier collides after sanitising")
            continue
        if r.function in holds and holds[r.function] in (ident, d.name if d else ident):
            hold("held in recomp/socom2_name_holds.csv")
            continue
        elsewhere = [(a, p) for a, p in by_ident.get(ident, []) if a != r.function]
        if elsewhere:
            hold("identifier spent in another proposals file")
            collisions.append("0x%08x %s: %s" % (r.function, ident, "; ".join(
                "%s proposes it for 0x%08x" % (p, a) for a, p in elsewhere)))
            continue
        differ = [(i, p) for i, p in by_addr.get(r.function, []) if i != ident]
        if differ:
            hold("another proposals file names this handler differently")
            collisions.append("0x%08x %s: %s" % (r.function, ident, "; ".join(
                "%s proposes %s" % (p, i) for i, p in differ)))
            continue
        if by_addr.get(r.function):
            count("agrees with another proposals file")
            for path in sorted({p for _i, p in by_addr[r.function]}):
                count("agrees with " + os.path.basename(path))
        if d is not None:
            if "@unnamed@" in d.name:
                count("proposed from an anonymous-namespace demo handler")
            rows.append({"Address": "0x%08x" % r.function, "Current": r.name, "Proposed": ident,
                         "Mangled": d.name, "Pass": PASS, "Score": "%.2f" % SCORE,
                         "Evidence": "binding table row: command %s -> demo %s" % (_text(r.string), d.name),
                         "DemoAddr": "0x%08x" % d.function})
        else:
            derived.append({"Address": "0x%08x" % r.function, "Current": r.name, "Proposed": ident,
                            "Mangled": "", "Pass": PASS_DERIVED, "Score": "%.2f" % SCORE_DERIVED,
                            "Evidence": "derived from the command string %s; no demo counterpart"
                                        % _text(r.string),
                            "DemoAddr": ""})
    count("proposed " + PASS, len(rows))
    count("proposed " + PASS_DERIVED, len(derived))
    return Join(rows, derived, held, census, findings, collisions)


# ---- the files ------------------------------------------------------------------------------------

def header(path: str, demo_table: Table, our_table: Table, res: Join, extra: Sequence[str] = ()) -> List[str]:
    """The `#` lines above a proposals file's column line (research/45 sec 8's convention): what the file is,
    the rule verbatim, the two tables found, and the counts the file's contents depend on."""
    lines = ["%s -- Sprint 12 Task 14 proposals (docs/research/55-class-inventory.md sec 4.2, S12-R15)." % path,
             "PROPOSALS ONLY: recomp/socom2_ghidra.csv and recomp/socom2_names.csv are unchanged; the applier",
             "(Task 3) writes the sidecar. Addresses are OURS (r0001); names come from the SOCOM 1 demo's .symtab",
             "(pass %s) or from r0001's own command string (pass %s)." % (PASS, PASS_DERIVED), ""]
    lines += textwrap.wrap(UI_BINDING_RULE, 110)
    lines += ["",
              "tables: demo 0x%08x, %d rows, stride %d; r0001 0x%08x, %d rows, stride %d"
              % (demo_table.addr, len(demo_table.rows), demo_table.stride,
                 our_table.addr, len(our_table.rows), our_table.stride),
              "proposed: %s %d, %s %d" % (PASS, len(res.rows), PASS_DERIVED, len(res.derived)),
              "census: " + "; ".join("%s %d" % kv for kv in sorted(res.census.items())),
              "refused: " + ("; ".join("%s %d" % kv for kv in sorted(res.held.items())) or "none")]
    lines += list(extra)
    return lines


def write_proposals(path: str, rows: Sequence[Dict], lines: Sequence[str]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    with open(path, "w", newline="") as fh:
        for line in lines:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def read_others(paths: Iterable[str]) -> List[Tuple[int, str, str]]:
    """[(address, Proposed, path)] from other proposals files (`#` lines skipped)."""
    out = []
    for path in paths:
        with open(path, newline="") as fh:
            lines = [ln for ln in fh if not ln.startswith("#")]
        for row in csv.DictReader(lines):
            if row.get("Address") and row.get("Proposed"):
                out.append((int(row["Address"], 16), row["Proposed"], path))
    return out


_R11_ROW = re.compile(r"`([A-Za-z][A-Za-z0-9/\s]*)`\s+(0x[0-9a-fA-F]+(?:/0x[0-9a-fA-F]+)*)")


def research11_rows(text: str) -> List[Tuple[str, int]]:
    """research/11 sec 2(a)'s (command, r0001 handler) rows, read from the note's online paragraph (the one
    that begins "The script bindings in the"): "`Name` 0xADDR" and "`A/B/C` 0xA/0xB/0xC", where B and C
    carry A's prefix (A without its last CamelCase word: `NetCnfInit/Uninit` -> NetCnfInit, NetCnfUninit)."""
    i = text.find("The script bindings in the")
    if i < 0:
        return []
    para = text[i:text.find("\n\n", i)]
    out = []
    for m in _R11_ROW.finditer(para):
        names = ["".join(n.split()) for n in m.group(1).split("/")]
        addrs = [int(a, 16) for a in m.group(2).split("/")]
        if len(names) != len(addrs):
            continue
        words = re.findall(r"[A-Z][a-z0-9]*|[A-Z]+(?![a-z])", names[0])
        prefix = "".join(words[:-1])
        out.extend((n if k == 0 else prefix + n, a) for k, (n, a) in enumerate(zip(names, addrs)))
    return out


# ---- the CLI --------------------------------------------------------------------------------------

def _pick(tables: List[Table], side_name: str) -> Tuple[Optional[Table], str]:
    if not tables:
        return None, "FINDING: no binding table found in the %s image" % side_name
    best = max(tables, key=lambda t: len(t.rows))
    want = NOTE_TABLES[side_name]
    got = (best.addr, len(best.rows))
    verdict = "matches research/55" if got == want else "DIFFERS from research/55's 0x%08x/%d" % want
    return best, "%s table: 0x%08x, %d rows, stride %d (%s)" % (side_name, best.addr, len(best.rows),
                                                                  best.stride, verdict)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the ui-binding lever (Sprint 12 Task 14)")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("matches_json", help="Task 7's game/demo_symbol_matches.json")
    ap.add_argument("--out", required=True, help="CSV: the %s proposals" % PASS)
    ap.add_argument("--derived-out", required=True, help="CSV: the %s proposals" % PASS_DERIVED)
    ap.add_argument("--sidecar", default="recomp/socom2_names.csv",
                    help="names already applied (skipped when absent)")
    ap.add_argument("--others", default="game/demo_symbol_renames*.csv",
                    help="glob of the other proposals files checked for collisions")
    ap.add_argument("--holds", default="recomp/socom2_name_holds.csv",
                    help="held (address, name) rows (skipped when absent)")
    ap.add_argument("--research11", default="docs/research/11-recom-applicability.md")
    args = ap.parse_args(argv)

    missing = [p for p in (args.demo_elf, args.our_elf, args.our_csv, args.matches_json) if not os.path.exists(p)]
    if missing:
        for path in missing:
            print("NO-DATA: missing %s" % path)
        print("NO-DATA: the demo ELFs are git-ignored; see docs/research/44-demo-symbols.md sec 1")
        return 2
    try:
        demo_rows, demo_segs = gsm.load_demo(args.demo_elf)
        our_rows, our_segs = gsm.load_ours(args.our_elf, args.our_csv)
    except ValueError as exc:
        print("NO-DATA: %s" % exc)
        return 2

    # Task 7's pairs with their demo addresses: the matcher re-run, checked against the json
    details: Dict = {}
    pairs = gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    with open(args.matches_json) as fh:
        js = json.load(fh)
    if sorted((p["name"], int(p["addr"], 16)) for p in js["pairs"]) != sorted((n, a) for n, a, _s in pairs):
        print("FINDING: the re-run matcher disagrees with %s; refusing" % args.matches_json)
        return 1
    anchors = anchors_from_details(details)
    proved = proved_anchors(anchors)
    name_of = {(info["demo_addr"], addr): name for (name, addr), info in details.items()}
    task7 = {o: (d, name_of[(d, o)]) for d, o, _how in anchors}

    demo_side = am.Side(demo_rows, demo_segs)
    our_side = am.Side(our_rows, our_segs)
    demo_tables = find_binding_tables(demo_side)
    our_tables = find_binding_tables(our_side)
    report = ["runs of >= %d (string, function) rows: demo %d (%s); r0001 %d (%s)"
              % (MIN_ROWS, len(demo_tables), ", ".join("0x%08x/%d/s%d" % (t.addr, len(t.rows), t.stride)
                                                       for t in demo_tables),
                 len(our_tables), ", ".join("0x%08x/%d/s%d" % (t.addr, len(t.rows), t.stride)
                                            for t in our_tables))]
    demo_t, line_d = _pick(demo_tables, "demo")
    our_t, line_o = _pick(our_tables, "r0001")
    report += [line_d, line_o]
    for line in report:
        print(line)
    if demo_t is None or our_t is None or "DIFFERS" in line_d + line_o:
        print("FINDING: the located tables are not research/55's; refusing to propose")
        return 1

    named = {}
    if args.sidecar and os.path.exists(args.sidecar):
        named = {a: r["Name"] for a, r in name_provenance.read(args.sidecar).items()
                 if not is_placeholder(r["Name"])}
    holds = {}
    if args.holds and os.path.exists(args.holds):
        with open(args.holds, newline="") as fh:
            holds = {int(r["Address"], 16): r["Proposed"] for r in csv.DictReader(fh)}
    mine = {os.path.realpath(args.out), os.path.realpath(args.derived_out)}
    other_paths = sorted(p for p in glob.glob(args.others) if os.path.realpath(p) not in mine)
    others = read_others(other_paths)

    res = join(demo_t, our_t, task7=task7, named=named, others=others, holds=holds)

    agree_proved = sum(1 for r in res.rows if int(r["Address"], 16) in task7
                       and task7[int(r["Address"], 16)][0] in proved)
    r11 = []
    if args.research11 and os.path.exists(args.research11):
        with open(args.research11, encoding="utf-8") as fh:
            r11 = research11_rows(fh.read())
    ours_by_cmd = {_text(r.string): r.function for r in our_t.rows}
    r11_agree = sum(1 for c, a in r11 if ours_by_cmd.get(c) == a)
    r11_disagree = [(c, a) for c, a in r11 if c in ours_by_cmd and ours_by_cmd[c] != a]
    r11_absent = [c for c, _a in r11 if c not in ours_by_cmd]

    extra = [line_d, line_o, report[0],
             "Task 7 pairs on a table handler: agree %d (%d of them non-prefix anchors), disagree %d; "
             "Task 7 pair overridden by a hold: %d (holds file %s, %d rows)"
             % (res.census.get("Task 7 agrees", 0), agree_proved, res.census.get("Task 7 disagrees", 0),
                res.census.get("Task 7 pair overridden by a hold", 0), args.holds, len(holds)),
             "research/11 sec 2(a) rows: %d; the r0001 table agrees on %d, disagrees on %d, lacks %d"
             % (len(r11), r11_agree, len(r11_disagree), len(r11_absent)),
             "other proposals files checked: %s; collisions %d"
             % (", ".join(other_paths) or "none", len(res.collisions))]
    for path, rows, which in ((args.out, res.rows, PASS), (args.derived_out, res.derived, PASS_DERIVED)):
        lines = header(path, demo_t, our_t, res, extra + ["this file: pass %s only" % which])
        try:
            write_proposals(path, rows, lines)
        except ValueError as exc:
            print("NO-DATA: %s" % exc)
            return 2

    print("census: " + "; ".join("%s %d" % kv for kv in sorted(res.census.items())))
    print("refused: " + ("; ".join("%s %d" % kv for kv in sorted(res.held.items())) or "none"))
    for line in extra[3:]:
        print(line)
    for c, a in r11_disagree:
        print("FINDING: research/11 binds %s to 0x%08x, the table to 0x%08x" % (c, a, ours_by_cmd[c]))
    for f in res.findings:
        print("FINDING: Task 7 disagreement: " + f)
    for c in res.collisions:
        print("COLLISION: " + c)
    print("wrote %s (%d rows) and %s (%d rows)" % (args.out, len(res.rows), args.derived_out, len(res.derived)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
