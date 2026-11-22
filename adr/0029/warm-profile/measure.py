"""Measure a release and a timestamped build loading the same warm cache."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
from statistics import mean, median
import subprocess
import tempfile
import time


def unpack(stderr, wall):
    parts = stderr.split()
    if len(parts) != 10 or parts[0] != b'WARDITE_STARTUP_NS':
        raise ValueError(f'unexpected probe output: {stderr!r}')
    stamps, lazy, calls = zip(*(map(int, part.split(b'/')) for part in parts[1:]))
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    if min(stamps) <= 0 or min(gaps) < 0 or any(calls[:5]) or calls[-1]:
        raise ValueError('expected one successful lazy MIR2 and snapshot restore')
    read, key, sections, mir_read, instance, snapshot, frames, guest = gaps
    snap_lazy = lazy[5] + lazy[6]
    guest_lazy = lazy[7]
    breakdown = dict(mir_key=key, mir_read=mir_read, mir_lazy_snapshot=snap_lazy,
                     mir_lazy_guest=guest_lazy, snapshot=snapshot+frames-snap_lazy,
                     guest=guest-guest_lazy, wasm_read=read, sections_and_checks=sections,
                     instance_and_link=instance, outside=wall-sum(gaps))
    if min(breakdown.values()) < 0 or sum(breakdown.values()) != wall:
        raise ValueError('phase timing did not reconcile to process wall time')
    return dict(ns=breakdown, lazy_snapshot_calls=calls[5]+calls[6], lazy_guest_calls=calls[7])


def measure(release, probe, wasm, cache, rounds):
    args = ['--mir-cache', cache, '--snapshot', cache, '--', wasm, '--disable-gems', '-e', 'puts RUBY_DESCRIPTION']
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SPINEL_', 'WARDITE_', 'WASMTIME_'))}

    def run(binpath, trace=False):
        return subprocess.run([binpath, *args], env=dict(env, WARDITE_TRACE='1') if trace else env,
                              stdin=subprocess.DEVNULL, capture_output=True, check=True)

    expected = run(release).stdout
    if not expected.startswith(b'ruby ') or b'wasm32-wasi' not in expected:
        raise ValueError(f'unexpected version: {expected!r}')
    sizes = {p.suffix: p.stat().st_size for p in cache.iterdir()}
    if set(sizes) != {'.mir2', '.snap'}:
        raise ValueError('untraced release did not populate both caches')
    # WARDITE_TRACE contributes to the snapshot identity through the guest environment.
    run(release, trace=True)
    for binary in (release, probe):
        result = run(binary, trace=True)
        if (b'MIR2 cache hit:' not in result.stderr or b'snapshot restored:' not in result.stderr
                or result.stdout != expected):
            raise ValueError(f'cache validation failed: {result.stderr!r}')

    samples = []
    for r in range(-2, rounds):
        binaries = [('release', release), ('probe', probe)]
        if r % 2:
            binaries.reverse()
        for name, binary in binaries:
            before = time.perf_counter_ns()
            result = run(binary)
            wall = time.perf_counter_ns() - before
            if result.stdout != expected:
                raise ValueError(f'unexpected {name} stdout: {result.stdout!r}')
            row = dict(round=r+1, build=name, wall_ns=wall)
            if name == 'probe':
                row.update(unpack(result.stderr, wall))
            if r >= 0:
                samples.append(row)
    return dict(platform=platform.platform(), ruby=expected.decode().strip(), samples=samples,
                sha256={k: hashlib.sha256(p.read_bytes()).hexdigest()
                        for k, p in dict(release=release, probe=probe, wasm=wasm).items()},
                cache_bytes=sizes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release', 'probe', 'wasm', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--rounds', type=int, default=32)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    with tempfile.TemporaryDirectory() as cache:
        data = measure(args.release.resolve(), args.probe.resolve(), args.wasm.resolve(), Path(cache), args.rounds)
    args.output.write_text(json.dumps(data, indent=2) + '\n')
    for build in ('release', 'probe'):
        rows = [r for r in data['samples'] if r['build'] == build]
        print(build, 'mean / median ms', mean(r['wall_ns'] for r in rows)/1e6,
              median(r['wall_ns'] for r in rows)/1e6)
    for phase in rows[0]['ns']:
        print(phase, mean(r['ns'][phase] for r in rows)/1e6)
