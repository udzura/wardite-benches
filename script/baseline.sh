#!/bin/sh
# Usage: script/baseline.sh [OUT_DIR]
#
# Records the measurements of Wardite ADR 0018. Each case is first checked
# against Wasmtime and iwasm, then the three engine binaries are timed with
# hyperfine (launched directly: script/run would add a shell start-up).
# WASI cases also record the Wardite load time (WARDITE_TRACE) and the MIR
# opcode counts (--mir-profile). OUT_DIR defaults to
# build/results/<timestamp>; summary.md tabulates the medians.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
out=${1:-build/results/$(date +%Y%m%d-%H%M%S)}
runs=${RUNS:-9}
mkdir -p "$out"
: > "$out/cases.txt"

ex=build/rust/wasm32-unknown-unknown/release/examples
wasi=build/rust/wasm32-wasip1/release/examples
fx=build/fixtures
W="build/wardite --new-engine"

{
    echo "wardite: $(sed -n 1p build/wardite.version)"
    echo "spinel: $(sed -n 2p build/wardite.version)"
    echo "wardite-benches: $(git describe --always --dirty)"
    echo "cpu: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || uname -m)"
    echo "os: $(sw_vers -productVersion 2>/dev/null || uname -sr)"
    echo "wasmtime: $(wasmtime --version)"
    echo "iwasm: $(iwasm --version | head -1)"
    echo "$(hyperfine --version)"
    shasum -a 256 build/wat/xorshift.wasm $ex/xorshift.wasm $ex/splitmix64.wasm $ex/mandelbrot.wasm \
        $ex/monte_carlo_pi.wasm $ex/count_primes.wasm $ex/crc8_stream.wasm $wasi/base64_codec.wasm $wasi/png_grayscale.wasm $wasi/json_log_summary.wasm $wasi/rss_summary.wasm
} > "$out/env.txt"

bench() { # NAME HYPERFINE_ARGS...
    name=$1
    shift
    echo "$name" >> "$out/cases.txt"
    hyperfine -N --warmup 2 --runs "$runs" --export-json "$out/$name.json" "$@" > "$out/$name.hyperfine.txt" 2>&1
}

check() { # NAME COMPARE_ARGS...
    name=$1
    shift
    if ! script/compare --iwasm "$@" > "$out/$name.compare.txt" 2>&1; then
        echo "$name: engines disagree, see $out/$name.compare.txt" >&2
        exit 1
    fi
}

num() { # NAME WASM EXPORT ARGS...
    name=$1 wasm=$2 fn=$3
    shift 3
    echo "$name" >&2
    check "$name" "$wasm" "$fn" "$@"
    bench "$name" -n Wardite "$W --no-wasi --invoke $fn -- $wasm $*" \
        -n Wasmtime "wasmtime run --invoke $fn -- $wasm $*" -n iwasm "iwasm --interp -f $fn $wasm $*"
}

wasi_case() { # NAME INPUT WASM ARGS...
    name=$1 input=$2 wasm=$3
    shift 3
    echo "$name" >&2
    check "$name" --wasi-stdin "$input" "$wasm" "$@"
    bench "$name" --input "$input" -n Wardite "$W -- $wasm $*" \
        -n Wasmtime "wasmtime run -- $wasm $*" -n iwasm "iwasm --interp $wasm $*"
    i=0
    while [ "$i" -lt "$runs" ]; do
        WARDITE_TRACE=1 $W -- "$wasm" "$@" < "$input" 2>&1 > /dev/null | grep -a '^load_from_buffer: '
        i=$((i + 1))
    done > "$out/$name.load.txt"
    $W --mir-profile -- "$wasm" "$@" < "$input" 2>&1 > /dev/null | grep -a -E '^(dispatches=|opcode )' > "$out/$name.mir.txt"
}

num xorshift-wat build/wat/xorshift.wasm xorshift 100000000 1
num xorshift $ex/xorshift.wasm xorshift 100000000 1
num splitmix64 $ex/splitmix64.wasm splitmix64 10000000 1
num mandelbrot-f32 $ex/mandelbrot.wasm mandelbrot_f32 200 150 100
num mandelbrot-f64 $ex/mandelbrot.wasm mandelbrot_f64 200 150 100
num monte-carlo-pi $ex/monte_carlo_pi.wasm monte_carlo_pi 1000000 1
num count-primes $ex/count_primes.wasm count_primes 1000000
num count-primes-sieve $ex/count_primes.wasm count_primes_sieve 1000000
num crc8-stream $ex/crc8_stream.wasm crc8_stream 4096 0
num crc8-stream-grown $ex/crc8_stream.wasm crc8_stream 4096 1
wasi_case base64-encode-empty $fx/empty $wasi/base64_codec.wasm encode
wasi_case base64-encode $fx/data.bin $wasi/base64_codec.wasm encode
wasi_case base64-encode-4m $fx/data-4m.bin $wasi/base64_codec.wasm encode
wasi_case base64-decode $fx/data.b64 $wasi/base64_codec.wasm decode
wasi_case base64-decode-4m $fx/data-4m.b64 $wasi/base64_codec.wasm decode
wasi_case png $fx/rgb.png $wasi/png_grayscale.wasm
wasi_case png-1024 $fx/rgb-1024.png $wasi/png_grayscale.wasm

wasi_case json-log-1k $fx/access-1024.json $wasi/json_log_summary.wasm
wasi_case json-log-16k $fx/access-16384.json $wasi/json_log_summary.wasm

wasi_case rss-1k $fx/feed-1024.xml $wasi/rss_summary.wasm
wasi_case rss-16k $fx/feed-16384.xml $wasi/rss_summary.wasm

python3 - "$out" > "$out/summary.md" <<'EOF'
import json
import statistics
import sys
from pathlib import Path

out = Path(sys.argv[1])


def seconds(value):
    return f"{value * 1000:.1f} ms" if value < 1 else f"{value:.3f} s"


print("| Case | Wardite | Load | Wardite RSS | Wasmtime | iwasm | Wardite / Wasmtime | Wardite / iwasm | MIR dispatches |")
print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for name in (out / "cases.txt").read_text().split():
    wardite, wasmtime, iwasm = (r["summary"] for r in json.loads((out / f"{name}.json").read_text())["results"])
    median = lambda r: r["time_wall_clock"]["median"]
    load = mir = "—"
    if (out / f"{name}.load.txt").exists():
        values = [float(line.split()[1]) for line in (out / f"{name}.load.txt").read_text().splitlines()]
        load = seconds(statistics.median(values))
        mir = f"{int((out / f'{name}.mir.txt').read_text().split()[0].split('=')[1]):,}"
    rss = wardite["memory_peak_resident"]["max"] / 2**20
    print(f"| {name} | {seconds(median(wardite))} | {load} | {rss:.1f} MiB | {seconds(median(wasmtime))} "
          f"| {seconds(median(iwasm))} | {median(wardite) / median(wasmtime):.1f} "
          f"| {median(wardite) / median(iwasm):.1f} | {mir} |")
EOF
cat "$out/env.txt" "$out/summary.md"
