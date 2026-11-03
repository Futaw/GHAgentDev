# 削除probeの確認入力待ちと標準入力の修正

2026-11-04。PR #27マージcommit `cc487ee`を基準に、削除probeのtimeoutを追加調査した。生成は無効のまま維持し、Permission Profile、CLI、実設定・認証情報は変更していない。

## 利用者の観測

利用者が60秒指定で実行した際、開始から28秒の観測で、同じ検証group内にNode起動用process、Codex本体、`/bin/rm`が存在した。3つとも同じstdout/stderr pipeを開いていた。60秒でtimeoutとなり、当時の親returncodeはnull、その後のgroupへのTERMでgroup消滅・親終了・pipe EOFを確認できた。KILLは不要で、fixture cleanupもpassedだった。

この実行では、少なくとも28秒の観測時点で削除コマンドまで起動していた。親が先に終了して子だけが残った状態ではない。pipeを3processが共有すること自体は継承による通常の構成であり、それだけでは待機原因にならない。`ps`のS状態だけから、具体的な待機先やOS拒否を判定することもできない。

利用者の過去のPIDを再利用して観測・停止していない。利用者のログにはrmの確認文自体が記録されていないため、以下の専用fixtureで因果関係を確認した。

## 原因の再現

macOSのローカル`man rm`は、書込みを許可されないfileで標準入力が端末の場合、stderrへ確認文を出して入力を求める仕様を示している。

`run_command()`はstdinを指定しておらず、呼出元のstdinを継承していた。利用者がターミナルからharnessを実行すると、その端末がNode→Codex→rmへ渡る。一方、harnessはstderrを`communicate()`で終了まで回収していたため、rmの確認文が実行中のターミナルへ表示されなかった。

実Codex CLI `/Users/futaw/.local/bin/codex`（0.164.0）、macOS 26.6.2、Python 3.12.0で、非機密の一時fixtureと空の専用homeを使用した。同じcanonical Profile・同じfile権限で、標準入力だけを変更した。

| 条件 | 結果 |
|---|---|
| rmのstdinが疑似端末 | 3秒待っても終了しない。否定の`n`を送るとexit 0で終了。確認文の存在を判定し、fileが不変であることを確認 |
| rmのstdinが`/dev/null` | 確認入力待ちなし。OS permission denialを出してexit 1。fileは不変 |

確認への肯定入力は送っていない。確認文やfileの生内容、環境の秘密値はログへ保存せず、固定文言の検出booleanと結果だけを保存した。否定回答後のexit 0はOS拒否の証拠として扱わない。

この比較で、端末stdinの継承により同じ削除probeが確認入力待ちになることと、非端末stdinでは削除を試みてOS拒否となることを実測した。利用者の観測とも整合する。以前の端末なし実行でtimeoutを再現できなかったことを、削除probeが全実行環境で問題ない証拠にしてはいけない。

## 修正と回帰テスト

共通の非対話コマンド実行`run_command()`へ`stdin=asyncio.subprocess.DEVNULL`を指定した。起動元の端末入力を渡さない。`cli_output()`とnative probeの両方へ適用される。App ServerのJSONL通信用`stdin=PIPE`は独立しており、変更していない。

許可Profile、OS権限、rmの引数、timeout判定、OS拒否の証拠条件は変更していない。確認待ちを避けるためにユーザー設定を削除したり、検査条件を緩和したりしていない。

通常の自動testには実Codexを使わず、疑似端末を標準入力に持つPythonから共通runnerで、専用の書込みbitのないfileを`/bin/rm`する回帰testを追加した。通常の非sandbox環境では親directoryの削除権限があるため、非対話のrmはこのfileを削除して終了できる。この成功はsandboxの安全性の証拠ではなく、端末継承の防止だけを確認する。

- 修正前: 追加testがtimeoutで失敗し、問題を検出できることを確認。
- 修正後: Backend **133 passed**、Ruff check/format、`git diff --check`成功。
- rootはrmの書込み可否判定を迂回できるため、この回帰testだけskipする。今回の実行ではskipなし。
- 既存のtimeout、TERM/KILL、キャンセル、SIGINT、他session非停止、cleanup失敗、Fake App Serverの回帰を含む。

## 修正後の実機確認

利用者と同様、標準入力が疑似端末である実行環境から以下を実施した。

```bash
.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 15 --only deletion
```

- sandboxなしの削除対照: passed。
- sandbox内の許可file: read。
- sandbox内の削除: timeoutなし、`status=error / errno=1`、process exit 1でOS拒否。
- process cleanup: group消滅、親終了、pipe EOFを確認。
- fixture: hashとGit status不変、削除完了。
- harness exit 1: 部分実行のため。`non_modification`全項目や全体gateのpassedを意味しない。

機密情報を含まない証拠は[JSON](./2026-11-04-verification-stdin.json)を参照する。実機fixtureと今回作成したprocess/groupは後始末済み。

## 残る課題

このPRは削除probeの対話待ちだけを修正する。利用者が手順5で再確認した範囲外sentinelの読取り成功と、shellのset table結合は未解決である。GENERATION_ENABLED=falseを維持する。

修正後の全体gate、認証付き実Turn、Viewer保存は今回実行していない。全必須gate合格やPhase 2全体の完了とは扱わない。最初の15分以上戻らなかった記録の最終pipe保持者も、この追加観測だけでは確定しない。timeout後の無期限出力回収はPR #27で修正済みである。
