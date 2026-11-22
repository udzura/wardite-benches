"""Time the 4 MiB Base64 decoder, including an unmodified-module control."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import struct
import subprocess
import tempfile
import time

from instrument import EVENTS, build

ENGINES = ("wardite", "iwasm")
VARIANTS = ("plain", "phases", "bulk")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_stderr(data, variant):
    if variant == "plain":
        if data:
            raise ValueError(f"unexpected stderr: {data[:200]!r}")
        return {}
    if len(data) != len(EVENTS) * 8:
        raise ValueError(f"invalid timestamp record: {data[:200]!r}")
    stamps = dict(zip(EVENTS, struct.unpack(f"<{len(EVENTS)}Q", data)))
    active = [t for label, t in stamps.items() if variant == "bulk" or not label.startswith("bulk")]
    if active[0] == 0 or active != sorted(active):
        raise ValueError(f"out-of-order or missing timestamps: {stamps}")
    spans = {key: stamps[key + "_end"] - stamps[key + "_start"]
             for key in ("read", "decode", "kernel", "write", "flush")}
    if variant == "bulk":
        spans["bulk"] = stamps["bulk_end"] - stamps["bulk_start"]
        if spans["bulk"] <= 0:
            raise ValueError("bulk loop did not execute")
    return spans


def sample(command, source, env, stdout, variant):
    with source.open("rb") as stdin:
        start = time.perf_counter_ns()
        result = subprocess.run(command, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, env=env)
        wall = time.perf_counter_ns() - start
    if result.returncode:
        raise RuntimeError(f"{command} exited {result.returncode}: {result.stderr[:500]!r}")
    spans = read_stderr(result.stderr, variant)
    if spans:
        spans["outside_decode"] = wall - spans["decode"]
        spans["other"] = spans["outside_decode"] - spans["read"] - spans["write"] - spans["flush"]
        if spans["other"] < 0:
            raise ValueError(f"guest times exceed process wall time: {spans}")
    return result.stdout, {"wall": wall, **spans}


def measure(args, temp):
    root = args.build.resolve()
    source = root / "fixtures/data-4m.b64"
    expected = (root / "fixtures/data-4m.bin").read_bytes()
    plain = root / "rust/wasm32-wasip1/release/examples/base64_codec.wasm"
    build(plain, temp)
    modules = {"plain": plain, "phases": temp / "phases.wasm", "bulk": temp / "bulk.wasm"}
    wardite = (args.wardite or root / "wardite").resolve(strict=True)
    iwasm = Path(shutil.which("iwasm")).resolve(strict=True)
    commands = {"wardite": [wardite, "--new-engine", "--"], "iwasm": [iwasm, "--interp"]}
    env = {k: v for k, v in os.environ.items() if not k.startswith("WARDITE_")}
    env.update(WARDITE_MIR_WORKERS="8", WARDITE_MIR_JIT="0")
    for engine in (*ENGINES, "wasmtime"):
        for variant, wasm in modules.items():
            cmd = [*commands.get(engine, ["wasmtime", "run", "--"]), wasm, "decode"]
            output, _ = sample(cmd, source, env, subprocess.PIPE, variant)
            if output != expected:
                raise ValueError(f"{engine} {variant} output differs from data-4m.bin")

    version = wardite.with_suffix(".version")
    info = dict(platform=platform.platform(), binary_sha256={name: sha256(command[0])
                for name, command in commands.items()}, module_sha256={k: sha256(p) for k, p in modules.items()},
                input_bytes=source.stat().st_size, input_sha256=sha256(source),
                output_bytes=len(expected), output_sha256=hashlib.sha256(expected).hexdigest(),
                wardite_version=version.read_text().strip() if version.exists() else None,
                iwasm_version=subprocess.check_output([iwasm, "--version"], text=True).splitlines()[0],
                workers=8, jit=False, warmups=2, rounds=args.rounds, reverse=args.reverse, unit="ns")
    # Each engine goes first equally often within each pair. Each module
    # takes each position equally often over six measured rounds.
    permutations = list(itertools.permutations(VARIANTS))
    rows = []
    for turn in range(-2, args.rounds):
        for variant in permutations[turn % len(permutations)]:
            for engine in (ENGINES if (turn + args.reverse) % 2 == 0 else reversed(ENGINES)):
                cmd = [*commands[engine], modules[variant], "decode"]
                _, spans = sample(cmd, source, env, subprocess.DEVNULL, variant)
                if turn >= 0:
                    rows.append(dict(round=turn + 1, engine=engine, variant=variant, **spans))
    return dict(metadata=info, samples=rows)


def summary(rows):
    for variant in VARIANTS:
        groups = [[r for r in rows if r["variant"] == variant and r["engine"] == e] for e in ENGINES]
        for field in ("wall", "decode", "kernel", "bulk", "outside_decode", "read", "write", "flush", "other"):
            if field not in groups[0][0]:
                continue
            a, b = [statistics.mean(r[field] for r in group) / 1e6 for group in groups]
            if field == "wall":
                wall_delta = a - b
            delta = a - b
            ratio = f"{a / b:.2f}x" if b else "n/a"
            share = f"{100 * delta / wall_delta:.1f}%" if wall_delta else "n/a"
            print(f"{variant:6} {field:14} {a:8.3f} {b:8.3f} ms   {ratio:>6}"
                  f"   delta {delta:8.3f} ms ({share} of wall gap)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=Path("build"))
    parser.add_argument("--wardite", type=Path)
    parser.add_argument("--reverse", action="store_true", help="reverse the initial engine order")
    parser.add_argument("--rounds", type=int, default=18)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.rounds <= 0 or args.rounds % 6:
        parser.error("use a positive multiple of six rounds to balance order")
    with tempfile.TemporaryDirectory() as directory:
        result = measure(args, Path(directory))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    summary(result["samples"])
