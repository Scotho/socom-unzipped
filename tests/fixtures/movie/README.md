# Movie-block fixture

Seven presents from a title-stage display dump (`PS2X_GS_DUMP_DISPLAY=<dir>:3:70`, stamp `s6_movie_dump3`,
2026-09-17, the exe of commit 3ee438b): `display_003s` is a full-screen movie present (the GL target mirrors the
shadow VRAM: the differential check of research/16 runs on it), the six `display_023s`..`display_033s` presents are the title
menu over its background video (menu furniture drawn by the GPU, learned into `furniture.txt`). Each present is
its `gpu` and `shadow` layer as PNG; `tools_py/tests/test_movie_blocks_fixture.py` rebuilds the PPM pairs and runs
`movie_blocks.py` with `--furniture-baseline furniture.txt`: no missing block, no furniture growth.

Regenerate from a fresh dump when the intro, the render-target scale or the classifier changes:
`python -m tools_py.parity.movie_blocks <dumpdir> --write-furniture tests/fixtures/movie/furniture.txt` on the same
selection of presents, then convert the pairs to PNG.
