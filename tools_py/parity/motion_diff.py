"""Sprint 6 Task 7: is our player seen moving on the console client? A pure scorer over the PCSX2 window captures
taken at 1 Hz while our instance holds a walk key for `hold_s` seconds, against captures taken while it stood
still: the mean absolute luma difference between consecutive frames. A still scene on the console client differs
by sensor-free amounts (the HUD clock, ~0.1-0.5); our player walking in its view moves whole regions (research/18
section 1's table: 3-10 on the frames either side of a hold)."""
import numpy as np

MOVING_MIN_RATIO = 3.0     # median moving-window diff over median still-window diff
MOVING_MIN_ABS = 1.0       # and at least this much absolute mean |diff| per consecutive pair


def luma(image):
    """PIL image -> float32 luma array."""
    return np.asarray(image.convert("L"), dtype=np.float32)


def consecutive_diffs(frames):
    """[luma arrays] -> [mean |a - b|] for each consecutive pair (empty for fewer than two frames)."""
    out = []
    for a, b in zip(frames, frames[1:]):
        h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        out.append(float(np.abs(a[:h, :w] - b[:h, :w]).mean()))
    return out


def motion_verdict(still_frames, moving_frames, min_ratio=MOVING_MIN_RATIO, min_abs=MOVING_MIN_ABS):
    """-> (moving: bool, detail) from two frame lists (luma arrays). The moving window's median consecutive
    diff must be at least `min_abs` and at least `min_ratio` times the still window's."""
    still = consecutive_diffs(still_frames)
    moving = consecutive_diffs(moving_frames)
    if len(moving) < 2:
        return False, f"NO-DATA moving window has {len(moving)} pairs (need 2)"
    still_med = float(np.median(still)) if still else 0.0
    moving_med = float(np.median(moving))
    ok = moving_med >= min_abs and moving_med >= min_ratio * max(still_med, 1e-6)
    detail = (f"moving median |diff| {moving_med:.2f} vs still {still_med:.2f} "
              f"(need >= {min_abs} and >= {min_ratio}x still): {'MOVING' if ok else 'not moving'}")
    return ok, detail
