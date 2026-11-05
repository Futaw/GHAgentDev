# Phase 2 shell環境と実Viewer保存の検証

2026-11-05、PR #29のmerge commit `335bc77`を基準に確認した。固定CLIは`/Users/futaw/.local/bin/codex`、0.164.0、macOS 26.6.2、Python 3.12.0。通常アプリの`GENERATION_ENABLED=false`、`.env`、実ユーザーのCodex設定と認証storeは変更していない。CLIの変更・切替、認証情報の複製、Profileの権限追加は行っていない。

## 判明した問題と修正

### shell_environment_merge

CLI overrideの`set={PATH=...}`は下位tableと結合される。従来の「setがPATHの1項目だけ」という検査は、実ユーザー設定の追加項目で停止していた。

policy v1.3-3では、`inherit=none`、固定PATH、`include_only=["PATH"]`、空excludeを起動時に指定する。[公式仕様](https://learn.chatgpt.com/docs/config-file/config-advanced#shell-environment-policy)の順序どおり、setの後のallowlistで追加値を除去する。実CLI 0.164.0の空home fixtureでも、下位setのcanaryが設定には残り、許可リストだけがPATHへ置き換わることを確認した。実Turnの補助診断では、setへ明示した非機密canaryと、親環境の非機密canaryがコマンド環境に存在しなかった。

設定の追加値を子環境へ無審査で許可する方式にはしない。最終allowlistの欠落・拡張、非空filters/exclude、固定PATHの不一致、大文字小文字違いのPATH、型不正・未知fieldは拒否する。設定table全体の完全一致から、評価済みの最終環境制約へ検査対象を変更した。設定内容、追加変数名、秘密値を診断ログへ出さない。

### CLIによるPATHとruntime変数の追加

最初の実Turn環境検査は不合格だった。CLIはfilter後に同梱tool directoryとruntime変数を追加するため、設定上のsystem PATHへの一致だけでは不十分だった。

固定インストールの`codex-package.json`は、version 0.164.0、target aarch64-apple-darwin、pathDir codex-path、layoutVersion 1だった。codex-path内は同梱rgである。CLI同versionの公式実装の`apply_package_path_prepend`、`apply_unified_exec_env`、`inject_session_env`等と実測を照合した。参考：[同versionの実装](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/core/src/tools/runtimes/mod.rs)、[環境filter](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/protocol/src/shell_environment.rs)。

PATHはこのレビュー済みdirectoryとsystem4directoryの固定値とし、manifestの内容とhash、directoryの存在・非symlinkを照合する。任意の実行時PATHや別インストールを自動受理しない。これは今回の固定macOS/CLI配置の契約であり、他の配置へ広げる際は再レビューが必要である。Permission Profileへ追加rootを許可していない。

全体harnessへ必須`shell_environment` gateを追加した。実際のcommand item、終了code、固定markerで、PATH完全一致と評価済みruntime変数名だけであることを確認する。値や変数名の一覧を出力しない。モデルの自己申告、単なる拒否、非実行、timeoutは合格にしない。違反後の再実行が成功しても、先のfailedをpassedへ戻さない。

### 正規のuserMessage通知

実CLIは入力を`userMessage` itemとして通知する。従来runnerはこれを未知toolと誤分類していた。正規のメッセージitemとして認め、未知toolやMCP/file/permission経路の拒否は維持した。Fakeもstarted/completedとTurn itemsに同通知を含めて、生成保存と異常時の非保存を回帰確認する。

harnessのcommandは、引用符を解釈したargvとshell wrapperの完全一致で照合する。echoによる偽装や追加commandを合格にしない。

### PostgreSQLの保存順序

実Viewer生成は文書・ソース・HTMLの検証まで進んだが、`saving_viewer`のflushでIntegrityErrorとなった。新規ViewerのINSERT前にJobのviewer_id外部キーが更新されるためだった。SQLiteの既定では外部キー制約が無効で、従来のFake統合testで検出できていなかった。

SQLiteの外部キー制約を有効にした既存の生成保存testで、修正前に同じ失敗を再現した。新規Viewerを先にflushしてからJobを更新するよう修正し、同じtestが成功することを確認した。両方を1トランザクションに保ち、途中commitや制約の緩和は行わない。

## 確認結果

- Backend: **165 passed**。設定allowlist・PATH別名・manifest・command照合、環境違反の上書き防止、外部キー制約付き生成保存、既存の拒否・timeout・cleanup回帰を含む。
- Frontend: **29 passed**。ESLint、TypeScript/Vite build成功。依存Zod由来のpure annotation警告あり。
- Ruff check/format、git diff --check成功。
- 固定CLIの通常全体検査は、下記の全9gateがpassed、exit **0**。部分実行の結果ではない。

```bash
.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 120
```

| gate | 結果 |
|---|---|
| protocol_config | passed |
| sandbox_read | passed |
| non_modification | passed |
| command_network | passed |
| real_turn | passed |
| shell_environment | passed |
| external_tools | passed |
| additional_permissions | passed |
| fixture_integrity | passed |

実RPCでの承認要求はnot_observed。Fakeでの拒否応答確認を実RPC拒否の観測へ置き換えていない。

## 実Viewer・PostgreSQL・Chat

実PostgreSQLにUUID付きの新規専用schemaを作成し、そのschemaだけをsearch_pathに設定した。migration `20261001_0001`、`20261025_0002`のupgrade関数を同じAlembic Operationsで適用した。通常schemaへのmigration適用や既存データの更新は行っていない。専用schemaは各試験のfinallyで削除し、消滅を確認した。

新規の非機密Git fixtureのgreeting.pyだけを対象に、実GenerationRunnerへ使い捨てJobを直接渡した。最終確認は通常APIで選択できるfunctional_spec / standard / engineerの条件で行った。

- 実Codexによる構造化文書生成、schema検証、実在ソース参照1件、renderer/sanitizer、PostgreSQL保存が成功した。
- Viewerは1件、Jobはcompleted、保存Git refは生成元Commitと一致した。source内容とGit statusは不変で、一時Generation refは残らなかった。
- 再生成のpreflight失敗を注入し、failedと既存Viewerの文書・revision保持を確認した。これは実モデルが違反した証拠ではなく、障害注入と実DBによる保存防止の証拠である。
- 通常APIの生成受付flagはfalseのまま。直接runnerの統合確認と、通常画面からの生成受付〜保存のE2Eは区別する。
- 同じ起動policyの実ChatServiceで、認証、最小応答、delta/完了イベント、中止、接続破棄後の再接続と次の応答を確認した。回答本文は記録していない。

## ブラウザ確認

生成済みの検証用Viewer・Git fixtureだけを別の使い捨てSQLite DBへ移し、127.0.0.1:8181の専用サーバーでbuilt frontendを表示した。通常の8000/5173のアプリには触れていない。

452px幅でViewer本文・メタデータ・目次・ソース参照popupを確認した。ThemeとDensityを変更してもrevisionは1、Jobは0件のままで、再生成は発生しなかった。再生成ボタンはGENERATION_DISABLEDとtrace IDを表示し、既存Viewerを保持した。表示画像は[専用fixtureの画面](./2026-11-05-viewer-fixture.png)に保存した。ソース本文表示は既存のPhase 3予定表示であり、今回実装していない。

専用DB/Git fixtureを削除し、専用サーバーとそのCodexを停止した。通常アプリの生成有効化、通常画面からのJob開始、全blockのDesktop/Mobile表示、実GenerationのUI中止・削除等は残る。これらが完了するまでPhase 2全体の完了とはしない。

安全な結果は[JSON証拠](./2026-11-05-generation-shell.json)を参照する。設定全文、秘密値、認証情報、生のモデル出力は含めない。

## マージ後の通常環境での確認

まず生成を無効のままmainを最新化し、上記の通常全体harnessを実行する。終了code 0、全9gate passed、process/fixture cleanup passedを確認する。部分実行や古いpolicyの記録では代替しない。

その後、管理者が生成を有効化した同じ環境で、非機密Public Repositoryから画面でViewerを1件生成し、Job完了・保存・再表示・ソース参照・再生成・中止・削除を確認する。有効化は今回の作業では行っていない。`.env`を変更せずに実施した専用runner試験を、この通常画面のE2E完了へ読み替えない。
