"""Compare MIR passes on identical Wasm modules and inputs. Emit JSON Lines."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

PASSES = ("fold", "cfg", "dce", "exit_copy", "licm")
MODES = ("profile", "cold", "miss", "hit", "snapshot")


def cases(build, ruby):
    wasi = build / "rust/wasm32-wasip1/release/examples"
    numeric = build / "rust/wasm32-unknown-unknown/release/examples"
    fixtures = build / "fixtures"
    sizes = (("small", "data", "rgb.png", 10000),
             ("large", "data-4m", "rgb-1024.png", 1000000))
    for size, stem, image, limit in sizes:
        for mode, ext in (("encode", ".bin"), ("decode", ".b64")):
            yield f"{mode}-{size}", wasi / "base64_codec.wasm", None, [mode], fixtures / (stem + ext)
        yield f"png-{size}", wasi / "png_grayscale.wasm", None, [], fixtures / image
        yield f"sieve-{size}", numeric / "count_primes.wasm", "count_primes_sieve", [str(limit)], None
    yield "ruby", ruby, None, ["--disable-gems", "-e", "puts RUBY_DESCRIPTION"], None


def switches(variant, passes):
    if variant in ("parent", "default"):
        return []
    selected = variant.split("+")
    flags = []
    for name in passes:
        flags.extend(("--mir-enable" if name in selected else "--mir-disable", name))
    return flags


def samples(mode, args):
    if mode == "profile":
        return [1]
    if mode == "miss":
        return range(1, args.misses + 1)
    # Build each cache at -1 and check restoration during the warmup at 0.
    first = -1 if mode in ("hit", "snapshot") else 0
    return range(first, args.runs + 1)


def run(command, env, stdin):
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
        source.write(stdin)
        source.seek(0)
        start = time.monotonic()
        proc = subprocess.Popen(command, stdin=source, stdout=output, stderr=subprocess.PIPE,
                                env=env, text=True)
        with proc.stderr:
            trace = "".join(proc.stderr)
        status = proc.wait()
        elapsed = time.monotonic() - start
        output.seek(0)
        if status:
            raise RuntimeError(f"{command} exited {status}\n{trace}")
        return elapsed * 1000, output.read(), trace


def trace_value(trace, prefix):
    for line in trace.splitlines():
        if line.startswith(prefix):
            return float(line.split()[-1])
    raise ValueError(f"missing {prefix} in trace")


def measurements(trace, variant, mode, rep):
    if mode == "profile":
        ops = {op: int(n) for op, n in re.findall(r"^opcode (\w+) (\d+)$", trace, re.M)}
        dispatches = int(re.search(r"dispatches=(\d+)", trace)[1])
        assert sum(ops.values()) == dispatches
        return dict(ops=ops, dispatches=dispatches)
    if mode == "miss":
        assert "MIR2 cache miss:" in trace
        if variant != "parent":
            seconds = trace_value(trace, "semantic MIR translation:")
            seconds += trace_value(trace, "MIR optimization and lowering:")
            return dict(build_ms=1000 * seconds)
    if mode in ("hit", "snapshot") and rep <= 0:
        phase = "miss" if rep == -1 else "hit"
        assert f"MIR2 cache {phase}:" in trace
        if mode == "snapshot":
            phase = "saved" if rep == -1 else "restored"
            assert f"snapshot {phase}:" in trace
    return {}


def measure_case(args, work, name, wasm, export, argv, fixture):
    stdin = fixture.read_bytes() if fixture else b""
    invoke = ["--invoke", export] if export else []
    expected = subprocess.run(["wasmtime", "run", *invoke, wasm, *argv], input=stdin,
                              capture_output=True, check=True).stdout
    print(json.dumps(dict(case=name, wasm=hashlib.sha256(wasm.read_bytes()).hexdigest(),
                          input=hashlib.sha256(stdin).hexdigest(),
                          output=hashlib.sha256(expected).hexdigest())), flush=True)
    guest = (["--no-wasi", *invoke] if export else []) + ["--", wasm, *argv]
    for mode in args.modes:
        if mode == "snapshot" and name != "ruby":
            continue
        for rep in samples(mode, args):
            order = args.variants if (rep + args.reverse) % 2 else reversed(args.variants)
            for variant in order:
                binary = args.parent if variant == "parent" else args.binary
                flags = switches(variant, args.passes)
                env = dict(os.environ, WARDITE_MIR_CSE="0", WARDITE_MIR_JIT="0")
                env.pop("WARDITE_TRACE", None)
                if mode == "profile":
                    flags.append("--mir-profile")
                if mode in ("miss", "hit", "snapshot"):
                    index = rep if mode == "miss" else 0
                    cache = work / f"{name}-{mode}-{variant}-{index}"
                    flags.extend(("--mir-cache", cache))
                    if mode == "snapshot":
                        flags.extend(("--snapshot", cache))
                    if mode == "miss" or rep <= 0:
                        env["WARDITE_TRACE"] = "1"
                ms, output, trace = run([binary, *flags, *guest], env, stdin)
                if export:
                    matches = f"return value: I32({int(expected)})" in trace.splitlines()
                else:
                    matches = output == expected
                if not matches:
                    raise RuntimeError(f"{name} {variant} {mode}: output differs from Wasmtime")
                metrics = measurements(trace, variant, mode, rep)
                if rep > 0:
                    print(json.dumps(dict(case=name, variant=variant, mode=mode, run=rep,
                                          ms=ms, **metrics)), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("binary", type=lambda s: Path(s).resolve(strict=True))
    p.add_argument("--parent", type=lambda s: Path(s).resolve(strict=True))
    p.add_argument("--ruby", type=Path, required=True)
    p.add_argument("--build", type=Path, default=Path("build"))
    p.add_argument("--variants", nargs="+", required=True)
    p.add_argument("--cases", nargs="+", default=["encode-large", "decode-large", "png-large",
                                                  "sieve-large", "ruby"])
    p.add_argument("--modes", nargs="+", choices=MODES, default=["profile", "cold"])
    p.add_argument("--passes", nargs="+", choices=PASSES, default=PASSES)
    p.add_argument("--runs", type=int, default=7)
    p.add_argument("--misses", type=int, default=3)
    p.add_argument("--reverse", action="store_true")
    args = p.parse_args()
    workloads = list(cases(args.build, args.ruby))
    if set(args.cases) - {case[0] for case in workloads}:
        p.error("unknown workload")
    for variant in args.variants:
        if variant not in ("parent", "default", "none") and set(variant.split("+")) - set(args.passes):
            p.error(f"unknown or unavailable pass in {variant}")
    if args.runs < 1 or args.misses < 1 or ("parent" in args.variants and not args.parent):
        p.error("provide positive counts and a parent executable for parent comparisons")
    with tempfile.TemporaryDirectory() as work:
        for case in workloads:
            if case[0] in args.cases:
                measure_case(args, Path(work), *case)
