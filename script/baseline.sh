#!/bin/sh
# Usage: build/baseline.sh  (run from wardite-benches root)
# Checks results with script/compare, then times each engine binary directly
# (script/run adds a shell start-up of ~24 ms on macOS).
set -u
ex=build/rust/wasm32-unknown-unknown/release/examples
wasi=build/rust/wasm32-wasip1/release/examples
fx=build/fixtures
W="build/wardite --new-engine"
echo "# wardite $(git -C ../wardite rev-parse --short HEAD)  $(date '+%F %T')  $(sysctl -n machdep.cpu.brand_string)"
shasum -a 256 $wasi/base64_codec.wasm $wasi/png_grayscale.wasm
hf() { hyperfine -N --warmup 2 --runs 9 "$@" 2>&1 | grep -E 'Benchmark|Wall Time|Memory'; }
num() { # wasm export args...
  wasm=$1 fn=$2; shift 2
  echo; echo "## $wasm $fn $*"; script/compare --iwasm "$wasm" "$fn" "$@" | tail -1
  hf -n Wardite "$W --no-wasi --invoke $fn -- $wasm $*" -n Wasmtime "wasmtime run --invoke $fn -- $wasm $*" -n iwasm "iwasm --interp -f $fn $wasm $*"
}
wasi_case() { # input wasm args...
  input=$1 wasm=$2; shift 2
  echo; echo "## $wasm $* < $input"; script/compare --iwasm --wasi-stdin "$input" "$wasm" "$@" | tail -1
  hf --input "$input" -n Wardite "$W -- $wasm $*" -n Wasmtime "wasmtime run -- $wasm $*" -n iwasm "iwasm --interp $wasm $*"
  for i in 1 2 3 4 5 6 7 8 9; do WARDITE_TRACE=1 $W -- $wasm "$@" < "$input" 2>&1 >/dev/null | grep -a load_from_buffer; done |
    awk '{print $2*1000}' | sort -n | awk '{a[NR]=$1} END {printf "  load_from_buffer median %.1f ms\n", a[int((NR+1)/2)]}'
}
num build/wat/xorshift.wasm xorshift 100000000 1
num $ex/xorshift.wasm xorshift 100000000 1
num $ex/splitmix64.wasm splitmix64 10000000 1
num $ex/mandelbrot.wasm mandelbrot_f32 200 150 100
num $ex/mandelbrot.wasm mandelbrot_f64 200 150 100
num $ex/monte_carlo_pi.wasm monte_carlo_pi 1000000 1
wasi_case $fx/empty $wasi/base64_codec.wasm encode
wasi_case $fx/data.bin $wasi/base64_codec.wasm encode
wasi_case $fx/data-4m.bin $wasi/base64_codec.wasm encode
wasi_case $fx/data.b64 $wasi/base64_codec.wasm decode
wasi_case $fx/data-4m.b64 $wasi/base64_codec.wasm decode
wasi_case $fx/rgb.png $wasi/png_grayscale.wasm
wasi_case $fx/rgb-1024.png $wasi/png_grayscale.wasm
