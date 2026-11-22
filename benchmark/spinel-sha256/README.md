# Spinel の Arm SHA2 と ruby.wasm の起動

Apple M3 Pro、macOS arm64、Wardite `3edaf5d`、Ruby 4.0.9（WASI）。同じ upstream Spinel `f341ce1bf` の変更前と、SHA-256 のブロック圧縮を Arm SHA2 命令に置き換えた `954dc004b` のランタイムで、同じ Wardite ソースを `-O2` でビルドした。

| 区間 | 変更前 | 変更後 | 短縮 |
|---|---:|---:|---:|
| 読み込み済み 21,444,697 B の Wasm の SHA-256 | 48.24 ms | 9.09 ms | 81.2% |
| MIR2 と起動スナップショットを復元して Ruby が終了するまで | 147.12 ms | 92.39 ms | 37.2% |

ハッシュ単体は1回ウォームアップ後に32回計測し、ビルドの順序を交換して繰り返した各64回の中央値。全ダイジェストを元の Wasm の既知の値と照合した。起動は各ビルドを2回ウォームアップした後、両者の順序を交替した新規プロセス各32回の中央値。ゲスト引数は `--disable-gems -e 'puts RUBY_DESCRIPTION'`。変更前で作った MIR2 とスナップショットを両ビルドで共有し、どちらもヒットと復元をトレースで確認した。計時中はトレースを外し、毎回の出力と測定前後の全キャッシュファイルの SHA-256 を照合した。[各回の値と実行ファイルの SHA-256](m3-pro.json)

## 再現

`before` と `after` は実行ファイルを置くディレクトリ、`spinel_before` と `spinel_after` はそれぞれのコンパイラの絶対パス。Wardite と Wasm のパスを指定し、このディレクトリで実行する。

```sh
mkdir -p "$before" "$after"
"$spinel_before" -O2 hash.rb -o "$before/hash"
make -C "$wardite_source" spinel SPINEL="$spinel_before" BUILD_DIR="$before"
"$spinel_after" -O2 hash.rb -o "$after/hash"
make -C "$wardite_source" spinel SPINEL="$spinel_after" BUILD_DIR="$after"
python3 measure.py "$before" "$after" "$ruby_wasm" samples.json
```
