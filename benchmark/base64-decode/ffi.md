# Wardite と Spinel の実装前後での比較

通常の Spinel コンパイラで Wardite の CLI をビルドし、MIR インタプリタで計測した。前回の生成 C 書き換えによる[要因実験](costs/README.md)から、本実装に移したときの効果を見る。

## Wardite の変更

Apple M3 Pro、macOS 27.2.1、Spinel は Wardite のピン 072516af1。各行は同じビルドの12回の中央値（ms）。ループ時間はゲストの単調時計で32文字ループを囲んだ値。残り3列は通常の Wasm を新規プロセスで動かした壁時計。encode / decode は4 MiB、PNG は1024×1024。

| 構成 | decode ループ | decode 全体 | encode 全体 | PNG 全体 |
|---|---:|---:|---:|---:|
| Wardite main 1f91865 | 225.67 | 249.70 | 297.92 | 214.37 |
| シフト FFI e873b74 | 223.47 | 247.19 | 296.29 | 216.01 |
| シフト FFI ＋ lookup / 分岐融合 7526476 | 195.71 | 218.48 | 294.12 | 214.84 |
| iwasm 2.4.5 --interp | 47.62 | 55.13 | 53.02 | 42.44 |

2つの Wardite 変更で decode ループは13.3%、全体は12.5%短縮した。ループ計測モジュールの別実行（--mir-profile）では新命令 I64_BYTE_LOOKUP_BR_EQ が 4,718,601 回実行され、ディスパッチは 38,632,715 → 33,914,114、MIR スロットへの書込みは 47,543,317 → 38,106,115。新命令は1回につき、消費後に読まれない一時アドレス2個の書込みを省く。スロットの配列アクセサは共通。[Wardite シフト PR](https://github.com/udzura/wardite/pull/87)・[Wardite 融合 PR](https://github.com/udzura/wardite/pull/88)

初回の比較には、Spinel のすべての対象整数配列で新しい fetch ヘルパーを使う試作も含めた。この試作は main の decode ループで 252.68 ms、Wardite の2変更との併用で 222.48 ms だった。[初回の各ラウンドの値と SHA-256](m3-pro-ffi-first.json)

## Spinel の最終パッチを組み合わせた比較

Spinel の変更は、nilable な整数ローカルを添字にして Array#fetch するときに、元の配列が GC root に残ると証明できれば余分な一時 root 登録を省くもの。整数配列への書込みでは、範囲内かを符号なしの比較1回で判定する。負の添字、配列の拡張、凍結、nil ビットの処理は元の経路を使う。Wardite のピンにこの2変更を移植して同時に測り直した。[Spinel PR #12369](https://github.com/matz/spinel/pull/12369)・[計測したバックポート](spinel-072516af1.patch)

| 構成 | decode ループ (ms) | decode 全体 (ms) | encode 全体 (ms) | PNG 全体 (ms) |
|---|---:|---:|---:|---:|
| 変更前 | 226.78 | 249.90 | 299.62 | 214.03 |
| Wardite シフトのみ | 222.73 | 249.27 | 297.30 | 216.22 |
| Wardite 2変更 | 194.33 | 220.08 | 296.66 | 215.22 |
| Spinel のみ | 207.90 | 232.89 | 289.81 | 210.76 |
| 両方 | **174.19** | **200.87** | **279.54** | **209.21** |
| iwasm --interp | 47.70 | 54.86 | 53.02 | 42.29 |

decode ループの対 main の短縮率は Wardite 単独 14.3%、Spinel 単独 8.3%、両方で23.2%。iwasm 比は4.75倍から3.65倍になった。プロセス全体では decode 19.6%、encode 6.7%、PNG 2.3%の短縮。タイマー付きモジュールと元のモジュールはそれぞれ6構成すべてで同一のものを使い、出力を全バイト照合した。[最終比較の各ラウンドの値と SHA-256](m3-pro-ffi.json)

## 再現

wardite-benches で script/fixtures、script/build を実行する。各リビジョンの Wardite 作業ツリーで make spinel BUILD_DIR=/absolute/output を使って実行ファイルを用意する。Spinel を変える場合は SPINEL=/absolute/path/to/spinel も指定する。バックポートは Spinel 072516af13322849eabe107eeb910e43fb2882be のクリーンな作業ツリーで `git apply /path/to/wardite-benches/benchmark/base64-decode/spinel-072516af1.patch` として適用し、通常どおり Spinel をビルドする。比較するコンパイラと同じリビジョンのヘッダとランタイムを使う。以下の各実行ファイルのパスはローカルで用意したものに置き換える。

```sh
python3 benchmark/base64-decode/compare_builds.py --build build \
  --wardite baseline /path/to/main/wardite \
  --wardite shift /path/to/shifts/wardite \
  --wardite wardite /path/to/lookup/wardite \
  --wardite spinel /path/to/main-with-patched-spinel/wardite \
  --wardite both /path/to/lookup-with-patched-spinel/wardite \
  --rounds 12 --output build/ffi-results.json
```

iwasm を自動で比較に加え、各構成の出力全体を Wasmtime と照合する。さらに2反復目の各文字を不正値に変え、全32箇所のエラー位置・終了ステータスを確認する。計時中は JIT とキャッシュを無効にし、MIR workers は8、入力は stdin、出力は /dev/null。各条件で1回ウォームアップし、各ラウンドで実行順をずらして2巡目は逆順にする。

## #12369 マージコミットへのピン更新

Apple M3 Pro、macOS 27.2.1、Apple Clang 21.0.0 上で、Spinel `072516af1` と #12369 のマージコミット `68476ebd3` をそれぞれソースからビルドした。下表の「旧ピン」と「新ピン」は同じ Wardite `3edaf5d` を `make spinel`（`-O2`、inline RBS 有効）でビルドしたもの。#88 そのもの（`7526476`＋旧ピン）も同じラウンドで実行した。ピン間には他の Spinel 変更も含まれる。[Wardite #89](https://github.com/udzura/wardite/pull/89)・[Spinel のピン間の差分](https://github.com/matz/spinel/compare/072516af13322849eabe107eeb910e43fb2882be...68476ebd3d91584899e8e40c42004aee591211cc)

各12回の中央値、単位は ms。変化率は同一 Wardite ソースでの所要時間の増減。JIT 無効、MIR workers 8。32文字ループだけをゲストの単調時計で計測し、他の3件はプロセス全体を計測した。

| ワークロード | #88 | 旧ピン | 新ピン | 時間変化 | iwasm 2.4.5 |
|---|---:|---:|---:|---:|---:|
| 4 MiB Base64 decode ループ | 198.14 | 197.52 | 176.37 | −10.7% | 48.48 |
| 4 MiB Base64 decode 全体 | 223.22 | 222.71 | 201.62 | −9.5% | 55.64 |
| 4 MiB Base64 encode 全体 | 300.84 | 301.23 | 292.19 | −3.0% | 53.96 |
| 1024×1024 PNG 全体 | 220.59 | 222.00 | 217.29 | −2.1% | 43.12 |

decode ループの新ピンと iwasm の時間比は3.64倍。すべての構成で Wasmtime 49.0.0 の出力と全バイトが一致した。不正入力は2反復目の32通りの位置と終了コードを照合した。[全サンプルと SHA-256](m3-pro-spinel-68476ebd3.json)

### ruby.wasm キャッシュヒット時の起動

同じ Wardite `3edaf5d` の新旧ビルドで、各バイナリ用の MIR2 キャッシュとスナップショットを作成した。`--disable-gems -e 'puts RUBY_DESCRIPTION'` の出力を Wasmtime と照合し、キャッシュのヒットと、スナップショットを指定した場合の復元を毎回確認した。各条件1回ウォームアップし、測定順を交互に変えた7回の壁時計中央値。Wasm の SHA-256 は `cb740da111ff6ef951f51fac3296466777cc7b9b48d327f8d8089edeae71a7a4`。[起動の全サンプル](m3-pro-spinel-68476ebd3-startup.jsonl)

| 起動条件 | 旧ピン (ms) | 新ピン (ms) | 時間変化 |
|---|---:|---:|---:|
| MIR2 ＋スナップショット、遅延復元（既定） | 154.1 | 152.3 | −1.2% |
| MIR2 のみ、eager | 716.4 | 698.0 | −2.6% |
| MIR2 ＋スナップショット、eager | 330.4 | 338.2 | +2.4% |

次のコマンドで再現できる。引数のパスは上記リビジョンでビルドしたバイナリに置き換える。

```sh
python3 benchmark/base64-decode/compare_builds.py --build build \
  --wardite pr88 /path/to/pr88/wardite \
  --wardite old /path/to/pr89-old/wardite --wardite merged /path/to/pr89-merged/wardite \
  --rounds 12 --output build/spinel-pin.json
WARDITE_MIR_WORKERS=8 WARDITE_MIR_JIT=0 python3 adr/0026/cached_startup.py \
  /path/to/pr89-old/wardite /path/to/pr89-merged/wardite /path/to/ruby.wasm \
  --runs 7 > build/spinel-pin-startup.jsonl
```

## `method_missing` を定義したときの Spinel のコスト

Spinel をマージコミット `68476ebd3` に固定した。#89 の途中コミット `ae6db3c` は3つのフックを含む状態でこのコンパイラを通る。このソースを2回ビルドし、片方だけから `Instance`、`Efflorescence::VM`、`Exports` の `method_missing` 定義を削除した。`respond_to?`、`respond_to_missing?`、WASI のロード順、MIR 実装は同一。比較用に #89 の最終版 `3edaf5d` と iwasm も同じラウンドで実行した。[A/B の差分](method-missing-ab.patch)

Apple M3 Pro、`-O2`、8 workers、JIT 無効。単位は ms。Base64 と PNG は12回、ruby.wasm は7回の中央値。

| ワークロード | 定義あり | 3定義を削除 | 所要時間の変化 |
|---|---:|---:|---:|
| 4 MiB Base64 decode ループ | 180.56 | 180.75 | +0.1% |
| 4 MiB Base64 decode 全体 | 213.55 | 201.52 | −5.6% |
| 4 MiB Base64 encode 全体 | 301.46 | 297.18 | −1.4% |
| 1024×1024 PNG 全体 | 257.08 | 223.30 | −13.1% |
| ruby.wasm、MIR2 ＋スナップショット、既定 | 162.2 | 152.1 | −6.2% |
| ruby.wasm、MIR2 のみ、eager | 733.5 | 699.9 | −4.6% |
| ruby.wasm、MIR2 ＋スナップショット、eager | 355.6 | 323.1 | −9.2% |

PNG はフックを外すと12組すべてで 28.9〜39.2 ms 短縮した。decode はループ単体でほぼ同じ時間だったが、プロセス全体では12組すべてで短縮した。[Base64 と PNG の全測定値](m3-pro-method-missing.json)・[キャッシュヒット時の全測定値](m3-pro-method-missing-startup.jsonl)

フックが実際に呼ばれたかは別ビルドで確認した。3つのメソッドの入口にクラス名を標準エラーに出すプローブを追加した。各フックを1回ずつ明示的に呼ぶ対照では3種類のマーカーが出た。Base64 のループ・decode・encode と PNG の通常実行ではどれも **0回** で、標準出力の SHA-256 は全件一致した。[計時に使わなかったプローブの差分](method-missing-probe.patch)

Spinel は、受け手によってメソッドが見つかるか変わる呼び出しについて、受け手が対象クラスなら `method_missing` に進む条件分岐を生成する。この A/B で `spinel -c` の出力にある `sp_class_eq(sp_poly_get_class(` は 5,335 箇所 → 0 箇所、実行ファイルは 7,010,408 → 5,404,120 バイトになった。5,335 は C ソース中の静的な出現数で、個々の分岐の実行回数は未計測。観測した差は、フックの存在によるコード生成の違いを含む。[該当する Spinel の変換](https://github.com/matz/spinel/blob/68476ebd3d91584899e8e40c42004aee591211cc/src/analyze_desugar.c#L28989-L29000)

再現するには Wardite `ae6db3c` の作業ツリーを2つ用意し、片方に `git apply /path/to/method-missing-ab.patch` を適用する。両方を同じ Spinel `68476ebd3` で `make spinel` し、上の計測コマンドの Wardite バイナリを `--wardite hooks <定義あり> --wardite removed <3定義を削除> --wardite head <#89 最終版>` に置き換える。起動計測には同じ hooks と removed のバイナリをこの順に渡す。入口の確認には別の未変更ツリーで `method-missing-probe.patch` を適用し、`build/wardite --probe-method-missing test/add.wasm` で3種類のマーカーを確認してから通常のワークロードを実行する。
