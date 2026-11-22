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
