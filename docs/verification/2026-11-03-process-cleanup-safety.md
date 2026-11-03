# Phase 2 検証プロセス終了処理と安全性の再確認

2026-11-03。`dbb6d1b`を基準に、CLI `/Users/futaw/.local/bin/codex`（`codex-cli 0.164.0`）、macOS 26.6.2、Python 3.12.0で確認した。**生成は有効化不可。`GENERATION_ENABLED=false`を維持する。** 実設定・認証情報・CLI installationを変更・複製していない。

## 問題の確定範囲

利用者の120秒指定実行では`wait_for(process.communicate(), timeout_seconds)`が時間切れになった後、`finally`の期限なし`communicate()`が戻らなかった。`--timeout`はコマンド/RPCごとの待機時間であり、実行全体の期限ではない。従来は最終JSONが出るまで進捗も見えなかった。

直接の親が終了しても、子孫がstdout/stderrを保持すればEOFにならない。親の`returncode`だけを見てkillを省略する処理と、親だけをkillして出力を無期限に回収する処理は、どちらもこの状況を解消できない。無害なforkプロセスで、この経路を再現した。

利用者の停止時にパイプを保持した最終プロセスと、削除検査自体が時間内に終了しなかった理由は未特定。今回の実Codexでは長時間停止は再現せず、当時のPIDや一時pathを停止対象に使っていない。元ログ冒頭の過去の`plugin/list` timeoutを今回の原因と結び付けない。利用者の停止結果はOSの削除拒否や検査合格の証拠にならない。

## 修正

- `codex/process.py`へPOSIX用の共通実行処理を追加。起動ごとに新規session/process groupを作成し、当該groupだけへTERM、続いて必要ならKILLを送る。親が終了済みでもgroupを検査する。`cli_output()`とnative probeが共有する。
- TERM猶予0.3秒、KILL後のgroup確認1秒、出力回収0.5秒、キャンセルした出力taskの回収0.5秒に制限。最後にasyncio transportのpipeを閉じる。通常完了時も残る子孫を検査する。
- spawn中の中断でもhandleを失わず、cleanup中の追加キャンセルでも停止確認を続ける。起動失敗、すでに終了した対象、通信回収失敗を扱う。
- group消滅、親の終了、pipe EOFを確認できなければcleanupを`failed`とする。意図的なsession離脱はgroup停止だけでは保証できない。pipeを保持した離脱プロセスの試験では期限内に`failed`で戻り、試験側が作成直後の専用PIDを確認して停止した。包括的なOS containmentを実装したという意味ではない。
- harness自身が起動するApp Serverにも同じsession/group停止を適用。独立readerの終了確認と停止失敗の報告を追加した。既存の起動中アプリには接続・停止していない。
- 検査名、開始、完了、timeout、中断、PID/PGID、停止signal、cleanup結果をstderrへ逐次出す。stdoutは最終JSONのみ。contract内のversion/help/schema等も段階別に表示する。
- 各probeの結果を直ちに共有reportへ保存し、途中失敗・中断でも完了済みの証拠を保持する。fixture準備中の失敗でもreportを返し、検査段階を記録する。起動できたことを確認する固定markerのないsandbox起動失敗を、操作のOS拒否へ読み替えない。
- `--only deletion / reads / protocol / shell-merge`を追加。通常実行の必須検査は維持する。部分実行は常に`partial=true`、exit 1で、未実行gateは合格にしない。`protocol`部分実行ではモデルTurnを開始しない。Ctrl+Cはcleanup後に途中reportを返しexit 130。

設定全文、環境変数の名前・秘密値、任意のfilter pattern、認証情報、モデル出力、実行command全文は診断へ出さない。

## 自動テスト

Backend全132テスト、Ruff check/format、`git diff --check`が成功。Frontendは変更しておらず、今回は再実行していない。

再現・回帰テストは実Codexと分離した無害なプロセスを使い、次を確認した。

- 親がexit 0で先に終了し、子が両pipeを保持。子はTERMを無視し、KILL後に消滅する。
- timeout、Task中断、追加キャンセル、spawn中断が制限時間内に戻る。
- 別PythonプログラムへSIGINTを送り、native probeが途中JSONを返してexit 130となり、子が残らない。
- 別sessionの無関係な試験プロセスは生存したままである。
- 起動失敗、非zero終了、cleanup確認失敗、sessionを離脱したpipe保持者を誤ってcleanup成功にしない。
- probe途中timeoutでも先行結果とstderr進捗を保持。sandbox起動拒否を削除拒否にしない。部分成功はexit 0にしない。削除対照が失敗した場合は非変更gateを合格にしない。
- shellの7項目を1項目ずつ不一致にし、不一致項目とlayer種別だけを診断する。秘密の名前・値・pathが例外やログへ出ない。

初回の追加test実装でimport不足が発生した際の離脱子は、当該testのPID記録とsession identityを照合して停止し、消滅を確認した。修正後の全testは成功している。試験プロセスの成功は実Codexの安全性を証明しない。

