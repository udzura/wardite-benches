# ADR 0026 のスロット圧縮を検証する

Apple M3 Pro で測定した中央値と各回の生データは[比較結果](results.md)に記録した。

`before` と `after` は同じ Spinel、同じフラグでビルドした変更前後の Wardite CLI。各チェックアウトで `make spinel` を実行すると `build/wardite` ができる。以下は wardite-benches のルートから実行する。

```sh
before=/path/to/baseline/wardite
after=/path/to/candidate/wardite
ruby_wasm=/path/to/ruby-wasm32-wasi/usr/local/bin/ruby
python3 adr/0026/measure.py "$before/build/wardite" "$after/build/wardite" "$ruby_wasm" > samples.jsonl
```

Python 3、WABT の `wat2wasm`、Wasmtime が必要。再帰の深さは既定で 10,000。96 個の加算を含む関数を再帰させ、加算自体は最深部でだけ実行する。export の引数は深さと走査回数で、1 回目にプールを満たし、2 回目以降は同じゲスト呼び出し内でフレームを再利用する。1・2・32 回の各ケースで戻り値を検査する。

Ruby の Wasm は `--disable-gems -e 'puts RUBY_DESCRIPTION'` で起動し、Wasmtime の出力と照合する。通常起動、全関数の一括生成、MIR2 ミス、MIR2 ヒットを測る。ミスには毎回新しいディレクトリを使い、ヒットにはウォームアップで生成したファイルを使う。両方ともトレースでキャッシュ状態を確認する。

各ケースで 1 組ウォームアップし、以降は前後の順を交互にする。既定は各 7 回、一括生成とミスは各 3 回。`--depth`、`--runs`、`--misses` で変更できる。JIT を無効にしてプロセス経過時間と個々の子プロセスのピーク RSS を記録する。一括生成の `mir_seconds` は、Wardite が報告する semantic MIR 翻訳時間に、翻訳完了からロード完了までのトレース行の到着間隔を足した近似値。Wasm デコード、キャッシュ書き込み、ゲスト実行はこの区間に含まれない。

## フレームの計数

CRuby の同じ入力で `FramePool#acquire` を計数する。新規作成したときだけ初期値配列の長さを加算する。計数コードは計時用の Spinel バイナリに入らない。

```sh
python3 adr/0026/recursive.py | wat2wasm - -o /tmp/adr0026-recursive.wasm
for root in "$before" "$after"; do
  for passes in 1 2 32; do
    ruby -I"$root/lib" -r"$PWD/adr/0026/probe.rb" "$root/exe/wardite" \
      --no-wasi --invoke run -- /tmp/adr0026-recursive.wasm 10000 "$passes"
  done
  ruby -I"$root/lib" -r"$PWD/adr/0026/probe.rb" "$root/exe/wardite" \
    -- "$ruby_wasm" --disable-gems -e 'puts RUBY_DESCRIPTION'
done
```

## スロット配置と実行結果

```sh
ruby -I"$after/lib" adr/0026/layout.rb
python3 adr/0026/verify.py "$after/build/wardite"
```

`layout.rb` は引数とローカルの順序、書き込みだけのスロット、副表の参照、定数値、再度圧縮しても同じ配置になることを調べる。`verify.py` は Apple Silicon macOS の Spinel と `wasm-tools` を使う。圧縮の有無、JIT の有無、遅延準備・MIR2 ミス・ヒットの各組み合わせで、直接呼び出し、間接呼び出し、メモリ操作、例外のペイロードと再送出、ゼロ除算を確認する。剰余を求める export ではネイティブコード実行とトラップ時のインタープリタへの復帰もトレースで確認する。
