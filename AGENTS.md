# RepoSpec Viewer 作業ルール

このリポジトリで作業を開始する際は、最初に以下を読むこと。

1. `WORKLOG.md`
2. `docs/README.md`
3. 対象に応じて`docs/frontend-spec.md`または`docs/backend-spec.md`

## Git運用

リモートリポジトリ:

```text
https://github.com/Futaw/GHAgentDev
```

追加、修正、削除は必ず以下の順序で行う。

1. 作業ツリーがクリーンであることを確認する。
2. `main`へ切り替える。
3. `git pull --ff-only origin main`で最新化する。
4. `codex/<task-name>`形式の新しいブランチを作成する。
5. 変更を実装し、必要な動作確認・テストを行う。
6. 差分を確認してコミットする。
7. 同名のリモートブランチへPushする。
8. `main`向けのPull Requestを作成する。
9. Pull Request URL、変更概要、確認結果、残っている注意点をユーザーへ報告する。
10. ユーザーが内容を確認するまでマージしない。

`main`への直接コミット・直接Pushは行わない。Pull Requestのマージもユーザーの責務とする。

## 実装順序

初期実装は`docs/README.md`のフェーズ順に進める。まずPhase 0のCodex App Server接続と最小チャットを完成させ、Repository管理やViewer機能を同時に作り込まない。

## セキュリティ

- 認証コード、パスワード、アクセストークンはファイル、コミット、Pull Request、作業ログに残さない。
- MVPのCodexによるRepository調査はread-onlyとする。
- AI生成HTMLを未検証のまま表示しない。
