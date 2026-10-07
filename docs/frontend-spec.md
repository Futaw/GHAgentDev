# RepoSpec Viewer フロントエンド仕様

- 文書バージョン: v0.2
- 更新日: 2026-10-08
- 対象: React + TypeScript + Vite
- ステータス: 概要設計

本文書では画面の役割、主要状態、画面遷移、API利用方針までを定義する。ピクセル単位のデザイン、全コンポーネントのProps、文言の最終確定は対象Phaseで行う。

用語の意味は[フロントエンド用語解説集](./frontend-glossary.md)を参照する。

## 1. 責務

フロントエンドは、Repositoryの登録・同期・削除、Viewerの生成条件入力、生成進捗の可視化、HTML仕様書の閲覧、Viewerに対する追加質問を担当する。

ブラウザはCodex App ServerやGitを直接操作しない。フロントエンドの外部通信先はFastAPIに限定する。

## 2. 技術構成

| 用途 | 採用技術 |
|---|---|
| UI | React, TypeScript |
| Build | Vite |
| Routing | React Router |
| Server state | TanStack Query |
| Form | React Hook Form + Zodを第一候補 |
| Code display | Monaco EditorまたはShiki系ビューア |
| HTML sanitization | DOMPurifyを多層防御として使用 |
| Test | Vitest, React Testing Library, Playwright |

UIライブラリは未確定とし、画面から直接ライブラリ固有APIを多用せず、`components/ui`層で吸収する。

## 3. 情報設計とルーティング

| Route | 画面 | 提供フェーズ |
|---|---|---|
| `/login` | Codex認証 | Phase 0 |
| `/chat` | 最小チャット検証画面 | Phase 0 |
| `/repositories` | Repository一覧 | Phase 1 |
| `/repositories/new` | Repository登録 | Phase 1 |
| `/repositories/:repositoryId` | Repository Dashboard | Phase 1 |
| `/repositories/:repositoryId/viewers/new` | Viewer作成 | Phase 2 |
| `/jobs/:jobId` | 生成進捗 | Phase 2 |
| `/viewers/:viewerId` | Viewer閲覧 + Q&A | Phase 2/3 |

認証前の保護Routeへのアクセスは`/login`へ戻す。ただし、一時的な認証状態取得失敗は未認証と同一視せず、「再試行」を表示する。

## 4. Phase 0: 最小チャット

### 4.1 Login画面

表示要素:

- プロダクト名
- Codex利用にChatGPT認証が必要であることの説明
- `ChatGPTでログイン`ボタン
- 認証状態: `checking | unauthenticated | authenticating | authenticated | expired | error`
- ログインキャンセル
- エラーと再試行導線

挙動:

1. 画面表示時に認証状態を取得する。
2. ログイン開始APIから受け取った`auth_url`を新しいタブまたはポップアップで開く。
3. 画面はログイン結果イベントを待つ。ポップアップが閉じられた場合も状態を再確認する。
4. 認証成功後は`/chat`へ遷移する。

### 4.2 Chat画面

Phase 0では以下だけを実装する。

- ユーザーメッセージ一覧
- Codex回答一覧
- テキスト入力
- 送信ボタン
- 実行中インジケータ
- 中止ボタン
- エラーと再送信
- App Server接続状態

不要なもの:

- Markdownの高度な装飾
- チャット検索
- 複数Conversation管理UI
- ファイル添付
- モデル選択UI
- 承認ダイアログ

MVPは読み取り専用・承認不要のポリシーで実行し、App Serverから予期しない承認要求が届いた場合はバックエンドが拒否し、画面に実行エラーを表示する。

### 4.3 ストリーミング表示

SSEイベントはバックエンドの内部JSON-RPCをそのまま表示せず、以下のUI向けイベントに変換する。

| Event | UIの処理 |
|---|---|
| `turn.started` | 実行中表示に切り替える |
| `message.delta` | 現在のAssistant Messageの末尾へ追記する |
| `activity.started` | 安全に表示できる作業概要を進捗欄へ追加する |
| `activity.completed` | 対応する作業を完了表示にする |
| `turn.completed` | 入力を再度有効化する |
| `turn.failed` | 復帰可能なエラーと再試行を表示する |
| `heartbeat` | 接続維持にのみ使用し、画面には表示しない |

