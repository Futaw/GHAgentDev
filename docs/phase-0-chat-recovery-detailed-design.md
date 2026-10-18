# RepoSpec Viewer Phase 0 Chat進捗・セッション復帰 詳細設計書

- 文書バージョン: v1.0
- 更新日: 2026-10-19
- ステータス: 詳細設計案・実装前
- 対象Phase: Phase 0「Codex接続と最小チャット」の品質改善

本文書は、[概要仕様](./README.md)、[フロントエンド仕様](./frontend-spec.md)、[バックエンド仕様](./backend-spec.md)で定めたPhase 0 Chatについて、進捗表示、画面遷移後の復帰、Session作成失敗時の扱いを具体化する。本文書と上位仕様が矛盾する場合は、Phase 0 Chatの範囲に限り本文書を優先する。

## 1. 背景と目的

現在のChat画面は、質問送信後に送信ボタンを中止ボタンへ切り替える。一方、回答が始まるまでの状態や経過時間を十分に表示していないため、処理が継続しているかを利用者が判断しにくい。

また、ChatのSession ID、Turn ID、メッセージ、SSE接続をChat画面内で管理している。回答中にRepository画面へ移動すると、ブラウザ側の状態とSSE接続が失われる。Chat画面へ戻った際には新しいSessionの作成を試みるため、元のTurnへ復帰できない。

Session作成が失敗した場合は、画面の再描画を契機に自動試行を繰り返す可能性もある。利用者には「セッションを準備しています」と表示され続け、失敗理由と再試行方法が伝わらない。

この改善では、次の状態を実現する。

- 質問受付から回答完了まで、現在の処理段階と経過時間を確認できる
- 回答中に別画面へ移動しても処理を継続し、Chatへ戻ったときに同じSessionとTurnを表示する
- ブラウザを再読み込みしても、バックエンドが保持しているSessionへ復帰する
- Session作成が失敗した場合は自動試行を止め、理由と再試行操作を表示する
- Codex接続エラーとrequest timeoutを区別し、機密情報を残さずバックエンドログで追跡できる

## 2. 現在の設計からの変更点

| 項目 | 現在 | 改善後 |
|---|---|---|
| Chatの対象 | `TEST_CHAT_WORKSPACE` | 変更しない。Repository登録数に依存しない |
| Frontendの状態 | `ChatPage`内のlocal state | `ChatSessionProvider`が画面遷移をまたいで保持する |
| 画面再読み込み | 新しいSessionを作成 | `sessionStorage`のSession IDからsnapshotを取得する |
| 回答中の画面移動 | SSEを閉じ、Turn情報を失う | ProviderがSSEとTurn情報を維持する |
| Session作成失敗 | 再描画後に再試行する可能性がある | 自動試行は1回で止め、利用者の再試行を待つ |
| 進捗 | 中止ボタンと回答欄のプレースホルダー | 処理段階、経過時間、接続状態を専用領域に表示する |
| SSE復帰 | 同じ`EventSource`の自動再接続だけ | Session snapshotとevent cursorから新しい接続も再開できる |
| エラー表示 | 固定文言 | `Problem Details`のcodeに応じた説明と操作を表示する |
| 503のログ | HTTP access logが中心 | operation、code、trace ID、安全な失敗理由を記録する |

今回の改善では、Phase 0 Chatを登録済みRepositoryへ紐づけない。RepositoryまたはViewerを対象とする会話はPhase 3で別に実装する。

## 3. 対象と対象外

### 3.1 対象

- ChatのSession作成、復帰、明示的な再試行
- 同一ブラウザタブ内のSession ID保持
- Repository画面とChat画面の間を移動した場合の状態維持
- ブラウザ再読み込み後のSession snapshot取得
- 実行中TurnへのSSE再接続
- 進捗段階、経過時間、遅延案内、接続状態の表示
- Session作成失敗とTurn失敗のエラー表示
- 失敗したSessionをバックエンドのメモリへ残さない処理
- 503応答の安全な診断ログ
- Frontend、Backend、手動テスト

### 3.2 対象外

