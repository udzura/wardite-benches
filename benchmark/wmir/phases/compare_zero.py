"""A/B comparison for clearing only pages which existed before the restore."""
import argparse
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import tempfile
from measure import clock, digest


def compare(binaries, wasm, directory, rounds):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("WARDITE_", "SPINEL_", "WASMTIME_"))}
    artifact, snapshot = directory / "ruby.wmir", directory / "snapshot"
    args = ["--snapshot", snapshot, "--", artifact, "--disable-gems", "-e", "puts RUBY_DESCRIPTION"]

    def run(binary, args, trace=False):
        return subprocess.run([binary, *args], stdin=subprocess.DEVNULL, capture_output=True,
                              env=dict(env, WARDITE_TRACE="1") if trace else env, check=True)

    run(binaries["control"], ["--compile-wmir", artifact, "--", wasm])
    expected = run(binaries["control"], args).stdout
    if not expected.startswith(b"ruby 4.0.9 ") or b"wasm32-wasi" not in expected:
        raise ValueError(expected)
    run(binaries["control"], args, True)
    for binary in binaries.values():
        probe = run(binary, args, True)
        if probe.stdout != expected or not all(k in probe.stderr for k in (b"WMIR mapped:", b"snapshot restored:")):
            raise ValueError(probe.stderr)
    def inputs():
        return {p.name: digest(p) for p in (artifact, *snapshot.iterdir())}
    before = inputs()
    samples = {b: [] for b in binaries}
    for r in range(-2, rounds):
        for name in (reversed(binaries) if r % 2 else binaries):
            t = clock()
            result = run(binaries[name], args)
            wall = clock()-t
            if result.stdout != expected:
                raise ValueError(result.stdout)
            if r >= 0:
                samples[name].append(wall)
    if before != inputs():
        raise ValueError("prepared inputs changed")
    return dict(wall_ns=samples, wasm_sha256=digest(wasm), inputs=before, guest_output=expected.decode().strip(),
                binaries={k: digest(p) for k,p in binaries.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "trial", "wasm", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--rounds", type=int, default=32)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    with tempfile.TemporaryDirectory() as tmp:
        data = compare(dict(control=args.control.resolve(), trial=args.trial.resolve()),
                       args.wasm.resolve(), Path(tmp), args.rounds)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    for name, walls in data["wall_ns"].items():
        print(name, "median ms", median(walls)/1e6)
