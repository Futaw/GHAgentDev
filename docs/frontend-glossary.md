# RepoSpec Viewer フロントエンド用語解説集

- 対象文書: [`frontend-spec.md`](./frontend-spec.md)
- 対象読者: Web開発の初学者
- ステータス: 概要設計の補助資料

本文書は、フロントエンド仕様に登場する用語を、初学者向けに言い換えたものである。実装時の正式な要件はフロントエンド仕様を正とする。

`Phase 0`と表示した用語は、最初の「Codex App Server接続と最小チャット」で先に使う。まずそこから読み、後続Phaseの用語は必要になったときに参照すればよい。

## 1. まず全体像

```text
ユーザーが画面で操作する
  ↓
Reactが画面を更新する
  ↓ REST APIでデータを送受信する
FastAPIが処理を受け付ける
  ↑ SSEで回答や進捗を少しずつ受け取る
ブラウザーが逐次表示する
```

## 2. Phase 0で最初に覚える用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| フロントエンド | ユーザーが直接見たり操作したりする部分。 | Login画面、Chat画面、Viewer画面などを担当する。 |
| ブラウザー | ChromeやSafariなど、Webページを表示するアプリ。 | Reactアプリを実行する。Codex App ServerやGitを直接操作しない。 |
| UI | User Interfaceの略。ボタン、入力欄、一覧など、人とアプリの接点。 | チャット入力、送信ボタン、実行中表示などを含む。 |
| React | データの変化に合わせて画面を組み立てるJavaScriptライブラリ。 | このプロジェクトの画面実装の中心とする。 |
| Component（コンポーネント） | 画面を「ボタン」「メッセージ」などの再利用できる部品に分けたもの。 | `ChatInput`や`MessageList`のような部品を組み合わせて画面を作る。 |
| State（状態） | 現在の画面が覚えている値。値が変わると表示も変わる。 | 「認証済み」「回答生成中」「入力中の文字」などを管理する。 |
| API | 異なるソフトウェア同士が決められた形で会話するための窓口。 | フロントエンドはFastAPIの`/api/...`へリクエストを送る。 |
| REST API | URLとHTTPメソッドを使って、データの取得・登録・更新・削除を行うAPIの設計方法。 | 認証状態の取得やメッセージ送信に使う。 |
| SSE | Server-Sent Eventsの略。サーバーからブラウザーへ、接続を保ったままデータを送り続ける方式。 | Codexの回答文やジョブ進捗を少しずつ画面へ届ける。 |
| Streaming（ストリーミング） | 処理がすべて終わるのを待たず、できた部分から送ること。 | Chat画面でCodexの回答が少しずつ伸びる表示を実現する。 |
| Event（イベント） | 「処理が始まった」「文字が追加された」など、起きた事実を表す通知。 | `turn.started`、`message.delta`、`turn.completed`などをUIが受け取る。 |
| Delta（デルタ） | 完成文全体ではなく、前回から増えた差分。 | `message.delta`の文字を現在のCodex回答の末尾へ追加する。 |
| Authentication（認証） | 利用者が正しくログインしているか確かめること。 | ChatGPT認証状態をLogin画面で確認し、未認証ならログインへ案内する。 |
| Thread | Codex側で会話の文脈をまとめる単位。「1冊の会話ノート」に近い。 | 会話を開始・再開するために使い、画面には内部IDを意識させない。 |
| Turn | Thread内の1回の処理単位。ユーザーが送信し、Codexが作業して回答するまで。 | 送信後の実行中、完了、失敗、中止をTurn単位で表示する。 |
| Conversation | アプリ側が保存する会話のまとまり。 | CodexのThreadと対応づけ、将来はViewerごとの質問履歴を保存する。 |
| Message | Conversation内のユーザーまたはCodexの発言1件。 | チャット欄に送信者と本文を分けて表示する。 |

