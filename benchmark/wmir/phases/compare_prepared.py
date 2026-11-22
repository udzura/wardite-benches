"""Compare prepared Ruby startup across Wardite builds and Wasmtime."""
import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
import subprocess
import tempfile

from measure import clock, digest


def macos_lowpowermode():
    try:
        result = subprocess.run(["/usr/bin/pmset", "-g"], capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] == "lowpowermode" and fields[1] in ("0", "1"):
            return int(fields[1])
    return None


def compare(builds, wasmtime, wasm, rounds, scratch):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("WARDITE_", "SPINEL_", "WASMTIME_"))}
    guest = ["--disable-gems", "-e", "puts RUBY_DESCRIPTION"]
    artifact = scratch / "ruby.wmir"
    compiled = scratch / "ruby.cwasm"
    snapshot = scratch / "snapshot"

    def run(args, trace=False):
        return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                              env=dict(env, WARDITE_TRACE="1") if trace else env, check=True)

    control = next(iter(builds.values()))
    run([control, "--compile-wmir", artifact, "--", wasm])
    run([wasmtime, "compile", "-C", "cache=n", "-o", compiled, wasm])
    commands = {name: [binary, "--snapshot", snapshot, "--", artifact, *guest]
                for name, binary in builds.items()}
    commands["wasmtime"] = [wasmtime, "run", "--allow-precompiled", compiled, *guest]
    first = next(iter(commands.values()))
    expected = run(first).stdout
    if not expected.startswith(b"ruby 4.0.9 ") or b"wasm32-wasi" not in expected:
        raise ValueError(expected)
    run(first, trace=True)
    for name in builds:
        probe = run(commands[name], trace=True)
        if (probe.stdout != expected or b"WMIR mapped:" not in probe.stderr
                or b"snapshot restored:" not in probe.stderr):
            raise ValueError((name, probe.stderr))

    def inputs():
        return {str(p.relative_to(scratch)): digest(p)
                for p in [artifact, compiled, *sorted(snapshot.iterdir())]}

    initial = inputs()
    samples = {name: [] for name in commands}
    names = list(commands)
    power = {}
    if platform.system() == "Darwin":
        power["before"] = macos_lowpowermode()
    for i in range(-2, rounds):
        start = i % len(names)
        order = names[start:] + names[:start]
        if (i // len(names)) % 2:
            order.reverse()
        for name in order:
            before = clock()
            result = run(commands[name])
            duration = clock() - before
            if result.stdout != expected:
                raise ValueError((name, result.stdout))
            if i >= 0:
                samples[name].append(duration)
    if power:
        power["after"] = macos_lowpowermode()
    if inputs() != initial:
        raise ValueError("prepared inputs changed")
    data = dict(platform=platform.platform(), guest_output=expected.decode().strip(),
                commands={k: list(map(str, v)) for k, v in commands.items()},
                wasmtime=run([wasmtime, "--version"]).stdout.decode().strip(),
                sha256={k: digest(p) for k, p in {**builds, "wasmtime": wasmtime, "wasm": wasm}.items()},
                prepared_sha256=initial, wall_ns=samples)
    if power:
        data["macos_lowpowermode"] = power
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wardite", nargs=2, metavar=("NAME", "BINARY"), action="append", required=True)
    parser.add_argument("--wasmtime", required=True, type=Path)
    parser.add_argument("--wasm", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rounds", default=32, type=int)
    args = parser.parse_args()
    builds = {k: Path(v).resolve() for k, v in args.wardite}
    if len(builds) != len(args.wardite) or {"wasmtime", "wasm"} & builds.keys() or args.rounds < 1:
        parser.error("use unique Wardite names other than wasm/wasmtime and a positive round count")
    with tempfile.TemporaryDirectory() as directory:
        data = compare(builds, args.wasmtime.resolve(), args.wasm.resolve(), args.rounds, Path(directory))
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    for name, values in data["wall_ns"].items():
        print(f"{name}: {median(values)/1e6:.3f} ms")
