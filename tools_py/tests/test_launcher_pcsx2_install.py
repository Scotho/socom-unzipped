"""Sprint 18 T4 (R341): the launcher's PCSX2 INSTALL, headless, against a LOOPBACK stand-in "release".

`socom_unzipped_launcher --install-pcsx2 <dir>` reads the latest-release JSON, picks the `-windows-x64-Qt.7z` asset,
downloads it (redirects only from github.com to *.githubusercontent.com), checks its size and the API's sha256 with
launcher::patchfetch::verifyPackage, extracts it with the system's tar.exe into <dir>/pcsx2/ and writes portable.txt
and socom_unzipped_pcsx2.txt (the tag) there. The API URL comes from PS2X_LAUNCHER_PCSX2_API, which the launcher
honours only for a loopback server and only in developer mode (PS2X_DEV=1: a Dev knob, as PS2X_LAUNCHER_PATCH_BASE
is). Every case here sets it: the real api.github.com is never asked by this test. The "archive" is a 7z the test
builds itself with bsdtar around a 16-byte stand-in pcsx2-qt.exe -- no PCSX2 byte anywhere (R-C).

Windows only: INSTALL extracts with %SystemRoot%\\System32\\tar.exe (the Linux client is out of scope, spec 2.4).
Skipped when the launcher is not built (the suite's convention).
"""
import hashlib
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from tools_py.parity import hostplatform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAUNCHER = os.path.join(ROOT, os.path.dirname(hostplatform.runtime_exe()),
                        hostplatform.exe_name("socom_unzipped_launcher"))
TAR = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")

TAG = "v0.0.0"
ASSET = "pcsx2-v0.0.0-windows-x64-Qt.7z"
STAND_IN = b"PCSX2 stand-in!\n"   # 16 bytes: the "exe" the 7z carries
assert len(STAND_IN) == 16


def build_archive(folder):
    """A real 7z, written by the system's bsdtar, holding one 16-byte pcsx2-qt.exe."""
    src = os.path.join(folder, "src")
    os.makedirs(src)
    with open(os.path.join(src, "pcsx2-qt.exe"), "wb") as fh:
        fh.write(STAND_IN)
    out = os.path.join(folder, "stand.7z")
    subprocess.run([TAR, "-cf", out, "--format", "7zip", "pcsx2-qt.exe"], cwd=src, check=True,
                   capture_output=True, timeout=60)
    with open(out, "rb") as fh:
        return fh.read()


class ReleaseServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, archive):
        super().__init__(("127.0.0.1", 0), Handler)
        self.archive = archive
        self.mode = "ok"            # ok | wrong-digest | redirect | rate-limit
        self.requests = []

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.server_address[1]

    def release_json(self):
        digest = hashlib.sha256(self.archive).hexdigest()
        if self.mode == "wrong-digest":
            digest = hashlib.sha256(b"another archive").hexdigest()
        return json.dumps({
            "tag_name": TAG, "name": TAG,
            "author": {"login": "stand-in", "id": 1},
            "assets": [
                {"name": "pcsx2-v0.0.0-windows-x64-Qt-symbols.7z", "size": 3,
                 "uploader": {"login": "stand-in"},
                 "digest": "sha256:" + "0" * 64,
                 "browser_download_url": self.base + "/symbols.7z"},
                {"name": ASSET, "size": len(self.archive),
                 "uploader": {"login": "stand-in"},
                 "digest": "sha256:" + digest,
                 "browser_download_url": self.base + "/pcsx2.7z"},
            ]}).encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, ctype="application/octet-stream", extra=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        srv = self.server
        srv.requests.append(self.path)
        if self.path == "/release.json":
            if srv.mode == "rate-limit":
                self.send(403, json.dumps({"message": "API rate limit exceeded for 127.0.0.1.",
                                           "documentation_url": "https://docs.github.com/rest"}).encode(),
                          "application/json")
                return
            self.send(200, srv.release_json(), "application/json")
            return
        if self.path == "/pcsx2.7z" and srv.mode == "redirect":
            # A loopback host is not github.com: the policy must refuse to follow, whatever the target.
            self.send(302, b"", extra=(("Location", srv.base + "/moved.7z"),))
            return
        if self.path in ("/pcsx2.7z", "/moved.7z"):
            self.send(200, srv.archive)
            return
        self.send(404, b"not here")


