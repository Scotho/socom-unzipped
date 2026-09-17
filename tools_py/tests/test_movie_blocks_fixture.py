"""Sprint 6 Task 8: `movie_blocks.py` wired into `build.sh test` (which runs this discovery) against a saved
fixture under tests/fixtures/movie/: a few intro-movie presents from a display dump (gpu and shadow layers,
stored as PNG to keep the repo small; the tool reads PPM, so they are rebuilt in a temp directory) and the
furniture map learned from that run. The check is research/16's differential: a block black in the GL target
but not in the shadow VRAM is a missing movie block; a furniture map that grows is corruption being learned.

The fixture's origin is documented in tests/fixtures/movie/README.md; regenerate it from a fresh
PS2X_GS_DUMP_DISPLAY dump when the intro movie, the render target scale or the tool's classifier changes."""
import glob
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "movie")


def _ppm_from_png(png_path, ppm_path):
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    with open(ppm_path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % im.size)
        f.write(im.tobytes())


@unittest.skipUnless(os.path.isdir(FIXTURE), "no movie fixture")
class MovieBlocksFixtureTest(unittest.TestCase):
    def test_saved_presents_have_no_missing_blocks_and_the_furniture_did_not_grow(self):
        from tools_py.parity import movie_blocks
        pngs = sorted(glob.glob(os.path.join(FIXTURE, "display_*_gpu.png")))
        self.assertGreaterEqual(len(pngs), 3, "the fixture needs a few movie presents")
        baseline = os.path.join(FIXTURE, "furniture.txt")
        self.assertTrue(os.path.isfile(baseline), "the fixture needs its furniture baseline")
        with tempfile.TemporaryDirectory() as tmp:
            for gpu in pngs:
                stem = os.path.basename(gpu)[:-len("_gpu.png")]
                shadow = os.path.join(FIXTURE, stem + "_shadow.png")
                self.assertTrue(os.path.isfile(shadow), stem)
                _ppm_from_png(gpu, os.path.join(tmp, stem + "_gpu.ppm"))
                _ppm_from_png(shadow, os.path.join(tmp, stem + "_shadow.ppm"))
            out = io.StringIO()
            with redirect_stdout(out):
                rc = movie_blocks.main([tmp, "--furniture-baseline", baseline])
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        self.assertIn("MISSING blocks=0", text)
        self.assertIn("0 blocks are furniture now and were not then", text)


if __name__ == "__main__":
    unittest.main()
