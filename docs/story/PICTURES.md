# Pictures in the story — the inventory (spec §5.3)

One row per image `docs/STORY.md` shows. Every picture is a frame the project's own program produced, at the
resolution it runs, uncropped except to remove a desktop; none is an asset lifted out of the disc. A video row is the same thing at
length: a screen recording of the program's own windows, cropped to remove the desktop and cut down, with a poster frame beside it. The four that were
already tracked under `docs/research/assets/` are copied here so the story has one published path. This table is
also the input to Sprint 11 Goal 1's disc-derived decision table and Goal 5's accreditation inventory. **The line is
the owner's** (spec §9 Q1); `tools_py/story/cite.py` only keeps this list and the document in step.

| File | Entry | Bytes | Copied from | What it is |
|---|---|---:|---|---|
| `2026-09-08-online-lobby.png` | 2026-09-08 — The project's own program gets online | 70,290 | `logs/parity/ours_login/09_lobby.png` | our program's window, run ours_login |
| `2026-09-13-first-kill.png` | 2026-09-13 — The first kill | 491,420 | `docs/research/assets/22-first-kill.png` | our program's two windows, run s5_t5_ladder2; already tracked as docs/research/assets/22-first-kill.png |
| `2026-09-14-grey-hill-before.png` | 2026-09-14 — Two defects the owner spotted | 326,272 | `docs/research/assets/31-console-dump-gl-replay-before.png` | our renderer's output over a console-recorded command stream; already tracked as docs/research/assets/31-console-dump-gl-replay-before.png |
| `2026-09-16-brighten-fixed.png` | 2026-09-16 — Every frame was 1.73 times too dark | 435,440 | `docs/research/assets/31-console-dump-gl-replay-fixed.png` | our renderer's output over the same command stream; already tracked as docs/research/assets/31-console-dump-gl-replay-fixed.png |
| `2026-09-17-launcher-first-cut.png` | 2026-09-17 — A launcher, and a folder you can copy | 30,842 | `docs/research/assets/launcher-first-cut.png` | our launcher's window; already tracked as docs/research/assets/launcher-first-cut.png |
| `2026-09-17-foxhunt-map-select.png` | 2026-09-17 — Twenty maps in one night | 187,316 | `logs/parity/ours_control_foxhunt_guard/A_14b_map_foxhunt.png` | our program's window, run ours_control_foxhunt_guard |
| `2026-09-18-linux-boot-dialog.png` | 2026-09-18 — The game runs on Linux | 41,872 | `logs/parity/vm/latest_frame.png` | our program's window in the Linux VM, logs/parity/vm |
| `2026-09-19-launcher-controller-page.png` | 2026-09-19 — The launcher gets a face | 107,817 | `logs/parity/launcher_ui/controller_1100x700.png` | our launcher's window, run launcher_ui |
| `2026-09-19-hosted-kill-round-1.png` | 2026-09-19 — A server of its own, on the internet | 307,490 | `logs/parity/s8_hosted_kill/A_kill_r1.png` | our program's window, run s8_hosted_kill; frame inspected, carries the test persona only |
| `2026-09-20-playtest-mission.png` | 2026-09-20 — The first build made for a person to play | 274,392 | `logs/parity/gate/s9_p7_playtest_gate/mission/final.png` | our program's window, gate s9_p7_playtest_gate |
| `2026-09-20-mixed-match.png` | A console and a PC in the same match | 220,003 | `logs/parity/mixed2_pcsx2_hosts_g/play02.png` | our program's window, run mixed2_pcsx2_hosts_g |
| `2026-09-11-the-dialog-the-gate-answered-blindly.png` | The check that had been passing for free | 128,879 | `D:/socom_archive/gate/first/mission/final.png` | our program's window, the first gate run (archived to D:\\socom_archive\\gate\\first on 2026-09-13; logs/parity/gate_first.out is its surviving readout) |
| `2026-09-12-the-gate-stuck-on-a-card-prompt.png` | Four times the pixels, and no sharper HUD | 183,516 | `D:/socom_archive/gate/pf_point_stuck/title/final.png` | our program's window, gate pf_point_stuck (archived to D:\socom_archive\gate on 2026-09-13) |
| `2026-09-07-briefing-drawn-at-the-origin.png` | The console becomes the marking scheme | 311,091 | `logs/parity/runs/ours_a/s05_CROSS.png` | our program's window, run ours_a, logs/parity/runs/ours_a |
| `2026-09-05-menu-with-no-captions.png` | The main menu, at full speed | 127,064 | `logs/parity/runs/ours_a/s02_CROSS.png` | our program's window, run ours_a (2026-09-07), logs/parity/runs/ours_a |
| `2026-09-14-the-clipped-terrain-the-owner-spotted.png` | Two things the owner spotted | 287,637 | `D:/socom_archive/gate/20260912_143356/mission/final.png` | our program's window, gate 20260912_143356 (archived to D:\socom_archive\gate on 2026-09-13) |
| `2026-09-21-online-kill.mp4` | 2026-09-21 — One round, on film | 10,822,738 | `E:/ForClaude/online_kill.mp4` (a 4:14 screen recording of the desktop, 70.9 MB) | our program's two windows, one round on the hosted server, both clients agent-driven; the whole recording, cropped to the two windows (1022x378 at 49,216) and re-encoded (H.264 CRF 25); its poster `2026-09-21-online-kill.png` (323,661 bytes) is the frame at 3:42.5 of the recording, the killfeed on both screens |

Total: 16 pictures and 1 video with its poster, 14,677,740 bytes.
