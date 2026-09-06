# RepoSpec Viewer バックエンド用語解説集

- 対象文書: [`backend-spec.md`](./backend-spec.md)
- 対象読者: Web・サーバー開発の初学者
- ステータス: 概要設計の補助資料

本文書は、バックエンド仕様に登場する用語を、初学者向けに言い換えたものである。実装時の正式な要件はバックエンド仕様を正とする。

`Phase 0`と表示した用語は、最初のCodex App Server接続と最小チャットで先に必要になる。

## 1. まず全体像

```text
ReactからHTTPリクエストを受ける
  ↓
FastAPI RouteがApplication Serviceを呼ぶ
  ↓
Codex GatewayがApp ServerとJSON-RPCで会話する
  ↓
処理状態をDBに保存する
  ↓
回答や進捗をSSEでReactへ返す
```

## 2. Phase 0で最初に覚える用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| バックエンド | 画面から見えにくいサーバー側で、データや業務処理を扱う部分。 | ブラウザーとCodex App Serverの間に入り、安全性と状態を管理する。 |
| Server（サーバー） | 他のプログラムからの要求を待ち、処理結果を返すプログラムまたはコンピューター。 | FastAPIはHTTPサーバーとしてReactからの要求を受ける。 |
| Python | 読みやすい文法を持つプログラミング言語。 | バックエンド全体の実装言語とする。 |
| FastAPI | PythonでHTTP APIを作るためのWebフレームワーク。 | REST/SSEの窓口、入力検証、OpenAPI生成を担当する。 |
| Codex App Server | Codexの会話、認証、実行イベントをプログラムから扱うためのサーバー。 | FastAPIが子プロセスとして起動し、Repository解析やQ&Aを依頼する。 |
| Process（プロセス） | 実行中のプログラム1つの単位。 | FastAPIとCodex App Serverは別Processとして動く。 |
| Child Process（子プロセス） | あるProcessが起動し、終了や入出力を管理する別Process。 | FastAPIが`codex app-server`を起動・監視する。 |
| stdio | Standard Input/Outputの略。プロセスの標準入力と標準出力を使ってデータをやり取りする方式。 | FastAPIとApp Serverの既定transportとする。 |
| stdin / stdout / stderr | stdinはプログラムへの入力、stdoutは通常出力、stderrはエラー・診断出力。 | JSON-RPCをstdin/stdoutで送受信し、stderrは機密情報をマスクしてログ化する。 |
| Transport | 2つのプログラムがデータを運ぶ通信路と方式。 | MVPではstdioを使い、実験的なWebSocketは既定にしない。 |
| JSONL | 1行に1つのJSONを書くデータ形式。 | stdoutを1行ずつ読み、各行をJSON-RPCメッセージとして処理する。 |
| JSON-RPC | JSONで「このメソッドを呼び出して」と依頼し、結果やエラーを受け取る通信規約。 | `initialize`、`thread/start`、`turn/start`などでApp Serverと会話する。 |
| Request / Response | Requestは処理の依頼、Responseはその成功結果またはエラー。 | Request IDで送信した依頼と後から届くResponseを結びつける。 |
| Notification | 相手からの返信を必要としない一方向の通知。 | 回答文の差分やTurn完了などをApp Serverから受け取る。 |
| Request ID | RequestとResponseを結びつける整理番号。 | 同時に複数の依頼が進んでも、どの結果か判別する。 |
| Handshake（ハンドシェイク） | 通信開始時に、双方が利用準備と情報を確認する手順。 | `initialize`の成功後に`initialized`を通知してから他の操作を行う。 |
| Lifespan | FastAPIの起動から終了までの生存期間と、その前後に行う処理。 | 起動時にApp Serverを始動し、終了時に安全に停止する。 |
| Async / Task | Asyncは待ち時間に他の処理を進める方式。Taskはその並行して進む処理単位。 | App Server出力を読み続けながらHTTP要求も受け付ける。 |
| Future / Pending Future | 将来受け取る結果の入れ物。Pendingはまだ結果が届いていない状態。 | Request IDごとに保持し、Response到着時に対応する待機処理を完了させる。 |
| EOF | End Of Fileの略。入力がこれ以上ないことを表す。 | App Serverのstdoutで予期せずEOFになったら、Process終了とみなし実行中依頼を失敗化する。 |
| Timeout | 決めた時間内に完了しない処理を打ち切る仕組み。 | App Server依頼、Git Clone、Viewer生成それぞれに上限を設ける。 |
| Thread / Turn / Item | Threadは会話全体、Turnは1回の依頼から完了まで、ItemはTurn中に生じるメッセージや作業単位。 | App Serverの内部形式をアプリ内型へ変換して管理する。 |
| SSE | サーバーからブラウザーへ、接続を保ったままイベントを送るHTTP方式。 | App Serverの通知をUI向けイベントへ変換して配信する。 |

