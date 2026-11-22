"""Time four prepared startup paths with and without native phase markers."""
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


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def clock():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def breakdown(stderr, before, after, snapshot):
    marker, first, last, initial, pages, used, *items = stderr.decode().split()
    if marker != "WMIR_PHASE_NS":
        raise ValueError(stderr)
    ns = {"before_open": int(first) - before, "after_guest": after - int(last)}
    lazy_calls = {}
    for item in items:
        phase, numbers = item.split("=")
        elapsed, lazy, calls = map(int, numbers.split("/"))
        ns[phase] = elapsed - lazy
        if lazy:
            ns["lazy_" + phase] = lazy
            lazy_calls[phase] = calls
    if min(ns.values()) < 0 or sum(ns.values()) != after - before:
        raise ValueError("exclusive phases did not reconcile with the wall clock")
    if (ns["frames"] > 0) != snapshot or "guest" not in lazy_calls:
        raise ValueError("unexpected resume or lazy restoration path")
    return dict(ns=ns, lazy_calls=lazy_calls, pages=list(map(int, (initial, pages, used))))


def measure(release, probe, wasm, scratch, rounds):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("WARDITE_", "SPINEL_", "WASMTIME_"))}
    guest = ["--disable-gems", "-e", "puts RUBY_DESCRIPTION"]
    mir = scratch / "mir"
    snap = scratch / "snap"
    artifact = scratch / "ruby.wmir"
    bins = dict(release=release, probe=probe)

    def run(binary, args, trace=False):
        return subprocess.run([binary, *args], env=dict(env, WARDITE_TRACE="1") if trace else env,
                              stdin=subprocess.DEVNULL, capture_output=True, check=True)

    run(release, ["--compile-wmir", artifact, "--", wasm])
    cases = {}
    for mode, path in (("mir2", wasm), ("wmir", artifact)):
        base = ["--mir-cache", mir] if mode == "mir2" else []
        for snapshot in (False, True):
            flags = ["--snapshot", snap] if snapshot else []
            cases[mode + ("_snap" if snapshot else "")] = [*base, *flags, "--", path, *guest]
    # Tracing is part of the guest environment and hence the snapshot identity.
    expected = run(release, cases["mir2_snap"]).stdout
    if not expected.startswith(b"ruby 4.0.9 ") or b"wasm32-wasi" not in expected:
        raise ValueError(expected)
    run(release, cases["mir2_snap"], True)
    for binary in bins.values():
        for mode, args in cases.items():
            result = run(binary, args, True)
            marker = b"MIR2 cache hit:" if mode.startswith("mir2") else b"WMIR mapped:"
            if (result.stdout != expected or marker not in result.stderr
                    or (b"snapshot restored:" in result.stderr) != mode.endswith("_snap")):
                raise ValueError((mode, result.stderr))
    def inputs():
        return {str(p.relative_to(scratch)): (p.stat().st_size, digest(p))
                for p in [artifact, *mir.iterdir(), *snap.iterdir()]}
    initial = inputs()
    # Rotate and reverse the four paths, and alternate the order of paired builds.
    samples = []
    for r in range(-2, rounds):
        modes = list(cases)
        start = r % len(modes)
        order = modes[start:] + modes[:start]
        if (r // len(modes)) % 2:
            order.reverse()
        for i, mode in enumerate(order):
            for build in (reversed(bins) if (r + i) % 2 else bins):
                before = clock()
                result = run(bins[build], cases[mode])
                after = clock()
                if result.stdout != expected:
                    raise ValueError((mode, result.stdout))
                sample = dict(round=r+1, mode=mode, build=build, wall_ns=after-before)
                if build == "probe":
                    sample.update(breakdown(result.stderr, before, after, mode.endswith("_snap")))
                if r >= 0:
                    samples.append(sample)
    if initial != inputs():
        raise ValueError("prepared inputs changed during the measurement")
    return dict(platform=platform.platform(), guest=guest, output=expected.decode().strip(),
                sha256={k: digest(p) for k, p in dict(wasm=wasm, **bins).items()},
                inputs=initial, samples=samples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release", "probe", "wasm", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--rounds", type=int, default=32)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    with tempfile.TemporaryDirectory() as tmp:
        data = measure(args.release.resolve(), args.probe.resolve(), args.wasm.resolve(), Path(tmp), args.rounds)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    for mode in dict.fromkeys(r["mode"] for r in data["samples"]):
        for build in ("release", "probe"):
            rows = [r for r in data["samples"] if (r["mode"], r["build"]) == (mode, build)]
            print(mode, build, "median ms", round(median(r["wall_ns"] for r in rows)/1e6, 3))