- Chat Session、Turn、MessageのPostgreSQL保存
- ブラウザや端末をまたいだChatの共有
- 複数タブ間のSession同期
- 複数Conversationの一覧、選択、削除
- RepositoryまたはViewerを選択するPhase 3のConversation
- Codexの完了予定時刻の予測
- モデルの非公開の推論内容の表示
- Phase 2 Generation Jobの進捗設計変更

FastAPIを再起動するとPhase 0のSessionは失われる。この場合、Frontendは古いSession IDを破棄して新しいSessionを1回だけ作成する。Chatの永続化はPhase 3で扱う。

## 4. 前提条件

### 4.1 Repository登録との関係

Phase 0 Chatは`TEST_CHAT_WORKSPACE`を読み取り専用で調査する。`repositories`テーブルと管理Workspaceを参照しないため、登録済みRepositoryが0件でも利用できる。

画面には「設定されたテスト用Workspaceが対象であり、登録済みRepositoryを選択する画面ではない」ことを表示する。Repositoryが0件であることを理由に、Chat入力欄やSession作成を無効にしない。

### 4.2 Sessionの保持範囲

ブラウザは同一タブにつき1件のPhase 0 Chat Sessionを保持する。Session IDだけを`sessionStorage`へ保存し、メッセージ本文、Codex Thread ID、認証情報は保存しない。

保存keyは次の値とする。

```text
repospec.phase0.chat-session-id
```

`sessionStorage`は同一タブの再読み込みに使用する。Repository画面とChat画面の移動中は、Reactの`ChatSessionProvider`が状態とSSE接続を保持する。

## 5. 状態設計

### 5.1 Session状態

FrontendはSessionの準備状態を次の値で管理する。

| 状態 | 意味 | 入力欄 |
|---|---|---|
| `uninitialized` | Chatをまだ開いていない | 非表示または無効 |
| `preparing` | 保存済みSessionの復帰または新規作成中 | 無効 |
| `ready` | 質問を送信できる | Turnがなければ有効 |
| `failed` | Sessionの復帰または作成に失敗 | 無効、再試行を表示 |

`failed`から`preparing`へ移るのは、利用者が再試行を押した場合だけとする。画面の再描画、Health polling、Repository一覧の再取得を理由に自動で再試行しない。

### 5.2 Turn状態

| 状態 | 意味 | 主な表示 |
|---|---|---|
| `idle` | 実行中Turnなし | 入力可能 |
| `submitting` | Message送信HTTPの応答待ち | `質問を送信しています` |
| `queued` | `202 Accepted`受信後、`turn.started`待ち | `質問を受け付けました` |
| `running` | CodexがTurnを実行中 | 現在の進捗段階 |
| `reconnecting` | 実行中にSSEが切断 | `進捗表示へ再接続しています` |
| `completed` | Turn完了 | 回答を表示し、入力を再度有効化 |
| `failed` | Turn失敗 | 公開可能な理由と再送信を表示 |
| `cancelled` | 利用者またはシステムが中止 | 中止済みと表示し、入力を有効化 |

`submitting`ではTurn IDがまだないため中止APIを呼ばない。`queued`、`running`、`reconnecting`ではTurn IDがあるため中止ボタンを表示する。

### 5.3 進捗段階

進捗段階は、モデルの推論内容ではなく、アプリが確認できた事実から決める。

| 段階 | 表示文言 | 遷移契機 |
|---|---|---|
| `accepted` | 質問を受け付けました | Message送信APIが`202`を返した |
| `starting` | Codexの処理を開始しています | `turn.started`を受信した |
| `investigating` | Workspaceを調査しています | 安全に公開できるactivityを受信した |
| `answering` | 回答を作成しています | 最初の`message.delta`を受信した |
| `reconnecting` | 進捗表示へ再接続しています | SSE接続が切断された |

画面はTurn開始からの経過時間を1秒単位で更新する。30秒を超えた場合は「通常より時間がかかっています。処理は継続中です。」と補足する。完了時刻はCodexの処理内容によって変わるため、予測値を表示しない。