## 3. APIとアーキテクチャの用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Architecture | システムをどの部品に分け、どう連携させるかという全体設計。 | Route、Application Service、Gateway、DBなどの責務を分ける。 |
| Route | URLとHTTP Methodを受け付けるAPIの入り口。 | 入力を受け取り、Application Serviceを呼び、HTTP応答に変換する。 |
| Endpoint | 特定の機能を提供するAPIのURLとMethodの組。 | `GET /api/health`や`POST /api/chat/sessions`など。 |
| Application Service | 「チャットを開始する」など、アプリの一連の使い方を組み立てる層。 | RouteからCodexやGitを直接呼ばず、ここで入出力、排他、保存を調整する。 |
| Gateway | 外部システム固有の通信を、アプリから使いやすい形に包む窓口。 | Codex GatewayがJSON-RPCの詳細を隠蔽する。 |
| Domain Model | そのアプリの業務上の概念をコード上で表した型。 | `CodexTurn`、`Repository`、`Viewer`などで状態とルールを表す。 |
| DTO | Data Transfer Objectの略。層や通信の境界を越えて値を運ぶためのデータ形。 | API入力や応答に必要な値だけを含め、DBモデルをそのまま返さない。 |
| Schema | データにどの項目があり、各項目がどの型かを定義したもの。 | APIとViewerDocumentの正しい形を定義する。 |
| Normalization（正規化） | 表記や外部形式の違いを、アプリ内の揃った形へ変換すること。 | `.git`付き/なしURLを同じRepository URLにし、App Serverの状態をアプリ内型にする。 |
| Validation | 入力データが定義された型・範囲・ルールに合っているか確かめること。 | GitHub URL、ViewerDocument、ソースパスなどを信頼せず再検証する。 |
| Pydantic | Pythonの型定義を使って入力や設定値を検証するライブラリ。 | FastAPIのDTOとViewerDocumentのValidationに使う。 |
| OpenAPI | HTTP APIのEndpoint、入力、応答を機械可読な形で表す仕様。 | FastAPIから出力し、フロントエンドのTypeScript型生成に使う。 |
| HTTP `202 Accepted` | 要求の受付は成功したが、長い処理はまだ完了していないことを示す状態。 | Message送信やViewer生成でTurn/Job IDをすぐ返し、進捗はSSEで配信する。 |
| Problem Details | HTTP APIエラーを共通形式で表すための仕組み。 | `code`、`retryable`、`trace_id`を含め、UIが対処を判断できるようにする。 |
| Trace ID | 1回の要求に関連するログを追うための識別子。 | UIに安全なIDを返し、詳細な内部エラーを公開せず調査する。 |

## 4. データ保存とJobの用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Database（DB） | データを後から検索・更新できる形で保存する仕組み。 | Repository、Viewer、Conversation、Message、Jobなどを保存する。 |
| PostgreSQL | 表と行の関係でデータを管理するリレーショナルDatabase。 | このプロジェクトの永続データ保存先。 |
| SQLAlchemy | PythonからDatabaseの表やSQLを扱うためのライブラリ。 | DBモデルとデータアクセス層の実装候補。 |
| Repository Pattern | データ保存・取得の詳細をビジネスロジックから隠す設計パターン。Git Repositoryとは別の意味。 | SQLAlchemyを直接さまざまなServiceへ広げないために使う。 |
| Migration | Databaseの表や列の変更を、順番付きの履歴として適用する仕組み。 | データを保ちながらスキーマを更新する。 |
| Persistence（永続化） | プログラムを終了してもデータが残るように保存すること。 | App Serverの履歴だけに頼らず、会話とViewerをDBに保存する。 |
| Transaction | 複数のDB操作を「すべて成功」または「すべて取り消し」として扱う単位。 | Job完了とViewer保存の片方だけが残らないよう境界を決める。 |
| Job | HTTPの1回の応答中に終わらない処理を、1件の仕事として管理する単位。 | Repository同期やViewer生成の状態、進捗、エラーを持つ。 |
| Pipeline | 処理を「準備→解析→検証→保存」のような順番付きの段階に分けたもの。 | Generation Jobの`current_phase`で現在位置を管理する。 |
| Worker | Queue等からJobを取り出して実行するプログラム。 | 初期はFastAPI内のasync taskで代用できるが、将来の分離を想定する。 |
| State Transition（状態遷移） | `queued`から`running`へのように、決められたルールで状態が変わること。 | Jobが不正な順番で完了や再実行にならないようにする。 |
| Lock（排他ロック） | 同じ対象を複数の処理が同時に更新して壊さないよう、一時的に他を待たせる仕組み。 | 同じRepositoryのSyncとGenerationを危険な形で同時実行しない。 |
| Advisory Lock | PostgreSQLが提供する、アプリが意味を決めて使う排他ロック。 | 複数Workerに拡張する際のRepository単位の排他候補。 |
| Broker | EventやJobを一時的に受け取り、必要な相手へ渡す中継役。 | 複数FastAPIに拡張する際はRedis Streams等を共有中継に使う候補。 |
| Bounded Buffer | 保存できる件数や容量に上限を持つ一時保管領域。 | 初期のSSE再送用Eventをメモリ上に無限に溜めない。 |

