# ADR 0027 の局所 CSE を測る

Wardite の [実装 PR](https://github.com/udzura/wardite/pull/82) と[比較結果](results.md)。同じ Spinel バイナリで `WARDITE_MIR_CSE=0` と `1` を切り替える。各コマンドは wardite-benches のルートで実行する。

## 再現手順

`script/build` と `script/fixtures` で Wasm と標準入力を用意する。Wardite の実装ブランチで `make spinel` を実行する。計測には Python 3、Wasmtime、WABT、ブロックの計数には CRuby を使う。

```sh
wardite=/path/to/wardite
bin="$wardite/build/wardite"
adr/0027/census.sh "$wardite"
python3 adr/0027/verify.py "$bin"
python3 adr/0027/measure.py "$bin" --large > primary.jsonl
python3 adr/0027/measure.py "$bin" --large --reverse > repeat.jsonl
```

- `census.sh` は CSE 無効の最適化済み MIR を走査する。純粋な整数式を入力の値番号と即値で照合し、以前の結果を保持するスロットが残っている重複式を数える。融合命令は構成命令に展開して調べる。候補ブロックの先頭にカウンタを挿入し、重複数に実行回数を掛ける。関数番号、開始 PC、候補、実行回数は `build/adr0027-census/*.json` に出力する。
- `verify.py` は入力・結果の上書き、合流、ブロックをまたぐ値、メモリ操作の副表、i64、ループ、ゼロ除算を Wasmtime と照合する。CSE の有無それぞれで、通常実行、同じディレクトリへの MIR2 の書き込みと復元を確認する。環境変数で有効にした状態での `--mir-disable cse` が、無効時のキャッシュを選ぶことも検査する。
- `measure.py` はすべての実行で JIT を無効にし、Base64 と PGM の出力を Wasmtime とバイト単位で比較する。整数ループは戻り値を比較する。入力・Wasm・参照出力の SHA-256 を各ケースの先頭行に出力する。
- 全体時間はトレース、プロファイル、MIR2 の指定を外し、プロセス起動から終了までを測る。各条件を 1 回ずつウォームアップした後、有効・無効の順を交互に入れ替えて各 9 回測る。`--reverse` で最初の順を逆にする。
- `profile` の行は別実行で採った opcode ごとの動的回数と全ディスパッチ数。`generation` は全関数の一括準備を別途実行し、semantic MIR 翻訳時間と、翻訳完了からロード完了までのトレース行の到着間隔を足した近似値。Wasm のファイル読み込みとゲストの実行時間は含まない。

`--large` では約 4 MiB のバイナリ、その Base64 表現、1024×1024 の PNG を使う。省略すると標準サイズのフィクスチャを使う。整数ループは 100 万回、各反復で同じ値の下位 8 ビットを 2 回求める。`--build` でビルド済みフィクスチャの場所、`--runs` で計測回数を変えられる。

## Ruby Wasm の起動キャッシュ

ADR 0026 の計測コードに、同じ実行ファイルの CSE を切り替えるラッパーを渡す。MIR2 とスナップショットは各条件で作り、復元トレースとゲスト出力を検査する。

```sh
export CSE_WARDITE_BIN="$bin"
mkdir -p build/adr0027
for cse in 0 1; do
  wrapper="build/adr0027/cse-$cse"
  printf '#!/bin/sh\nexport WARDITE_MIR_CSE=%s\nexec "$CSE_WARDITE_BIN" "$@"\n' "$cse" > "$wrapper"
  chmod +x "$wrapper"
done
python3 adr/0026/cached_startup.py build/adr0027/cse-0 build/adr0027/cse-1 \
  "$wardite/ruby-wasm32-wasi/usr/local/bin/ruby" > cached-startup.jsonl
```
