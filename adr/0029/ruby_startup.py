"""Time fresh Ruby/WASI processes with and without engine-specific preparation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
from statistics import median
import subprocess
import tempfile
import time


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(wardite, wasm, work, rounds):
    iwasm = Path(shutil.which('iwasm')).resolve()
    wasmtime = Path(shutil.which('wasmtime')).resolve()
    env = {k: v for k, v in os.environ.items() if not k.startswith('WARDITE_')}
    env.update(WARDITE_MIR_WORKERS='8', WARDITE_MIR_JIT='0')
    guest = ['--disable-gems', '-e', 'puts RUBY_DESCRIPTION']
    codegen = ['-C', 'compiler=cranelift', '-C', 'cache=n']
    compiled = work / 'ruby.cwasm'
    cache = work / 'wardite-cache'
    commands = {
        'wardite': [wardite, '--', wasm, *guest],
        'iwasm': [iwasm, '--interp', '--stack-size=1048576', wasm, *guest],
        'wasmtime': [wasmtime, 'run', *codegen, '--', wasm, *guest],
        'wardite-snapshot': [wardite, '--mir-cache', cache, '--snapshot', cache, '--', wasm, *guest],
        'wasmtime-precompiled': [wasmtime, 'run', *codegen, '--allow-precompiled', '--', compiled, *guest],
    }

    def run(name, trace=False):
        return subprocess.run(commands[name], stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, env=dict(env, WARDITE_TRACE='1') if trace else env)

    expected = run('wasmtime').stdout
    if not expected.startswith(b'ruby ') or b'wasm32-wasi' not in expected:
        raise ValueError(f'unexpected Ruby version: {expected!r}')
    subprocess.run([wasmtime, 'compile', *codegen, '-o', compiled, wasm], check=True)
    for markers in [(b'MIR2 cache miss:', b'snapshot saved:'), (b'MIR2 cache hit:', b'snapshot restored:')]:
        probe = run('wardite-snapshot', trace=True)
        if probe.stdout != expected or not all(marker in probe.stderr for marker in markers):
            raise ValueError(f'failed cache validation: {probe.stderr!r}')

    names = list(commands)
    samples = []
    for turn in range(-1, rounds):
        shift = turn % len(names)
        order = names[shift:] + names[:shift]
        if (turn // len(names)) % 2:
            order.reverse()
        for name in order:
            start = time.perf_counter_ns()
            result = run(name)
            elapsed = time.perf_counter_ns() - start
            if result.stdout != expected:
                raise ValueError(f'{name}: unexpected output {result.stdout!r}')
            if turn >= 0:
                samples.append(dict(engine=name, round=turn + 1, ns=elapsed))
    for name in names:
        ms = median(s['ns'] for s in samples if s['engine'] == name) / 1e6
        print(f'{name:22} {ms:8.2f} ms')
    return dict(platform=platform.platform(), workers=8, wardite_jit=False,
                ruby_description=expected.decode().strip(), module_sha256=sha256(wasm),
                binary_sha256={k: sha256(v) for k, v in dict(wardite=wardite, iwasm=iwasm, wasmtime=wasmtime).items()},
                samples=samples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wardite', type=Path)
    parser.add_argument('wasm', type=Path)
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    with tempfile.TemporaryDirectory() as directory:
        result = measure(args.wardite.resolve(strict=True), args.wasm.resolve(strict=True), Path(directory), args.rounds)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
