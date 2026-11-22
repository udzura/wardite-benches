# Ruby 4.0.9 の全キャッシュ起動の追加実験

Wardite の基準は `1f0b9e7`（#92 と #93 に、スナップショット復元時の新規ページのゼロクリア省略を適用）。Apple M3 Pro、Spinel `a64542970`、`-O2`。Wasmtime は 51.0.0。各回新しいプロセスを起動し、`--disable-gems -e 'puts RUBY_DESCRIPTION'` が終了するまでを測定した。事前生成した同一の WMIR とスナップショットを全 Wardite ビルドで共有し、Wasmtime には同じ Wasm から生成した cwasm を指定した。2回のウォームアップ後に実行順を回して各32回計測し、標準出力と成果物のハッシュを確認した。

| 系列 | 基準 | 比較したビルドの中央値（ms） | Wasmtime |
|---|---:|---|---:|
| [段階別](trials.json) | 49.19 | 新規バッファ 47.20、＋MIR ディレクトリ 47.18、＋data オフセット 41.04、＋バッファリーダー 41.37 | — |
| [配列と FFI](lazy-ffi.json) | 77.08 | data オフセットまで 65.10、＋配列の遅延確保 59.49、代わりに命令検証の FFI 71.03 | 48.29 |
| [data セグメントの FFI](segments.json) | 78.02 | data オフセットまで 64.85、＋セグメント走査の FFI 69.00 | 50.12 |
| [ページコピーの試作](scatter.json) | 49.48 | data オフセットまで 41.16、ページコピー試作 47.17（ディレクトリ変更を含まず） | 31.82 |
| [最終比較](m3-pro.json) | 77.06 | 01・03・04 のみ 66.42、01〜04 すべて 60.15 | 48.56 |

最終比較時に macOS の `lowpowermode=1` を確認した。前半の電力設定は記録していない。同じ系列の差を使って比較する。30.85 ms は ADR 0029 の別計測。基準 49 ms の条件での最終試作の起動時間は未測定。

## 試作の再現

Wardite `1f0b9e7` の独立したチェックアウトで、以下の数値順にパッチを `git apply` して各段階を別々の `BUILD_DIR` にビルドする。

1. `01-fresh-memory.patch` は、スナップショットに合わせてメモリを拡張するとき、ゼロ初期化されたバッファに置き換える。
2. `02-mir-directory.patch` は、関数ディレクトリの整数をまとめて読み、型ごとに作った署名のバイト列でレイアウトを照合する。
3. `03-data-offset.patch` は、active data セグメントの i32.const・符号付き LEB32・end を1回で読む。
4. `04-lazy-arrays.patch` は、MIR 関数の空の配列を使うときに確保する。

`probe-ffi-validator.patch`、`probe-ffi-segments.patch`、`probe-buffer-reader.patch` はそれぞれ 01〜03 に適用する独立した試作。`probe-ffi-snapshot.patch` は 01・03 に重ねた。ページコピーの試作は複数箇所が異なるため、47.17 ms から FFI 単独のコストは求められない。

```sh
make spinel SPINEL="$spinel" BUILD_DIR="$out"
python3 -B "$phases/compare_prepared.py" \
  --wardite head "$base/wardite" --wardite trial "$out/wardite" \
  --wasmtime "$wasmtime" --wasm "$wasm" --rounds 32 --output "$results"
```

基本動作は WMIR・MIR キャッシュ・スナップショットのテスト36件（481 assertions）で確認した。4 MiB Base64 decode も各8回、標準入力から復号して終了まで計測した。基準 289.30 ms、01〜03 が 289.68 ms、01〜04 が 291.52 ms（基準比 +0.8%）。全回の出力 SHA-256 を照合した。[Base64 生データ](base64-decode.json)

## Wardite の stacked PR 先端での再計測

Wardite `05e8170` を Spinel `a64542970` の `-O2` でビルドした。全変更入りでは、Spinel が直接呼び出し先テーブルを専用のポインタ配列として維持できるよう、そのテーブルを関数宣言時に確保する。保存済みの対照バイナリと Wasmtime 51.0.0 を同じスクリプトで交互に実行した。macOS の低電力モードは計測前後とも有効。各32回の中央値は変更前 107.62 ms、ゼロクリア変更のみ 79.87 ms、全変更入り 63.66 ms、Wasmtime 50.78 ms。[全128サンプルとバイナリの SHA-256](wardite-pr-stack.json)
