"""Compare two Spinel Wardite executables in alternating order (JSON Lines)."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from recursive import WIDTH, module


def run(command, expected, cache_phase=None):
    env = dict(os.environ, WARDITE_MIR_JIT="0", WARDITE_TRACE="1")
    with tempfile.TemporaryFile() as stdout:
        start = time.monotonic()
        proc = subprocess.Popen(command, env=env, stdout=stdout, stderr=subprocess.PIPE, text=True)
        lines = []
        mir_start = loaded = None
        with proc.stderr:
            for line in proc.stderr:
                now = time.monotonic()
                if line.startswith("semantic MIR translation:"):
                    mir_start = now - float(line.split()[-1])
                elif line.startswith("load_from_buffer:"):
                    loaded = now
                lines.append(line)
        _, status, usage = os.wait4(proc.pid, 0)
        elapsed = time.monotonic() - start
        proc.returncode = os.waitstatus_to_exitcode(status)
        stdout.seek(0)
        output = stdout.read().decode()
        trace = "".join(lines)
    if "--invoke" in command:
        matches = output == "" and expected in trace.splitlines()
    else:
        matches = output == expected + "\n"
    if proc.returncode or not matches:
        raise RuntimeError(f"{command}\n{output}{trace}")
    rss_bytes = usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024
    row = dict(seconds=elapsed, rss_bytes=rss_bytes)
    if "--mir-eager" in command:
        # In eager, uncached mode this interval ends just after lowering.
        # The Wasm guest has no start section that would run inside the load.
        row["mir_seconds"] = loaded - mir_start
    if cache_phase:
        match = re.search(rf"^MIR2 cache {cache_phase}: (.+)$", trace, re.M)
        if not match:
            raise RuntimeError(trace)
        row["cache_bytes"] = Path(match[1]).stat().st_size
    row["load_seconds"] = float(re.search(r"^load_from_buffer: (.+)$", trace, re.M)[1])
    return row


def measure(args, work):
    wasm = work / "recursive.wasm"
    subprocess.run(["wat2wasm", "-", "-o", wasm], input=module(), text=True, check=True)
    guest = ["--", args.ruby_wasm, "--disable-gems", "-e", "puts RUBY_DESCRIPTION"]
    description = subprocess.check_output(["wasmtime", "run", *guest[1:]], text=True).strip()
    engines = [("before", args.before), ("after", args.after)]

    for case in ("fresh", "twice", "reuse32", "ruby-lazy", "ruby-eager", "ruby-miss", "ruby-hit"):
        runs = args.misses if case in ("ruby-eager", "ruby-miss") else args.runs
        for rep in range(runs + 1):  # First pair warms both executables.
            for version, binary in (engines if rep % 2 else reversed(engines)):
                cache_phase = None
                if case.startswith("ruby"):
                    command = [binary]
                    if case == "ruby-eager":
                        command.append("--mir-eager")
                    elif case != "ruby-lazy":
                        cache_phase = case.split("-")[1]
                        cache = work / f"{version}-{rep if cache_phase == 'miss' else 0}"
                        command += ["--mir-cache", cache]
                    command += guest
                    expected = description
                else:
                    passes = {"fresh": 1, "twice": 2, "reuse32": 32}[case]
                    command = [binary, "--no-wasi", "--invoke", "run", "--", wasm,
                               str(args.depth), str(passes)]
                    result = ((args.depth + WIDTH * (WIDTH + 1) // 2) * passes) & 0xffffffff
                    expected = f"return value: I32({result})"
                row = run(command, expected, cache_phase)
                if rep:
                    print(json.dumps(dict(case=case, version=version, run=rep, **row)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("before", "after", "ruby_wasm"):
        parser.add_argument(key, type=lambda p: Path(p).resolve(strict=True))
    parser.add_argument("--depth", type=int, default=10000)
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--misses", type=int, default=3)
    args = parser.parse_args()
    if min(args.runs, args.misses, args.depth) < 1:
        parser.error("runs, misses and depth must be positive")
    with tempfile.TemporaryDirectory() as directory:
        measure(args, Path(directory))
