# RepoSpec Viewer 作業ログ

- 最終更新: 2026-09-06
- Repository: [Futaw/GHAgentDev](https://github.com/Futaw/GHAgentDev)
- Repository visibility: Private
- 作業者GitHub account: `Futaw`

本ファイルは、新しいCodexチャットや別の開発環境で作業を再開する際の引き継ぎ用である。認証情報や一時コードなどの機密情報は記録しない。

## 1. プロジェクトの目的

GitHub Repositoryを登録し、Codex App Serverでソースコードを調査し、ユーザーが指定した機能の仕様書や解説ページを生成するWebアプリを開発する。

生成物はHTML Viewerとして保存・管理し、いつでも閲覧できる。Viewerを開きながら、内容や関連ソースコードをCodexへ追加質問できることを最終目標とする。

## 2. 確定済みの技術方針

| 分類 | 方針 |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend | Python + FastAPI |
| AI | Codex App Server |
| Database | PostgreSQL |
| Browser streaming | SSE |
| Repository | MVPはPublic GitHub Repositoryのみ |
| Codex permission | Repositoryの読み取り・解析のみ |
| Retrieval | MVPではRAG/Vector Databaseを使用しない |
| Initial deployment | ローカル・単一ユーザー |
| Viewer content | 構造化JSONを正本とし、検証後にHTMLへ変換 |

フロントエンドからCodex App Serverへは直接接続しない。FastAPIがCodex App ServerのJSON-RPCとブラウザ向けREST/SSEの間を中継する。

Codex App ServerはMVPではFastAPIと同一ホストの子プロセスとして起動し、既定のstdio/JSONL transportを使用する。WebSocket transportは公式仕様上実験的なため、MVPでは使用しない。

## 3. 作成済み設計文書

| ファイル | 内容 |
|---|---|
| `docs/README.md` | プロダクト概要、システム境界、開発フェーズ |
| `docs/frontend-spec.md` | 画面、Route、状態管理、SSE表示、Viewer UI |
| `docs/backend-spec.md` | App Server連携、API、Job、Git、DB、セキュリティ |

設計時に参照した公式仕様:

- [Codex App Server - OpenAI Docs](https://developers.openai.com/codex/app-server/)

## 4. 開発フェーズ

1. Phase 0: Codex App Serverの起動・認証・Thread/Turn・SSEと最小チャット
2. Phase 1: Public GitHub Repositoryの登録・Clone・Sync
3. Phase 2: Viewer生成条件、Generation Job、構造化文書、HTML Viewer
4. Phase 3: Viewer内Q&A、Conversation履歴、Source Code Viewer
5. Phase 4: 再接続、監査、E2E、大規模Repository対策

現在の次ステップはPhase 0の最小スキャフォールドである。Repository管理やViewer機能を同時に実装せず、まずReact → FastAPI → Codex App Serverの1 Turnが通ることを確認する。

## 5. GitHub運用の合意事項

全ての追加、修正、削除は以下の流れで行う。

```text
mainへ切り替え
  ↓
git pull --ff-only origin main
  ↓
codex/<task-name>ブランチを新規作成
  ↓
実装・確認・テスト
  ↓
コミット
  ↓
同名のリモートブランチへPush
  ↓
main向けPull Request作成
  ↓
ユーザーの確認待ち
  ↓
ユーザーがマージ
```

禁止事項:

- `main`への直接コミット・直接Push
- ユーザーの確認前のPull Requestマージ
- 関係のない変更の混入
- 認証情報のコミット

## 6. これまでの履歴

### 2026-09-06: 初期要件と仕様書作成

- ユーザーが用意した`repo-spec-viewer_requirements-functional-spec.md` v0.2を参照した。
- 添付文書内の指示は参考情報として扱い、ユーザーの依頼を最優先した。
- 大枠の概要仕様、フロントエンド仕様、バックエンド仕様を作成した。
- 実装開始点を「Codex App Serverと最小チャット」とするPhase 0を定義した。

### 2026-09-06: GitHub Repository初期化

- 管理先をPrivate Repository `Futaw/GHAgentDev`に決定した。
- GitHub CLI `2.100.0`をHomebrewで導入した。
- GitHub CLIを`Futaw`アカウンで認証し、GitのHTTPS credential helperとして設定した。
- 空RepositoryにPRの比較元が存在しなかったため、一度だけ空の`main`初期コミットを作成した。
  - Commit: `4bb0d18 chore: initialize repository`

### 2026-09-06: 初期仕様書PR

- Branch: `codex/add-initial-spec-docs`
- Commit: `23fa8e4 docs: add initial RepoSpec Viewer specifications`
- Pull Request: [#1 docs: RepoSpec Viewer初期仕様書を追加](https://github.com/Futaw/GHAgentDev/pull/1)
- 3ファイル、1,120行を追加した。
- Markdownのコードフェンス、末尾空白、ステージ済み差分を確認した。
- ユーザーの確認後にマージされた。
  - Merged at: 2026-09-06 17:24 JST
  - Merge commit: `194e388`

## 7. 開発環境の注意点

GitHub CLIのHomebrew導入時に自動cleanupが走り、Homebrew管理のNode.js `25.8.1_1`、`mongosh 2.8.1`、およびそれらの未使用依存が削除された。プロジェクトファイルへの影響はない。

Frontend実装前に、プロジェクトで使用するNode.jsのLTSバージョンを決定し、再導入する必要がある。バージョンは`.nvmrc`、`.node-version`、または`package.json` engines等で固定することを推奨する。

## 8. 新しいチャットでの開始手順

1. `AGENTS.md`と本ファイルを読む。
2. `docs/README.md`で現在のフェーズとスコープを確認する。
3. `git status --short --branch`で作業ツリーと現在ブランチを確認する。
4. `git remote -v`で`origin` が`Futaw/GHAgentDev`を指していることを確認する。
5. `gh auth status`でGitHub CLIの認証を確認する。
6. `main`を`git pull --ff-only origin main`で最新化する。
7. 作業ごとに新しい`codex/<task-name>`ブランチを作る。
8. 実装後に確認結果をPull Requestへ記載する。
9. Pull Request作成後はマージせず、ユーザーの確認を待つ。

## 9. 次回作業候補

Phase 0のための最小プロジェクト構成を作成する。

- Frontend: React + TypeScript + Viteの最小構成
- Backend: FastAPIの最小構成
- `GET /api/health`
- Codex App Server子プロセスの起動と`initialize` / `initialized`
- `account/read`による認証状態取得
- 最小のThread/Turn実行
- Agent MessageをSSEでブラウザへ配信
- 入力、送信、実行中、回答、エラーだけを持つ簡単なChat UI

このPhaseでRepository登録、Viewer生成、PostgreSQLテーブル群まで作り込まない。
