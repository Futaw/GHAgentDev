# Phase 2 v1.3 実装・安全性検証記録

2026-11-03、設計PR #25のマージcommit `1c01e84`を基準に確認した。生成の有効化は不可。`GENERATION_ENABLED`の既定値falseと実際の`.env`は変更していない。

## 実装

既存のstdio App Server、Job固有Permission Profile、構造化文書の生成・検証・保存を維持した。固定feature無効化、strict起動validation、CLI/schema契約検査を共通化した。Jobごとのcwd設定・requirementsと、ThreadのProfile・runtime roots・指示元・全pageのfeature/MCP状態を照合し、runtime検査後に設定/layer versionが変わっていないことを再確認する。修正Turn前にも同じ検査を行う。

Plugin列挙と`disabledPluginIds`は生成経路から除いた。設定の取得失敗を空一覧へ変換しない。設定の継承、shell環境tableのmerge、旧sandbox、指示file、Profile衝突、未評価のmanaged制約は拒否する。接続世代、account変更、logout、拒否イベントで検査を失効させる。追加権限要求・外部tool通知・不整合は非保存とし、実行状態が不明なら共有processを破棄する。通知処理はstdout readerから分離し、通知handlerがrequestを待ってもresponse routingが止まらないようにした。

作成・再生成・Job再試行の画面は、生成無効、Codex未接続、安全設定確認失敗を区別し、Problem Detailsの説明・code・trace IDを表示する。入力と既存Viewerを保持し、POSTの自動再試行を無効化する。非retryable Jobの再試行ボタンは表示しない。非同期エラーのtrace IDにはJob UUIDを使う。

## 自動確認

- Backend: `pytest -q`、109 passed。Fake + SQLiteの生成保存と、baseline不整合/timeout/未接続、Job設定timeout、Thread情報欠落・timeout、command/file/permissions要求、外部tool、接続世代変更、修正Turn前の設定変更での非保存を検証。
- CLI/schema契約、Profile、設定/layer/requirements、全pageのinventory、検査失効、空・boolean自己申告・timeoutのprobe誤合格防止を検証。
- Fake App Serverで3種類のschemaに沿った承認拒否応答、readerを塞がない通知処理、既存Chatの接続・再起動を検証。実Codexの承認要求を観測した証拠には使わない。
- Frontend: 29 passed。3分類、trace ID、入力保持、POSTの自動再試行なし、再生成失敗時の既存Viewer表示、Job再試行失敗と非retryable Jobのボタン非表示を検証。Chat回帰を含む。
- Ruff check/format、ESLint、TypeScript、Vite production build: 成功。Zod依存元のpure annotationに関するbuild警告あり。
- SQLiteのfresh DBにmigration適用: `20261025_0002 (head)`。PostgreSQL offline SQL生成成功。実PostgreSQLへの適用は未実施。

## 実Codex

実行ファイルは指定された `/Users/futaw/.local/bin/codex`、versionは`codex-cli 0.164.0`、OSは`macOS-26.6.2-arm64-arm-64bit`。CLIの更新・再インストール・別CLIへのfallbackはしていない。

`--version`、App Serverとsandboxのhelp、feature一覧、通常/experimental JSON schema、experimental TypeScript型を確認した。ThreadStartParams + TurnStartParamsの連結hashは設計14.2の両方と一致した。追加契約ファイルを含むhashとgate別の生結果は[JSON記録](./2026-11-03-generation-safety.json)を参照する。生RPC、設定全文、認証値、モデル出力は記録していない。

```bash
.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 120
```

上記を外側sandboxの影響を除いた許可済み実行環境で実施し、終了codeは1だった。probeは専用の一時Git fixtureと非機密sentinelだけを対象とし、既存Repository、実認証file、ユーザーdocumentへ向けていない。認証情報のコピー、user configや認証情報への書込みは行っていない。

| 検査 | 結果 | 証拠・限界 |
|---|---|---|
| 親の読取り・通信対照 | passed | 全sentinelを親が読める。受け付けるloopback listenerとpublic endpointへ親から疎通成功 |
| 専用homeでのprotocol/config | passed（補助検査） | trusted projectの全禁止feature再有効化・enabled MCP canaryに対し、起動override、canonical Profile、cwd/root、空instructionSources、feature false、MCP disabledを確認。canaryは未起動 |
| 実ユーザー設定でのprotocol/config | failed | `shell_environment_merge`で停止。設定内容や値を公開せず、user configを変更していない。Turn未開始 |
| 決定的な読み取り範囲 | **failed** | 許可fileだけでなく、兄弟、Workspace外、専用home内の認証path相当sentinelの3種類も`cat`で読めた。実認証情報は読んでいない |
| 決定的な非変更 | passed | update/create/delete/rename/`.git/config`書込みを試し、OSのpermission denialを確認 |
| 決定的なcommand通信 | passed | 疎通対照と同じloopback/public IP・portへのcurl接続がOSに拒否された。DNS失敗や単なる接続timeoutは合格に含めない |
| 実Turn・構造化出力・tool誘導・追加権限誘導 | not_run | 実設定の事前検査で停止。モデルのboolean自己申告や拒否回答を合格根拠にしていない |
| 実RPCでの承認要求 | not_observed | 防御用拒否はFakeの証拠と分ける |
| fixture非変更・cleanup | passed | 全保護pathの内容/存在/配置とGit metadataのhash、Git statusが不変。一時fixtureを削除 |

決定的probeはモデルを介さない`codex sandbox --permission-profile ... --include-managed-config -C ...`で、Threadへ送るものと同じcanonical Profileを使用した。最小runtimeの読取り範囲は追加していない。初期probeは標準Pythonの実行環境不足、Perlのruntime読取り拒否で実行できなかったため、標準のcat/sh/rm/mv/curlで個別に試験する方式へ変更した。実行不能は不合格のOS拒否証拠にも合格にも読み替えていない。

対象外の読み取り成功は実測結果であるが、内部原因は未特定。`:minimal`、platform既定許可、Profile解決のどれが原因かは断定しない。実際の利用者homeの認証fileや、fixtureと異なる配置の既存Repositoryの読取り可否も推測しない。従来の`plugin/list` timeout原因を特定・解消したという主張もしない。

## 未完了と引き継ぎ

生成は有効化しない。まずcanonical Profileの対象外読取りと、実設定のshell環境mergeを別々に調査する。権限拡大、未評価設定の容認、設定削除、CLI更新で回避しない。調査・設計見直し後は同じ環境で全必須gateを再実行する。

認証付きの実Turn、実ViewerDocument生成とDB/Git ref保存、実RPCでの承認拒否観測、実CodexでのPhase 0 Chat回帰は未実施。ブラウザの実画面幅目視、3分類の手動操作、実PostgreSQLも未実施であり、自動テストの成功で代替したとは扱わない。設計21.3の手動確認とPhase 2全体の完了条件は未完了である。
