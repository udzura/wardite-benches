"""Compare direct and cache-directory loads using the same Wardite executable."""
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
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def measure(binary, wasm, directory, rounds):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SPINEL_", "WARDITE_"))}
    artifact = directory / "ruby.wmir"
    cache, snapshot = directory / "mir2", directory / "snapshot"
    guest = ["--disable-gems", "-e", "puts RUBY_DESCRIPTION"]

    def run(args, trace=False):
        return subprocess.run([binary, *args], capture_output=True, stdin=subprocess.DEVNULL,
                              env=dict(env, WARDITE_TRACE="1") if trace else env, check=True)

    t = time.perf_counter_ns()
    run(["--compile-wmir", artifact, "--", wasm])
    compile_ns = time.perf_counter_ns() - t
    modes = {
        "wasm_default": ["--", wasm],
        "wasm_mir2": ["--mir-cache", cache, "--", wasm],
        "wmir": ["--", artifact],
        "wasm_mir2_snapshot": ["--mir-cache", cache, "--snapshot", snapshot, "--", wasm],
        "wmir_snapshot": ["--snapshot", snapshot, "--", artifact],
    }
    cases = {k: [*args, *guest] for k, args in modes.items()}
    expected = run(cases["wasm_default"]).stdout
    if b"ruby 4.0.9 " not in expected or b"wasm32-wasi" not in expected:
        raise ValueError(expected)
    for trace in (False, True):
        run(cases["wasm_mir2_snapshot"], trace)
        for name, args in cases.items():
            result = run(args, trace)
            if result.stdout != expected:
                raise ValueError((name, result.stdout))
            if trace and name.endswith("snapshot") and b"snapshot restored:" not in result.stderr:
                raise ValueError((name, result.stderr))
    paths = [artifact, *cache.iterdir(), *snapshot.iterdir()]
    digests = {p: sha256(p) for p in paths}
    samples = {name: [] for name in modes}
    order = list(modes)
    for i in range(rounds):
        offset = i % len(order)
        sequence = order[offset:] + order[:offset]
        if (i // len(order)) % 2:
            sequence.reverse()
        for name in sequence:
            t = time.perf_counter_ns()
            result = run(cases[name])
            ns = time.perf_counter_ns() - t
            if result.stdout != expected:
                raise ValueError((name, result.stdout))
            samples[name].append(ns)
    if set([artifact, *cache.iterdir(), *snapshot.iterdir()]) != set(paths) or any(sha256(p) != digests[p] for p in paths):
        raise ValueError("a measured process changed its inputs")
    return dict(platform=platform.platform(), binary_sha256=sha256(binary), wasm_sha256=sha256(wasm),
                wasm_bytes=wasm.stat().st_size, artifact_bytes=artifact.stat().st_size,
                compile_ns=compile_ns, guest=guest, output=expected.decode().strip(), wall_ns=samples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("wardite", "wasm", "output"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--rounds", type=int, default=15)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    with tempfile.TemporaryDirectory() as tmp:
        data = measure(args.wardite.resolve(), args.wasm.resolve(), Path(tmp), args.rounds)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    for case, samples in data["wall_ns"].items():
        print(f"{case:20} {median(samples)/1e6:.2f} ms")
