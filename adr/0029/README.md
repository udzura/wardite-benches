# ADR 0029 のランタイム比較

2026-11-22 時点の最新安定版を Apple M3 Pro / macOS 27.2.1 で比較した。Wardite は #89 の `3edaf5d` を Spinel `68476ebd3` の `-O2` でビルドし、MIR workers 8、JIT 無効で実行した。iwasm 2.4.6 はリリースタグから arm64 の fast interpreter をビルドし、`--interp` で実行した。Wasmtime 51.0.0 は公式の aarch64-macos CLI と Cranelift を使い、コンパイルキャッシュを無効にした。[Wardite #89](https://github.com/udzura/wardite/pull/89)・[WAMR リリース](https://github.com/wasm-micro-runtime/wasm-micro-runtime/releases/tag/WAMR-2.4.6)・[Wasmtime リリース](https://github.com/bytecodealliance/wasmtime/releases/tag/v51.0.0)

## 測定区間

32文字の復号ループはゲストの単調時計、通常の decode、encode、PNG は新規プロセスの起動から終了までの壁時計を使った。全ランタイムで同じ Wasm と入力を使用し、出力全体と、2反復目の全32位置に不正文字を入れた際のエラー位置・終了コードを照合した。1回ウォームアップした後、各ラウンドで順序をずらし、交互の巡回で順序を反転した。各12回の中央値。[全測定値と SHA-256](../../benchmark/base64-decode/m3-pro-adr0029-runtimes.json)

ruby.wasm は同じ Ruby 4.0.9 の WASI コマンドで `--disable-gems -e 'puts RUBY_DESCRIPTION'` を実行した。全ケースで出力を照合し、同様に実行順を変えた10回の中央値を取った。「未準備」は Wasm からの新規プロセス起動で、ファイルシステムのキャッシュは温まっている。「事前準備あり」は Wardite では MIR2 と起動スナップショットからの遅延復元、Wasmtime では同じ Wasm から `wasmtime compile` した Cranelift コードを使う。準備時間は計時外。Wardite は別のトレース実行でキャッシュヒットと復元を確認した。iwasm は Ruby の既定スタックで operand stack overflow になったため、このゲストだけ `--stack-size=1048576` を指定した。[起動の全測定値と SHA-256](m3-pro-ruby-startup.json)

## 結果

各欄は中央値（ms）。iwasm はインタプリタ実行のみを測定した。

| 測定区間 | Wardite #89 | iwasm 2.4.6 | Wasmtime 51.0.0 |
|---|---:|---:|---:|
| 4 MiB Base64 decode・32文字ループ | 176.89 | 48.49 | 1.89 |
| 4 MiB Base64 decode・全体 | 199.58 | 55.27 | 21.81 |
| 4 MiB Base64 encode・全体 | 290.59 | 53.37 | 21.35 |
| 1024×1024 PNG・全体 | 217.96 | 42.92 | 29.21 |
| ruby.wasm 起動・未準備 | 2,179.17 | 318.23 | 5,965.19 |
| ruby.wasm 起動・事前準備あり | 152.13 | — | 31.65 |

## 再現

iwasm のソースを `WAMR-2.4.6`（`0fa4211`）でチェックアウトし、次の設定でビルドする。

```sh
cmake -S "$wamr/product-mini/platforms/darwin" -B "$wamr_build" \
  -DCMAKE_BUILD_TYPE=Release -DWAMR_BUILD_MULTI_MODULE=1 -DWAMR_BUILD_DUMP_CALL_STACK=1 \
  -DWAMR_BUILD_JIT=0 -DWAMR_BUILD_LIBC_UVWASI=0 -DWAMR_BUILD_SIMD=0
cmake --build "$wamr_build" --parallel 8
```

その `iwasm` と Wasmtime 51.0.0 を `PATH` の先頭に置く。wardite-benches のルートで `script/fixtures` と `script/build` を実行し、`wardite` と `ruby_wasm` に対象ファイルのパスを指定する。

```sh
python3 benchmark/base64-decode/compare_builds.py --wasmtime --build build \
  --wardite wardite "$wardite" --rounds 12 --output build/adr0029-runtimes.json
python3 adr/0029/ruby_startup.py "$wardite" "$ruby_wasm" \
  --rounds 10 --output build/adr0029-startup.json
```
