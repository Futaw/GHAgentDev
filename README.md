# RepoSpec Viewer

GitHub RepositoryのソースコードをCodex App Serverで調査し、読みやすい仕様書として閲覧するためのWebアプリです。Phase 0のReact → FastAPI → Codex App Server接続と最小チャット、およびPhase 1のPublic GitHub Repository管理を実装しています。

## 利用できる機能

- FastAPI起動時の`codex app-server`子プロセス起動と再接続
- ChatGPT認証状態の確認、ブラウザログイン、キャンセル、ログアウトAPI
- 読み取り専用WorkspaceでのThread/Turn開始
- Agent MessageのSSEストリーミング
- Turnの完了、失敗、中止表示
- App Server停止時の診断と自動再初期化
- Public GitHub Repository URLの登録、正規化、重複防止
- 管理Workspaceへの非同期Cloneと状態表示
- Repository一覧、Dashboard、最新コードの取得
- Default Branch、Commit SHA、最終同期日時のPostgreSQL保存
- 容量・ファイル数・timeout制限とRepository単位の排他制御

Viewer生成はPhase 2で追加します。

## 必要な環境

- Python 3.12以上
- Node.js 24
- Codex CLI（`codex`コマンド）
- Codex CLIで利用可能なChatGPTアカウント
- PostgreSQL

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
npm --prefix frontend install
```

`.env`の`DATABASE_URL`に作成済みPostgreSQL Databaseの接続先を、`TEST_CHAT_WORKSPACE`にはCodexが読み取り可能なテスト用ディレクトリを指定します。Phase 0のTurnは`approvalPolicy: never`、`readOnly` sandbox、network無効で実行されます。現在のローカルCLI schemaでは読み取りルートの追加制限を指定できないため、信頼できるローカル・単一ユーザー環境だけで使用してください。

初回起動時とschema更新時はMigrationを明示的に実行します。アプリ起動時には自動Migrationしません。

```bash
source .venv/bin/activate
alembic upgrade head
```

## 起動

ターミナルを2つ開いて、それぞれ次を実行します。

```bash
source .venv/bin/activate
uvicorn backend.app.main:app --reload --workers 1
```

```bash
npm --prefix frontend run dev
```

ブラウザで`http://localhost:5173`を開きます。API仕様は`http://127.0.0.1:8000/docs`で確認できます。

## テスト

```bash
source .venv/bin/activate
pytest
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

BackendテストはSQLiteとローカルbare Git Repositoryをtest seamとして使用します。Codex App ServerとのJSONL結合テストはfake app-serverを使用するため、ChatGPT認証や外部通信なしで実行できます。PostgreSQL用Migrationは`alembic upgrade head --sql`でも確認できます。

## 仕様書

- [概要仕様](./docs/README.md)
- [バックエンド仕様](./docs/backend-spec.md)
- [フロントエンド仕様](./docs/frontend-spec.md)
- [Phase 1 詳細設計書](./docs/phase-1-detailed-design.md)
