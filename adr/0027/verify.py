"""Check outputs and traps across local CSE, MIR2 writes and restores."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def result(command, env, reference=False, phase=None, cache_file=None):
    proc = subprocess.run(command, env=env, capture_output=True, text=True)
    if phase and f"MIR2 cache {phase}:" not in proc.stderr:
        raise RuntimeError(proc.stderr)
    if cache_file and f"MIR2 cache hit: {cache_file}" not in proc.stderr.splitlines():
        raise RuntimeError(proc.stderr)
    if proc.returncode:
        if "integer divide by zero" in proc.stderr:
            return "divide by zero"
        raise RuntimeError(proc.stderr)
    return (int(proc.stdout) if reference else
            int(re.search(r"^return value: I32\((-?\d+)\)$", proc.stderr, re.M)[1])) & 0xffffffff


def verify(binary, work):
    wasm = work / "cases.wasm"
    subprocess.run(["wat2wasm", HERE / "cases.wat", "-o", wasm], check=True)
    checks = overrides = 0
    for name, args in (("input", [255, 256]), ("result", [259]), ("join", [1, 4]),
                       ("escape", [0, 259]), ("side", [511]), ("wide", [4294967298]),
                       ("divide", [0, 7]), ("loop", [0, 1, 518])):
        for arg in args:
            guest = [wasm, str(arg)]
            expected = result(["wasmtime", "run", "--invoke", name, *guest], os.environ, True)
            cache = work / f"{name}-{arg}"
            for cse in (0, 1):
                env = dict(os.environ, WARDITE_TRACE="1", WARDITE_MIR_JIT="0", WARDITE_MIR_CSE=str(cse))
                for phase in (None, "miss", "hit"):
                    flags = ["--mir-cache", cache] if phase else []
                    actual = result([binary, *flags, "--no-wasi", "--invoke", name, "--", *guest], env, phase=phase)
                    if actual != expected:
                        raise RuntimeError(f"{name=} {arg=} {cse=} {phase=} {expected=} {actual=}")
                    checks += 1
                if cse == 0:
                    off_cache, = cache.glob("*.mir2")
            # An explicit disable must select the off-cache even in an opt-in process.
            flags = ["--mir-disable", "cse", "--mir-cache", cache]
            actual = result([binary, *flags, "--no-wasi", "--invoke", name, "--", *guest], env, phase="hit", cache_file=off_cache)
            if actual != expected:
                raise RuntimeError(f"explicit disable: {name=} {arg=} {expected=} {actual=}")
            overrides += 1
    print(f"{checks} result, trap and cache checks plus {overrides} explicit-disable cache hits passed")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        verify(sys.argv[1], Path(directory))
