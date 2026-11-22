# Ruby 4.0.9 の WMIR 起動内訳

Apple M3 Pro、macOS 27.2.1 arm64。Wardite #92（`6216b50`）と #93（`c56e07c`）のローカルマージ `7360e1b`、Spinel `a64542970`、`-O2`。Ruby 4.0.9 の Wasm は 21,444,697 B、WMIR は 112,245,440 B。ゲスト引数は `--disable-gems -e 'puts RUBY_DESCRIPTION'`。各条件で2回ウォームアップし、新規プロセス各32回を交互に実行した。[入力の SHA-256 と全256サンプル](m3-pro.json)

| 終了までの中央値 | Wasm＋MIR2 | WMIR |
|---|---:|---:|
| 同じスナップショットを復元 | 92.78 ms | 64.17 ms |
| スナップショットなし | 515.07 ms | 483.54 ms |

## スナップショットあり

下表は計測ビルドの算術平均（ms）。1起動を排他的に分割した。計測ビルドの全体中央値は各 92.69 / 64.14 ms。

| 区間 | Wasm＋MIR2 | WMIR |
|---|---:|---:|
| Wasm の読み取りまたは WMIR の mmap・ディレクトリ検証、キー生成 | 12.60 | 0.20 |
| Wasm セクション解析・モジュール検査 | 9.39 | 7.31 |
| MIR2 ファイルの読み込み・ペイロード取り出しと検証 | 15.04 | 0.00 |
| MIR 関数宣言とレイアウト確認 | 8.50 | 9.72 |
| インスタンス初期化・リンク・WASI 設定 | 2.35 | 4.96 |
| スナップショット復元とフレーム再構築（遅延 MIR を除く） | 30.25 | 29.38 |
| 復元中の MIR 関数デコード（10関数） | 6.72 | 7.01 |
| 再開後の MIR 関数デコード（12関数） | 0.16 | 0.18 |
| 再開後のゲスト実行・WASI | 0.11 | 0.11 |
| プロセス起動・CLI・終了など | 8.65 | 7.10 |
| 合計 | 93.77 | 65.96 |

WMIR の復元 29.38 ms のうち、メモリ拡張 6.31 ms、保存ページの書き戻し 0.84 ms、その他のページのゼロクリア 15.68 ms、スナップショットの SHA-256 3.69 ms。範囲ごとの全内訳は `report.py` で表示できる。314 → 4,857 ページに拡張し、119 ページを書き戻す。現行実装は残りの 4,738 ページ（296.125 MiB）を 64 KiB ずつクリアする。スナップショットなしの WMIR では、遅延 MIR デコードが平均 45.75 ms（933関数）、それを除く Ruby の初期化・実行と WASI が 417.08 ms。

## 既存ページのみをクリアする比較実験

元のビルドと、拡張前のページにだけゼロクリアを実行するビルドを、同じ WMIR とスナップショットで比較した。新規プロセス各32回の中央値は 67.31 → 49.85 ms。各回の出力、復元のトレース、計測前後のファイルハッシュを確認した。別の計測系列のため、この対照値は上表の WMIR の中央値と多少異なる。[比較パッチ](existing-pages-only.patch)・[生データ](zero-m3-pro.json)

既存ページにはインスタンス生成時に Wasm の data セクションの値が入る。ゲストが保存前にそれを消していた場合、復元時にクリアする必要がある。試作は新規ページがゼロ初期化される `Memory#grow` の保証を使い、保存された非ゼロページは新旧とも書き戻す。`zero-pages.wat` では、既存の初期値を消したページ、新規のゼロページ、新規の非ゼロページの3か所を再開後に検査した。現行・試作とも復元時の終了コードは0だった。

## 再現

Wardite の独立したクリーンな作業ツリーを用意し、#92 と #93 をローカルで合わせる。`phases` はこのディレクトリ、`spinel` は指定リビジョンの実行ファイル、`out` はビルドの出力先、`wasm` は同じ Ruby Wasm の絶対パス。Python 3.11 以降を使う。

```sh
make spinel SPINEL="$spinel" BUILD_DIR="$out/release"
git apply "$phases/markers.patch"
make spinel SPINEL="$spinel" BUILD_DIR="$out/probe"
python3 "$phases/measure.py" "$out/release/wardite" "$out/probe/wardite" "$wasm" samples.json
python3 "$phases/report.py" samples.json
git apply -R "$phases/markers.patch"
git apply "$phases/existing-pages-only.patch"
make spinel SPINEL="$spinel" BUILD_DIR="$out/trial"
python3 "$phases/compare_zero.py" "$out/release/wardite" "$out/trial/wardite" "$wasm" zero.json
```

計測パッチは単調時計でフェーズ境界を記録し、終了時に一度だけ stderr へ出す。親の時計と全区間の合計を各回で照合する。キャッシュと成果物は無改変ビルドで作成し、別途トレースで両経路のヒットを確認する。
