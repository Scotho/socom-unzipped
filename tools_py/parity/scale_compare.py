"""Sprint 7 Task 1c: is a 1280x896 frame the 640x448 frame, or a different render?

The window default moves to 2x (spec Goal 1c), and the only thing that makes that safe to ship is
evidence that the bigger window is a *presentation* scale and not a second rendering path with its
own geometry. So: take the 640x448 gate capture, blow it up by nearest neighbour (the exact
operation an integer present filter performs), and score the mean absolute grey difference against
the 1280x896 capture. A pure upscale scores ~0; the spec's bar is a mean |diff| below 3, which
leaves room for the title loop's animation between the two captures but not for a moved vertex.

Grey, not RGB: the question is geometry, not colour, and a single channel keeps one number to read.
"""
import numpy as np
from PIL import Image


def _grey(path):
    """PNG path -> float32 luma array (H, W)."""
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.float32)


def upsample_nearest(arr, scale):
    """Nearest-neighbour upsample by an integer factor -- every pixel repeated `scale` times on
    each axis, which is what an integer-scale present filter does."""
    if scale < 1:
        raise ValueError("scale must be >= 1, got %r" % (scale,))
    return np.repeat(np.repeat(arr, scale, axis=0), scale, axis=1)


def mean_abs_diff(big_png, small_png, scale):
    """Mean |difference| in grey levels between `big_png` and `small_png` upsampled `scale`x.

    Raises ValueError when the two do not line up after the upsample: a shape mismatch means the
    captures are not the same frame at two scales, and averaging over a cropped overlap would hide
    exactly the failure this check exists to catch."""
    big = _grey(big_png)
    small = upsample_nearest(_grey(small_png), scale)
    if big.shape != small.shape:
        raise ValueError("shape mismatch: %s is %dx%d, %s at %dx is %dx%d"
                         % (big_png, big.shape[1], big.shape[0], small_png, scale,
                            small.shape[1], small.shape[0]))
    return float(np.abs(big - small).mean())
