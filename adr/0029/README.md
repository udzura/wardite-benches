# ADR 0029 のランタイム比較

2026-11-22 時点の最新安定版を Apple M3 Pro / macOS 27.2.1 で比較した。Wardite は #89 の `3edaf5d` を Spinel `68476ebd3` の `-O2` でビルドし、Base64・PNG は MIR workers 8、JIT 無効で実行した。iwasm 2.4.6 はリリースタグから arm64 の fast interpreter をビルドした。Wasmtime 51.0.0 は公式の aarch64-macos CLI と Cranelift を使い、Base64・PNG のコンパイルキャッシュを無効にした。[Wardite #89](https://github.com/udzura/wardite/pull/89)・[WAMR リリース](https://github.com/wasm-micro-runtime/wasm-micro-runtime/releases/tag/WAMR-2.4.6)・[Wasmtime リリース](https://github.com/bytecodealliance/wasmtime/releases/tag/v51.0.0)

## 測定区間

32文字の復号ループはゲストの単調時計、通常の decode、encode、PNG は新規プロセスの起動から終了までの壁時計を使った。全ランタイムで同じ Wasm と入力を使用し、出力全体と、2反復目の全32位置に不正文字を入れた際のエラー位置・終了コードを照合した。1回ウォームアップした後、各ラウンドで順序をずらし、交互の巡回で順序を反転した。各12回の中央値。[全測定値と SHA-256](../../benchmark/base64-decode/m3-pro-adr0029-runtimes.json)

## 結果

各欄は中央値（ms）。Base64・PNG は iwasm を `--interp` で実行した。

| 測定区間 | Wardite #89 | iwasm 2.4.6 | Wasmtime 51.0.0 |
|---|---:|---:|---:|
| 4 MiB Base64 decode・32文字ループ | 176.89 | 48.49 | 1.89 |
| 4 MiB Base64 decode・全体 | 199.58 | 55.27 | 21.81 |
| 4 MiB Base64 encode・全体 | 290.59 | 53.37 | 21.35 |
| 1024×1024 PNG・全体 | 217.96 | 42.92 | 29.21 |

## ruby.wasm の起動

Ruby 4.0.9 の同じ Wasm とゲスト引数 `--disable-gems -e 'puts RUBY_DESCRIPTION'` を使い、毎回新規プロセスで終了までを測った。単位は ms、実行順を変えた各12回の中央値。OS のファイルキャッシュはウォーム。

| ruby.wasm の起動条件 | Wardite #89 | iwasm 2.4.6 | Wasmtime 51.0.0 |
|---|---:|---:|---:|
| オプションなし・永続キャッシュが空 | 2,134.72 | スタック不足 | 6,093.77 |
| オプションなし・自動キャッシュヒット | — | — | 101.86 |
| スタックを 1 MiB に指定 | — | 310.48 | — |
| 全キャッシュ復元・事前コンパイル済み起動 | 147.65 | — | 30.85 |

通常起動では各ランタイムの既定設定を使う。Wasmtime はどちらも同じ `wasmtime run ruby.wasm …` で、変えたのは自動キャッシュの中身だけ。ミスは毎回空のディレクトリで、コンパイルとキャッシュへの保存を含む。ヒットは測定前に同じ Wasm を1回実行して作ったキャッシュを使う。Wardite は通常起動で永続キャッシュを作らない。iwasm はこの Wasm が既定スタックで起動できないため、成功した条件を別行に示した。

最終行では Wardite は MIR2 と起動スナップショットを遅延復元し、Wasmtime は `wasmtime compile` で作った `.cwasm` を直接指定した。両方とも事前準備は計時外。

トレースを外して計時した。Wasmtime のミスとヒットは `WASMTIME_CODEGEN` で自動キャッシュの保存場所だけを隔離し、別実行のログで書き込みと再利用を確認した。Wardite も別のトレース実行で MIR2 ヒットとスナップショット復元を確認した。全72回で同じ Ruby の出力を照合した。[今回の全測定値](m3-pro-ruby-cache-modes.json)・[従来のキャッシュ無効との比較](m3-pro-ruby-startup.json)

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
  --rounds 12 --output build/adr0029-startup.json
```
