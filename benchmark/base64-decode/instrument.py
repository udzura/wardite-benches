"""Place WASI timers around calls in the existing release base64_codec.wasm."""
import argparse
from pathlib import Path
import re
import subprocess

# Twelve little-endian u64 timestamps, followed by an iovec and a byte count.
# Rust's WASI stack grows down. Reserve a 16-byte-aligned frame around main.
EVENTS = ("read_start", "read_end", "decode_start", "kernel_start", "bulk_start",
          "bulk_end", "kernel_end", "decode_end", "write_start", "write_end",
          "flush_start", "flush_end")
SIZE = len(EVENTS) * 8
FRAME = 112


def unique(indices, description):
    matches = list(indices)
    if len(matches) != 1:
        raise ValueError(f"expected one {description}, found {len(matches)}")
    return matches[0]


def markers(event):
    return f"i32.const {EVENTS.index(event) * 8}\n    call $bench_tick"


def instrument(source, bulk):
    lines = source.splitlines()
    # Insert an import only after confirming that every function has a name.
    # wasm-tools emits symbolic references for named functions, preserving
    # the exports, table entries and call targets as function indices shift.
    if any(re.search(r'\(func \(;\d+;\)', line) for line in lines):
        raise ValueError("expected the unstripped Rust release module")
    funcs = [i for i, line in enumerate(lines) if line.startswith("  (func ")]
    starts = set(funcs)
    owners = []
    owner = ""
    for i, line in enumerate(lines):
        if i in starts:
            owner = line.split()[1]
        owners.append(owner)

    def site(owner_suffix, pattern):
        return unique((i for i, line in enumerate(lines) if owners[i].endswith(owner_suffix)
                       and re.fullmatch(pattern, line.strip())), pattern)

    def surround(i, before, after, end=None):
        last = i if end is None else end
        lines[i] = "    " + before + "\n" + lines[i]
        lines[last] += "\n    " + after

    main = "12base64_codec4main"
    for pattern, label in [(r"call \$.*StdinLock.*Read11read_to_end", "read"),
                           (r"call_indirect \(type \d+\)", "decode"),
                           (r"call \$.*StdoutLock.*Write9write_all", "write"),
                           (r"call \$.*StdoutLock.*Write5flush", "flush")]:
        surround(site(main, pattern), markers(label + "_start"), markers(label + "_end"))

    kernel_call = site("", r"call \$.*GeneralPurpose.*15internal_decode")
    surround(kernel_call, markers("kernel_start"), markers("kernel_end"))
    if bulk:
        # The bulk loop processes four 8-symbol groups. Record once on entry
        # from outside and once on normal exit, never on a loop backedge.
        candidates = []
        for i, line in enumerate(lines):
            if owners[i].endswith("15internal_decode") and line.lstrip().startswith("loop "):
                indent = line[:len(line) - len(line.lstrip())]
                end = lines.index(indent + "end", i + 1)
                if sum(op.strip() == "i64.load8_u" for op in lines[i:end]) == 32:
                    candidates.append((i, end))
        first, last = unique(candidates, "32-symbol decode loop")
        surround(first, markers("bulk_start"), markers("bulk_end"), last)

    start = site("$_start", r"call \$__main_void")
    surround(start, f"""global.get $__stack_pointer
    i32.const {FRAME}
    i32.sub
    global.set $bench_frame
    global.get $bench_frame
    global.set $__stack_pointer
    (i64.store offset={8*EVENTS.index("bulk_start")} (global.get $bench_frame) (i64.const 0))
    (i64.store offset={8*EVENTS.index("bulk_end")} (global.get $bench_frame) (i64.const 0))""", f"""call $bench_report
    global.get $bench_frame
    i32.const {FRAME}
    i32.add
    global.set $__stack_pointer""")
    first_import = next(i for i, line in enumerate(lines) if line.startswith("  (import "))
    lines[first_import] = ('  (import "wasi_snapshot_preview1" "clock_time_get" '
                           '(func $bench_clock (param i32 i64 i32) (result i32)))\n' + lines[first_import])
    fd_write = re.search(r'"fd_write" \(func (\$[^ ]+)', source)[1]
    lines[funcs[0]] = f"""  (global $bench_frame (mut i32) (i32.const 0))
  (func $bench_tick (param $offset i32)
    (if (call $bench_clock (i32.const 1) (i64.const 1)
          (i32.add (global.get $bench_frame) (local.get $offset))) (then unreachable)))
  (func $bench_report
    (i32.store offset={SIZE} (global.get $bench_frame) (global.get $bench_frame))
    (i32.store offset={SIZE+4} (global.get $bench_frame) (i32.const {SIZE}))
    (if (call {fd_write} (i32.const 2) (i32.add (global.get $bench_frame) (i32.const {SIZE}))
          (i32.const 1) (i32.add (global.get $bench_frame) (i32.const {SIZE+8}))) (then unreachable))
    (if (i32.ne (i32.load offset={SIZE+8} (global.get $bench_frame)) (i32.const {SIZE})) (then unreachable)))
""" + lines[funcs[0]]
    return "\n".join(lines) + "\n"


def build(wasm, out):
    source = subprocess.check_output(["wasm-tools", "print", wasm], text=True)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("phases", "bulk"):
        target = out / (name + ".wasm")
        subprocess.run(["wasm-tools", "parse", "-", "-o", target],
                       input=instrument(source, name == "bulk"), text=True, check=True)
        subprocess.run(["wasm-tools", "validate", target], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    build(args.module, args.out)
