"""Compare production interpreters, without modifying generated interpreter code."""
import argparse
import base64
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

from instrument import build
from measure import read_stderr, sha256


def measure(args, tmp):
    ex = args.build / 'rust/wasm32-wasip1/release/examples'
    fixtures = args.build / 'fixtures'
    codec = ex / 'base64_codec.wasm'
    build(codec, tmp)
    cases = {
        'bulk': (tmp / 'bulk.wasm', ['decode'], fixtures / 'data-4m.b64'),
        'decode': (codec, ['decode'], fixtures / 'data-4m.b64'),
        'encode': (codec, ['encode'], fixtures / 'data-4m.bin'),
        'png': (ex / 'png_grayscale.wasm', [], fixtures / 'rgb-1024.png'),
    }
    wardite = {name: Path(path).resolve(strict=True) for name, path in args.wardite}
    if len(wardite) != len(args.wardite) or 'iwasm' in wardite:
        raise ValueError('choose distinct Wardite build names, excluding iwasm')
    iwasm = Path(shutil.which('iwasm')).resolve()
    commands = {name: [binary, '--new-engine', '--'] for name, binary in wardite.items()}
    commands['iwasm'] = [iwasm, '--interp']
    env = {k: v for k, v in os.environ.items() if not k.startswith('WARDITE_')}
    env.update(WARDITE_MIR_WORKERS='8', WARDITE_MIR_JIT='0')

    checksums = {}
    for case, (wasm, argv, fixture) in cases.items():
        reference = subprocess.run(['wasmtime', 'run', '--', wasm, *argv], input=fixture.read_bytes(),
                                   capture_output=True, check=True).stdout
        checksums[case] = hashlib.sha256(reference).hexdigest()
        if case in ('bulk', 'decode') and reference != (fixtures / 'data-4m.bin').read_bytes():
            raise ValueError('unexpected reference decode')
        for name, cmd in commands.items():
            result = subprocess.run([*cmd, wasm, *argv], input=fixture.read_bytes(),
                                    capture_output=True, env=env, check=True)
            if result.stdout != reference:
                raise ValueError(f'{case}: incorrect output from {name}')
    payload = base64.b64encode(bytes(range(256)))
    for name, cmd in commands.items():
        for offset in range(32, 64):
            bad = payload[:offset] + b'!' + payload[offset + 1:]
            result = subprocess.run([*cmd, codec, 'decode'], input=bad, capture_output=True, env=env)
            if result.returncode != 1 or f'InvalidByte({offset}, 33)'.encode() not in result.stderr:
                raise ValueError(f'{name}: wrong exit at offset {offset}')

    samples = []
    names = list(commands)
    for case, (wasm, argv, fixture) in cases.items():
        with fixture.open('rb') as f:
            # Round -1 warms all engines. Shift order and reverse alternate cycles.
            for turn in range(-1, args.rounds):
                shift = turn % len(names)
                order = names[shift:] + names[:shift]
                if (turn // len(names)) % 2:
                    order.reverse()
                for name in order:
                    f.seek(0)
                    start = time.perf_counter_ns()
                    result = subprocess.run([*commands[name], wasm, *argv], stdin=f, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE, env=env, check=True)
                    ns = time.perf_counter_ns() - start
                    if case == 'bulk':
                        ns = read_stderr(result.stderr, 'bulk')['bulk']
                    if turn >= 0:
                        samples.append(dict(case=case, engine=name, round=turn+1, ns=ns))
        for name in names:
            times = [s['ns'] for s in samples if s['engine'] == name and s['case'] == case]
            print(f'{case:8} {name:16} {median(times)/1e6:8.2f} ms', flush=True)
    return dict(platform=platform.platform(), workers=8, jit=False, output_sha256=checksums,
                binaries={k: sha256(v) for k, v in {**wardite, 'iwasm': iwasm}.items()},
                modules={k: sha256(v[0]) for k, v in cases.items()},
                inputs={k: sha256(v[2]) for k, v in cases.items()}, samples=samples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=Path('build'))
    parser.add_argument('--wardite', nargs=2, metavar=('NAME', 'BIN'), action='append', required=True)
    parser.add_argument('--rounds', type=int, default=12)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    with tempfile.TemporaryDirectory() as work:
        result = measure(args, Path(work))
        samples = result.pop('samples')
        metadata = json.dumps(result, indent=2)
        rows = ',\n'.join('    ' + json.dumps(row) for row in samples)
        args.output.write_text(metadata[:-2] + ',\n  "samples": [\n' + rows + '\n  ]\n}\n')
