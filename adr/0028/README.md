# ADR 0028 の段階別評価

Wardite の [定数畳み込み](https://github.com/udzura/wardite/pull/83)、[制御フロー簡約](https://github.com/udzura/wardite/pull/84)、[死命令除去](https://github.com/udzura/wardite/pull/85)、[ループ不変式移動](https://github.com/udzura/wardite/pull/86)を同じ Wasm と入力で比較する。[比較結果と採用判断](results.md)

## 再現手順

wardite-benches のルートで実行する。Rust の Wasm ターゲット、Spinel、CRuby、Python 3、Wasmtime、wasm-tools が必要。Ruby ゲストには Wardite の ruby-wasm32-wasi 配布物を使う。計測に使った Wasm・入力・参照出力の SHA-256 は各生データのケース先頭行にある。

```sh
script/build
script/fixtures
wardite=/path/to/wardite
parent=/path/to/wardite-at-1e66db7
make -C "$parent" spinel
make -C "$wardite" spinel
bin="$wardite/build/wardite"
ruby_wasm="$wardite/ruby-wasm32-wasi/usr/local/bin/ruby"
adr/0028/verify.sh "$wardite"
python3 adr/0028/invalid_decode.py "$bin" build/rust/wasm32-wasip1/release/examples/base64_codec.wasm
adr/0028/profile.sh "$wardite"
```

`verify.sh` は同じ手書き Wasm で各段階の分岐先・レジスタと、インライン化後の定数戻り値を確認する。CRuby・Spinel で8構成を通常・MIR2 ミス・ヒットの順に実行する。同じディレクトリを使い、構成ごとにキャッシュを区別することを確かめ、整数の境界値、異なる値の合流、catch、ループ、エラー分岐、trap の順序と直前のメモリ書き込みを照合する。`invalid_decode.py` は実際のデコーダに不正な文字を入れ、エラーに含まれるバイト値と位置を66か所で Wasmtime と比較する。

`profile.sh` は小入力で各基本ブロックへの到達回数を計数し、上位30件を `build/adr0028-profile/blocks-*.json` に書く。行は関数番号、PC、実行回数。別実行で実際の LICM の選択結果を MIR の複製から取り、元のプログラムにカウンタを挿入する。`loops-*.json` の行は関数番号、ループ先頭 PC、元の PC、命令名、回数。`entry` は外からループに入った回数で、巻き上げる各命令について1回ずつ計算費用に数える。

```sh
measure() {
  python3 adr/0028/measure.py "$bin" --parent "$parent/build/wardite" --ruby "$ruby_wasm" "$@"
}
measure --variants parent none default --cases decode-large --modes profile cold hit --runs 9 --reverse > decode-a.jsonl
measure --variants parent none fold cfg dce default exit_copy+licm \
  --cases encode-small decode-small png-small sieve-small encode-large decode-large png-large sieve-large \
  --modes profile cold miss --runs 7 --misses 3 > stages.jsonl
measure --variants parent none fold cfg dce default exit_copy+licm --cases ruby \
  --modes profile cold miss snapshot --runs 5 --misses 2 > ruby.jsonl
measure --variants parent none default --cases decode-large --modes cold hit --runs 9 > decode-b.jsonl
```

`parent` はスタック直前のバイナリ、`none` は同じ新バイナリで ADR 0028 の全パスを無効にした対照、`default` は新バイナリの既定値（`exit_copy`）。`fold`、`cfg`、`dce` はそれぞれを単独で有効にし、`exit_copy+licm` は採用したパスに LICM を加える。JIT と ADR 0027 の CSE は全条件で無効。

- `cold` は MIR2 とスナップショットを指定しない遅延準備。OS のファイルキャッシュは通常通り。各条件を1回ウォームアップし、条件の実行順を毎ラウンド反転する。
- `hit` は既存の MIR2 を復元する。`snapshot` は MIR2 と Ruby 起動スナップショットの両方を復元する。条件ごとにキャッシュを新規作成し、ウォームアップ時にヒットと復元をトレースで確認する。計時時はトレースを外す。
- `miss` は毎回新しい MIR2 ディレクトリで、キャッシュミスを確認する。`build_ms` は semantic MIR 翻訳と最適化・検証・lowering の実測時間の和。旧バイナリには後者のトレースがないため、親の比較には通常のプロセス時間を使う。
- `profile` は時間計測とは別に opcode ごとの実行回数を採る。各実行で Wasmtime と同じ stdout または整数戻り値を確認する。ファイルの準備と比較は時間に含めず、プロセス生成から終了までを測る。

MIR2 の一括復元も含めた Ruby 起動の追試には ADR 0026 のスクリプトを再利用した。こちらは計測時にも復元トレースを有効にする。

```sh
WARDITE_MIR_CSE=0 python3 adr/0026/cached_startup.py \
  "$parent/build/wardite" "$bin" "$ruby_wasm" --runs 7 > full-cache.jsonl
```