## 5. Gitとファイルの用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Git Repository | ソースコードと変更履歴を保管する単位。 | Public GitHub Repositoryを解析用Workspaceへ取得する。 |
| Clone | 遠隔Repositoryの履歴とファイルをローカルに初回コピーすること。 | Repository登録時にサーバー管理Workspaceへ取得する。 |
| Fetch / Sync | Fetchは遠隔の新しい履歴を取得すること。Syncは本アプリでの「最新コードに合わせる」一連の操作名。 | 対象Commitを確定し、状態と最終同期日時を更新する。 |
| Branch | 同じRepository内で開発の流れを分ける指し示し。 | Default BranchとViewer生成対象を表示する。 |
| Commit / Commit SHA | Commitはある時点の変更記録。SHAはそれを一意に識別する文字列。 | Generation開始時にSHAを固定し、Viewerの根拠となった時点を再現できるようにする。 |
| Workspace | CloneしたRepositoryを安全に置き、Codexが読むための作業ディレクトリ。 | サーバーがRepository IDから配置先を決め、ユーザー入力でパスを作らない。 |
| Canonical URL | 表記違いを取り除いた代表となるURL。 | `.git`付きなどを正規化し、同じRepositoryの重複登録を防ぐ。 |
| Relative Path（相対パス） | 決めた基準ディレクトリからの位置を表すパス。 | Source ReferenceはRepositoryルートからの相対パスだけを許可する。 |
| Path Traversal | `../`などを使い、許可されたディレクトリの外のファイルを読もうとする攻撃。 | パス正規化後にWorkspace外へ出ていないか必ず確認する。 |
| Symlink | 別のファイルやディレクトリを指すリンク。 | 表面上のパスだけでなく、解決先もWorkspace内か検証する。 |
| Blob | Gitが保存する特定Commit時点のファイル内容。 | 現在のファイルではなく、Viewer生成時のCommitのソースを取得する。 |
| Binary File | テキストとして安全に行単位表示できない画像や実行ファイル等。 | Source Code APIでは拒否する。 |
| Git Submodule / Git LFS | Submoduleは別Repositoryの参照、LFSは大きなファイルを別管理するGit拡張。 | データ取得と安全性が複雑になるためMVPの対象外。 |
| Shell Injection | ユーザー入力をshell命令文に連結し、意図しない命令を実行させる攻撃。 | Gitコマンドはshell文字列でなく、検証済みの引数配列で起動する。 |

