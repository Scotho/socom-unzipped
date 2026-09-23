#!/usr/bin/env bash
# Item 1 step (b): the two small builds, each queued behind the loop lock (waits up to 3 h), run detached from any
# agent session so the session's memory reaper cannot take the waiter with it. Logs: build-iop.log, build.log.
ROOT=/c/projects/socom_pc
export PATH="$ROOT/tools/llvm-mingw/bin:$ROOT/tools/cmake/bin:$ROOT/tools/ninja:/usr/bin:/bin:/c/Windows/System32:$PATH"
export LOOP_LOCK_WAIT_SEC=3   # the chain's steps leave only a few seconds between lock acquisitions
cd "$ROOT" || exit 1
echo "build_both start $(date -u +%FT%TZ) pid $$" >> "$ROOT/research/irx-differential/build_both.log"

[ "$1" = "harness-only" ] || bash scripts/loop_lock.sh run agent-upstream --purpose "item1 spike: PR244 ps2xIOP standalone + ctest" --wait 3600 -- bash -c '
  cd /c/projects/socom_pc/research/ps2recomp-244 &&
  cmake -S ps2xIOP -B build-iop -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DPS2X_IOP_BUILD_TESTS=ON > build-iop.log 2>&1 &&
  cmake --build build-iop -j 6 >> build-iop.log 2>&1 &&
  ctest --test-dir build-iop --output-on-failure >> build-iop.log 2>&1; echo "EXIT $?" >> build-iop.log'
echo "build 1 lock-run exit $? $(date -u +%FT%TZ)" >> "$ROOT/research/irx-differential/build_both.log"

bash scripts/loop_lock.sh run agent-upstream --purpose "item1 spike: irx_differential harness build" --wait 3600 -- bash -c '
  cd /c/projects/socom_pc/research/irx-differential &&
  cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ > build.log 2>&1 &&
  cmake --build build -j 6 >> build.log 2>&1; echo "EXIT $?" >> build.log'
echo "build 2 lock-run exit $? $(date -u +%FT%TZ)" >> "$ROOT/research/irx-differential/build_both.log"
echo "build_both done" >> "$ROOT/research/irx-differential/build_both.log"
