"""Sprint 9 Q0 (2026-09-20): read the mixer's stream-event trace out of a run log and turn it into the two numbers
the mission music needed and never had -- the hole at every stem boundary, and the frames a stem spent starved.

The trace (snd989::StreamEvent, snd989_mixer.cpp) is on the mixer's OUTPUT-FRAME clock, the clock PS2X_AUDIO_DUMP's
WAV is written on, so every frame here is a WAV offset:
    [audio] 989snd stream <handle> start frame=N detail=0
    [audio] 989snd stream <handle> done frame=N detail=0
    [audio] 989snd stream <handle> UNDERRUN frame=N silent=M
Each stream's group and sector come from the snd_PlayVAGStreamByLoc line the IOP module printed just before it,
matched by the handle the call returned. Group 1 is the mission music.

    python -m tools_py.parity.stream_events <run.log> [--group 1]
"""
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

RATE = 48000

_PLAY = re.compile(r"snd_PlayVAGStreamByLoc \(fno[^\[]*\[([^\]]*)\] -> (0x[0-9a-fA-F]+)")
_EVENT = re.compile(r"\[audio\] 989snd stream ([0-9a-fA-F]+) (start|done|UNDERRUN) frame=(\d+) (?:detail|silent)=(\d+)")


@dataclass
class Stream:
    handle: int
    group: Optional[int] = None
    sector: Optional[int] = None
    start: Optional[int] = None
    done: Optional[int] = None
    underruns: List[tuple] = field(default_factory=list)   # (frame, silent frames)

    @property
    def silent_frames(self) -> int:
        return sum(n for _, n in self.underruns)

    @property
    def played_frames(self) -> Optional[int]:
        return None if self.start is None or self.done is None else self.done - self.start


@dataclass
class Gap:
    prev: int
    next: int
    frames: int

    @property
    def ms(self) -> float:
        return self.frames * 1000.0 / RATE


def read(path: str) -> List[Stream]:
    """Every stream the log traced, in order of first appearance."""
    order: List[Stream] = []
    by_handle: Dict[int, Stream] = {}
    pending: Dict[int, tuple] = {}   # handle -> (group, sector) from the play call, until its start line arrives

    def get(handle: int) -> Stream:
        st = by_handle.get(handle)
        if st is None or st.done is not None:   # a handle the game reuses starts a new stream
            st = Stream(handle)
            by_handle[handle] = st
            order.append(st)
        return st

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _PLAY.search(line)
            if m:
                args = [int(x, 16) for x in m.group(1).split(",")]
                handle = int(m.group(2), 16)
                # In a real run the mixer's start line has already been printed (it is emitted inside the RPC,
                # before the module logs the call), so the stream usually exists by now and lacks its group.
                st = by_handle.get(handle)
                if st is not None and st.group is None:
                    st.group, st.sector = args[4], args[0]
                else:
                    pending[handle] = (args[4], args[0])
                continue
            m = _EVENT.search(line)
            if not m:
                continue
            handle, kind, frame, n = int(m.group(1), 16), m.group(2), int(m.group(3)), int(m.group(4))
            if kind == "start":
                st = Stream(handle)
                by_handle[handle] = st
                order.append(st)
                st.start = frame
                if handle in pending:
                    st.group, st.sector = pending.pop(handle)
            elif kind == "done":
                get(handle).done = frame
            else:
                get(handle).underruns.append((frame, n))
    return order


def music_gaps(streams: List[Stream], group: int = 1) -> List[Gap]:
    """The hole between one stem's done and the next stem's start, for consecutive streams of `group`."""
    stems = [s for s in streams if s.group == group and s.start is not None]
    out: List[Gap] = []
    for a, b in zip(stems, stems[1:]):
        if a.done is None or b.start < a.done:
            continue   # overlapping (a crossfade) or unfinished: not a boundary
        out.append(Gap(a.handle, b.handle, b.start - a.done))
    return out


def report(streams: List[Stream], group: int = 1) -> str:
    stems = [s for s in streams if s.group == group]
    gaps = music_gaps(streams, group)
    worst = max(gaps, key=lambda g: g.frames) if gaps else None
    worst_txt = f"worst={worst.ms:.1f}ms ({worst.prev:08x}->{worst.next:08x})" if worst else "worst=none"
    lines = [f"streams={len(streams)} group{group}_stems={len(stems)} boundaries={len(gaps)} {worst_txt}"
             f" underrun_frames={sum(s.silent_frames for s in stems)}"]
    for g in gaps:
        lines.append(f"  gap {g.prev:08x}->{g.next:08x} {g.frames} frames = {g.ms:.1f} ms")
    for s in stems:
        if s.underruns:
            lines.append(f"  starved {s.handle:08x} sector {s.sector:x}: {len(s.underruns)} underruns, "
                         f"{s.silent_frames} silent frames ({s.silent_frames * 1000.0 / RATE:.1f} ms)")
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-1]); return 2
    group = int(argv[argv.index("--group") + 1]) if "--group" in argv else 1
    print(report(read(argv[1]), group))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