## 実Codexでの結果

最初の制限付き実行は、外側sandboxで通信対照を開始できず終了した。これを安全性の合格証拠には使わない。続いて、外側sandboxの影響を除いた許可済み実行で専用の非機密fixtureだけを対象に実施した。

```bash
.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 12 --only deletion

.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 15 --only reads

.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 15 --only protocol

.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 15 --only shell-merge

.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 120
```

全体再実行はexit 1。各probeはtimeoutにならず終了し、元の停止は再現しなかった。fixtureは一時Git repositoryと専用homeの無作為sentinelであり、既存Repository・実認証file・個人文書はprobe対象外である。[安全なJSON証拠](./2026-11-03-process-cleanup-safety.json)を参照。

| 確認 | 結果 |
|---|---|
| sandboxなしの削除対照 | 削除成功、正常終了 |
| canonical Profile内の許可file読取り | 正常終了、hash一致 |
| 同Profile内の削除 | command開始後のOS permission denial、exit 1。fixtureは残る |
| update/create/rename/`.git/config`書込み | OS拒否、fixtureとGit status不変 |
| 親から到達可能なloopback/public宛の通信 | commandのconnectをOSが拒否 |
| 兄弟、Workspace外、専用homeの認証path相当sentinel | **3種類とも読める。sandbox_read failed** |
| 専用homeのprotocol/runtime | passed（補助検査） |
| 実ユーザー設定のprotocol/config | **shell_environment_merge failed、Turn未開始** |
| 実Turn・構造化出力・外部tool・追加権限誘導 | not_run |
| cleanup | 各probeのgroup消滅・親終了・pipe EOF、App Server停止、fixture削除を確認 |

### ① 許可範囲外の読み取り

再確認でも不合格。空の専用homeを使い、次を1条件ずつ比較した。アプリで使うProfileは変更していない。

| 条件 | 許可file | 隣接sentinel |
|---|---|---|
| canonical（`:minimal=read`と相対workspace root） | read | read |
| `:minimal`だけ除去 | command開始前にexit 134 | command開始前にexit 134 |
| workspace指定だけ同じRepositoryの絶対pathへ置換 | read | read |

`:minimal`除去時の失敗はOS読取り拒否や対策成功の証拠ではない。絶対path指定でも読めたため、相対path解釈の変更だけでは解決していない。生成されるOS policy、platform defaults、Profile解決、実行経路のどこが原因かは未特定。App Server経由の実Turnは設定gateで未実行なので、経路間の同等性も未確認である。

次の設計調査は、同じfixtureで実際のProfile/OS policyを対応付け、CLI側の修正が必要か、アプリ側に別のOS隔離境界が必要かを評価する。権限追加・gate緩和・CLI更新をこのPRの回避策として採用しない。

### ② shell_environment_merge

原因を切り分けた。実設定では`inherit`、`ignore_default_excludes`、`include_only`、`exclude`、`filters`、`experimental_use_profile`が一致し、**`set`だけが不一致**。PATH自体は固定値に一致するが、effectiveなsetは2項目で、`sessionFlags`と`user`の両layerにsetがある。追加項目の名前と値は記録していない。

専用homeのuser configに`REPOSPEC_HARMLESS_CANARY="fixture"`という無害なsetを1項目だけ置き、実アプリと同じ起動overrideで再試験した。PATHとcanaryが結合され、同じ診断・同じ拒否となった。実user configはコピーも編集もしていない。`inherit="none"`とPATHのsetだけでは、下位layerのset tableを置換できないことを実測した。

このPRでは診断だけを追加し、既存の完全一致条件を維持する。次の設計では「table全体を確実に置換する方法」と「秘密値を含まない専用fixtureで、実際の子環境をPATHだけに制限できる方法」を比較し、requirements/layer/runtime検査も含めて評価する。未知の追加setを許可する変更は行わない。

## 残る確認

過去の停止時の最終pipe保持者・削除probe停滞原因は未特定。今回の実Codexでのtimeout後cleanupは、同じ停止が再現しなかったため実測していない。無害なプロセスの再現testでの証拠と区別する。

範囲外読取りの修正、shell環境の隔離設計、認証付き実Turn、実Viewer保存、実RPC承認拒否、実Codex Chat操作の回帰は未完了。既存のPostgreSQL・ブラウザ手動確認の未完了も継続する。全必須gateがpassedになるまでは生成を有効化しない。


## 2026-11-04の追加調査

利用者の端末実行で削除probeのtimeoutが再現した。疑似端末と非端末stdinの比較によりrmの確認入力待ちを再現し、非対話コマンドのstdin継承を止める修正を行った。利用者観測、因果関係を確認した比較、修正後の端末実行は[追補記録](./2026-11-04-verification-stdin.md)を参照する。読み取り範囲とshell環境の課題は継続し、生成は無効のままとする。
