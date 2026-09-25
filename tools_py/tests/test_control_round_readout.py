"""Sprint 13 -- control_round_readout: the verdict lines of C3's UDP-shift round and V7's paused-peer round, over
synthetic log fragments in the exe's own formats (the install and port lines of game_overrides_socom2.cpp, libnetb's
trace lines, the FreezeFields sampler line, EeScheduler's [clock] line, the GS backend's backpressure line).
Addresses are RFC 5737 documentation addresses."""
import io
import json
import os
import struct
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

from tools_py.parity import control_round_readout as R
from tools_py.parity import verdict_core as vc

GETTER_R0001 = R.GETTER_GLOBAL["r0001"]
GETTER_R0004 = R.GETTER_GLOBAL["r0004"]


def install_line(getter, port=3660, at=0x620648):
    return ("[socom2] rt_net config init at 0x%x done on the host (getter global 0x%x), peer UDP port %d"
            % (at, getter, port))


def ip_le(dotted):
    return bytes(reversed([int(x) for x in dotted.split(".")]))


def record(int_ip, int_port, ext_ip, ext_port):
    """The DME client record's NetAddress pair: ip(4, LE) port(2, LE) 00 00 ip(4, LE) port(2, LE)."""
    return ip_le(int_ip) + struct.pack("<H", int_port) + b"\0\0" + ip_le(ext_ip) + struct.pack("<H", ext_port)


def tcp_send(payload):
    return "[socom2/libnetb] tcp send cid 3 len=%d -> %d [%s ]" % (
        len(payload), len(payload), " ".join("%02x" % b for b in payload))


def dash(payload):
    return "DME recv 00-18: " + "-".join("%02X" % b for b in payload)


PAD = bytes(range(0x20, 0x30))


