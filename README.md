# RepoSpec Viewer

GitHub RepositoryのソースコードをCodex App Serverで調査し、読みやすい仕様書として閲覧するためのWebアプリです。現在はPhase 0として、React → FastAPI → Codex App Serverの接続と最小チャットを実装しています。

## Phase 0で利用できる機能

- FastAPI起動時の`codex app-server`子プロセス起動と再接続
- ChatGPT認証状態の確認、ブラウザログイン、キャンセル、ログアウトAPI
- 読み取り専用WorkspaceでのThread/Turn開始
- Agent MessageのSSEストリーミング
- Turnの完了、失敗、中止表示
- App Server停止時の診断と自動再初期化

Repository登録、PostgreSQL永続化、Viewer生成はPhase 1以降で追加します。

## 必要な環境

- Python 3.12以上
- Node.js 24
- Codex CLI（`codex`コマンド）
- Codex CLIで利用可能なChatGPTアカウント

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
npm --prefix frontend install
```

`.env`の`TEST_CHAT_WORKSPACE`には、Codexが読み取り可能なテスト用ディレクトリを指定します。Phase 0のTurnは`approvalPolicy: never`、`readOnly` sandbox、network無効で実行されます。現在のローカルCLI schemaでは読み取りルートの追加制限を指定できないため、Phase 0は信頼できるローカル・単一ユーザー環境だけで使用してください。

## 起動

ターミナルを2つ開いて、それぞれ次を実行します。

```bash
source .venv/bin/activate
uvicorn backend.app.main:app --reload
```

```bash
npm --prefix frontend run dev
```

ブラウザで`http://localhost:5173`を開きます。API仕様は`http://127.0.0.1:8000/docs`で確認できます。

## テスト

```bash
source .venv/bin/activate
pytest
npm --prefix frontend test
npm --prefix frontend run build
```

Codex App ServerとのJSONL結合テストはfake app-serverを使用するため、ChatGPT認証や外部通信なしで実行できます。

## 仕様書

- [概要仕様](./docs/README.md)
- [バックエンド仕様](./docs/backend-spec.md)
- [フロントエンド仕様](./docs/frontend-spec.md)
