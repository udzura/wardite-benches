"""Measure local CSE with one Spinel executable. Run from wardite-benches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def measure(binary, build, work, runs, large, reverse):
    wasi = build / "rust/wasm32-wasip1/release/examples"
    fixture = build / "fixtures"
    loop = work / "cases.wasm"
    subprocess.run(["wat2wasm", HERE / "cases.wat", "-o", loop], check=True)
    stem = "data-4m" if large else "data"
    cases = [
        ("encode", wasi / "base64_codec.wasm", ["encode"], fixture / (stem + ".bin")),
        ("decode", wasi / "base64_codec.wasm", ["decode"], fixture / (stem + ".b64")),
        ("png", wasi / "png_grayscale.wasm", [], fixture / ("rgb-1024.png" if large else "rgb.png")),
        ("loop", loop, ["1000000"], None),
    ]
    for case, wasm, args, input_path in cases:
        numeric = input_path is None
        stdin = b"" if numeric else input_path.read_bytes()
        reference = ["wasmtime", "run"] + (["--invoke", "loop"] if numeric else [])
        expected = subprocess.run(reference + [wasm, *args], input=stdin,
                                  check=True, capture_output=True).stdout
        invocation = (["--no-wasi", "--invoke", "loop"] if numeric else []) + ["--", wasm, *args]
        print(json.dumps(dict(case=case, wasm=digest(wasm.read_bytes()), stdin=digest(stdin),
                              output=digest(expected), bytes=len(stdin))), flush=True)
        for mode, count in (("profile", 1), ("time", runs), ("generation", runs)):
            for rep in range(0 if mode != "profile" else 1, count + 1):
                for cse in ((0, 1) if (rep + reverse) % 2 else (1, 0)):
                    env = dict(os.environ, WARDITE_MIR_CSE=str(cse), WARDITE_MIR_JIT="0")
                    env.pop("WARDITE_TRACE", None)
                    flags = []
                    if mode == "profile":
                        flags = ["--mir-profile"]
                    if mode == "generation":
                        flags = ["--mir-eager"]
                        env["WARDITE_TRACE"] = "1"
                    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
                        source.write(stdin)
                        source.seek(0)
                        start = time.monotonic()
                        proc = subprocess.Popen([binary, *flags, *invocation], stdin=source,
                                                stdout=output, stderr=subprocess.PIPE, env=env, text=True)
                        lines = []
                        translated = loaded = None
                        for line in proc.stderr:
                            now = time.monotonic()
                            lines.append(line)
                            if line.startswith("semantic MIR translation:"):
                                translated = now - float(line.split()[-1])
                            if line.startswith("load_from_buffer:"):
                                loaded = now
                        status = proc.wait()
                        elapsed = time.monotonic() - start
                        output.seek(0)
                        actual = output.read()
                    trace = "".join(lines)
                    if numeric:
                        match = re.search(r"^return value: I32\((-?\d+)\)$", trace, re.M)
                        valid = actual == b"" and match and (int(match[1]) & 0xffffffff) == (int(expected) & 0xffffffff)
                    else:
                        valid = actual == expected
                    if status or not valid:
                        raise RuntimeError(f"{case=} {cse=} {mode=} {status=}\n{trace}")
                    row = dict(case=case, cse=cse, mode=mode, run=rep)
                    if mode == "profile":
                        row["opcodes"] = {name: int(n) for name, n in re.findall(r"^opcode (\w+) (\d+)$", trace, re.M)}
                        row["dispatches"] = int(re.search(r"dispatches=(\d+)", trace)[1])
                        assert sum(row["opcodes"].values()) == row["dispatches"]
                    elif mode == "time":
                        row["ms"] = elapsed * 1000
                    else:
                        row["ms"] = (loaded - translated) * 1000
                    if rep:
                        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--build", type=Path, default=Path("build"))
    parser.add_argument("--runs", type=int, default=9)
    parser.add_argument("--large", action="store_true")
    parser.add_argument("--reverse", action="store_true", help="reverse the order of the first pair")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("runs must be positive")
    with tempfile.TemporaryDirectory() as tmp:
        measure(args.binary.resolve(strict=True), args.build.resolve(strict=True), Path(tmp), args.runs, args.large, args.reverse)
