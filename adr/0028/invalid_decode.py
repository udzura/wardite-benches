"""Check the offset and offending byte on taken Base64 decoder exits."""
import argparse
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("wardite")
parser.add_argument("wasm")
args = parser.parse_args()
engines = (["wasmtime", "run"], [args.wardite, "--mir-disable", "exit_copy", "--"],
           [args.wardite, "--mir-enable", "exit_copy", "--"])
for offset in [*range(64), 127, 1022]:
    data = bytearray(b"A" * 1024)
    data[offset] = ord("!")
    expected = f"InvalidByte({offset}, 33)".encode()
    for engine in engines:
        result = subprocess.run([*engine, args.wasm, "decode"], input=data, capture_output=True)
        if result.returncode == 0 or result.stdout or expected not in result.stderr:
            raise RuntimeError(f"{engine} offset={offset}: {result.stderr!r}")
print("66 invalid byte offsets agree for both Wardite configurations and Wasmtime")