## 6. 主要フロー

### 6.1 初回のChat表示

```mermaid
sequenceDiagram
    actor User
    participant Page as ChatPage
    participant Provider as ChatSessionProvider
    participant API as FastAPI
    participant Codex as Codex App Server

    User->>Page: Chatを開く
    Page->>Provider: ensureSession
    Provider->>Provider: sessionStorageを確認
    Provider->>API: POST /api/chat/sessions
    API->>Codex: thread/start
    Codex-->>API: thread
    API-->>Provider: 201 Session snapshot
    Provider->>Provider: Session IDだけを保存
    Provider-->>Page: ready
```

Session作成要求は1回だけ送る。失敗した場合は`failed`へ遷移し、自動で同じPOSTを繰り返さない。

### 6.2 質問送信と進捗表示

```mermaid
sequenceDiagram
    actor User
    participant Page as ChatPage
    participant Provider as ChatSessionProvider
    participant API as FastAPI
    participant Codex as Codex App Server

    User->>Page: 質問を送信
    Page->>Provider: submit
    Provider->>API: POST /chat/sessions/{id}/messages
    API-->>Provider: 202 + turn_id + events_url
    Provider-->>Page: accepted + 経過時間
    Provider->>API: EventSource
    API->>Codex: turn/start
    Codex-->>API: activity / message delta / completed
    API-->>Provider: 正規化したSSE
    Provider-->>Page: 進捗段階と回答を更新
```

### 6.3 回答中の画面移動

`ChatSessionProvider`は認証後の共通Layout内に配置し、子Routeの外側で維持する。ChatからRepositoriesへ移動してもProviderとEventSourceを破棄しない。

Chatへ戻った場合はProviderが保持するSession、Turn、Messageをそのまま表示する。新しいSessionを作成せず、実行中Turnを重複送信しない。

### 6.4 ブラウザ再読み込み後の復帰

```mermaid
sequenceDiagram
    actor User
    participant Provider as ChatSessionProvider
    participant API as FastAPI

    User->>Provider: Chatを再読み込み
    Provider->>Provider: sessionStorageからSession IDを取得
    Provider->>API: GET /api/chat/sessions/{id}
    API-->>Provider: Session snapshot
    Provider->>Provider: MessageとTurn状態を復元
    alt active_turnあり
        Provider->>API: SSEへcursor付きで接続
        API-->>Provider: cursorより後のEvent
    else active_turnなし
        Provider-->>User: 入力可能なChatを表示
    end
```

`GET /api/chat/sessions/{id}`が`404`を返した場合は、FastAPI再起動によってSessionが失われたものとして保存済みIDを削除する。その後、新しいSessionを1回だけ作成する。

`503`、`502`、通信失敗の場合は保存済みIDを削除しない。エラーを表示し、利用者の再試行時に同じSessionの取得からやり直す。

## 7. API設計

### 7.1 Session snapshot

`POST /api/chat/sessions`と`GET /api/chat/sessions/{session_id}`は、同じ`ChatSessionSnapshot`を返す。

```json
{
  "id": "session-uuid",
  "status": "running",
  "created_at": "2026-10-19T01:00:00Z",
  "messages": [
    {
      "id": "message-uuid",
      "role": "assistant",
      "content": "登録処理では",
      "status": "streaming",
      "created_at": "2026-10-19T01:00:05Z"
    }
  ],
  "active_turn": {
    "turn_id": "turn-uuid",
    "status": "running",
    "events_url": "/api/turns/turn-uuid/events",
    "started_at": "2026-10-19T01:00:04Z",
    "last_event_id": 4,
    "progress": {
      "stage": "investigating",
      "label": "Workspaceを調査しています"
    }
  }
}
```

`status`は`idle | queued | running`とする。`active_turn`は実行中Turnがない場合に`null`とする。完了、失敗、中止したTurnは`messages`へ反映し、`active_turn`には含めない。

既存の`GET /api/chat/sessions/{session_id}/messages`は互換性のため残す。Frontendの復帰処理は、状態の不整合を避けるためSession snapshotを使用する。

