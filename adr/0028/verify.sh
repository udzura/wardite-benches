#!/bin/sh
set -eu
export WARDITE_MIR_JIT=0 WARDITE_MIR_CSE=0
root=${1:?Wardite source checkout}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
wasm-tools parse "$here/cases.wat" -o "$work/cases.wasm"
wasm-tools validate --features exceptions "$work/cases.wasm"
reference() {
  expected=$1
  export_name=$2
  shift 2
  actual=$(wasmtime run -W exceptions=y --invoke "$export_name" "$work/cases.wasm" "$@")
  if [ "$actual" != "$expected" ]; then
    echo "Wasmtime $export_name: expected $expected, got $actual" >&2
    exit 1
  fi
}
reference 1 inline
reference 2 width
reference 1 signed
reference 8 join 0
reference 10 join 1
reference 7 condition
reference 73 caught
reference 5 dead 71
for n in 0 1 100; do
  reference "$((9 + n * 5))" loop "$n" 5
done
reference 3 edge 255 0 0 1
reference 7 edge 0 255 0 1
reference 9 edge 0 0 255 1
reference 13 edge 0 0 0 8
ruby -I"$root/lib" "$here/verify_stages.rb" "$work/cases.wasm"
spinel --strict-require -O2 -I"$root/lib" "$here/verify.rb" -o "$work/verify"
for runtime in cruby spinel; do
  for mode in none fold cfg dce exit_copy exit_copy+licm licm all; do
    for phase in lazy miss hit; do
      if [ "$runtime" = cruby ]; then
        ruby -I"$root/lib" "$here/verify.rb" "$work/cases.wasm" "$work/$runtime" "$mode" "$phase"
      else
        "$work/verify" "$work/cases.wasm" "$work/$runtime" "$mode" "$phase"
      fi
    done
  done
done
