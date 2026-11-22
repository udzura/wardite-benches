# ruby.wasm と生成済み .wmir の起動

[Wardite #93](https://github.com/udzura/wardite/pull/93) の同一バイナリで Ruby 4.0.9 を新規プロセスから実行し、終了までの壁時計を比較する。MIR2 とスナップショットは Wasm で事前に生成し、直接起動でも同じスナップショットが復元されたことをトレースで確認する。OS のファイルキャッシュはウォーム。ゲスト引数は `--disable-gems -e 'puts RUBY_DESCRIPTION'`。

## 再現

Wardite を [#92 の Spinel](https://github.com/udzura/wardite/pull/92) で `make spinel` し、Python 3.11 以降で次を実行する。`ruby_wasm` は SHA-256 が `cb740da111ff6ef951f51fac3296466777cc7b9b48d327f8d8089edeae71a7a4` のモジュール。

```sh
python3 benchmark/wmir/measure.py "$wardite" "$ruby_wasm" samples.json --rounds 15
```

各条件15回、実行順をローテーションし5回ごとに反転する。生成時間は別に記録する。全回のゲスト出力を照合し、計測後に成果物とキャッシュファイルの集合および各 SHA-256 が一致することを確認する。

## Apple M3 Pro の結果

macOS 27.2.1 arm64、Wardite `fe4457e`、Spinel `a64542970`、通常の `make spinel`（`-O2`）、JIT 無効。Ruby 4.0.9 の Wasm は 21,444,697 B、生成した WMIR は 112,245,440 B。成果物の生成は1回で 4.05 秒だった。表は新規プロセスの起動から Ruby 終了までを各15回測った中央値。[各回の壁時計とバイナリの SHA-256](m3-pro.json)

| 入力・準備 | 起動から終了まで |
|---|---:|
| Wasm、オプションなし | 2,204.33 ms |
| Wasm、MIR2 ヒット | 527.69 ms |
| WMIR を直接指定 | 493.66 ms |
| Wasm、MIR2 とスナップショットがヒット | 98.18 ms |
| WMIR を直接指定、同じスナップショットがヒット | 66.79 ms |

MIR2 ヒットから WMIR への変更で、通常の Ruby 起動は 34.04 ms（6.5%）、同じスナップショットからの起動は 31.40 ms（32.0%）短縮した。スナップショットありの全15回の範囲は Wasm が 92.96〜107.90 ms、WMIR が 63.08〜73.15 ms。