### 7.2 SSE再開位置

Turn SSEは次の2種類の再開位置を受け付ける。

```http
GET /api/turns/{turn_id}/events?after=4
Last-Event-ID: 4
```

新しい`EventSource`を作る復帰処理では`after` queryを使う。同じ`EventSource`が自動再接続する場合はブラウザが送る`Last-Event-ID`を使う。両方がある場合は大きい値を採用し、処理位置を巻き戻さない。

EventBufferが保持する最古のEventより古い位置を指定された場合でも、FrontendはSession snapshotのメッセージを基準に表示を再構築できる。MVPではEventBufferの欠落専用エラーを追加しない。

### 7.3 回答Eventの冪等性

`message.delta`には差分と、そのEvent時点の累積回答を含める。

```json
{
  "turn_id": "turn-uuid",
  "message_id": "message-uuid",
  "delta": "次の処理です。",
  "content": "登録処理は次の処理です。",
  "sequence": 5,
  "occurred_at": "2026-10-19T01:00:08Z"
}
```

Frontendは`content`でAssistant Messageを置き換える。`delta`の単純追記だけに依存しないため、SSE Eventが再送されても回答を重複させない。

### 7.4 進捗Event

BackendはCodex App ServerのItemを、そのままFrontendへ渡さない。公開可能な種類だけをアプリ内の進捗へ変換する。

```json
{
  "turn_id": "turn-uuid",
  "stage": "investigating",
  "label": "Workspaceを調査しています",
  "sequence": 3,
  "occurred_at": "2026-10-19T01:00:07Z"
}
```

未知のItem type、コマンド全文、ローカル絶対パス、モデルのreasoningは進捗Eventへ含めない。安全な対応表にないItemは画面表示を更新せず、Turn全体は継続する。

### 7.5 エラー応答

| HTTP | code | 画面の扱い |
|---:|---|---|
| `404` | `RESOURCE_NOT_FOUND` | 保存済みSession IDを削除し、新規作成を1回だけ試す |
| `409` | `TURN_CONFLICT` | snapshotを再取得し、実行中Turnへ復帰する |
| `502` | `CODEX_TURN_FAILED` | Codex要求の失敗を表示し、明示的な再試行を待つ |
| `503` | `CODEX_UNAVAILABLE` | App Serverへ接続できないことを表示し、明示的な再試行を待つ |
| `504` | `CODEX_TIMEOUT` | Codex要求が時間内に応答しなかったことを表示し、明示的な再試行を待つ |
| 通信失敗 | `NETWORK_ERROR` | Backend接続を確認する案内と再試行を表示する |

Frontendは`Problem Details.detail`を基本文言として表示し、`code`に応じて次の操作を決める。原因をログと照合できるよう、`trace_id`を問い合わせ用IDとしてエラー領域へ表示する。APIが返した未知のHTMLを描画せず、文字列として表示する。

## 8. Frontend設計

### 8.1 コンポーネント構成

```text
frontend/src/features/chat/
  ChatSessionProvider.tsx
  ChatPage.tsx
  ChatProgress.tsx
  chatApi.ts
  chatReducer.ts
  chatTypes.ts
```

責務は次のように分ける。

| 対象 | 責務 |
|---|---|
| `ChatSessionProvider` | Sessionの準備・復帰、Turn、Message、SSE、sessionStorageを管理 |
| `ChatPage` | Message一覧、入力欄、送信・中止・再試行操作を表示 |
| `ChatProgress` | 進捗段階、経過時間、遅延案内、再接続状態を表示 |
| `chatApi` | REST DTO、`ApiError`、SSE URLをアプリ内型へ変換 |
| `chatReducer` | SessionとTurnの状態遷移、累積回答によるMessage更新 |

Providerは認証済みLayoutの内側、子Routeの外側へ配置する。Chatを一度も開いていない場合はSessionを作らず、`ChatPage`から`ensureSession()`が呼ばれた時点で初期化する。

### 8.2 Session初期化の多重実行防止

Sessionの初期化は、Reactの再描画回数ではなく、Providerが保持する状態と同一Promiseで制御する。