class UdpShiftCriteria(unittest.TestCase):
    def test_install_line_passes_with_the_revision_getter(self):
        self.assertEqual(R.install_verdict(install_line(GETTER_R0001)).status, R.PASS)
        self.assertEqual(R.install_verdict(install_line(GETTER_R0004, at=0x627f38), "r0004").status, R.PASS)

    def test_install_line_with_the_other_revision_getter_fails(self):
        v = R.install_verdict(install_line(GETTER_R0004))
        self.assertEqual(v.status, R.FAIL)
        self.assertIn("wanted getter global", v.detail)

    def test_install_left_alone_is_named(self):
        v = R.install_verdict("[socom2] the routine at 0x620648 is not the rt_net config init this runtime knows; left "
                              "alone, peer UDP port shift stays host-side only")
        self.assertEqual(v.status, R.FAIL)
        self.assertIn("is not the rt_net config init", v.detail)

    def test_port_line(self):
        self.assertEqual(R.port_verdict("[socom2] rt_net base peer UDP port -> 3660 (PS2X_SOCOM2_UDP_SHIFT)").status,
                         R.PASS)
        self.assertEqual(R.port_verdict("[socom2] rt_net base peer UDP port -> 3658 (PS2X_SOCOM2_UDP_SHIFT)").status,
                         R.FAIL)
        self.assertEqual(R.port_verdict("nothing").status, R.FAIL)

    def test_a_unshifted(self):
        self.assertEqual(R.unshifted_verdict("[socom2/hostnet] Winsock ready").status, R.PASS)
        self.assertEqual(R.unshifted_verdict(install_line(GETTER_R0001)).status, R.FAIL)

    def test_dme_record_from_the_client_hex_both_slots(self):
        b = tcp_send(PAD + record("192.0.2.10", 3660, "192.0.2.10", 3660) + PAD)
        v = R.dme_record_verdict(None, b)
        self.assertEqual(v.status, R.PASS)
        self.assertIn("both slots :3660", v.detail)
        self.assertIn("192.0.2.10:3660", v.detail)

    def test_dme_record_external_slot_is_the_servers_observation(self):
        b = tcp_send(PAD + record("192.0.2.10", 3660, "203.0.113.7", 61234))
        v = R.dme_record_verdict(None, b)
        self.assertEqual(v.status, R.PASS)
        self.assertIn("external :61234", v.detail)

    def test_the_pre_fix_record_fails(self):
        dme = dash(PAD + record("192.0.2.10", 3658, "192.0.2.10", 3658)) + "\n" + \
            dash(PAD + record("192.0.2.10", 3658, "192.0.2.10", 3660))
        v = R.dme_record_verdict(dme, "")
        self.assertEqual(v.status, R.FAIL)
        self.assertIn("pre-fix", v.detail)

    def test_the_server_log_is_read_first_and_a_records_are_ignored(self):
        dme = dash(PAD + record("192.0.2.10", 3658, "198.51.100.4", 3658)) + "\n" + \
            dash(PAD + record("192.0.2.10", 3660, "198.51.100.4", 3660))
        v = R.dme_record_verdict(dme, tcp_send(b"\x17" * 40))
        self.assertEqual(v.status, R.PASS)
        self.assertIn("server's DME log", v.detail)

    def test_encrypted_client_bytes_are_no_data(self):
        v = R.dme_record_verdict(None, tcp_send(bytes((i * 37) & 0xFF for i in range(96))))
        self.assertEqual(v.status, R.NO_DATA)
        self.assertIn("server-dme.log", v.detail)

    def test_a_addresses_b_at_3660_only(self):
        ok = "\n".join("[socom2/libnetb] udp peer send #%d to 192.0.2.10:3660 ra=0x0 aa bb" % i for i in (1, 2))
        self.assertEqual(R.peer_address_verdict(ok).status, R.PASS)
        bad = ok + "\n[socom2/libnetb] udp peer send #3 to 192.0.2.10:3658 ra=0x0 aa"
        self.assertEqual(R.peer_address_verdict(bad).status, R.FAIL)
        self.assertEqual(R.peer_address_verdict("").status, R.NO_DATA)

    def test_lobby(self):
        self.assertEqual(R.lobby_verdict(" 120.0s B_[lobby] teams: seals=143 terrorists=144 -> ok (attempt 1)").status,
                         R.PASS)
        self.assertEqual(R.lobby_verdict(" 300.1s A_LOBBY class=ok").status, R.PASS)
        self.assertEqual(R.lobby_verdict("RESULT LOBBY-FAIL join:list detail").status, R.FAIL)
        self.assertEqual(R.lobby_verdict(None).status, R.NO_DATA)

    def _round(self, b_extra="", dme=None, r0004=None):
        a = "[ret] NetIdle #0 v0=0x0\n[ret] NetIdle #1 v0=0x10\n" \
            "[socom2/libnetb] udp peer send #1 to 192.0.2.10:3660 ra=0x0 aa"
        b = "\n".join([install_line(GETTER_R0001), "[socom2] rt_net base peer UDP port -> 3660 (PS2X_SOCOM2_UDP_SHIFT)",
                       "[ret] NetIdle #0 v0=0x0", b_extra])
        drive = " 120.0s B_[lobby] teams: seals=1 terrorists=1 -> ok (attempt 1)\n" \
                "RESULT CONTROL-ROUND round_ended=yes"
        return R.udp_shift(a, b, drive, r0004, dme)

    def test_the_whole_round_passes(self):
        verdicts, info, overall = self._round(tcp_send(PAD + record("192.0.2.10", 3660, "192.0.2.10", 3660)),
                                              r0004=install_line(GETTER_R0004, at=0x627f38))
        self.assertEqual(overall, R.PASS, [R.fmt("udp-shift", x) for x in verdicts])
        self.assertIn("INFO udp-shift netidle_ret A=2 B=1", info)
        self.assertTrue(any("RESULT CONTROL-ROUND" in ln for ln in info))

    def test_a_addresses_b_carries_the_round_while_the_record_is_no_data(self):
        verdicts, info, overall = self._round()
        self.assertEqual({x.name: x.status for x in verdicts}["dme-record"], R.NO_DATA)
        self.assertEqual(overall, R.PASS)
        self.assertTrue(any("read client-side" in ln for ln in info), info)

    def test_no_record_and_no_peer_sends_is_incomplete_not_pass(self):
        a = ""
        b = install_line(GETTER_R0001) + "\n[socom2] rt_net base peer UDP port -> 3660 (x)"
        _, _, overall = R.udp_shift(a, b, " 1.0s B_[lobby] teams: seals=1 terrorists=1 -> ok (attempt 1)")
        self.assertEqual(overall, "INCOMPLETE")

    def test_a_sending_to_its_own_port_fails_the_round(self):
        a = "[socom2/libnetb] udp peer send #16 to 192.0.2.10:3658 ra=0x0 aa"
        b = install_line(GETTER_R0001) + "\n[socom2] rt_net base peer UDP port -> 3660 (x)"
        _, _, overall = R.udp_shift(a, b, " 1.0s B_[lobby] teams: seals=1 terrorists=1 -> ok (attempt 1)")
        self.assertEqual(overall, R.FAIL)

    def test_a_wrong_r0004_getter_fails_the_round(self):
        _, _, overall = self._round(tcp_send(PAD + record("192.0.2.10", 3660, "192.0.2.10", 3660)),
                                    r0004=install_line(GETTER_R0001))
        self.assertEqual(overall, R.FAIL)


