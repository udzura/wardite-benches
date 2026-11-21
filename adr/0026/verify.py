"""Check slot remapping, cache restore and native bailout on Apple Silicon."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def verify(binary, wasm, cache, flags, jit, export, arg, expected, phase):
    env = dict(os.environ, WARDITE_MIR_JIT=str(jit), WARDITE_TRACE="1")
    args = [binary, *flags, "--no-wasi", "--invoke", export]
    if phase != "lazy":
        args += ["--mir-cache", cache]
    proc = subprocess.run([*args, "--", wasm, str(arg)], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = proc.stdout
    correct = ((proc.returncode == 0 and f"return value: I32({expected})" in output)
               if expected is not None else
               (proc.returncode == 1 and "integer divide by zero" in output))
    if phase != "lazy":
        correct &= f"MIR2 cache {phase}:" in output
    if jit and export == "rem":
        correct &= "MIR JIT function 0: compiled" in output and "mapping unavailable" not in output
        if expected is None:
            correct &= "interpreter bailout" in output
    if not correct:
        raise RuntimeError(f"{flags=} {jit=} {phase=} {export=} {arg=}\n{output}")


def main(binary):
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        wasm = work / "operands.wasm"
        subprocess.run(["wasm-tools", "parse", HERE / "operands.wat", "-o", wasm], check=True)
        checks = 0
        for compact in (False, True):
            flags = [] if compact else ["--mir-disable", "compact"]
            for jit in (0, 1):
                for export, arg, expected in (("rem", 2, 1), ("run", 2, 44),
                                              ("rem", 0, None), ("run", 0, None)):
                    cache = work / f"{compact}-{jit}-{export}-{arg}"
                    for phase in ("lazy", "miss", "hit"):
                        verify(binary, wasm, cache, flags, jit, export, arg, expected, phase)
                        checks += 1
    print(f"{checks} result, trap and cache checks passed")


if __name__ == "__main__":
    main(sys.argv[1])