## 3. 画面を作るための用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| TypeScript | JavaScriptに「この値は文字列」などの型情報を追加した言語。 | APIの応答やComponentの入力違いを、実行前に見つけやすくする。 |
| Vite | フロントエンドを開発・ビルドするためのツール。 | 開発サーバーの起動と、公開用ファイルの生成に使う。 |
| Build（ビルド） | 開発用ソースを、ブラウザーが配信・実行しやすい形に変換すること。 | ViteがTypeScriptやCSSをまとめ、本番用ファイルを作る。 |
| DOM | Document Object Modelの略。ブラウザーがHTMLをツリー状の要素として扱う仕組み。 | ReactがDOMを更新し、ユーザーが見る画面を変化させる。 |
| Props | 親Componentから子Componentへ渡す値。部品への設定値に近い。 | メッセージ本文やボタンの無効状態などを渡す。 |
| SPA | Single Page Applicationの略。ページ全体を毎回読み直さず、JavaScriptが必要な部分を切り替えるWebアプリ。 | LoginからChat、Repository、Viewerへの移動を滑らかに行う。 |
| Route（ルート） | URLと表示する画面の対応関係。 | `/chat`ならChat画面、`/viewers/:viewerId`なら指定Viewerを表示する。 |
| React Router | Reactアプリ内のRouteと画面遷移を管理するライブラリ。 | 認証前の保護Routeから`/login`へ戻す処理にも使う。 |
| パスパラメーター | URLの一部に埋め込まれたIDなどの値。 | `/viewers/:viewerId`の`:viewerId`を読み、表示対象を決める。 |
| 画面遷移 | 別のURLや画面へ移ること。 | 認証成功後に`/chat`へ、Viewer生成開始後に進捗画面へ移る。 |
| Dialog | 現在の画面の上に表示し、確認や入力を求める小さな画面。 | Viewer削除の確認などに使う。 |
| Drawer | 画面の端から引き出しのように開く領域。 | Mobile表示でViewerを隠さずにチャットを開く候補とする。 |
| Responsive（レスポンシブ） | 画面幅に合わせて配置や表示方法を変えること。 | DesktopはViewerとChatの2カム、Mobileは切り替え表示にする。 |

## 4. データ、フォーム、通信の用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Server State | サーバーが正本を持つデータの状態。他の処理で更新される可能性がある。 | 認証状態、Repository一覧、Viewer詳細など。 |
| Local UI State | そのブラウザー画面だけで使う一時的な状態。 | Dialogの開閉、入力中の文字、未確定のストリーミング文など。 |
| Cache（キャッシュ） | 取得済みデータを一時保存し、毎回取り直さなくて済むようにする仕組み。 | TanStack QueryがAPI応答を管理し、必要なときに再取得する。 |
| TanStack Query | APIから取得するServer Stateのキャッシュ、再取得、エラー状態を管理するライブラリ。 | RepositoryやViewerの取得・更新を統一して扱う。 |
| Form（フォーム） | 入力欄、選択欄、送信ボタンなどをまとめた入力用UI。 | Repository URL登録やViewer作成条件の入力に使う。 |
| React Hook Form | ReactのForm入力、エラー、送信を管理するライブラリ。 | Viewer作成フォームの入力状態と二重送信防止に使う候補。 |
| Validation（検証） | 入力値が必須か、正しい形式かなどを確かめること。 | 空の要求や不正なGitHub URLを画面で早く知らせる。正式判定はバックエンドも必ず行う。 |
| Zod | TypeScript上でデータの形や条件を定義し、値を検証するライブラリ。 | Formの必須項目や文字列形式を定義する候補。 |
| JSON | 文字列、数値、配列、キーと値の組を表せるデータ形式。 | REST APIのリクエストと応答で主に使う。 |
| HTTP Method | APIに対して何をしたいかを表す種類。 | `GET`は取得、`POST`は作成・開始、`PATCH`は一部更新、`DELETE`は削除に使う。 |
| HTTP Status | API処理の結果を3桁の数字で表したもの。 | `200`は成功、`202`は受付済みで処理継続中、`4xx`は入力等の問題、`5xx`はサーバー側の問題の目安。 |
| Fetch | ブラウザーからHTTPリクエストを送る標準機能。 | 共通wrapperを用意し、URL、JSON変換、エラー変換を統一する。 |
| API Client | フロントエンドからAPIを呼ぶ処理をまとめたコード。 | ComponentがURLやエラー形式を毎回意識しないようにする。 |
| Base URL | API URLの共通部分。 | 開発環境と本番環境で接続先を切り替える。 |
| Mutation | サーバー上のデータを作成、更新、削除する操作。 | メッセージ送信、Repository登録、Viewer削除など。 |
| Idempotency Key | 同じ送信が通信再試行で複数回届いても、1回の操作として扱うための識別子。 | POST再試行でViewerやMessageが二重作成されるのを防ぐ。 |
| OpenAPI | REST APIのURL、入力、応答を機械が読める形で表す仕様。 | FastAPIが生成する定義からTypeScriptの型を作り、前後端のずれを減らす。 |
| Problem Details | APIエラーの種類、説明、HTTP状態などを揃えて返す形式。 | 入力不備、認証切れ、Codex停止などをUIで適切に出し分ける。 |
| Heartbeat | データがない間も、接続が生きていることを示す定期的なイベント。 | SSE接続の維持に使い、通常は画面に表示しない。 |
| Event ID / `Last-Event-ID` | Eventの順番と、切断後に「この続きから送って」と伝える値。 | SSE再接続時の取りこぼしと重複表示を減らす。 |