# --- paused-peer --------------------------------------------------------------------------------------------------
def sampler(t, vsync, seq, ee, net_wait=(0, 0), net_park=None):
    park = "" if net_park is None else " net_park=%d/%d" % net_park
    return ("[pc-sampler] live pc=0x180008 ra=0x0 sp=0x1fffff0 t=%.2f vsync=%d ee=%.2f seq=%d dpc=0x1c6730 idle=26 "
            "bp_pending=0 bp_waiters=0 bp_wait_ms=0 net_wait=%d/%d%s running=0 threads: [1 pc=0x1c6730 ra=0x1c6730 "
            "sp=0x1edfe00 st=2 prio=0 wait=4/0]" % (t, vsync, ee, seq, net_wait[0], net_wait[1], park))


def words_of(s):
    raw = s.encode("ascii") + b"\0" * (8 - len(s))
    return struct.unpack("<2I", raw[:8])


def peek(clock_s, clock_str):
    f = struct.unpack("<I", struct.pack("<f", clock_s))[0]
    w0, w1 = words_of(clock_str)
    return "[peek] @%x: %08x(%g) @%x: %08x(0) %08x(0)" % (vc.ROUND_TIME_ADDR, f, clock_s, vc.CLOCK_STRING_ADDR, w0, w1)


def clock_line(host):
    return ("[clock] host=%.1fs eeCycle=%.3fs T0=1 mode=0x0 nextDeadline=0.000s vsyncTick=1 checkpoints=1 gap_ms=0 "
            "excluded_ms=0 lost_ms=0" % (host, host))


def gs_line(frames):
    return ("[gs-gl stats] backpressure N=3 guest_frames=%d waits=0 wait_ms=0.0 timeouts=0 skipped=0 unlatched=0 "
            "pending=0 pending_bytes=0 dropped_cmds=0 dropped_bytes=0 hard_waits=0 stall_engaged=0 "
            "stall_absorbed_cmds=0 stall_absorbed_bytes=0 stall_reanchor_bytes=0" % frames)


