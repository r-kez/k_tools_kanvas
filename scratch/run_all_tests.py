"""Run every scratch/test_*.py in headless Blender and summarize the results.

    python scratch/run_all_tests.py [blender.exe]

Tests that need a GPU or a network folder report themselves as skipped or fail with
a recognizable message, and are listed separately from real failures.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
blender = sys.argv[1] if len(sys.argv) > 1 else r'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
GPU_MARKERS = ('GPU functions for drawing are not available', "has no attribute 'init'",
               'GPU API not available', 'No GPU')
PASS_MARKERS = re.compile(r'\b(PASS|PASSED|OK|SKIPPED)\b|_OK\b|passed', re.I)

ARGUMENT_MARKERS = ("'--' is not in list",)   # tests that need a file passed after `--`
results = {'passed': [], 'gpu': [], 'needs_args': [], 'failed': []}
for test in sorted(root.glob('test_*.py')):
    try:
        run = subprocess.run([blender, '-b', '--factory-startup', '-P', str(test)],
                             capture_output=True, text=True, timeout=240, env=os.environ)
    except subprocess.TimeoutExpired:
        results['failed'].append((test.name, 'timed out'))
        continue
    output = (run.stdout or '') + (run.stderr or '')
    if 'Traceback' in output or 'AssertionError' in output or 'Error:' in output:
        if any(m in output for m in ARGUMENT_MARKERS):
            results['needs_args'].append((test.name, ''))
            continue
        gpu = next((m for m in GPU_MARKERS if m in output), None)
        last = [line for line in output.splitlines() if line.strip()][-3:]
        (results['gpu'] if gpu else results['failed']).append((test.name, ' | '.join(l.strip() for l in last)[:200]))
    elif PASS_MARKERS.search(output):
        results['passed'].append((test.name, ''))
    else:
        results['failed'].append((test.name, 'no pass marker in the output'))

print(f"\nPASSED {len(results['passed'])}  GPU-ONLY {len(results['gpu'])}  "
      f"NEEDS ARGUMENTS {len(results['needs_args'])}  FAILED {len(results['failed'])}")
for name, detail in results['needs_args']:
    print('  needs file:', name)
for name, detail in results['gpu']:
    print('  needs GPU :', name)
for name, detail in results['failed']:
    print('  FAILED    :', name, '->', detail)
sys.exit(1 if results['failed'] else 0)