## 5. Viewerと安全性の用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Repository（リポジトリ） | ソースコードとその変更履歴をまとめた保管場所。 | GitHub URLで登録し、Viewerの調査対象にする。 |
| Viewer | Codexの調査結果を読みやすい仕様書として表示する画面または保存データ。 | 本文、目次、参照ソース、右側のQ&Aをまとめる。 |
| Generation Job | Viewerを作るための長時間処理を1件として管理する単位。 | 待機、実行中、完了、失敗、中止と詳細フェーズを表示する。 |
| Commit SHA | Gitの特定時点の変更内容を識別する文字列。 | Viewerがどの時点のソースを根拠にしたか示す。 |
| Source Reference | 説明の根拠となるソースファイルと行範囲の情報。 | 参照IDをクリックするとSource Code Viewerを開く。 |
| HTML | 見出し、段落、表、リンクなどWebページの構造を表す言語。 | バックエンドで安全化されたViewer本文だけを表示する。 |
| CSS | 色、余白、文字サイズ、配置など見た目を指定する言語。 | テーマとしてアプリ側が管理し、AIに任意のCSSを作らせない。 |
| JavaScript | ブラウザー内で画面操作や通信を動かす言語。 | Reactの動作に必要だが、AI生成HTML内のJavaScriptは実行しない。 |
| Sanitization（サニタイズ） | 受け取ったHTMLから危険な要素や属性を除去・無害化すること。 | バックエンドとDOMPurifyの両方で多層防御する。 |
| DOMPurify | HTMLをサニタイズするためのフロントエンド用ライブラリ。 | バックエンドで検証済みのHTMLにも追加適用する。 |
| XSS | Cross-Site Scriptingの略。悪意あるスクリプトをページ内で実行させる攻撃。 | AI生成内容やRepository内文字列を無検証でHTMLにしない。 |
| Allowlist | 「これだけは使ってよい」と許可するものを列挙する方式。 | 許可済みHTMLタグと属性だけをViewerに残す。 |
| `noopener noreferrer` | 新しいタブで開いた外部ページから、元画面へ不要に干渉されたり情報を送ったりするのを抑える指定。 | GitHubなどの外部リンクに設定する。 |
| Syntax Highlight | ソースコードを言語の構文に合わせて色分けする表示。 | Source Code Viewerで参照範囲を読みやすくする。 |
| Monaco Editor / Shiki | Monacoはコード表示・編集部品、Shikiは高品質なコード色分けツール。 | 読み取り専用Source Code Viewerに適した方を後続Phaseで選ぶ。 |

## 6. 使いやすさとテストの用語

| 用語 | やさしい説明 | RepoSpec Viewerでの使い方 |
|---|---|---|
| Accessibility | 障害の有無や操作方法にかかわらず利用しやすくする考え方。 | キーボード操作、フォーカス移動、文字での状態表示を実装する。 |
| `aria-live` | 画面の更新をスクリーンリーダーへ伝えるHTML属性。 | 回答中の更新を通知するが、1文字ごとの過剰な読み上げは避ける。 |
| Focus（フォーカス） | 現在キーボード入力の対象になっている要素。 | Dialogを開いたら中へ移し、閉じたら元のボタンへ戻す。 |
| Unit Test | 関数や小さなロジックを独立して確認するテスト。 | SSEの順番処理やパス検証などを素早く確認する。 |
| Component Test | 画面部品を表示し、操作と表示結果を確認するテスト。 | 認証状態ごとのLogin表示やFormエラーを確認する。 |
| E2E Test | End-to-End Testの略。ブラウザー操作からバックエンドまで、利用者の一連の流れを確認する。 | ログイン後にチャットを送信し、逐次回答が表示されるまでを確認する。 |
| Vitest | Viteと相性のよいJavaScript/TypeScriptテストランナー。 | Unit TestやComponent Testの実行に使う。 |
| React Testing Library | 実装内部ではなく、ユーザーが見る表示や操作を中心にReactをテストするライブラリ。 | ボタン操作やエラー文言の表示を確認する。 |
| Playwright | 実際のブラウザーを自動操作するテストツール。 | LoginからChat回答までのE2E Testに使う。 |

## 7. 似た用語の違い

| 比較 | 違い |
|---|---|
| Server State / Local UI State | サーバーが正本を持つか、その画面だけの一時値か。 |
| Thread / Turn / Message | Threadは会話全体、Turnは1回の処理、Messageは1件の発言。 |
| REST / SSE | RESTは必要なときに1回ずつ要求・応答する。SSEはサーバーから継続的に送る。 |
| Validation / Sanitization | Validationは形や条件が正しいか確認する。Sanitizationは危険な内容を除去・無害化する。 |
| Unit / Component / E2E | Unitは小さなロジック、ComponentはUI部品、E2Eはアプリ全体の流れを確認する。 |

## 8. 関連文書

- [RepoSpec Viewer 概要仕様](./README.md)
- [フロントエンド仕様](./frontend-spec.md)
- [バックエンド用語解説集](./backend-glossary.md)