モデルの非公開の推論内容はUIに表示しない。進捗表示は、Turn状態、計画の公開更新、Itemの開始/完了など、表示用に変換された事実ベースのイベントに限定する。

## 5. Phase 1: Repository画面

### 5.1 Repository一覧

表示項目:

- Repository名
- GitHub URL
- Default Branch
- Commit SHAの短縮表示
- 最終同期日時
- Viewer数
- Clone/Sync状態

状態は`pending | cloning | ready | syncing | failed`を識別できる表示にする。

### 5.2 Repository登録

- URLは必須
- `https://github.com/{owner}/{repository}`形式のみ受け付ける
- ブラウザ側検証は利便性向上のために行い、正式な判定はバックエンドの応答に従う
- 登録後はRepository Dashboardへ遷移する

### 5.3 Repository Dashboard

- Repositoryの基本情報
- `最新コードを取得`ボタン
- `Repositoryを削除`ボタン
- `Viewerを作成`ボタン
- Viewer一覧
- Clone/Sync失敗時の詳細と再試行

### 5.4 Repository削除

- 削除操作はRepository Dashboardの危険操作領域にだけ表示し、一覧画面には置かない。
- `Repositoryを削除`を押すと確認ダイアログを開く。
- ダイアログには、アプリの登録情報とローカルの管理Workspaceが削除され、GitHub上のRepositoryは削除されないことを明記する。
- CloneまたはSync中、およびViewerなどの関連データが存在する場合は削除ボタンを無効化する。
- 削除できない理由と、関連データを先に削除する必要があることをボタン付近に表示する。
- 削除成功後はRepository一覧へ遷移し、完了メッセージを表示する。
- 削除失敗時はDashboardと確認ダイアログを維持し、再試行できるエラーを表示する。

## 6. Phase 2: Viewer作成と閲覧

### 6.1 Viewer作成フォーム

| 項目 | 種別 | 初期値 |
|---|---|---|
| Document Type | select | `functional_spec` |
| Detail Level | select | `standard` |
| Target Audience | select | `engineer` |
| Theme | select + preview | `technical-light` |
| Request | textarea, required | なし |
| Additional Instruction | textarea, optional | なし |

送信成功時はGeneration Jobを作成し、`/jobs/:jobId`へ遷移する。二重送信を防止し、バックエンドのvalidation errorを各項目へ対応づけて表示する。

### 6.2 Generation Progress

- Job全体の状態: `queued | running | completed | failed | cancelled`
- 現在のフェーズ
- 完了済みフェーズ
- 安全に表示できる対象ファイルパス
- 開始日時と経過時間
- 中止
- 失敗理由と再試行

完了イベント受信後はViewerへ自動遷移できる。自動遷移しない場合にも`Viewerを開く`導線を残す。

### 6.3 Viewer画面

Desktopでは主領域と右ペインの2カム構成とする。

```text
+----------------------------------------------------------------+
| Viewer Header                                                  |
+-------------------------------------------+--------------------+
| HTML Document                             | Ask Codex          |
| 目次 / 本文 / 表 / コード / 参照         | Conversation       |
|                                           | Input              |
+-------------------------------------------+--------------------+
```

MobileではチャットをDrawerまたは別タブに切り替える。Viewer Headerにはタイトル、Repository、Branch、Commit SHA、文書種別、詳細度、対象読者、テーマ、作成日時を表示する。

主要操作:

- 再生成
- テーマ変更
- 削除
- GitHubを開く
- 右ペインの開閉

### 6.4 HTML表示の安全性

- バックエンドで作成・サニタイズされたHTMLだけを表示する
- フロントエンドでDOMPurifyを追加適用する
- `script`, `style`, `iframe`, `object`, `embed`, form系要素、`on*`イベント属性は許可しない
- テーマはアプリが持つCSS class/CSS variablesで適用する
- 外部リンクは別タブで開き、`noopener noreferrer`を付与する
- Repository内ソース参照は通常のHTMLリンクではなく、構造化参照IDからアプリ内操作に変換する

