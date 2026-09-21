"""Contention harness for the threaded simulation tests (KNOWN §4: a threaded Python simulation test can redden CI
on a push that did not touch Python; Sprint 10 closed it with the lockstep online_rows.Clock).

Runs N subprocesses, `--parallel` at a time, each running the unittest `--targets` (default: the two threaded
classes of test_freeze_contact_fire) under a small GIL switch interval and `--burn` pure-Python CPU-burning threads
-- the way a loaded two-core hosted runner starved the shooter thread. Prints failed / runs and the failing tests.
The RED that proved the flake, from the repository root:

  python scripts/flake_repro.py --runs 100 --parallel 25 --switch 1e-5 --burn 4
    before the fix: failed=50 (31, 17/40, 24-42/60 in other batches)     after: failed=0, 0/300 twice

The test modules are imported BEFORE the burners start: CPython 3.13 on Windows crashed (access violation in
importlib) importing under them at a 10 us switch interval -- that crash is the harness's, not the tests'.
"""
import argparse
import collections
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

INNER = r"""
import sys, threading, unittest, faulthandler; faulthandler.enable()
# import first: CPython 3.13 on Windows crashed (access violation in importlib) importing under the burners
suite = unittest.TestSuite()
for name in sys.argv[3].split(","):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
sys.setswitchinterval(float(sys.argv[1]))
stop = threading.Event()
def burn():
    x = 0
    while not stop.is_set():
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
for _ in range(int(sys.argv[2])):
    threading.Thread(target=burn, daemon=True).start()
r = unittest.TextTestRunner(stream=sys.stdout, verbosity=0).run(suite)
stop.set()
for test, tb in r.failures + r.errors:
    print("FAILTEST", test.id(), tb.strip().splitlines()[-1])
sys.exit(0 if r.wasSuccessful() else 1)
"""


def one(args, k):
    t0 = time.time()
    p = subprocess.run([sys.executable, "-c", INNER, str(args.switch), str(args.burn), args.targets], cwd=args.tree,
                       capture_output=True, text=True, timeout=600)
    fails = [ln for ln in p.stdout.splitlines() if ln.startswith("FAILTEST")]
    if p.returncode != 0 and not fails:
        fails = ["FAILTEST <crash> rc=%s stderr=%r stdout=%r" % (p.returncode, p.stderr[-600:], p.stdout[-900:])]
    return p.returncode, fails, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=60)
    ap.add_argument("--parallel", type=int, default=os.cpu_count())
    ap.add_argument("--switch", type=float, default=1e-5)
    ap.add_argument("--burn", type=int, default=4)
    ap.add_argument("--tree", default=os.getcwd(), help="the repository root the subprocesses run in")
    ap.add_argument("--targets", default="tools_py.tests.test_freeze_contact_fire.FireWindowLateTest,"
                    "tools_py.tests.test_freeze_contact_fire.CooperativeFireWindowTest")
    args = ap.parse_args()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        results = list(ex.map(lambda k: one(args, k), range(args.runs)))
    failed = [r for r in results if r[0] != 0]
    names = collections.Counter(ln.split()[1] for r in failed for ln in r[1])
    print(f"runs={args.runs} parallel={args.parallel} switch={args.switch} burn={args.burn} "
          f"failed={len(failed)} wall={time.time() - t0:.0f}s max_run={max(r[2] for r in results):.1f}s")
    for name, n in names.most_common():
        print(f"  {n:3d}x {name}")
    shown = 0
    for r in failed:
        for ln in r[1]:
            if "<crash>" in ln or shown < 5:
                print("   ", ln[:1500])
                shown += 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
