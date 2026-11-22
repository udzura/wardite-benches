"""Matched measurements of the same 32-symbol loop on 2^3 Wardite configurations."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from measure import read_stderr, sha256

MODES = ('stock', 'iwasm', 'original', 'base', 'D', 'R', 'M', 'DR', 'DM', 'RM',
         'DRM', 'roots', 'W', 'RMW', 'DRMW')


def command(mode, opts):
    if mode == 'iwasm':
        return ['iwasm', '--interp', opts.experiment/'bulk.wasm', 'decode']
    if mode == 'wasmtime':
        return ['wasmtime', 'run', '--', opts.experiment/'bulk.wasm', 'decode']
    binary = opts.build/'wardite' if mode == 'stock' else opts.experiment/'experiment'
    return [binary, '--new-engine', '--', opts.experiment/'bulk.wasm', 'decode']


def run(mode, opts, stdin, stdout, *, audit=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith('WARDITE_')}
    env.update(WARDITE_MIR_WORKERS='8', WARDITE_MIR_JIT='0')
    if mode not in ('stock', 'iwasm', 'wasmtime', 'original'):
        env['WARDITE_BENCH_MODE'] = mode
        if audit:
            env['WARDITE_BENCH_AUDIT'] = '1'
    if isinstance(stdin, bytes):
        return subprocess.run(command(mode, opts), input=stdin, stdout=stdout,
                              stderr=subprocess.PIPE, env=env)
    return subprocess.run(command(mode, opts), stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, env=env)


def preflight(opts, fixture, expected):
    # Verify successful paths for two input distributions and all 32 error
    # exits of the unrolled body. Force at least one backedge before error.
    alternate = bytes(range(255, -1, -1)) * 19
    for mode in (*opts.modes, 'wasmtime'):
        with fixture.open('rb') as f:
            r = run(mode, opts, f, subprocess.PIPE, audit=True)
        if r.returncode or r.stdout != expected:
            raise RuntimeError(f'{mode}: incorrect fixture output: {r.stderr[:200]!r}')
        trace = r.stderr
        if mode not in ('stock', 'iwasm', 'wasmtime', 'original'):
            prefix = f'matched decode MIR: {mode}\n'.encode()
            if not trace.startswith(prefix):
                raise RuntimeError(f'{mode}: unmodified MIR')
            trace = trace[len(prefix):]
        read_stderr(trace, 'bulk')
        payload = base64.b64encode(alternate)
        r = run(mode, opts, payload, subprocess.PIPE)
        if r.returncode or r.stdout != alternate:
            raise RuntimeError(f'{mode}: alternate output mismatch')
        for offset in range(32, 64):
            r = run(mode, opts, payload[:offset]+b'!'+payload[offset+1:], subprocess.PIPE)
            error = f'InvalidByte({offset}, 33)'.encode()
            # iwasm prints its proc_exit backtrace on stdout.
            stdout_ok = (r.stdout == b'' or (mode == 'iwasm' and
                         re.fullmatch(rb'\s*(?:#\d+: 0x[0-9a-fA-F]+ - [^\n]+\n)+\s*', r.stdout)))
            if r.returncode != 1 or not stdout_ok or error not in r.stderr:
                raise RuntimeError(f'{mode}: incorrect error at {offset}: {r.stderr[:200]!r}')


def measure(opts):
    fixture = opts.build/'fixtures/data-4m.b64'
    expected = (opts.build/'fixtures/data-4m.bin').read_bytes()
    preflight(opts, fixture, expected)
    order = list(opts.modes)
    records = []
    with fixture.open('rb') as f:
        def sample(mode):
            f.seek(0)
            r = run(mode, opts, f, subprocess.DEVNULL)
            if r.returncode:
                raise RuntimeError(f'{mode}: {r.stderr[:200]!r}')
            return read_stderr(r.stderr, 'bulk')['bulk']
        for mode in order:
            sample(mode)
        # Rotate a fixed permutation. Each mode occupies each position once
        # in a series; reverse the order within each block for the repeat.
        for series in range(2):
            for round_no in range(len(order)):
                block = order[round_no:] + order[:round_no]
                for mode in (block if series == 0 else reversed(block)):
                    records.append(dict(series=series+1, round=round_no+1, mode=mode, ns=sample(mode)))
    meta = dict(platform=platform.platform(), stock=(opts.build/'wardite.version').read_text().strip(),
                spinel=subprocess.check_output(['spinel','--version'],text=True).strip(),
                iwasm=subprocess.check_output(['iwasm','--version'],text=True).splitlines()[0],
                sha256={f.name: sha256(f) for f in (opts.build/'wardite', Path(shutil.which('iwasm')),
                        opts.experiment/'experiment', opts.experiment/'bulk.wasm', fixture)},
                output_sha256=hashlib.sha256(expected).hexdigest(), output_bytes=len(expected),
                workers=8, jit=False, warmups=1, preflight_bad_offsets_per_mode=32,
                path=json.loads((opts.experiment/'plan.json').read_text()))
    return dict(metadata=meta, samples=records)


def write_results(path, result):
    rows = ',\n'.join('  ' + json.dumps(row) for row in result['samples'])
    path.write_text('{"metadata": ' + json.dumps(result['metadata']) + ',\n"samples": [\n' + rows + '\n]}\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('build', type=Path, help='wardite-benches build directory')
    p.add_argument('experiment', type=Path, help='output directory from build.py')
    p.add_argument('output', type=Path)
    p.add_argument('--residual', action='store_true', help='time the supplementary build')
    opts = p.parse_args()
    opts.modes = (('stock', 'iwasm', 'original', 'base', 'P', 'A', 'DRMW', 'DRMWP',
                   'DRMWA', 'DRMWPA') if opts.residual else MODES)
    write_results(opts.output, measure(opts))
