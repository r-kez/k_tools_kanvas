"""Run every scratch/test_*.py in headless Blender and summarize the results.

    python scratch/run_all_tests.py [blender.exe ...] [--jobs N] [--slowest K]

Each test runs in its own Blender process, so almost all the time goes to starting
Blender and registering the add-on. The tests are independent (factory startup, their
own board, temporary folders), so several run at once: --jobs (default: half the CPU
cores, at least 2). Several Blender executables can be given: they run one after the
other, each with its own summary. --slowest lists the K slowest tests.

Tests that need a GPU or a network folder report themselves as skipped or fail with
a recognizable message, and are listed separately from real failures.
"""

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

root = Path(__file__).resolve().parent
# One version is enough. 5.2 is the stricter one: it crashes on stale item references
# that 5.1 silently tolerates.
DEFAULT_BLENDER = r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
GPU_MARKERS = ('GPU functions for drawing are not available', "has no attribute 'init'",
               'GPU API not available', 'No GPU')
PASS_MARKERS = re.compile(r'\b(PASS|PASSED|OK|SKIPPED)\b|_OK\b|passed', re.I)
ARGUMENT_MARKERS = ("'--' is not in list",)   # tests that need a file passed after `--`


def parse_arguments(argv):
    blenders, jobs, slowest = [], max(2, (os.cpu_count() or 4) // 2), 0
    items = iter(argv)
    for item in items:
        if item == '--jobs':
            jobs = max(1, int(next(items)))
        elif item == '--slowest':
            slowest = max(0, int(next(items)))
        else:
            blenders.append(item)
    return blenders or [DEFAULT_BLENDER], jobs, slowest


def run_one(blender, test):
    start = time.perf_counter()
    try:
        run = subprocess.run([blender, '-b', '--factory-startup', '-P', str(test)],
                             capture_output=True, text=True, timeout=240, env=os.environ)
    except subprocess.TimeoutExpired:
        return test.name, 'failed', 'timed out', time.perf_counter() - start
    elapsed = time.perf_counter() - start
    output = (run.stdout or '') + (run.stderr or '')
    if 'Traceback' in output or 'AssertionError' in output or 'Error:' in output:
        if any(m in output for m in ARGUMENT_MARKERS):
            return test.name, 'needs_args', '', elapsed
        gpu = next((m for m in GPU_MARKERS if m in output), None)
        last = [line for line in output.splitlines() if line.strip()][-3:]
        detail = ' | '.join(l.strip() for l in last)[:200]
        return test.name, 'gpu' if gpu else 'failed', detail, elapsed
    if PASS_MARKERS.search(output):
        return test.name, 'passed', '', elapsed
    return test.name, 'failed', 'no pass marker in the output', elapsed


def run_suite(blender, jobs, slowest):
    tests = sorted(root.glob('test_*.py'))
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        outcomes = list(pool.map(lambda test: run_one(blender, test), tests))
    total = time.perf_counter() - start
    results = {'passed': [], 'gpu': [], 'needs_args': [], 'failed': []}
    for name, kind, detail, _elapsed in outcomes:
        results[kind].append((name, detail))
    print(f"\n{Path(blender).parent.name}: {len(tests)} tests in {total:.0f} s with {jobs} at once")
    print(f"PASSED {len(results['passed'])}  GPU-ONLY {len(results['gpu'])}  "
          f"NEEDS ARGUMENTS {len(results['needs_args'])}  FAILED {len(results['failed'])}")
    for name, detail in results['needs_args']:
        print('  needs file:', name)
    for name, detail in results['gpu']:
        print('  needs GPU :', name)
    for name, detail in results['failed']:
        print('  FAILED    :', name, '->', detail)
    if slowest:
        print('  slowest:', ', '.join(f'{name} {elapsed:.1f}s' for name, _k, _d, elapsed
                                      in sorted(outcomes, key=lambda o: -o[3])[:slowest]))
    return not results['failed']


if __name__ == '__main__':
    blenders, jobs, slowest = parse_arguments(sys.argv[1:])
    ok = all([run_suite(blender, jobs, slowest) for blender in blenders])
    sys.exit(0 if ok else 1)