def window(n=12, moving=True, parked=True, hole=False, net_wait=False, v7=True):
    lines = []
    for i in range(n):
        t = 100.0 + i * 0.25
        vsync = 6000 + (i * 15 if not hole else 0)
        seq = 400 + (i * 5 if not hole else 0)
        ee = 90.0 + (i * 0.25 if not hole else 0)
        park = ((1 if parked else 0), 200 + i * 250) if v7 else None
        nw = (1, 10000) if net_wait else (0, 0)
        lines.append(sampler(t, vsync, seq, ee, nw, park))
        clock_s = 30.0 + (i * 0.25 if moving else 0)
        lines.append(peek(clock_s, "04:%02d" % (30 - (i // 4 if moving else 0))))
        if i % 4 == 0 and not hole:
            lines.append(clock_line(500.0 + i * 0.25))
        if i % 6 == 0:
            lines.append(gs_line(60 if moving else 0))
    return lines


def frames(moving):
    rng = np.random.default_rng(3)
    base = rng.integers(0, 255, size=(40, 60)).astype(np.uint8)
    imgs, out = {}, []
    for i in range(6):
        img = base.copy()
        if moving:
            img[:20, :20] = (i * 40) % 255
        imgs["f%d" % i] = img
        out.append({"phase": "pause", "path": "f%d" % i, "mtime": 1000.0 + (i if moving else 0)})
    return out, imgs.__getitem__


class PausedPeerCriteria(unittest.TestCase):
    def test_sampler_rows_read_net_park_and_leave_it_none_before_v7(self):
        rows = R.sampler_rows([sampler(1.0, 10, 2, 0.5, (0, 0), (1, 250)), sampler(1.25, 25, 7, 0.75)])
        self.assertEqual(rows[0]["net_park"], 1)
        self.assertEqual(rows[0]["net_park_ms"], 250)
        self.assertIsNone(rows[1]["net_park"])
        self.assertEqual(rows[1]["vsync"], 25)
        self.assertEqual(rows[1]["t"], 1.25)

    def test_peek_clock_reads_the_float_and_the_string(self):
        f, s = R.peek_clock(peek(31.5, "04:29"))
        self.assertAlmostEqual(f, 31.5)
        self.assertEqual(s, "04:29")

    def test_clock_trace_hole(self):
        self.assertEqual(R.clock_trace_verdict([10.0, 11.0, 12.0], 9.0, 13.0).status, R.PASS)
        v = R.clock_trace_verdict([], 9.0, 19.9)
        self.assertEqual(v.status, R.FAIL)
        self.assertIn("hole", v.detail)
        self.assertEqual(R.clock_trace_verdict([], None, None).status, R.NO_DATA)

    def test_no_gs_stats_line_is_no_data_not_stands(self):
        self.assertIsNone(R.guest_frames_reading([])[0])
        self.assertEqual(R.guest_frames_reading([0, 0])[0], "stands")

    def test_a_torn_capture_is_skipped_not_voiding_the_rest(self):
        fr, load = frames(True)

        def torn(path):
            if path == "f2":
                raise OSError("truncated PNG")
            return load(path)
        reading, detail = R.captures_reading(fr, load=torn)
        self.assertEqual(reading, "moves")
        self.assertIn("1 skipped", detail)

    def test_mixed_when_the_readings_disagree(self):
        fr, load = frames(False)
        _, info, _, outcome = R.paused_peer(window(moving=True), [clock_line(499.5)], [clock_line(503.5)], fr,
                                            load=load)
        self.assertEqual(outcome, "MIXED", info)

    def test_captures_reading(self):
        fr, load = frames(True)
        self.assertEqual(R.captures_reading(fr, load=load)[0], "moves")
        fr, load = frames(False)
        self.assertEqual(R.captures_reading(fr, load=load)[0], "stands")
        self.assertIsNone(R.captures_reading([], load=load)[0])

    def test_the_frames_move_through_the_pause_closes_34(self):
        fr, load = frames(True)
        verdicts, info, overall, outcome = R.paused_peer(window(), [clock_line(499.5)], [clock_line(503.5)], fr, load=load)
        self.assertEqual(overall, R.PASS, [R.fmt("paused-peer", x) for x in verdicts])
        self.assertTrue(any(ln.startswith("DECISIVE paused-peer CLOSES") for ln in info), info)
        self.assertEqual(outcome, "CLOSES")

    def test_frames_stand_while_the_executor_runs_retracts_the_theory(self):
        fr, load = frames(False)
        verdicts, info, overall, outcome = R.paused_peer(window(moving=False), [clock_line(499.5)], [clock_line(503.5)], fr,
                                                load=load)
        self.assertEqual(overall, R.PASS)            # the executor criteria hold; the decisive line says the rest
        self.assertTrue(any(ln.startswith("DECISIVE paused-peer RETRACT") for ln in info), info)
        self.assertEqual(outcome, "RETRACT")
        self.assertTrue(any("hud-clock stands" in ln for ln in info))

    def test_the_before_run_shows_the_hole(self):
        fr, load = frames(False)
        verdicts, info, overall, outcome = R.paused_peer(window(moving=False, hole=True, net_wait=True, v7=False),
                                                [clock_line(490.0)], [clock_line(501.0)], fr, before_mode=True,
                                                load=load)
        status = {x.name: x.status for x in verdicts}
        self.assertEqual(status["clock-trace"], R.FAIL)
        self.assertEqual(status["net_park"], R.FAIL)
        self.assertEqual(status["seq"], R.FAIL)
        self.assertTrue(any(ln.startswith("DECISIVE paused-peer BLOCKED") for ln in info), info)
        self.assertIn("EXPECT paused-peer before: a [clock] hole with net_wait=1 -- seen", info)
        self.assertEqual(outcome, "BLOCKED")
        self.assertEqual(overall, R.PASS)

    def test_an_after_run_without_net_park_fails(self):
        fr, load = frames(True)
        _, _, overall, _ = R.paused_peer(window(v7=False), [clock_line(499.5)], [clock_line(503.5)], fr, load=load)
        self.assertEqual(overall, R.FAIL)


class MainReadsTheRoundDirectory(unittest.TestCase):
    def test_paused_peer_from_files(self):
        with tempfile.TemporaryDirectory() as d:
            a_log = os.path.join(d, "run_A.log")
            pre = [clock_line(490.0 + i) for i in range(10)]
            body = window()
            post = [clock_line(503.5 + i) for i in range(3)]
            with open(a_log, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(pre) + "\n")
                start = f.tell()
                f.write("\n".join(body) + "\n")
                end = f.tell()
                f.write("\n".join(post) + "\n")
            shots = []
            rng = np.random.default_rng(5)
            from PIL import Image
            for i in range(4):
                p = os.path.join(d, "A_%03d_pause.png" % i)
                Image.fromarray(rng.integers(0, 255, size=(30, 40)).astype(np.uint8)).save(p)
                shots.append({"phase": "pause", "path": p, "mtime": 10.0 + i})
            with open(os.path.join(d, "pause.json"), "w", encoding="utf-8") as f:
                json.dump({"a_log": a_log, "peer": "ours", "mode": "after", "t_suspend": 1.0, "t_resume": 31.0,
                           "a_log_bytes_at_suspend": start, "a_log_bytes_at_resume": end, "frames": shots}, f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = R.main(["paused-peer", d])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn("VERDICT paused-peer net_park PASS", out)
            self.assertRegex(out, r"RESULT PAUSED-PEER (CLOSES|MIXED) PASS")
            self.assertIn("pause=30.0s peer=ours mode=after", out)

    def test_paused_peer_without_a_pause_is_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "pause.json"), "w", encoding="utf-8") as f:
                json.dump({"a_log": None, "error": "the driver ended before A's round clock reached 30 s"}, f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = R.main(["paused-peer", d])
            self.assertEqual(rc, 2)
            self.assertIn("the driver ended", buf.getvalue())

    def test_udp_shift_from_round_txt(self):
        with tempfile.TemporaryDirectory() as d:
            def put(name, text):
                p = os.path.join(d, name)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                return p
            a = put("run_A.log", "[socom2/libnetb] udp peer send #1 to 192.0.2.10:3660 ra=0x0 aa\n")
            b = put("run_B.log", install_line(GETTER_R0001) + "\n[socom2] rt_net base peer UDP port -> 3660 (x)\n")
            drive = put("drive.txt", " 99.0s B_[lobby] teams: seals=1 terrorists=1 -> ok (attempt 1)\n")
            put("server-dme.log", dash(PAD + record("192.0.2.10", 3660, "192.0.2.10", 3660)) + "\n")
            put("round.txt", "ROUND=udp-shift\nA_LOG=%s\nB_LOG=%s\nDRIVE=%s\nR0004_LOG=\n" % (a, b, drive))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = R.main(["udp-shift", d])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn("VERDICT udp-shift r0004 SKIP", out)
            self.assertIn("VERDICT udp-shift dme-record PASS -- the server's DME log -- both slots :3660", out)
            self.assertIn("RESULT UDP-SHIFT PASS", out)


if __name__ == "__main__":
    unittest.main()