## 6. Viewer生成とセキュリティの用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Structured JSON | 項目名と型があらかじめ決まったJSON。 | Codexは自由形式HTMLではなく`ViewerDocument`を返す。 |
| JSON Schema | JSONの必須項目、型、許可値を記述する標準的な形式。 | Codex出力の形を指定し、受信後の検証にも使う。 |
| ViewerDocument | Viewerのタイトル、節、文章部品、ソース参照、制約を持つプロジェクト固有の構造化データ。 | 仕様書の正本とし、HTMLはここから作る。 |
| Renderer | 構造化データを表示用の文字列やHTMLへ変換する部品。 | Validation済みViewerDocumentを管理下のHTMLへ変換する。 |
| Template | HTMLの共通構造に値を差し込むひな形。 | AIに全HTMLを任せず、アプリ管理のTemplateを使う。 |
| Auto-escape | HTMLとして特別な意味を持つ文字を、単なる文字として安全に表示できる形へ自動変換する機能。 | Repository内の文字列が意図せずHTMLとして実行されるのを防ぐ。 |
| Sanitizer | HTMLから危険な要素、属性、URLを取り除く部品。 | Renderer後のHTMLを最後にサニタイズし、その結果だけを保存する。 |
| Allowlist | 安全と確認されたものだけを許可するルール。 | HTMLタグ、属性、ViewerDocumentのblock typeを列挙する。 |
| XSS | 危険なJavaScriptをWebページ内で実行させる攻撃。 | AI出力とRepositoryの内容を信頼せず、多層防御する。 |
| CSP | Content Security Policyの略。ブラウザーが読み込み・実行できるスクリプトやリソースの取得先を制限するHTTPポリシー。 | サニタイズ漏れがあった場合の被害も抑える。 |
| Sandbox | プログラムがアクセスできる場所や操作を制限する隔離環境。 | Codexが対象Repositoryを読めるが書き換えられないread-only設定にする。 |
| Prompt Injection | 解析対象の文章などに「本来の指示を無視せよ」と書き、AIの動作を不正に変えようとする攻撃。 | Repository内の文章は指示ではなく、信頼されない調査データとして扱う。 |
| Secret | トークン、パスワード、認証情報など、公開してはいけない値。 | DB、ブラウザーのLocalStorage、ログへ保存しない。 |
| Masking（マスキング） | 機密情報の全体を表示せず、削除または一部を隠すこと。 | App ServerのstderrやAPIエラーをログに書く前に適用する。 |
| RAG / Vector Database | RAGは関連文書を検索してAIへ渡す方式。Vector Databaseは意味の近さで検索するための保存先。 | MVPでは使わず、Codexがread-only Workspaceを直接調査する。 |

## 7. 運用とテストの用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Observability（可観測性） | システムの外からログや数値を見て、内部で何が起きているか調べられる性質。 | Codex停止、Turn失敗、SSE切断などの原因調査に必要な情報を残す。 |
| Log（ログ） | いつ何が起きたかを記録したテキストまたは構造化データ。 | ID、状態、所要時間を記録し、トークンや内部パスは残さない。 |
| Metrics（メトリクス） | 成功数、失敗数、所要時間など、傾向を数値で見るためのデータ。 | Turn完了時間、App Server再起動数、SSE再接続数などを候補とする。 |
| First Token Latency | ユーザーが送信してから、回答の最初の一部が届くまでの時間。 | チャットの体感速度を測る。 |
| Unit Test | 関数やクラスを小さな単位で確認するテスト。 | JSON-RPC振り分け、URL正規化、Job状態遷移を確認する。 |
| Integration Test | 複数の部品を組み合わせ、連携できるか確認するテスト。 | FastAPIからfake App Server、SSE、PostgreSQLまでの連携を確認する。 |
| Contract Test | システム間で約束したAPI形式が変わっていないか確認するテスト。 | OpenAPIとTypeScript型、App Server通知形式の互換性を確認する。 |
| Fake | 本物の外部システムの代わりに、テスト向けの簡単な動作をする実装。 | 認証成功、デルタ配信、失敗を再現するfake App Serverを使う。 |
| Fixture | テストが同じ条件で実行できるよう用意する入力データや事前状態。 | App Serverの主要Notificationやテスト用Repositoryを固定データにする。 |
| Environment Variable | OSや実行環境からプログラムへ渡す設定値。 | `DATABASE_URL`、`WORKSPACE_ROOT`、Timeout等をコードと分けて設定する。 |

## 8. 似た用語の違い

| 比較 | 違い |
|---|---|
| HTTP REST / JSON-RPC / SSE | RESTはBrowserからFastAPIへの要求、JSON-RPCはFastAPIからApp Serverへの呼び出し、SSEはFastAPIからBrowserへの継続配信に使う。 |
| Process / Async Task / Job | Processは実行中プログラム、Async TaskはProcess内の並行処理、Jobはアプリが保存・管理する仕事。 |
| Request ID / Trace ID / Domain ID | Request IDはJSON-RPCの応答対応、Trace IDは一連のログ追跡、Domain IDはRepositoryやViewerの識別に使う。 |
| Validation / Sanitization | Validationは形とルールの確認、Sanitizationは危険な内容の除去・無害化。 |
| Git Repository / Repository Pattern | Git Repositoryはソースの保管場所。Repository PatternはDBアクセスを隠すコード設計。 |
| Thread / Conversation | ThreadはCodex App Server側の会話、ConversationはRepoSpec ViewerのDBで保存する会話。 |

## 9. 関連文書

- [RepoSpec Viewer 概要仕様](./README.md)
- [バックエンド仕様](./backend-spec.md)
- [フロントエンド用語解説集](./frontend-glossary.md)
