# Phase 2 通常画面の生成・保存と中止処理

2026-11-09、PR #31マージ後のmain `846f7c9`、macOS、Python 3.12.0、固定CLI `/Users/futaw/.local/bin/codex` 0.164.0で確認した。利用者がUTF8 DBへの切替・Migration・生成の再有効化・Backend再起動を行った。Codex側で`.env`、実ユーザー設定、認証情報、CLIは変更していない。

**通常画面からのViewer生成・保存と再生成は成功した。Phase 2全体は、中止修正を取り込んだ通常Backendでの再確認が残る。** 安全な数値・状態・hashの記録は[JSON](./2026-11-09-viewer-ui-verification.json)を参照する。

## 実環境で確認できたこと

接続先は`repospec_viewer_utf8`、server_encoding UTF8、Migration head `20261025_0002`だった。固定の非機密UnicodeをTEXTとJSONBへ保存・読戻しできた。試験には接続内だけのTEMP TABLEを使い、アプリの既存行は変更していない。Backendのhealth・App Server接続・認証も正常だった。

同じPublic Repositoryを新DBへ再登録した。管理IDは`2c1879c2-3ff4-48b3-841c-aa3e2ec551f6`、Futaw/GHAgentDev、main `846f7c9`、readyである。旧DBと旧Workspaceは残した。

| 操作 | 結果と証拠 |
|---|---|
| 通常画面から新規生成 | Job `efa659bc-71c8-482d-bfdd-b5da211d7683` completed、153秒。Viewer `87810752-10d6-4dc4-b96e-ea10b7d7f92b` revision 1、4 Section・23 source referenceを保存し、画面がViewerへ自動遷移した |
| 再表示・ソース参照 | Reload後も本文を表示。参照popupは相対path・行範囲を表示した。Source Code Viewer本体はPhase 3の対象 |
| Theme / Density | editorial / compactへ変更。本文・HTML hashとrevisionは変わらず、生成Jobも増えなかった |
| 修正前の再生成中止 | Job `907fd7bd-c5ea-4a41-9acb-3a71833cbc0e`はCODEX_TURN_FAILED。元Viewerのrevision 1と本文・HTML hashは保持された。cancelledの成功証拠には数えない |
| 画面の「同じ条件で再試行」 | Job `ae2eb1fa-01f4-4585-b3d8-caf5af3a759a` completed、147秒。同一Viewerがrevision 2へ更新され、表示設定も保持された |
| 保存後の再検査 | revision 2の29参照を指定CommitのGit blobで再検証。sanitizer再適用でHTMLは不変、管理Repositoryのtracked sourceはHEADと一致し、Git statusもクリーン |
| 削除試験 | 別の短い実生成Job `301b45ea-5a15-430a-a3fd-94a33bd5ef86`から試験用Viewerを作成。画面の削除dialogとキャンセルを確認後、その試験ViewerだけをAPIで削除。204→GET 404、対応refも消滅。主Viewerは保持 |

生成文書には、Codex側でGitを使えなかった旨の制約が記載された。sandbox内のGit/Command Line Tools経路の原因は今回切り分けていない。一方、Backend側の指定Commit blob・行範囲検査は保存時と独立した再検査の両方で成功した。モデル自身の説明を検証結果として採用していない。

[保存・再生成後の通常画面](./2026-11-09-viewer-generated.png)を記録した。生成文書のJSONや生モデル出力は、この記録へ複製していない。

## 発見した不具合と修正

中止要求をDBへ記録して`turn/interrupt`を送った後、CLIは`turn/completed`のstatus `interrupted`を返す。従来は`completed`以外を一律CODEX_TURN_FAILEDにしていたため、利用者の中止もfailedになった。

TurnとJobを対応づけ、**DBに中止要求があるinterruptedだけ**をcancelledへ進める。要求なしのinterruptedや通常のfailedは失敗のままとする。未知tool等の安全性違反は、中止要求があっても優先して拒否する。検証済みの終端通知がある場合は共用App Serverを切断せず、終端未確認の場合は既存の停止処理を維持する。過去の失敗Jobは書き換えない。

Job画面の見出しもstatusに合わせる。完了・失敗・中止後に「生成中」と表示し続けない。

Mobileの8列表は、各列が1文字程度まで縮んで縦に長くなった。セルに最小幅8emを設け、表内部の横スクロールで読む形に修正した。画面全体の横幅は増えない。

## 修正後の検証と証拠の範囲

Backend **188 passed**、Frontend **33 passed**。Ruff check/format、ESLint、TypeScript/Vite build成功。依存Zodのannotation警告は残る。

Fake結合テストでは、再生成の中止要求→interrupted→cancelled、SSEのjob.cancelled、元Viewer保持、一時ref削除、共用接続保持を確認した。Unit testでは、要求なしの中断・要求ありでも通常failed・未知toolを含む終端通知を区別した。

修正コードと実CLIを用い、専用の使い捨てPostgreSQL schemaと非機密Git fixtureでも中止を確認した。中止要求後0.031秒でcancelled、errorなし、Viewer 0件、一時refなし、Codex接続保持となった。専用Codexの停止、schemaとfixtureの削除を確認した。この試験は通常画面での修正後の中止確認とは区別する。

合成fixtureでは12種類のblockと大きいflowの表表示を、実renderer・sanitizer・built Frontendで確認した。専用サーバーは127.0.0.1:8181、DB・Codexへは未接続で、実生成の証拠には数えない。1440pxと390pxでpage幅がviewport幅と一致し、13個のblockが範囲内に収まること、長いcode・多列表が内部スクロールになることを確認した。technical-light / comfortable、editorial / compactを確認した。

- [Desktopの全block](./2026-11-09-all-blocks-desktop.png)
- [Mobileの全block](./2026-11-09-all-blocks-mobile.png)
- [Mobile表の修正後](./2026-11-09-viewer-mobile-table.png)

同日の生成再有効化前には、実CLI全体harnessがexit 0、必須9gateすべてpassedだった。policyは`repospec-generation-v1.3-3`であり、今回の修正は権限・検証条件を緩和していない。実RPC承認要求の拒否が未観測である点は、過去記録と同じくFake拒否試験と区別する。

## 後始末と残る確認

通常Backendは利用者が起動したまま維持した。生成は利用者が有効化したtrueのままで、Codex側では変更していない。主Viewerのrevision 2と現行のGit refを残し、一時ref、旧revision ref、削除試験用Viewerのrefは消滅を確認した。通常DBのactive Jobは0件。専用サーバー、専用Codex、使い捨てschema・Git fixtureは後始末済みである。

修正PRのマージ・mainのPull・Backend再起動後、通常画面から中止してcancelledとなることと再試行を確認する。削除の実行自体は実APIで成功したが、画面の削除確定ボタンを押してDashboardへ戻る一連の確認は未実行である。次回は別の削除試験用Viewerを用意して行う。これらを終えるまでPhase 2を完了扱いにしない。
