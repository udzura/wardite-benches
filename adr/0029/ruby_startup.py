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


def cache_env(env, directory):
    config = directory / 'cache.toml'
    config.write_text('[cache]\ndirectory = ' + json.dumps(str(directory / 'modules-cache')) + '\n')
    return dict(env, WASMTIME_CODEGEN='cache-config=' + str(config))


def measure(wardite, wasm, work, rounds):
    iwasm = Path(shutil.which('iwasm')).resolve()
    wasmtime = Path(shutil.which('wasmtime')).resolve()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('WARDITE_', 'WASMTIME_', 'SPINEL_'))}
    guest = ['--disable-gems', '-e', 'puts RUBY_DESCRIPTION']
    compiled = work / 'ruby.cwasm'
    cache = work / 'wardite-cache'
    default_wasmtime = [wasmtime, 'run', wasm, *guest]
    commands = {
        'wardite-default': [wardite, '--', wasm, *guest],
        'iwasm': [iwasm, '--stack-size=1048576', wasm, *guest],
        'wasmtime-auto-miss': default_wasmtime,
        'wasmtime-auto-hit': default_wasmtime,
        'wardite-snapshot': [wardite, '--mir-cache', cache, '--snapshot', cache, '--', wasm, *guest],
        'wasmtime-precompiled': [wasmtime, 'run', '--allow-precompiled', compiled, *guest],
    }

    def run(name, environment):
        return subprocess.run(commands[name], stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, env=environment)

    shared = work / 'warm'
    shared.mkdir()
    warm_env = cache_env(env, shared)
    probe_env = dict(warm_env, WASMTIME_LOG='wasmtime_internal_cache=trace')
    first = run('wasmtime-auto-miss', probe_env)
    expected = first.stdout
    if not expected.startswith(b'ruby ') or b'wasm32-wasi' not in expected:
        raise ValueError(f'unexpected Ruby version: {expected!r}')
    hit = run('wasmtime-auto-hit', probe_env)
    cache_path = os.fsencode(shared / 'modules-cache')
    if (b'update_data() for path: ' + cache_path not in first.stderr or
            b'get_data() for path: ' + cache_path not in hit.stderr or
            b'update_data()' in hit.stderr or hit.stdout != expected):
        raise ValueError(f'unexpected automatic-cache behavior: {first.stderr!r}, {hit.stderr!r}')

    subprocess.run([wasmtime, 'compile', '-C', 'cache=n', '-o', compiled, wasm], check=True, env=env)
    for markers in [(b'MIR2 cache miss:', b'snapshot saved:'), (b'MIR2 cache hit:', b'snapshot restored:')]:
        probe = run('wardite-snapshot', dict(env, WARDITE_TRACE='1'))
        if probe.stdout != expected or not all(marker in probe.stderr for marker in markers):
            raise ValueError(f'failed cache validation: {probe.stderr!r}')

    names = list(commands)
    samples = []
    for turn in range(-1, rounds):
        shift = turn % len(names)
        order = names[shift:] + names[:shift]
        if (turn // len(names)) % 2:
            order.reverse()
        # Set up this round's empty cache outside the timed interval.
        with tempfile.TemporaryDirectory(dir=work) as directory:
            cold = Path(directory)
            environments = {'wasmtime-auto-miss': cache_env(env, cold), 'wasmtime-auto-hit': warm_env}
            for name in order:
                process_env = environments.get(name, env)
                start = time.perf_counter_ns()
                result = run(name, process_env)
                elapsed = time.perf_counter_ns() - start
                if result.stdout != expected:
                    raise ValueError(f'{name}: unexpected output {result.stdout!r}')
                if turn >= 0:
                    samples.append(dict(engine=name, round=turn + 1, ns=elapsed))
            if not any((cold / 'modules-cache' / 'modules').glob('*/*')):
                raise ValueError('automatic-cache miss did not populate the fresh store')
    for name in names:
        ms = median(s['ns'] for s in samples if s['engine'] == name) / 1e6
        print(f'{name:22} {ms:8.2f} ms')
    return dict(platform=platform.platform(), wardite_settings='CLI defaults',
                ruby_description=expected.decode().strip(), module_sha256=sha256(wasm),
                binary_sha256={k: sha256(v) for k, v in dict(wardite=wardite, iwasm=iwasm, wasmtime=wasmtime).items()},
                samples=samples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wardite', type=Path)
    parser.add_argument('wasm', type=Path)
    parser.add_argument('--rounds', type=int, default=12)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    with tempfile.TemporaryDirectory() as directory:
        result = measure(args.wardite.resolve(strict=True), args.wasm.resolve(strict=True), Path(directory).resolve(), args.rounds)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
