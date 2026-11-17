# wardite-benches

Wardite の試験・ベンチマーク用 Wasm プログラム集です。Wardite を Spinel でビルドし、`--new-engine` で実行します。

| ディレクトリ | 内容 |
| --- | --- |
| `wat/` | 小さなサンプルや、使う Wasm 命令を指定したいサンプル |
| `rust/examples/` | Cargo の example としてビルドする Wasm サンプル |
| `script/` | 環境チェック、ビルド、実行の入口 |
| `spinel/` | Wardite のネイティブビルド設定 |

## ビルドと実行

`spinel`、C コンパイラ、`make`、`wat2wasm`（WABT）、Rust と Cargo が必要です。Wardite のソースは既定で `../wardite` を参照します。WASI サンプルには Spinel ビルドで WASI Preview 1 が動く Wardite が必要です（1.2.1 で確認）。別のチェックアウトを使う場合は `WARDITE_DIR` に絶対パスを指定してください。`SPINEL` と `SPINELFLAGS` でコンパイラとフラグも指定できます（既定は `spinel` と `-O2`）。

`script/doctor` で Wardite のソース、必要なコマンド、Rust の Wasm ターゲットを確認できます。必須項目が不足している場合は終了コード `1` を返します。ベンチマーク用の `hyperfine` は任意です。

```sh
rustup target add wasm32-unknown-unknown wasm32-wasip1
script/doctor
script/build
script/run --no-wasi --invoke xorshift -- build/wat/xorshift.wasm 1 1
script/run --no-wasi --invoke xorshift -- build/rust/wasm32-unknown-unknown/release/examples/xorshift.wasm 1 1
```

両方とも `return value: I32(270369)` を出力します。`xorshift` の引数は反復回数とシードです。`script/run` には Wardite CLI の引数をそのまま渡せます。Wardite だけを再ビルドする場合は `make -C spinel` を実行します。

### Rust の数値サンプル

`splitmix64` は反復回数と 64 ビットのシードを受け取り、生成した乱数すべての XOR を返します。[SplitMix64 の参照実装](https://prng.di.unimi.it/splitmix64.c)

`mandelbrot_f32` と `mandelbrot_f64` はグリッドの幅、高さ、点ごとの最大反復回数を受け取り、全点で実行した反復回数の合計を下位 32 ビットで返します。

`monte_carlo_pi` は点の数と 64 ビットのシードを受け取ります。SplitMix64 で単位正方形に点を打ち、半径 1 の四分円に入った点の割合を 4 倍して `f64` で返します。点が 0 個の場合は `NaN` を返します。

```sh
examples=build/rust/wasm32-unknown-unknown/release/examples
script/run --no-wasi --invoke splitmix64 -- "$examples/splitmix64.wasm" 1 0
# return value: I64(16294208416658607535)
script/run --no-wasi --invoke mandelbrot_f32 -- "$examples/mandelbrot.wasm" 160 120 100
# return value: I32(479498)
script/run --no-wasi --invoke mandelbrot_f64 -- "$examples/mandelbrot.wasm" 160 120 100
# return value: I32(479480)
script/run --no-wasi --invoke monte_carlo_pi -- "$examples/monte_carlo_pi.wasm" 100000 1
# return value: F64(3.12568)
```

### WASI Preview 1 のサンプル

`base64_codec` の `encode` は標準入力のバイナリを標準アルファベットとパディング付きでエンコードします。`decode` は改行や空白を含まない Base64 を受け取り、元のバイト列を返します。`png_grayscale` は PNG をデコードし、RGB を `0.299R + 0.587G + 0.114B` で 8 ビットのグレースケールに変換します。出力はアルファチャンネルを省いたバイナリ PGM（P5）です。

`script/fixtures` は Python 3 で固定入力を `build/fixtures/` に生成します。自分のファイルも標準入力から渡せます。

```sh
script/fixtures
wasi=build/rust/wasm32-wasip1/release/examples
script/run -- "$wasi/base64_codec.wasm" encode < build/fixtures/data.bin > build/encoded.b64
script/run -- "$wasi/base64_codec.wasm" decode < build/fixtures/data.b64 > build/decoded.bin
script/run -- "$wasi/png_grayscale.wasm" < build/fixtures/rgb.png > build/gray.pgm
```

## エンジン間の結果比較

`script/compare WASM EXPORT [ARG ...]` は、ビルド済みの Wasm を Wardite の new-engine と Wasmtime で実行し、export の数値の戻り値を 1 つ比較します。Python 3 と `wasmtime` が必要です。

```sh
script/compare build/wat/xorshift.wasm xorshift 1 1
script/compare build/rust/wasm32-unknown-unknown/release/examples/splitmix64.wasm splitmix64 7 -1
script/compare build/rust/wasm32-unknown-unknown/release/examples/monte_carlo_pi.wasm monte_carlo_pi 100000 1
```

整数は符号の表示が違ってもビット列が同じなら一致とします。浮動小数点は戻り値の精度で比較し、NaN 同士は一致とします。終了コードは一致が `0`、不一致が `1`、実行や出力の読み取りに失敗した場合が `2` です。

`--iwasm` を付けると `iwasm --interp` も実行します。`--interp` をサポートする `iwasm` が必要です。iwasm の浮動小数点出力は有効数字 7 桁なので、その表示精度で照合します。

WASI コマンドは `script/compare --wasi-stdin FILE WASM [ARG ...]` で実行します。各エンジンに同じファイルを標準入力として渡し、標準出力をバイト単位で比較します。

## ベンチマーク

`script/compare --bench` は戻り値の一致を確認してから、`hyperfine` で選んだエンジンを比較します。各エンジンを 2 回ウォームアップし、5 回計測します。計測対象はプロセス起動から終了までの時間で、Wasm のロードや実行準備も含みます。

```sh
script/compare --bench build/rust/wasm32-unknown-unknown/release/examples/monte_carlo_pi.wasm monte_carlo_pi 1000000 1
script/compare --bench --iwasm build/rust/wasm32-unknown-unknown/release/examples/monte_carlo_pi.wasm monte_carlo_pi 1000000 1
```

WASI サンプルは標準入力と標準出力の処理も含めて計測します。

```sh
wasi=build/rust/wasm32-wasip1/release/examples
script/compare --bench --wasi-stdin build/fixtures/data.bin "$wasi/base64_codec.wasm" encode
script/compare --bench --wasi-stdin build/fixtures/data.b64 "$wasi/base64_codec.wasm" decode
script/compare --bench --wasi-stdin build/fixtures/rgb.png "$wasi/png_grayscale.wasm"
```

同じエンジン上で別々のサンプルを比較する場合は、`hyperfine` に実行コマンドを渡します。

```sh
hyperfine --warmup 2 \
  'script/run --no-wasi --invoke xorshift -- build/wat/xorshift.wasm 5000000 1' \
  'script/run --no-wasi --invoke xorshift -- build/rust/wasm32-unknown-unknown/release/examples/xorshift.wasm 5000000 1'
```