- `preparing`中に`ensureSession()`が呼ばれた場合は同じ処理を待つ
- `ready`の場合はAPIを呼ばない
- `failed`の場合は自動で呼び直さない
- 再試行ボタンは処理中に無効化する
- React Strict ModeでEffectが再評価されても、同じPOSTを二重送信しない

TanStack QueryのMutation再試行は無効にする。ChatのSession作成は副作用を伴うため、Queryの一般的な自動再試行へ委ねない。

### 8.3 画面表示

実行中はMessage一覧の末尾だけでなく、入力欄の直上へ進捗領域を表示する。

```text
Workspaceを調査しています
経過時間 00:18
[中止]
```

30秒を超えた場合は、同じ領域へ遅延案内を追加する。入力欄は実行中に無効化するが、状態文言と中止ボタンは常に操作可能な位置に残す。

進捗領域は`role="status"`と`aria-live="polite"`を使う。経過時間の1秒ごとの更新はスクリーンリーダーへ毎回読み上げさせず、進捗段階が変わった場合だけ通知する。

### 8.4 画面移動と終了

子Routeの移動ではTurnを中止しない。Providerが残るためSSEも維持する。

ブラウザタブを閉じた場合も、自動で中止APIを送らない。`beforeunload`の通信は成功が保証されず、意図しない中止にもなるためである。FastAPIが動作している間はTurnが完了し、同じタブを復元できる場合はsnapshotから結果を取得する。

## 9. Backend設計

### 9.1 Session作成の整合性

Chat Sessionは`thread/start`が成功してから公開する。`thread/start`より前に一時オブジェクトを作る場合でも、失敗時はSession辞書とThread対応表へ残さない。

処理順は次のとおりとする。

1. 未公開のSessionオブジェクトを作成する。
2. Codex App Serverへ`thread/start`を送る。
3. 成功したThread IDをSessionへ設定する。
4. Session辞書とThread対応表へ登録する。
5. `201 Created`を返す。

同じHTTP要求が失敗しても、到達できないSessionをメモリへ蓄積しない。

### 9.2 Session snapshot

snapshot作成中にMessage本文とevent cursorの対応がずれないよう、Chat Service内で一貫した状態を読み取る。通知によるMessage更新、進捗更新、Event発行も同じ更新単位で扱う。

累積回答を`message.delta.content`へ含めるため、BackendはAssistant Message更新後の本文をEventへ設定する。Frontendは累積回答を正として置き換えるため、同じEventの再送に対して冪等になる。

### 9.3 App Server切断

App Serverが切断された場合、実行中Turnを`failed`へ変更し、`turn.failed`をEventBufferへ保存する。SessionのCodex Thread IDは破棄するが、Session、Message、失敗状態は保持する。

App Server再接続後に利用者が同じ内容を再送信した場合は、新しい一時Threadを作成してからTurnを開始する。

### 9.4 診断ログ

Codex接続エラーまたはrequest timeoutをHTTPエラーへ変換する際は、次の項目をwarning levelで記録する。

- `operation`: `chat.session.create`などの固定値
- `problem_code`: `CODEX_UNAVAILABLE`または`CODEX_TIMEOUT`
- `trace_id`
- 失敗分類: unavailable、process exited、request timeout
- timeoutの場合はJSON-RPC method

request timeoutは接続断と区別し、`504 / CODEX_TIMEOUT / retryable: true`へ変換する。Codex App Serverのプロセス停止や接続不能は`503 / CODEX_UNAVAILABLE / retryable: true`とする。

ログへ次の情報を含めない。

- access token、refresh token、Authorization header
- Codex認証保存先
- User Message本文、Assistant Message本文
- `TEST_CHAT_WORKSPACE`の絶対パス
- Codex App Serverのstderr全文

API応答は現在の一般化した日本語文言を維持する。内部例外の全文をブラウザへ返さない。

## 10. テスト設計

### 10.1 Frontend component test

