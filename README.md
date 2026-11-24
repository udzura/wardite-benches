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

### 素数の個数

`count_primes.wasm` の両 export は、指定した上限以下の素数の個数を返します。`count_primes` は奇数の候補を試し割りし、剰余演算と早期打ち切りの分岐を測ります。`count_primes_sieve` はエラトステネスの篩を使い、奇数の候補に 1 バイトずつ割り当てた配列への書き込みを測ります。篩の配列の確保と初期化も計測に含まれます。

ベースラインでは両方とも上限を `1_000_000` に設定します。期待値は `78_498` です。

```sh
wasm=build/rust/wasm32-unknown-unknown/release/examples/count_primes.wasm
script/compare --bench --iwasm "$wasm" count_primes 1000000
script/compare --bench --iwasm "$wasm" count_primes_sieve 1000000
```

### ストリームの CRC-8

`crc8_stream` は4 KiBのチャンクを第1引数の回数だけ読み、CRC-8（多項式 `0x07`）を返します。各バイトで入力とCRC表を1回ずつ読むので、線形メモリのバイト読み出しを比較できます。第2引数が `1` のときは処理前にメモリを1ページ拡張します。次の2例はどちらも1 MiBを処理し、期待値は `228`（`0xe4`）です。

```sh
cargo build --manifest-path rust/Cargo.toml --locked --release --target wasm32-unknown-unknown --target-dir build/rust --example crc8_stream
wasm=build/rust/wasm32-unknown-unknown/release/examples/crc8_stream.wasm
script/compare --bench "$wasm" crc8_stream 256 0
script/compare --bench "$wasm" crc8_stream 256 1
```

### WASI Preview 1 のサンプル

`base64_codec` の `encode` は標準入力のバイナリを標準アルファベットとパディング付きでエンコードし、末尾に LF を 1 つ付けます。`decode` は末尾に LF が 0 個または 1 個の Base64 を受け取り、元のバイト列を返します。`png_grayscale` は PNG をデコードし、RGB を `0.299R + 0.587G + 0.114B` で 8 ビットのグレースケールに変換します。出力はアルファチャンネルを省いたバイナリ PGM（P5）です。

`script/fixtures` は Python 3 で固定入力を `build/fixtures/` に生成します。既定の入力（`data.bin`、`data.b64`、`rgb.png`）に加えて、データを16倍にした `data-4m.bin` と `data-4m.b64`、画像の一辺を4倍にした `rgb-1024.png`、空の `empty` を作ります。自分のファイルも標準入力から渡せます。

```sh
script/fixtures
wasi=build/rust/wasm32-wasip1/release/examples
script/run -- "$wasi/base64_codec.wasm" encode < build/fixtures/data.bin > build/encoded.b64
script/run -- "$wasi/base64_codec.wasm" decode < build/fixtures/data.b64 > build/decoded.bin
script/run -- "$wasi/png_grayscale.wasm" < build/fixtures/rgb.png > build/gray.pgm
```

### JSON アクセスログの集計

`json_log_summary` は標準入力の JSON 配列を `serde_json` で Rust の構造体の配列に変換します。5xx の件数、5xx のレスポンスバイト数の合計、全レコード中で最長のパスの UTF-8 バイト数を出力します。`script/fixtures` が生成するログには、UTF-8 の日本語と Unicode エスケープの両方が含まれます。

```sh
wasm=build/rust/wasm32-wasip1/release/examples/json_log_summary.wasm
script/compare --bench --iwasm --wasi-stdin build/fixtures/access-1024.json "$wasm"
script/compare --bench --iwasm --wasi-stdin build/fixtures/access-16384.json "$wasm"
```

期待する出力は 1,024 件で `186 6723674 34`、16,384 件で `2978 97590534 35` です。

### XML（RSS フィード）の集計

`rss_summary` は `xml-rs` のイベントリーダーで標準入力を逐次解析し、RSS の `channel/item` の件数と、それらの `title` に含まれる Unicode スカラー値の総数を出力します。チャンネル自身のタイトルは集計対象外です。固定入力には日本語、実体参照（`&amp;`）、数値文字参照（`&#x1F4DA;`）、CDATA を含め、展開後のテキストを数えます。

```sh
script/fixtures
wasm=build/rust/wasm32-wasip1/release/examples/rss_summary.wasm
script/compare --bench --iwasm --wasi-stdin build/fixtures/feed-1024.xml "$wasm"
script/compare --bench --iwasm --wasi-stdin build/fixtures/feed-16384.xml "$wasm"
```

期待する出力は 1,024 件で `1024 12458`、16,384 件で `16384 222362` です。

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

`script/compare --bench` は戻り値の一致を確認してから、`hyperfine` で選んだエンジンを比較します。各エンジンを 2 回ウォームアップし、5 回計測します。計測対象はプロセス起動から終了までの時間で、Wasm のロードや実行準備も含みます。Wardite は `script/run` を経由せず、`build/wardite --new-engine` を直接起動します。macOS ではシェルスクリプトの起動に 20 ms 以上かかり、Wardite だけが不利になるためです。

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
hyperfine -N --warmup 2 \
  'build/wardite --new-engine --no-wasi --invoke xorshift -- build/wat/xorshift.wasm 5000000 1' \
  'build/wardite --new-engine --no-wasi --invoke xorshift -- build/rust/wasm32-unknown-unknown/release/examples/xorshift.wasm 5000000 1'
```

## ベースラインの記録

`script/baseline.sh [OUT_DIR]` は、[Wardite の ADR 0018](https://github.com/udzura/wardite/blob/main/docs/adr/0018-efflorescence-real-workload-measurement.md) の手順で全サンプルを計測します。`script/build` と `script/fixtures` を先に実行し、`hyperfine`、`wasmtime`、`iwasm` を用意してください。

各ケースで `script/compare --iwasm` により結果を照合してから、3 つのエンジンを `hyperfine` で 2 回ウォームアップして 9 回計測します。回数は `RUNS` で変えられます。WASI のケースでは、`WARDITE_TRACE` によるロード時間と、`--mir-profile` による MIR 命令の実行回数も記録します。WASI での `--mir-profile` の出力には、ADR 0018 の変更を含む Wardite が必要です。

```sh
script/build
script/fixtures
script/baseline.sh
```

結果は `OUT_DIR`（既定は `build/results/<日時>`）に置きます。

| ファイル | 内容 |
| --- | --- |
| `env.txt` | Wardite と Spinel のリビジョン、wardite-benches のリビジョン、CPU、OS、各エンジンのバージョン、Wasm の SHA-256 |
| `summary.md` | ケースごとの中央値、Wardite のロード時間と最大 RSS、Wasmtime・iwasm に対する Wardite の実行時間の中央値の比、MIR 命令の総数 |
| `<case>.json` | `hyperfine --export-json` の生値 |
| `<case>.load.txt` | `WARDITE_TRACE` の `load_from_buffer` の各回の値 |
| `<case>.mir.txt` | `--mir-profile` の合計と opcode ごとの実行回数 |
| `<case>.compare.txt` | `script/compare` の照合結果 |

`script/build` は Wardite をビルドしたときの `git describe` と `spinel --version` を `build/wardite.version` に書き、`env.txt` はそこから読みます。比べる前後のバイナリは、同じ Spinel でビルドしてください。
