"""Compare two matched Spinel builds using the same Ruby 4.0.9 Wasm and warm cache."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
from statistics import median
import subprocess
import tempfile
import time


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(bins, wasm, cache):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SPINEL_', 'WARDITE_'))}
    guest = ['--disable-gems', '-e', 'puts RUBY_DESCRIPTION']
    cli = ['--mir-cache', cache, '--snapshot', cache, '--', wasm, *guest]

    def start(build, trace=False):
        settings = dict(env, WARDITE_TRACE='1') if trace else env
        return subprocess.run([bins[build] / 'wardite', *cli], stdin=subprocess.DEVNULL,
                              capture_output=True, check=True, env=settings)

    original = start('before').stdout
    if not original.startswith(b'ruby 4.0.9 ') or b'wasm32-wasi' not in original:
        raise ValueError(original)
    start('before', trace=True)
    for build in bins:
        probe = start(build, trace=True)
        if probe.stdout != original or not all(marker in probe.stderr for marker in
                                               (b'MIR2 cache hit:', b'snapshot restored:')):
            raise ValueError(probe.stderr)
    files = {p.name: sha256(p) for p in cache.iterdir()}
    samples = []
    for r in range(-2, 32):
        for build in (reversed(bins) if r % 2 else bins):
            t = time.perf_counter_ns()
            result = start(build)
            ns = time.perf_counter_ns() - t
            if result.stdout != original:
                raise ValueError(result.stdout)
            if r >= 0:
                samples.append(dict(build=build, round=r+1, wall_ns=ns))
    if files != {p.name: sha256(p) for p in cache.iterdir()}:
        raise ValueError('a run rewrote or added a cache artifact')

    digest_ms = {k: [] for k in bins}
    for r in range(2):
        for build in (reversed(bins) if r % 2 else bins):
            output = subprocess.check_output([bins[build] / 'hash', wasm], env=env, text=True)
            values = list(map(float, output.splitlines()))
            if len(values) != 32:
                raise ValueError('expected 32 checked digests per run')
            digest_ms[build].extend(values)
    return dict(platform=platform.platform(), wasm_sha256=sha256(wasm),
                output=original.decode().strip(), samples=samples, digest_ms=digest_ms,
                binaries={k: {name: sha256(d / name) for name in ('wardite', 'hash')}
                          for k, d in bins.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'wasm', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as cache:
        data = measure(dict(before=args.before.resolve(), after=args.after.resolve()),
                       args.wasm.resolve(), Path(cache))
    args.output.write_text(json.dumps(data, indent=2) + '\n')
    for build in ('before', 'after'):
        wall = [s['wall_ns']/1e6 for s in data['samples'] if s['build'] == build]
        print(build, 'digest / process (median ms)', median(data['digest_ms'][build]), median(wall))
