# Phase 2 最終受入確認

2026-11-09、PR #32を含むmain `1b934ab79428dbe2585a7223221e0938843b643c`をPullし、利用者が通常Backendを再起動した後に確認した。**ローカル・単一ユーザー・Public Repository・固定CLIという対象範囲で、Phase 2の完了条件を満たした。** 今回追加するのは完了記録だけで、アプリの実装修正はない。

安全な状態・件数・hashの詳細は[JSON記録](./2026-11-09-phase-2-acceptance.json)、生成・保存・表示の前回結果は[通常UI検証](./2026-11-09-viewer-ui-verification.md)を参照する。過去記録の未完了事項を成功へ書き換えず、今回の再検証で解消したものとして扱う。

## 通常アプリでの最終確認

Backendの起動時刻は再起動前21:58:52から22:17:46へ更新された。DBは`repospec_viewer_utf8`、server_encoding UTF8、Migration head `20261025_0002`、認証はauthenticated、healthはok/connectedだった。生成の有効化とBackend再起動は利用者の操作である。Codex側で`.env`、実Codex設定、認証、CLIは変更していない。

管理Repository `2c1879c2-3ff4-48b3-841c-aa3e2ec551f6`を画面から最新コードへ同期し、HEADが`1b934ab`になったことを確認した。既存Viewerは旧Commit `846f7c9`のrefを維持し、同期後も閲覧できた。

| 操作 | 実測 |
|---|---|
| 試験用Viewerを新規生成 | Job `96fd8795-a1cc-48fa-b822-a32687404d51` completed。試験Viewer `daf5e94c-3e8c-4c01-85a1-b2070e36676a` revision 1を保存し自動表示。最初の中止操作前に生成が完了したため、このJobを中止成功には数えない |
| 再生成を画面から中止 | Job `3a9d8ed2-9da8-4dd6-9862-d696cc3435e9` cancelled、errorなし。DBでTurn IDと中止要求があることを確認。画面は「CANCELLED／Viewerの生成を中止しました」と表示し、既存の試験Viewerを保持 |
| 「同じ条件で再試行」 | Job `01eb4811-fa85-4a0e-91f9-e6e39e1b7e0d` completed、約21秒。同じ試験Viewerがrevision 2へ更新され、自動表示された。新しいCommitのソース参照1件を含む文書を保存 |
| 画面から削除確定 | 利用者が対象を確認して許可した後、「最終確認用・削除予定」1件だけを削除。Dashboardへ遷移し、対象ViewerはGET 404、対応するrevision refは消滅 |
| 主Viewerの保持 | Viewer `87810752-10d6-4dc4-b96e-ea10b7d7f92b`はrevision 2のまま。文書とHTMLのhashは前回と一致。29件のソース参照を生成元Commitのblobで再検証し、HTMLのsanitizer再適用も不変 |

削除済みViewerを指すJobのviewer_idは外部キーのSET NULLによってnullになる。完了Job自体は残り、completedをfailedへ変えるものではない。JSONには削除前の再試行結果と削除後のJob状態を分けて記録した。

- [中止後の画面](./2026-11-09-phase-2-cancelled.png)
- [削除後のDashboard](./2026-11-09-phase-2-dashboard.png)

## 回帰と安全性

マージ後のBackend **188 passed**、Frontend **33 passed**。Ruff check/format、ESLint、TypeScript/Vite buildも成功した。依存Zodのannotation警告は引き続き出るが、buildは成功している。

固定CLI `/Users/futaw/.local/bin/codex` 0.164.0、policy `repospec-generation-v1.3-3`で全体harnessを再実行し、exit 0、必須9gateすべてpassed、process/fixture cleanupもpassedとなった。部分実行、Fake、timeoutや起動失敗を合格へ読み替えていない。

| 完了条件 | 根拠 |
|---|---|
| 1 非同期生成 | 前回・今回の通常UI生成と自動表示 |
| 2 読取り範囲・非変更 | 今回の実CLI全体harness、管理RepositoryのGit status clean |
| 3 Theme/Density | 前回の通常UI変更、本文/HTML/revision不変 |
| 4 12種block | schema/rendererテストと前回の全block合成表示fixture |
| 5 未知HTML等の拒否 | Backend validator/sanitizerとFrontend sanitizer回帰テスト |
| 6 実ファイル・行範囲 | 通常保存時と今回の29参照再検査、指定Commitのblobを使用 |
| 7 検証済みHTMLのみ | サーバーとブラウザのsanitizerテスト、保存HTMLの再適用不変 |
| 8 進捗・中止・再試行 | 通常UIでSSE接続・中止表示・同条件再試行・保存成功 |
| 9 再生成失敗時の保持 | 前回の実失敗時のhash保持とFake結合テスト。今回も主Viewer不変 |
| 10 Commitのref保持 | 同期後も旧Commitの現行Viewer refが一致。試験用refだけを削除 |
| 11 Repository排他 | DB/Fake結合テスト、通常UIの同期と生成。実機で競合を強制した試験とは区別 |
| 12 Desktop/Mobile | 前回の12種＋大きいflowの合成fixture、1440/390px、両Theme/Density |
| 13 自動・手動確認 | 上記188/33件、lint/build、UTF8/Migration、通常UIの残項目完了 |
| 14 非公開情報の扱い | 秘密値を含む例外・SQL値を出さない回帰テスト、状態・hashのみの記録。実ユーザー設定・認証・生モデル出力を複製しない |
| 15 必須gate | 今回の実CLI全体harnessで9項目passed。証拠種別はJSONに保持 |

## 後始末と現在の状態

通常DBのactive Jobは0件、Viewerは主Viewerの1件だけである。主Viewerのrevision 2用refだけが残り、試験用Viewerのrefとgeneration一時refはない。管理RepositoryのHEADは`1b934ab`、Git statusはクリーンだった。

全体harnessのprocess/fixture cleanupはpassed、記録PID/PGIDの残存は0。通常Backendは利用者の起動を維持し、生成フラグは利用者が設定したtrueのままである。旧EUC_JP DBと旧Workspaceも削除していない。

今回の機能検証は完了した。完了記録のPRは利用者がレビュー・マージする。文書だけの変更なので、そのマージを理由とするBackend再起動は不要である。

## Phase 3以降へ残す事項

実RPCの承認要求拒否は今回もnot_observedであり、Fake拒否試験と区別する。Codex側のGit/Command Line Tools経路が使えない旨は生成文書の制約として残る。原因は未切分だが、BackendのCommit blobによる参照検証は成功しており、権限拡大や別CLIで回避していない。

Q&AとSource Code Viewer本体、Private Repository、複数ユーザー、リモート公開・本番運用は今回の完了対象外である。CLI、policy、設定・実行環境を変更した場合は、今回の結果をそのまま流用せず安全性を再確認する。
