#!/bin/sh
# Run from wardite-benches. Capture optimized baseline blocks on the large fixtures.
set -eu
wardite=${1:?wardite source directory}
build=${2:-build}
out=${3:-build/adr0027-census}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$out"
wat2wasm "$here/cases.wat" -o "$out/cases.wasm"
run() {
  case_name=$1
  shift
  CSE_CENSUS="$out/$case_name.json" WARDITE_MIR_CSE=0 WARDITE_MIR_JIT=0 \
    ruby -I"$wardite/lib" -r"$here/census.rb" "$wardite/exe/wardite" --mir-profile "$@" > /dev/null
}
wasi="$build/rust/wasm32-wasip1/release/examples"
run encode -- "$wasi/base64_codec.wasm" encode < "$build/fixtures/data-4m.bin"
run decode -- "$wasi/base64_codec.wasm" decode < "$build/fixtures/data-4m.b64"
run png -- "$wasi/png_grayscale.wasm" < "$build/fixtures/rgb-1024.png"
run loop --no-wasi --invoke loop -- "$out/cases.wasm" 1000000
