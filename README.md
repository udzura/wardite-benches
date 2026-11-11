# wardite-benches

Wardite の試験・ベンチマーク用 Wasm プログラム集です。Wardite を Spinel でビルドし、`--new-engine` で実行します。

| ディレクトリ | 内容 |
| --- | --- |
| `wat/` | 小さなサンプルや、使う Wasm 命令を指定したいサンプル |
| `rust/examples/` | Cargo の example としてビルドする Wasm サンプル |
| `script/` | 環境チェック、ビルド、実行の入口 |
| `spinel/` | Wardite のネイティブビルド設定 |

## ビルドと実行

`spinel`、C コンパイラ、`make`、`wat2wasm`（WABT）、Rust と Cargo が必要です。Wardite のソースは既定で `../wardite` を参照します。別のチェックアウトを使う場合は `WARDITE_DIR` に絶対パスを指定してください。`SPINEL` と `SPINELFLAGS` でコンパイラとフラグも指定できます（既定は `spinel` と `-O2`）。

`script/doctor` で Wardite のソース、必要なコマンド、Rust の Wasm ターゲットを確認できます。必須項目が不足している場合は終了コード `1` を返します。ベンチマーク用の `hyperfine` は任意です。

```sh
rustup target add wasm32-unknown-unknown
script/doctor
script/build
script/run --no-wasi --invoke xorshift -- build/wat/xorshift.wasm 1 1
script/run --no-wasi --invoke xorshift -- build/rust/wasm32-unknown-unknown/release/examples/xorshift.wasm 1 1
```

両方とも `return value: I32(270369)` を出力します。`xorshift` の引数は反復回数とシードです。`script/run` には Wardite CLI の引数をそのまま渡せます。Wardite だけを再ビルドする場合は `make -C spinel` を実行します。

### Rust の数値サンプル

`splitmix64` は反復回数と 64 ビットのシードを受け取り、生成した乱数すべての XOR を返します。[SplitMix64 の参照実装](https://prng.di.unimi.it/splitmix64.c)

`mandelbrot_f32` と `mandelbrot_f64` はグリッドの幅、高さ、点ごとの最大反復回数を受け取り、全点で実行した反復回数の合計を下位 32 ビットで返します。

```sh
examples=build/rust/wasm32-unknown-unknown/release/examples
script/run --no-wasi --invoke splitmix64 -- "$examples/splitmix64.wasm" 1 0
# return value: I64(16294208416658607535)
script/run --no-wasi --invoke mandelbrot_f32 -- "$examples/mandelbrot.wasm" 160 120 100
# return value: I32(479498)
script/run --no-wasi --invoke mandelbrot_f64 -- "$examples/mandelbrot.wasm" 160 120 100
# return value: I32(479480)
```

## Wasmtime との結果比較

`script/compare WASM EXPORT [ARG ...]` は、ビルド済みの Wasm を Wardite の new-engine と Wasmtime で実行し、export の数値の戻り値を 1 つ比較します。Python 3 と `wasmtime` が必要です。

```sh
script/compare build/wat/xorshift.wasm xorshift 1 1
script/compare build/rust/wasm32-unknown-unknown/release/examples/splitmix64.wasm splitmix64 7 -1
```

整数は符号の表示が違ってもビット列が同じなら一致とします。浮動小数点は戻り値の精度で比較し、NaN 同士は一致とします。終了コードは一致が `0`、不一致が `1`、実行や出力の読み取りに失敗した場合が `2` です。

## ベンチマーク

ビルド後、同じ入力で各サンプルを `hyperfine` から実行できます。計測値には Wardite のプロセス起動、Wasm のロードと変換、実行が含まれます。

```sh
hyperfine --warmup 2 \
  'script/run --no-wasi --invoke xorshift -- build/wat/xorshift.wasm 5000000 1' \
  'script/run --no-wasi --invoke xorshift -- build/rust/wasm32-unknown-unknown/release/examples/xorshift.wasm 5000000 1'
```
