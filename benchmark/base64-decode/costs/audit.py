"""Check actual hot dispatch counts, successful memory accesses and fallback counts."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def audit(build, out):
    plan = json.loads((out/'plan.json').read_text())
    source = build/'fixtures/data-4m.b64'
    expected = (build/'fixtures/data-4m.bin').read_bytes()
    # Exclude the final, potentially padded quartet from the bulk loop.
    iterations = (len(source.read_bytes().rstrip(b'\n')) - 4) // 32
    report = {}
    for mode in ('base', 'D', 'M', 'DRMW'):
        with source.open('rb') as f:
            result = subprocess.run([out/'audit', '--new-engine', '--', out/'bulk.wasm', 'decode'],
                                    env=dict(os.environ, WARDITE_MIR_JIT='0', WARDITE_MIR_WORKERS='8',
                                             WARDITE_BENCH_MODE=mode), stdin=f, capture_output=True, check=True)
        if result.stdout != expected:
            raise ValueError(f'incorrect output in {mode}')
        match = re.fullmatch(rb'cost counters: (.+)\n', result.stderr[result.stderr.index(b'cost counters: '):])
        if not match:
            raise ValueError(f'missing counters in {mode}')
        counts = {k.decode(): int(v) for k, v in re.findall(rb'(\w+)=(\d+)', match[1])}
        groups = plan['groups'] if 'D' in mode else plan['pcs']
        wanted = {'tags': iterations * len(groups), 'ops': iterations * len(plan['pcs']),
                  'loads': iterations * 64 if 'M' in mode else 0,
                  'stores': iterations * 8 if 'M' in mode else 0, 'fallback': 0,
                  'views': 1 if 'M' in mode else 0}
        if any(counts[k] != v for k, v in wanted.items()):
            raise ValueError(f'{mode}: {counts} vs {wanted}')
        report[mode] = counts
    return dict(iterations=iterations, counts=report)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('build', type=Path)
    p.add_argument('experiment', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    args.output.write_text(json.dumps(audit(args.build, args.experiment), indent=2)+'\n')
