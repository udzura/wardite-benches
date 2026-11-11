# wardite-benches

Wardite の試験・ベンチマーク用 Wasm プログラム集です。Wardite を Spinel でビルドし、`--new-engine` で実行します。

| ディレクトリ | 内容 |
| --- | --- |
| `wat/` | WAT で書いたサンプル |
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

## ベンチマーク

ビルド後、同じ入力で各サンプルを `hyperfine` から実行できます。計測値には Wardite のプロセス起動、Wasm のロードと変換、実行が含まれます。

```sh
hyperfine --warmup 2 \
  'script/run --no-wasi --invoke xorshift -- build/wat/xorshift.wasm 5000000 1' \
  'script/run --no-wasi --invoke xorshift -- build/rust/wasm32-unknown-unknown/release/examples/xorshift.wasm 5000000 1'
```