- Chat初回表示でSession作成POSTが1回だけ送信される
- React Strict ModeでもSessionを二重作成しない
- Session作成が503の場合に自動再試行せず、説明と再試行ボタンを表示する
- 再試行ボタンを押した場合だけ2回目の要求を送る
- Repository画面へ移動して戻ってもSession IDとMessageを維持する
- 回答中の画面移動でEventSourceを閉じず、Chatへ戻ると進捗を表示する
- `sessionStorage`のSession IDからsnapshotを復元する
- snapshotが404の場合にIDを削除し、新しいSessionを1回だけ作成する
- snapshotが503の場合はIDを維持してエラーを表示する
- `after` cursor付きでSSEへ接続する
- 同じ`message.delta`を複数回受信しても累積回答が重複しない
- accepted、starting、investigating、answering、reconnectingを表示する
- 30秒経過後に遅延案内を表示する
- 完了、失敗、中止後に入力欄を再度有効化する
- IME、通常Enter、Shift + Enter、送信ボタンの既存テストが継続して成功する

### 10.2 Backend unit / integration test

- `thread/start`失敗時にSession辞書とThread対応表へデータを残さない
- Session snapshotがMessage、active Turn、進捗、event cursorを返す
- idle Sessionの`active_turn`が`null`になる
- `after` queryより後のEventだけを返す
- `after`と`Last-Event-ID`の大きい値を採用する
- `message.delta`が差分と累積回答を返す
- 同じEventの再送でFrontendが重複しない契約になっている
- 未知のCodex Itemやreasoningを進捗Eventへ出さない
- App Server切断時に実行中Turnを失敗へ変更する
- Codex接続失敗が`503 / CODEX_UNAVAILABLE / retryable: true`になる
- request timeoutが`504 / CODEX_TIMEOUT / retryable: true`になる
- 503と504のログにtrace IDと分類があり、Message本文と絶対パスがない

### 10.3 手動テスト

- Repositoryが0件の状態でPhase 0 Chatを利用できる
- 質問受付直後から進捗段階と経過時間が表示される
- 回答中にRepositoriesへ移動し、Chatへ戻って同じTurnの進捗または結果を確認できる
- 回答中にブラウザを再読み込みし、同じSessionへ復帰できる
- App Server接続失敗時に準備中表示が続かず、エラーと再試行を確認できる
- エラー中にSession作成POSTが繰り返されない
- App Server復旧後、再試行操作でChatを利用できる

## 11. 実装対象ファイル

主な変更対象は次のとおりとする。実装中に責務を保ったままファイルを分割することは許容する。

```text
frontend/src/app/AppLayout.tsx
frontend/src/features/chat/ChatSessionProvider.tsx
frontend/src/features/chat/ChatPage.tsx
frontend/src/features/chat/ChatProgress.tsx
frontend/src/features/chat/chatApi.ts
frontend/src/features/chat/chatReducer.ts
frontend/src/features/chat/*.test.tsx
frontend/src/lib/types.ts

backend/app/api/models.py
backend/app/api/routes.py
backend/app/chat.py
backend/app/events.py
backend/app/main.py
backend/tests/unit/
backend/tests/integration/
```

Database Migrationは追加しない。

## 12. 完了条件

1. 登録済みRepositoryが0件でもPhase 0 Chatを利用できる。
2. 質問送信後、回答開始前から進捗段階と経過時間が表示される。
3. 回答中に別画面へ移動してもTurnが継続し、Chatへ戻ると同じ状態を確認できる。
4. ブラウザ再読み込み後、同じSessionのMessageと実行中Turnへ復帰できる。
5. SSEの再送または復帰でAssistant Messageが重複しない。
6. Session作成が失敗した場合は自動再試行を止め、理由と再試行操作を表示する。
7. 503と504をtrace IDで追跡でき、ログに機密情報、Message本文、Workspace絶対パスが含まれない。
8. 失敗したSession作成がBackendのメモリへ残らない。
9. IMEを含む既存のBackend、Frontendテストが継続して成功する。
10. ChromeとSafariの手動テストで、進捗、画面移動、再読み込み、エラー復帰を確認できる。