## 7. Phase 3: Viewer内Q&AとSource Code Viewer

### 7.1 Ask Codex

- Viewerを開いた時に過去Messageを取得する
- 質問はViewerとその生成元Commitに紐づける
- 回答本文とソース参照を別々の要素として表示する
- 回答中もViewer本文のスクロールと閲覧を妨げない
- 新しいRepository Commitが存在する場合は、質問対象がViewer Commitであることを明示する

### 7.2 Source Code Viewer

- Repository内相対パス
- Commit SHA
- 行番号
- シンタックスハイライト
- 参照範囲の強調
- 指定行への自動スクロール
- GitHub上の対応するCommit/行への導線

パスに`..`や絶対パスを含む参照は表示要求を送信しない。最終的なパス検証はバックエンドが行う。

## 8. 状態管理

### 8.1 TanStack Queryで管理する状態

- 認証状態
- Repository一覧・詳細
- Viewer一覧・詳細
- Theme一覧
- Conversation履歴
- Generation Job状態

### 8.2 ローカルUI state

- Form入力中の値
- Drawer/Dialogの開閉
- Viewerの目次選択
- Source Code Viewerの選択範囲
- ストリーミング中の未確定テキスト

SSEで受信したデルタはキャッシュに直接混ぜず、ストリーム完了後に正式データを再取得してTanStack Queryのキャッシュを更新する。

## 9. APIクライアント方針

- OpenAPIからTypeScript型を生成する
- `fetch` wrapperでBase URL、JSON parse、Problem Details形式のエラーを統一処理する
- mutationは二重送信を防止する
- 自動再試行はGETと安全な接続復旧に限定する
- POSTの再試行にはIdempotency Keyを使う
- SSEはEvent IDを保持し、再接続で`Last-Event-ID`を送信する

## 10. エラー表示

| 種別 | UI |
|---|---|
| 入力不備 | 対象項目直下に表示 |
| 認証切れ | 作業中の入力を可能な限り保持してログイン導線を表示 |
| App Server停止 | 接続エラーと再接続を表示 |
| 利用上限 | 一般エラーと区別し、時間を置いて再試行するよう案内 |
| SSE切断 | 自動再接続中と表示し、失敗時はJob/Turn状態をRESTで再取得 |
| Generation失敗 | 保存済み条件での再試行を提供 |
| 削除失敗 | Viewerを一覧から消さずエラーを表示 |
| Repository削除失敗 | Dashboardを維持し、GitHub上のRepositoryは変更されていないことを伝えて再試行を案内 |

## 11. アクセシビリティとレスポンシブ

- 全ての操作はキーボードで実行可能にする
- ストリーミング更新は`aria-live="polite"`を使い、デルタごとの過剰な読み上げを防ぐ
- 進捗は色だけでなく文字とアイコンで区別する
- Dialogは開いたときにfocusを移し、閉じたときに元の操作へ戻す
- 768px未満ではViewerとChatを同時に固定表示しない

## 12. テスト方針

### Unit / Component

- ログイン状態ごとの表示
- Viewer作成フォームのvalidation
- SSE event reducerの順序性と重複排除
- ソース参照のパス検証
- Theme切り替え
- Repository削除の確認、キャンセル、成功、失敗

### E2E

1. 認証済み状態からチャット送信し、逐次回答を表示できる。
2. Repositoryを登録し、Clone完了後にDashboardを表示できる。
3. Viewerを生成し、進捗画面から生成済みViewerへ遷移できる。
4. Viewerへ質問し、参照をクリックしてSource Code Viewerを開ける。
5. Repository削除を確認すると一覧へ戻り、キャンセルするとDashboardに留まる。

## 13. 想定ディレクトリ

```text
src/
  app/
    router/
    providers/
  components/
    ui/
    layout/
  features/
    auth/
    chat/
    repositories/
    generation/
    viewers/
    source-code/
  lib/
    api/
    sse/
    validation/
  styles/
    themes/
  test/
```