@unittest.skipUnless(sys.platform == "win32", "INSTALL extracts with the Windows system tar.exe (spec 2.4)")
@unittest.skipUnless(os.path.isfile(LAUNCHER), "no launcher build at " + LAUNCHER)
class LauncherPcsx2InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        work = os.path.join(self.tmp.name, "work")
        os.makedirs(work)
        self.archive = build_archive(work)
        self.home = os.path.join(self.tmp.name, "launcher")
        os.makedirs(self.home)
        self.pcsx2 = os.path.join(self.home, "pcsx2")
        self.server = ReleaseServer(self.archive)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def run_launcher(self, *args):
        # PS2X_LAUNCHER_PCSX2_API is a Dev knob: honoured only in developer mode, and only for a loopback URL.
        # NO_PROXY keeps a proxy in the environment from carrying the loopback request anywhere.
        env = {**os.environ, "PS2X_DEV": "1", "PS2X_LAUNCHER_PCSX2_API": self.server.base + "/release.json",
               "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        return subprocess.run([LAUNCHER, *args], capture_output=True, text=True, timeout=180, env=env)

    def install(self):
        return self.run_launcher("--install-pcsx2", self.home)

    def leftovers(self):
        found = []
        for dirpath, _dirs, files in os.walk(self.home):
            found += [f for f in files if f.endswith((".7z", ".part", ".new"))]
        return found

    def test_install_extracts_the_verified_archive_and_marks_it(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        exe = os.path.join(self.pcsx2, "pcsx2-qt.exe")
        with open(exe, "rb") as fh:
            self.assertEqual(fh.read(), STAND_IN)
        self.assertTrue(os.path.isfile(os.path.join(self.pcsx2, "portable.txt")))
        with open(os.path.join(self.pcsx2, "socom_unzipped_pcsx2.txt")) as fh:
            self.assertEqual(fh.read().strip(), TAG)
        self.assertEqual(self.leftovers(), [])
        self.assertIn("installed PCSX2 %s at" % TAG, r.stdout)
        # The Windows asset, never the symbols one; the API first.
        self.assertEqual(self.server.requests, ["/release.json", "/pcsx2.7z"])

    def test_status_reads_the_marker_after_an_install(self):
        self.assertEqual(self.install().returncode, 0)
        r = self.run_launcher("--pcsx2-status", os.path.join(self.pcsx2, "pcsx2-qt.exe"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PCSX2 %s (installed by the launcher)" % TAG, r.stdout)

    def test_a_wrong_digest_is_refused_and_nothing_is_left(self):
        self.server.mode = "wrong-digest"
        r = self.install()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sha256", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.pcsx2, "pcsx2-qt.exe")))
        self.assertFalse(os.path.exists(self.pcsx2), "the folder INSTALL made is removed on a refusal")
        self.assertEqual(self.leftovers(), [])

    def test_a_refusal_leaves_an_existing_folder_and_its_files(self):
        os.makedirs(self.pcsx2)
        keep = os.path.join(self.pcsx2, "keep.txt")
        with open(keep, "w") as fh:
            fh.write("mine")
        self.server.mode = "wrong-digest"
        r = self.install()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(keep) as fh:
            self.assertEqual(fh.read(), "mine")
        self.assertEqual(self.leftovers(), [])

    def test_a_redirect_off_github_is_refused_not_followed(self):
        self.server.mode = "redirect"
        r = self.install()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("redirect", r.stdout)
        self.assertEqual(self.server.requests, ["/release.json", "/pcsx2.7z"])   # /moved.7z never asked
        self.assertFalse(os.path.exists(self.pcsx2))

    def test_the_apis_rate_limit_message_is_surfaced(self):
        self.server.mode = "rate-limit"
        r = self.install()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("rate limit", r.stdout)
        self.assertEqual(self.server.requests, ["/release.json"])
        self.assertFalse(os.path.exists(self.pcsx2))


if __name__ == "__main__":
    unittest.main()
