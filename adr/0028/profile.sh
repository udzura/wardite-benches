#!/bin/sh
set -eu
root=${1:?Wardite source directory}
build=${2:-build}
out=${3:-build/adr0028-profile}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$out"
run() {
  name=$1; input=$2; shift 2
  WARDITE_MIR_CSE=0 LOOP_CENSUS="$out/loops-$name.json" ruby -I"$root/lib" -r"$here/loops.rb" "$root/exe/wardite" --mir-enable licm --mir-profile "$@" <"$input" >/dev/null
  for switch in enable disable; do
    WARDITE_MIR_CSE=0 BLOCK_PROFILE="$out/blocks-$name-$switch.json" ruby -I"$root/lib" -r"$here/blocks.rb" "$root/exe/wardite" "--mir-$switch" exit_copy --mir-profile "$@" <"$input" >/dev/null
  done
}
wasi="$build/rust/wasm32-wasip1/release/examples"
run encode "$build/fixtures/data.bin" -- "$wasi/base64_codec.wasm" encode
run decode "$build/fixtures/data.b64" -- "$wasi/base64_codec.wasm" decode
run png "$build/fixtures/rgb.png" -- "$wasi/png_grayscale.wasm"
run sieve /dev/null --no-wasi --invoke count_primes_sieve -- "$build/rust/wasm32-unknown-unknown/release/examples/count_primes.wasm" 10000
run ruby /dev/null -- "$root/ruby-wasm32-wasi/usr/local/bin/ruby" --disable-gems -e 'puts RUBY_DESCRIPTION'
