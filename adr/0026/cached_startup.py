"""Time Ruby Wasm with prebuilt MIR2 and startup snapshots (JSON Lines)."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from measure import run


def measure(args, work):
    guest = ["--", args.ruby_wasm, "--disable-gems", "-e", "puts RUBY_DESCRIPTION"]
    expected = subprocess.check_output(["wasmtime", "run", *guest[1:]], text=True).strip()
    engines = [("before", args.before), ("after", args.after)]
    for name, binary in engines:
        run([binary, "--mir-cache", work / name, "--snapshot", work / name, *guest],
            expected, "miss", "saved")
    for case, options, snapshot in [
        ("ruby-snapshot", [], True),
        ("ruby-hit-eager", ["--mir-eager"], False),
        ("ruby-snapshot-eager", ["--mir-eager"], True),
    ]:
        for rep in range(args.runs + 1):
            for name, binary in (engines if rep % 2 else reversed(engines)):
                command = [binary, "--mir-cache", work / name, *options]
                if snapshot:
                    command += ["--snapshot", work / name]
                row = run(command + guest, expected, "hit", "restored" if snapshot else None)
                if rep:
                    print(json.dumps(dict(case=case, version=name, run=rep, **row)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("before", "after", "ruby_wasm"):
        parser.add_argument(key, type=lambda p: Path(p).resolve(strict=True))
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("runs must be positive")
    with tempfile.TemporaryDirectory() as directory:
        measure(args, Path(directory))
