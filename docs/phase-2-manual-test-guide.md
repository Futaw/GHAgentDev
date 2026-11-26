# Phase 2 手動テストガイド

- 更新日: 2026-11-25
- 対象: RepoSpec Viewer Phase 2「Viewer生成と保存」
- 想定環境: macOS、Python 3.12以上、Node.js 24、UTF8のPostgreSQL、Codex CLI 0.164.0
- 照合元: [Phase 2詳細設計](./phase-2-detailed-design.md)、現行のBackend / Frontend実装、[最終受入記録](./verification/2026-11-09-phase-2-acceptance.md)

この文書は、利用者がブラウザでPhase 2を再確認するための手順書です。各テストに操作、期待結果、確認するAPIを記載しています。コマンドには目的と処理内容を添えています。

過去の受入結果と、今回実行した結果は分けて記録してください。この手順書を追加した時点では、今回の手動テストは未実施です。

## 1. テストの進め方

まず2〜3章で起動を準備し、4章の通常操作を上から順に確認してください。その後、5章の異常系と競合を確認します。6章はAPIで詳しく調べたい場合、7章は自動テストも併用する場合の補足です。

| 区分 | 実行するもの | 用途 |
|---|---|---|
| ターミナル操作 | Python、Alembic、Uvicorn、npm、curl、Git | 起動、状態確認、APIの直接確認 |
| ブラウザ操作 | フォーム、進捗、Viewer、各ダイアログ | 利用者が操作する流れと表示の確認 |
| アプリ内部の処理 | HTTP API、JSON-RPC、Git ref更新 | 画面操作の裏で何が起きるかを理解するための説明。8章の内部コマンドを手動実行する必要はありません |

### 1.1 使用するデータ

- 削除してよいテスト用Viewerを作成してください。既存の主Viewerを再生成・削除する必要はありません。
- 対象は非機密のPublic GitHub Repositoryです。小さく、READMEとソースコードがあるものを選んでください。
- 通常環境に保存済みデータがある場合は、テスト前のViewer一覧とIDを控えてください。専用DBを使う場合は、UTF8で作成します。
- パスワード、認証コード、アクセストークン、`.env`やCodex設定の全文を、結果表・スクリーンショット・ログへ貼らないでください。
- `<DB_USER>`などの山括弧付きの値は、自分の環境に置き換えてください。

### 1.2 テスト対象の範囲

今回確認するのは、生成条件入力、非同期Job、保存・閲覧、表示設定、再生成、中止、再試行、削除です。Phase 3のQ&AとSource Code Viewer本体は未実装です。ソース参照は、説明・相対ファイルパス・行範囲の表示までを確認します。

生成文書の章構成や本文は毎回同一になるとは限りません。文書種別、依頼内容、ソースの根拠に合う説明になっているかを確認してください。

## 2. 実行前の準備

### 2.1 作業場所と依存関係

以降のコマンドは、指定がなければRepositoryのルートで実行します。

```bash
# アプリのルートへ移動し、相対パスで指定する設定・モジュールの基準をそろえます。
cd "/Users/futaw/Documents/ChatGPT/ソース解説AIエージェント作成"

# 今回テストするソースコードのCommitを確認します。結果表に記録してください。
git rev-parse HEAD
```

セットアップ済みなら、次の作業は不要です。未準備の場合だけ実行してください。

```bash
# アプリ専用のPython仮想環境を作成します。既存の.venvがある場合は省略します。
python3 -m venv .venv

# 現在のターミナルで、仮想環境のPythonとコマンドを使えるようにします。
source .venv/bin/activate

# Backend本体と開発・テスト用の依存ライブラリをインストールします。
python -m pip install -e '.[dev]'

# Frontendの依存ライブラリを、ロックファイルに従ってインストールします。
npm --prefix frontend ci
```

`.env`がまだない場合だけ、次のコマンドでひな型をコピーします。既存の`.env`は上書きしないでください。

```bash
# ローカル設定用のファイルを作成します。コピー後に接続先などを編集します。
cp .env.example .env
```

### 2.2 設定と固定CLI

`.env`で次の設定を確認してください。下の例の接続情報は、そのまま使わず実環境に合わせて編集します。

```dotenv
DATABASE_URL=postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@127.0.0.1:5432/<DB_NAME>
WORKSPACE_ROOT=.data/workspaces
TEST_CHAT_WORKSPACE=<存在するテスト用ディレクトリ>
CODEX_EXECUTABLE=/Users/futaw/.local/bin/codex
GENERATION_ENABLED=false
```

| 設定 | 目的と確認事項 |
|---|---|
| `DATABASE_URL` | Repository、Viewer、Jobの保存先。PostgreSQLのDB自体の文字コードがUTF8である必要があります |
| `WORKSPACE_ROOT` | CloneしたRepositoryをアプリが管理する場所。既存DBを使う場合は、そのDBと対応するWorkspaceを維持します |
| `TEST_CHAT_WORKSPACE` | Phase 0 Chatの調査先。Phase 2の調査先は、登録済みRepositoryの管理Workspaceです |
| `CODEX_EXECUTABLE` | 受入検証で使用した固定CLI。`.env.example`は`codex`なので、PATH上の別CLIを使っていないか確認します |
| `GENERATION_ENABLED` | Viewer生成の受付可否。未指定時の既定値は`false`です。`.env.example`にはこの項目がないため、必要に応じて1行だけ設定します |

```bash
# 受入検証で使った実行ファイルのバージョンを調べます。期待値はcodex-cli 0.164.0です。
/Users/futaw/.local/bin/codex --version
```

固定CLIがない、またはバージョンが異なる場合は、その結果を記録してください。別CLIへの切替や権限拡大で生成を進める手順は含みません。

### 2.3 PostgreSQLとMigration

PostgreSQLが起動済みなら、接続確認から実行してください。現在のローカル環境でPostgreSQL 17を使う場合のコマンドは次のとおりです。

```bash
# PostgreSQL 17のpsqlやpg_isreadyを呼び出せるようにPATH等を設定します。
source /Library/PostgreSQL/17/pg_env.sh

# DBサーバーが接続を受け付けているかを調べます。DBやテーブルは変更しません。
pg_isready -h 127.0.0.1 -p 5432
```

期待結果は`accepting connections`です。停止中の場合だけ、次を実行します。このコマンドは既存のDBサーバーも再起動するため、別の処理が接続中でないことを確認してください。

```bash
# macOSに登録されたPostgreSQL 17のサービスを起動または再起動します。
sudo launchctl kickstart -k system/postgresql-17
```

```bash
# .envの接続先と同じDBの文字コードを確認します。パスワードは求められた場合に対話入力します。
psql -h 127.0.0.1 -U <DB_USER> -d <DB_NAME> -c 'SHOW server_encoding;'
```

期待結果は`UTF8`です。`client_encoding`だけがUTF8でも条件を満たしません。非UTF8だった場合は、[旧DBを残してUTF8 DBを用意する手順](./verification/2026-11-06-database-encoding.md#利用者にお願いする手順)へ進んでください。既存DBを削除して作り直す必要はありません。

```bash
# .envの接続先DBへ、未適用のテーブル・制約の変更を適用します。Backend起動前に実行します。
.venv/bin/alembic upgrade head

# 接続先DBに適用済みのMigration番号を確認します。
.venv/bin/alembic current
```

現行Phase 2の期待値は`20261025_0002 (head)`です。アプリ起動だけではMigrationは適用されません。

### 2.4 生成の安全性と有効化

受入済みと同じ環境で再確認する場合は、過去の[最終受入記録](./verification/2026-11-09-phase-2-acceptance.md)とCLI・設定・OS等の変更有無を確認します。CLI、policy、設定、実行環境を変更した場合や、初めて使う環境では、生成を無効にして次の全体検査を行ってください。

```bash
# 専用の非機密fixtureを作り、実CLIで読取り範囲、変更拒否、通信拒否、設定、実Turn等を検査します。
# 実モデルを呼び出すため、Codexの認証と利用枠が必要です。通常DBや.envは変更しません。
.venv/bin/python -m backend.scripts.verify_generation_sandbox \
  --codex /Users/futaw/.local/bin/codex --timeout 120
```

`--codex`は検査する実行ファイル、`--timeout`は各コマンド・RPCの待機上限秒数です。全体の制限時間ではありません。stderrに進捗、stdoutに最終JSONが出ます。

合格条件は終了コード0、必須9項目がすべて`passed`、`process_cleanup`と`fixture_cleanup`も`passed`であることです。9項目は`protocol_config`、`sandbox_read`、`non_modification`、`command_network`、`real_turn`、`shell_environment`、`external_tools`、`additional_permissions`、`fixture_integrity`です。`failed / inconclusive / not_run`は合格に含めません。診断用の`--only`を付けた部分実行も、全体合格にはなりません。

実RPCの承認要求が`not_observed`なら、観測できた拒否として記録しないでください。必須項目の判定と、個別の観測結果を分けて残します。

条件を満たした環境で通常操作を試す際に、ご自身で`.env`の`GENERATION_ENABLED`を`true`へ変更してください。すでに有効化済みで環境変更がなければ、設定を戻してからやり直す必要はありません。設定変更はBackend再起動後に反映されます。

## 3. アプリの起動と事前確認

### 3.1 ターミナル1: Backend

Repositoryルートで実行します。すでに8000番ポートでBackendが動いている場合は、そのターミナルで終了してから起動し直してください。

```bash
# FastAPIをローカルの8000番ポートで起動し、Codex App Serverも子プロセスとして開始します。
.venv/bin/python -m uvicorn backend.app.main:app \
  --workers 1 --host 127.0.0.1 --port 8000
```

`--workers 1`は必須です。排他制御とSSEバッファをプロセス内で管理します。`--reload`は付けません。管理Workspaceのファイル変更で意図せずBackendが再起動するのを防ぐためです。

### 3.2 ターミナル2: Frontend

別ターミナルでRepositoryルートへ移動して実行します。

```bash
# React画面を配信するVite開発サーバーを起動します。/apiはBackendへ代理送信されます。
npm --prefix frontend run dev
```

表示されたURLを確認し、通常は[アプリ画面](http://localhost:5173)を開きます。APIの一覧は[Swagger UI](http://127.0.0.1:8000/docs)で確認できます。

### 3.3 ターミナル3: 状態確認

```bash
# HTTPサーバーとCodex App Serverの接続状態を取得します。
curl -sS http://127.0.0.1:8000/api/health

# Codexの認証状態を取得します。未認証ならブラウザのログイン画面で認証します。
curl -sS http://127.0.0.1:8000/api/auth/status

# Viewerフォームで選べる値と既定値を取得します。生成は開始しません。
curl -sS http://127.0.0.1:8000/api/viewer-options

# 登録済みRepositoryと状態を取得します。調査対象のIDとready状態を確認します。
curl -sS http://127.0.0.1:8000/api/repositories
```

`curl -sS`は通常の進捗表示を省き、接続等のエラーは表示する指定です。HTTPステータスも見たい場合は`-i`を追加します。

期待結果はHealthの`status: ok`、`http_server: true`、`app_server_connected: true`と、認証の`status: authenticated`です。Health成功だけでは、生成有効・UTF8・Job固有の安全検査成功までは判断できません。

対象Repositoryがない場合は画面から登録し、Clone完了の`ready`を待ってください。必要な登録・Syncの詳しい手順は[Phase 0・1手動テストガイド](./phase-0-1-manual-test-guide.md)を参照します。

ブラウザの開発者ツールでNetworkとConsoleを開いておくと、HTTP応答、SSE、画面エラーを確認できます。

## 4. 通常操作のテスト

### P2-01: Viewer作成フォーム

1. 対象RepositoryのDashboardで「Viewerを作成」を押します。
2. 下表の初期値と選択肢を確認します。
3. ThemeとDensityを切り替え、固定サンプルのプレビューが変わることを確認します。
4. Requestを空、次に空白だけにして「生成を開始」を押します。
5. エラーを確認後、次のP2-02用に初期値へ戻します。

| 項目 | 初期値 | 選択肢 |
|---|---|---|
| Document Type | 機能仕様 `functional_spec` | 機能仕様、技術ガイド、処理フロー |
| Detail Level | 標準 `standard` | 概要、標準、詳細 |
| Target Audience | エンジニア `engineer` | エンジニア、初学者、プロダクトマネージャー |
| Theme | Technical Light `technical-light` | Technical Light、Editorial |
| Density | ゆったり `comfortable` | ゆったり、コンパクト |
| Request | 空 | 必須。空白除去後1〜4,000文字 |
| Additional Instruction | 空 | 任意。最大4,000文字 |

期待結果: Request直下に「生成対象を入力してください。」が表示され、作成POSTが送信されないこと。プレビュー切替だけでJobやViewerが作られないこと。

確認するAPI: 選択肢の取得は`GET /api/viewer-options`です。

### P2-02: 新規生成と進捗

次の例を入力します。Repository固有の機能を調べる場合は、Requestをその機能名へ変更してください。

```text
Request:
READMEと主要なソースコードを調べ、このRepositoryの目的と主要な処理の流れを説明してください。

Additional Instruction:
これは削除予定の手動テスト用Viewerです。タイトルに「Phase2手動テスト」を含めてください。
根拠となるファイルと行範囲を示し、確認できない点は制約として記載してください。
```

1. 「生成を開始」を押します。押した直後に連続クリックしても、送信が重複しないか確認します。
2. `/jobs/<Job ID>`へ移動したら、URLからJob IDを控えます。
3. 進捗とSSE接続表示を確認します。
4. 完了を待ち、自動表示されたViewerのIDを控えます。このViewerを以降の試験用Aとします。

期待結果は次のとおりです。

- 作成APIは`202 Accepted`とJobを返します。Job IDのJSONキーは`id`です。`job_id`ではありません。新規作成受付時の`viewer_id`は`null`です。
- Jobは`queued / running`を経て`completed`になります。早いフェーズは画面で見逃しても、直ちに不合格にはしません。
- 「Repositoryを確認」から「文書と参照を検証」「Viewerを保存」「完了」へ進みます。生の生成JSON、推論内容、実行コマンド全文は表示しません。
- 検証済みソースが表示される場合は、Repository内の相対パスです。
- 実行中はSSEに加えてJob詳細のGETが約5秒ごとに送られ、終端状態では止まります。
- 完了後に`/viewers/<Viewer ID>`へ自動遷移します。Job画面を再度開いた場合は「Viewerを開く」から移動できます。
- DashboardのViewer一覧へ追加され、保存前の途中Viewerは一覧に出ません。

### P2-03: 保存内容、目次、ソース参照

1. 試験用Aでタイトル、概要、本文、目次を確認します。
2. HeaderのRepository、Branch、Commit、Type / Detail、Audience、Theme / Density、Updatedを確認します。
3. 目次をクリックし、対応する見出しへ移動することを確認します。
4. ソース参照をクリックし、説明・相対パス・開始行と終了行を確認して閉じます。
5. HeaderのCommitリンクからGitHubを開き、生成元Commitと一致することを確認します。ソース参照の行もそのCommitで照合します。
6. ブラウザを再読み込みし、Dashboardへ戻ってから再び試験用Aを開きます。

期待結果: 同じViewerが再表示され、再生成Jobは作られません。新規Viewerの`content_revision`はAPIで1です。本文が依頼内容に合い、参照先の実装と説明に矛盾がないことも確認します。

Phase 2の参照表示には「Source Code ViewerはPhase 3で追加します。」と表示されます。コード本文が開かないことをPhase 2の失敗には数えません。

### P2-04: Theme / Density変更とキャンセル

1. 「表示設定」を開き、Themeが初期フォーカスになることを確認します。
2. Editorial、コンパクトへ変更して「キャンセル」を押します。元の表示が維持されることを確認します。
3. 再び開き、同じ変更を「保存」します。
4. 再読み込み後も選択が保存されていることを確認します。
5. Technical Light / Editorialと、ゆったり / コンパクトの4組を確認します。

期待結果: 色・書体・余白等が変わります。`PATCH /api/viewers/<ID>/appearance`だけで更新でき、生成POSTや新しいJobは発生しません。`content_json`、`sanitized_html`、`commit_sha`、`content_revision`は変わらず、`updated_at`は更新されます。APIでの比較方法は6.2を参照してください。

### P2-05: 画面移動・再読み込み後のJob確認

1. 新しい試験用Viewerの生成を開始し、JobのURLを控えます。
2. 実行中にDashboardへ移動し、控えたURLからJob画面へ戻ります。
3. 実行中ならブラウザを再読み込みします。
4. Job詳細の再取得後に状態が表示され、完了したらViewerを開けることを確認します。

期待結果: 画面移動・SSE切断だけでJobは中止されません。完了をRESTで確認した場合も「Viewerを開く」で移動できます。SSEの過去イベントや検証済みパス一覧が、すべて復元されることまでは要求しません。

### P2-06: 再生成の成功

1. 試験用Aの`content_revision`とCommitをAPIで控えます。
2. 必要ならDashboardで「最新コードを取得」を押し、`ready`を待ちます。
3. 試験用Aへ戻り、「再生成」を押します。
4. 完了後のViewer ID、revision、Commitと、DashboardのViewer数を確認します。

期待結果: 保存済みの生成条件で新しいJobを作り、同じViewer IDを更新します。Viewer数は増えず、revisionが1増えます。調査するCommitは、再生成開始時点でアプリが取得済みのRepositoryの最新Commitです。GitHubに新Commitがあっても、Sync前に自動取得する操作ではありません。

### P2-07: 実行中の中止と既存Viewer保持

1. 試験用Aの本文とrevisionを控え、再生成を開始します。
2. `running`、できれば「Repositoryを調査」の段階で「中止」を押します。
3. 最終状態まで待ちます。中止要求のHTTP受付だけで成功と判断しないでください。
4. 「Viewerを開く」で試験用Aへ戻ります。

期待結果: Jobは`cancelled`となり、「Viewerの生成を中止しました」と表示されます。通常の中止で`failed / GENERATION_FAILED`にならないことを確認します。既存Viewerの本文・revision・Commitは変わりません。

生成の保存が先に完了した場合は、最終状態が`completed`になることがあります。この試行は中止成功には数えず、別Jobで再確認してください。新規作成でも中止を試し、その場合はViewerが追加されないことを確認します。

### P2-08: 同じ条件で再試行

1. P2-07で`cancelled`になったJob画面を開きます。
2. 「同じ条件で再試行」を押します。
3. 新しいJob IDへ移動したことを確認し、完了を待ちます。
4. 元JobをAPIで再取得し、状態を比較します。

期待結果: 別のJobが作成され、`retry_of_job_id`に元Job IDが入ります。元Jobは`cancelled`のままです。再生成の再試行なら同じViewerを更新し、新規作成の再試行なら成功時にViewerを作成します。

「再生成」は取得済み最新Commitを使い、「同じ条件で再試行」は元Jobに保存された条件とCommitを使います。再試行までに対象Viewerが別の再生成で更新された場合は、`409 VIEWER_CHANGED`で拒否されます。

### P2-09: Desktop / Mobileと文書の読みやすさ

1. ブラウザのレスポンシブ表示で幅1,440px、1,024px、768px、390px、320pxを確認します。
2. 長い見出し、本文、ソースパス、表、コード、図が読めるか確認します。
3. 768px未満で目次を開閉し、狭い画面でも操作ボタンに到達できることを確認します。
4. 4組のTheme / Densityで文字の見やすさとフォーカス表示を確認します。

期待結果: Viewer本文containerが1,024px未満ではblockが1列になります。表・コードは領域内で横スクロールでき、ページ全体を横に押し広げません。多列表の文字が1文字ずつ縦に折れないことも確認します。

12種類すべてのblockが1回の実生成に含まれる必要はありません。未出現のblockは未確認とし、7章のrendererテストと[全block合成表示の過去記録](./verification/2026-11-09-viewer-ui-verification.md)を区別して参照してください。文書種別による説明の違いも確認する場合は、技術ガイド・処理フローで試験用Viewerを追加生成します。

### P2-10: Viewer削除とキャンセル

1. active Jobがないことを確認し、削除してよい試験用Viewerを開きます。
2. 「削除」を押し、確認ダイアログのタイトルが対象と一致することを確認します。
3. 一度「キャンセル」し、Viewerが残ることを確認します。
4. 再び開いて「Viewerを削除」を確定します。
5. Dashboardへ戻ったことと、対象Viewerが一覧から消えたことを確認します。
6. 対象IDをAPIで取得し、`404 VIEWER_NOT_FOUND`になることを確認します。

期待結果: 削除APIは`204 No Content`です。対象Viewerの管理refも削除されます。Repository、他のViewer、GitHub上のRepositoryは保持されます。対応する完了Jobは残り、削除後の`viewer_id`は`null`になります。完了Jobが残っていることを削除失敗には数えません。

## 5. 異常系・競合のテスト

### P2-11: 生成受付エラーと入力保持

生成無効の確認は、active Jobがない状態で`.env`の`GENERATION_ENABLED=false`を設定し、Backendを再起動して行います。フォームに入力して「生成を開始」を押してください。確認後は元の設定へ戻し、再起動します。

期待結果: `503 GENERATION_DISABLED`、code・説明・trace IDが表示され、入力は保持されます。新しいJobは作られず、自動再送を繰り返しません。既存Viewerの閲覧は継続できます。

ほかの失敗は、条件が再現した場合に以下を確認します。再現のために通常のCodex設定、認証、権限を壊す必要はありません。再現できなかった項目は「未実施」とし、自動テストの成功と区別してください。

| 条件 | 期待するエラーと確認事項 |
|---|---|
| Codexへ接続できない | `503 CODEX_UNAVAILABLE`。接続確認と明示的な再試行を案内する |
| Codexの安全設定確認に失敗 | `503 CODEX_SANDBOX_UNSUPPORTED`。権限を広げて続行せず、入力を保持する |
| 保存先DBが非UTF8 | `503 DATABASE_ENCODING_UNSUPPORTED`。Job作成・モデルTurn前に停止する。既存DBを非UTF8へ変更して試す操作は不要 |
| Backendとの通信断 | 通信エラーを表示し、入力を保持する。Backend復帰後に利用者が再試行できる |

受付前のHTTPエラーと、受付後のJobの`failed`は区別してください。Jobが非再試行可能なエラーになった場合は、「同じ条件で再試行」を表示しません。

### P2-12: 同時生成・Sync・削除の拒否

試験用Aを残し、同じRepositoryのDashboardとViewerを別タブで開きます。再生成の`queued / running`中に、次の操作を確認します。Jobが終わっていた場合は競合試験として数えません。

| 操作 | 期待結果 |
|---|---|
| 別のViewer生成または再生成 | `409 GENERATION_ALREADY_RUNNING`。新しいJobを作らない |
| 同じRepositoryの「最新コードを取得」 | `409 REPOSITORY_BUSY`、または画面で操作不可。生成中のCommitを変更しない |
| 同じRepositoryの削除 | `409 REPOSITORY_BUSY`、または画面で操作不可 |
| 再生成対象の試験用Aを削除 | `409 VIEWER_BUSY`。試験用Aが消えない |

画面でボタンが無効ならUIの確認結果を記録し、HTTPの拒否まで確認したことにはしません。APIで補足する場合は6章を使用します。削除APIはJob終了後なら実際に削除するため、対象は必ず試験用データに限定してください。

Job終了後も、Viewerが残るRepositoryの削除は`409 REPOSITORY_IN_USE`または操作不可になります。試験のために通常のRepositoryを削除する必要はありません。

### P2-13: 再生成失敗時の本文保持

1. 試験用Aのrevision・Commitと、6.2の本文・HTMLのhashを控えます。
2. 再生成し、実行中の失敗が起きた場合にJob IDとエラーを控えます。
3. 試験用Aを再取得して比較します。

期待結果: 既存Viewerの本文・HTML・revision・Commitが保持されます。再試行可能な`failed`には再試行ボタンがあり、非再試行可能なら表示しません。

通常設定を壊して失敗を誘発する操作は含めません。実失敗を観測できなければ、この項目は未実施とし、7章のFake結合テストで確認した範囲を別記します。中止試験だけで失敗時の保持を確認済みにはしません。

### P2-14: Backend再起動時の中断回復

1. 試験用Viewerの再生成を開始し、Job IDを控えます。
2. `queued / running`中にBackendのターミナルで`Ctrl+C`を押します。アプリ全体が停止するため、ほかのテストとは同時に行いません。
3. 3.1のコマンドでBackendを再起動します。
4. 控えたJobをAPIで再取得し、試験用Viewerも開き直します。

起動時にDBへ`queued / running`が残っていた場合の期待結果は、`failed / OPERATION_INTERRUPTED`と、既存Viewerの保持です。自動でモデル処理を再開しません。再試行可能なら利用者の操作で新Jobを作成できます。

終了処理が先に`cancelled`などへ確定した場合、その状態を維持します。すでに`completed`なら中断回復の確認にはなりません。端末停止だけで残存active Jobを必ず再現できるとは限らないため、実際の終端状態を記録してください。

## 6. API・保存状態を直接確認するコマンド

### 6.1 IDの設定とGET

API操作用ターミナルで、自分のテスト対象IDを設定します。変数代入は、このターミナル内で後続コマンドへ渡す値を保存するだけです。

```bash
# APIの接続先と、画面URL等で控えた各IDを設定します。IDは実際のUUIDに置き換えます。
api_base='http://127.0.0.1:8000'
repository_id='<Repository ID>'
viewer_id='<試験用Viewer ID>'
job_id='<Job ID>'

# 対象Repositoryに保存されたViewerの一覧を取得します。
curl -sS "$api_base/api/repositories/$repository_id/viewers"

# Viewerのmetadata、構造化本文、保存HTMLを取得します。生成処理は実行しません。
curl -sS "$api_base/api/viewers/$viewer_id"

# Jobの永続状態、元Job ID、エラー等を取得します。終端状態の確認に使います。
curl -sS "$api_base/api/generation-jobs/$job_id"

# Jobの進捗イベントをバッファせず逐次表示します。30秒でこの接続だけを終了します。
curl -N --max-time 30 "$api_base/api/generation-jobs/$job_id/events"
```

`-N`は受信したSSEを逐次表示する指定です。30秒の終了や`Ctrl+C`でcurlを止めても、Jobの中止要求にはなりません。終了コード28は、この例では接続の待機上限に達したことを示します。再起動等でSSEの過去イベントがない場合も、Job詳細GETで状態を確認します。

### 6.2 表示設定変更前後の比較

次のコマンドをP2-04の前後、または再生成の中止・失敗の前後で実行し、出力を比較します。Repositoryルートで実行してください。

```bash
# APIからViewerを取得し、本文そのものを出力せず、revision・Commit・本文/HTMLのSHA-256を表示します。
.venv/bin/python - "$api_base" "$viewer_id" <<'PY'
import hashlib
import json
import sys
from urllib.request import urlopen

with urlopen(f"{sys.argv[1]}/api/viewers/{sys.argv[2]}", timeout=30) as response:
    viewer = json.load(response)
document = json.dumps(viewer["content_json"], ensure_ascii=False, sort_keys=True)
print(json.dumps({
    "id": viewer["id"],
    "revision": viewer["content_revision"],
    "commit": viewer["commit_sha"],
    "theme": viewer["theme_slug"],
    "density": viewer["density"],
    "document_sha256": hashlib.sha256(document.encode()).hexdigest(),
    "html_sha256": hashlib.sha256(viewer["sanitized_html"].encode()).hexdigest(),
}, ensure_ascii=False, indent=2))
PY
```

SHA-256は内容の比較に使う値です。表示設定変更、中止、失敗の前後で2つのhashが同じなら、取得した本文とHTMLは同じです。再生成成功後は本文が変わり得るため、hashの一致は要求しません。

### 6.3 作成APIと二重送信防止

この節は実際に生成を開始します。ほかのJobが動いていない状態で、追加の試験用Viewerを作ってよい場合だけ実行してください。

```bash
# 作成要求を識別するUUIDを1つ発行します。同じ要求を再送するときは、この値を変えません。
idempotency_key="$(.venv/bin/python -c 'import uuid; print(uuid.uuid4())')"

# 条件を指定して非同期Jobを作成します。-iでHTTPステータスとLocation等も表示します。
curl -i -sS -X POST "$api_base/api/repositories/$repository_id/viewers" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $idempotency_key" \
  --data-binary '{"request":"READMEと主要な実装の概要を説明してください。","document_type":"technical_guide","detail_level":"overview","target_audience":"beginner","theme_slug":"technical-light","density":"comfortable","additional_instruction":"削除予定の手動テスト用Viewerです。"}'
```

`Content-Type`はJSON形式を指定します。`--data-binary`は上のJSONをそのまま送信します。`Idempotency-Key`は同じ要求からJobを二重に作らないための識別子です。

同じcurlを、同じキー・同じ本文で再実行してください。`202`と同じ`id`が返り、Jobが増えないことが期待結果です。同じキーのまま`request`だけ変更すると、`409 IDEMPOTENCY_KEY_REUSED`になります。別の生成には新しいキーを発行します。

入力上限や不正な選択肢も確認する場合は、[Swagger UI](http://127.0.0.1:8000/docs)の同APIで、Requestが4,001文字、Additional Instructionが4,001文字、未定義のenum、必須ヘッダーなしをそれぞれ送信します。期待結果は`422`、Job・Viewerが増えないことです。UIでのエラー表示の有無と、APIの入力拒否は分けて記録してください。

### 6.4 更新・中止・再試行・削除

次のコマンドは状態を変更します。画面テストと同じ操作をAPIで補足したい場合に使い、各操作に適した状態の試験用IDを指定してください。

```bash
# Codexを再実行せず、保存済みViewerのThemeとDensityだけを変更します。
curl -i -sS -X PATCH "$api_base/api/viewers/$viewer_id/appearance" \
  -H 'Content-Type: application/json' \
  --data-binary '{"theme_slug":"editorial","density":"compact"}'

# 新しい要求キーを発行します。再生成POSTの応答を失った場合の再送には同じ値を使います。
regenerate_key="$(.venv/bin/python -c 'import uuid; print(uuid.uuid4())')"

# 保存済み条件と取得済み最新Commitで、同じViewerを再生成するJobを開始します。
curl -i -sS -X POST "$api_base/api/viewers/$viewer_id/regenerate" \
  -H "Idempotency-Key: $regenerate_key"

# 指定したJobの中止を要求します。再生成を止める場合は、上の応答のidをjob_idへ設定し直します。
curl -i -sS -X POST "$api_base/api/generation-jobs/$job_id/cancel"

# 元Jobから別の再試行Jobを作るため、新しい要求キーを発行します。
retry_key="$(.venv/bin/python -c 'import uuid; print(uuid.uuid4())')"

# 中止済み、または再試行可能な失敗Jobを、元の条件とCommitで再試行します。
curl -i -sS -X POST "$api_base/api/generation-jobs/$job_id/retry" \
  -H "Idempotency-Key: $retry_key"
```

再生成・再試行は`202`、表示設定保存は`200`が期待結果です。中止は処理中なら`202`、すでに終端なら`200`で現在状態を返します。中止の最終結果は、Job詳細GETで確認してください。

削除だけは別に掲載します。active再生成Jobがない場合、確認ダイアログを経ずに実際に削除されます。

```bash
# 試験用Viewerとその管理refを削除します。対象IDを再確認してから実行してください。
curl -i -sS -X DELETE "$api_base/api/viewers/$viewer_id"
```

### 6.5 Git refの保持と後始末

アプリの管理Workspaceを読み取って確認する場合の補足です。開発用Repositoryのルートと、調査対象の管理Workspaceを混同しないでください。パスの末尾は対象Repository IDです。

```bash
# WORKSPACE_ROOTが既定値の場合の管理Cloneへのパスを、このターミナルの変数へ保存します。
managed_repo=".data/workspaces/repositories/$repository_id"

# 保存済みViewerの各revisionを保持するrefと、対応するCommitを一覧表示します。
git -C "$managed_repo" for-each-ref \
  --format='%(refname) %(objectname)' "refs/repospec/viewers/$viewer_id/revisions/"

# 実行中の生成を保持する一時refを調べます。全Job終了後は残っていないことを確認します。
git -C "$managed_repo" for-each-ref \
  --format='%(refname) %(objectname)' refs/repospec/generation/

# 管理Cloneの追跡ファイルに変更がないことを確認します。空出力ならクリーンです。
git -C "$managed_repo" status --porcelain
```

保存済みViewerのrefのCommitは、そのViewerの`commit_sha`と一致します。Sync後も旧CommitのViewerを開けることを確認してください。再生成成功後は現revisionのrefがあり、通常は旧revisionのrefが片付きます。Viewer削除後はそのViewerのref一覧が空になります。

`WORKSPACE_ROOT`を変更している場合は、`managed_repo`の値を合わせます。この節のコマンドは読み取りのみです。`update-ref -d`などでアプリの管理refを手動削除しないでください。

## 7. 自動テストを併用する場合

手動テストとは別の結果として記録します。通常のBackendテストはFake App ServerやSQLite等を用いるため、成功しても実Codexの安全性検査や実PostgreSQL・ブラウザ操作の代わりにはなりません。

```bash
# Backendの検証・renderer・Job・API・中止・保存失敗時保持等の回帰テストを実行します。
.venv/bin/pytest

# Pythonコードの静的チェックを実行します。
.venv/bin/ruff check backend

# Pythonコードの整形規則への適合を調べます。ファイルは書き換えません。
.venv/bin/ruff format --check backend

# Frontendのフォーム、Job、Viewer、サニタイズ等のコンポーネントテストを実行します。
npm --prefix frontend test

# Frontendの静的チェックを実行します。
npm --prefix frontend run lint

# TypeScriptの型検査と本番用Frontendのビルドを実行します。
npm --prefix frontend run build
```

HTMLの不正要素除去、未知blockの拒否、12種blockの描画、ソースパス・行範囲の検証は、自動テストでも確認します。モデルへの依頼だけでは不正出力を確実に作れないため、実生成で攻撃文字列が出なかったことをサニタイズの証拠にはしません。

## 8. 画面操作を受けてアプリが内部で行う処理

この節は動作の説明です。表中のHTTP・JSON-RPC・Gitコマンドを、ターミナルへ順番に貼り付ける必要はありません。

| 操作・段階 | 内部のAPI・コマンド | 目的と処理内容 |
|---|---|---|
| Backend起動 | `codex app-server`、`initialize`、`initialized` | 固定の外部機能無効化設定で子プロセスを起動し、JSON-RPC接続を初期化する |
| フォーム表示 | `GET /api/viewer-options` | 文書種別、詳細度、対象読者、Theme、Densityの候補と初期値を取得する |
| 生成受付 | `POST /api/repositories/{id}/viewers` | 入力・生成フラグ・DB文字コード・接続と安全設定・排他を確認し、Jobを保存する |
| 調査Commitの保持 | `git update-ref refs/repospec/generation/{job_id} <commit> <zero-sha>` | 調査中のCommitが失われないよう、一時的なローカルrefを新規作成する |
| Job固有の安全検査 | `config/read`、`configRequirements/read` | 調査先cwdの有効設定、managed制約、shell環境等を確認する |
| 調査Thread準備 | `thread/start`、`experimentalFeature/list`、`mcpServerStatus/list` | 読取り専用Profileとroot、外部機能無効化、全ページの実行時状態を確認する |
| ソース調査 | `turn/start` | 生成条件とViewerDocumentのJSON Schemaを渡す。ThemeとDensityはモデルへ渡さない |
| 進捗表示 | `GET /api/generation-jobs/{id}/events`、Job詳細GET | 検証済みの進捗をSSEで配信し、RESTでも永続状態を確認する |
| 参照検証 | `git ls-tree`、`git cat-file` | 指定Commitの実ファイル・blob・行数で参照を検証する。任意のホストファイルを開かない |
| 文書保存 | Pydantic検証、renderer、sanitizer、`git update-ref` | 構造化文書を検証し、HTMLを生成・サニタイズする。revision用refを用意し、ViewerとJob完了を同じDB transactionで保存する |
| 中止 | `POST /api/generation-jobs/{id}/cancel`、必要に応じ`turn/interrupt` | 中止要求を保存し、実行段階に応じて停止する。終端状態はDBで確定する |
| 表示設定 | `PATCH /api/viewers/{id}/appearance` | ThemeとDensityを更新する。モデル実行・本文やHTMLの再生成は行わない |
| 再生成 | `POST /api/viewers/{id}/regenerate` | 取得済み最新Commitで新Jobを作り、成功時だけ同じViewerのrevisionを更新する |
| 再試行 | `POST /api/generation-jobs/{id}/retry` | 元Jobの条件とCommitを引き継ぐ新Jobを作る。元Jobは変更しない |
| Viewer削除 | `DELETE /api/viewers/{id}`、`git update-ref -d` | active再生成を拒否し、対象のrevision用ref、Viewer行を削除する。GitHubへのPushは行わない |
| 起動回復 | Job状態更新、ref照合 | 残存active Jobを中断失敗へ変え、孤立した一時ref等を片付ける。自動生成再開は行わない |

## 9. 結果の記録と終了

結果表をコピーし、OK・NG・未実施を記入してください。未実施の場合は理由を残します。コード修正が必要な問題は、再現操作、Job ID、error code、trace IDとともに記録します。

```text
実施日時:
実施者:
アプリのCommit:
OS / ブラウザ / 画面幅:
固定CLIのバージョン:
DB文字コード / Migration:
Repository URL / ID / 調査Commit:
生成の安全性検査: 今回実施 / 同一環境の受入記録を参照（参照日・変更有無）
今回作成したViewer ID / Job ID:
```

| ID | 確認内容 | 結果 | Job / Viewer ID・補足 |
|---|---|---|---|
| P2-01 | 入力・初期値・プレビュー・空入力 | 未実施 | |
| P2-02 | 生成・進捗・保存・二重送信防止 | 未実施 | |
| P2-03 | 本文・目次・参照・再読み込み | 未実施 | |
| P2-04 | 表示設定・キャンセル・本文不変 | 未実施 | |
| P2-05 | 画面移動・Job復帰 | 未実施 | |
| P2-06 | 再生成・同じID・revision更新 | 未実施 | |
| P2-07 | 中止・既存Viewer保持・新規非保存 | 未実施 | |
| P2-08 | 同条件再試行・別Job | 未実施 | |
| P2-09 | Desktop / Mobile・Theme / Density | 未実施 | |
| P2-10 | 削除キャンセル・確定・対象だけ削除 | 未実施 | |
| P2-11 | 受付エラー分類・入力保持 | 未実施 | 再現できた分類を個別に記載 |
| P2-12 | 同時生成・Sync・削除の競合拒否 | 未実施 | UI拒否とAPI拒否を区別 |
| P2-13 | 再生成失敗時の本文保持 | 未実施 | 実失敗とFakeを区別 |
| P2-14 | Backend再起動・中断回復 | 未実施 | 実際の終端状態を記載 |
| 補足 | API上限・不正値・Idempotency | 未実施 | |
| 補足 | Git ref・Git status・Sync後の旧Viewer | 未実施 | |
| 補足 | 自動テスト・lint・build | 未実施 | 実Codex検査と分けて記載 |

終了前に、試験で作った不要なViewerを画面から削除し、残すViewerを再表示してください。active Jobがあれば中止して最終状態を確認します。生成無効テスト等で変更した設定も元の値へ戻してください。DB・Workspace・管理refの一括削除は不要です。

Frontend、Backendを起動した各ターミナルで`Ctrl+C`を押すと、それぞれのサーバーを終了できます。Backendは子のCodex App Serverや実行中Taskの終了処理も行います。Python仮想環境を有効にしたターミナルでは、次で抜けられます。

```bash
# 現在のターミナルのPATH等を仮想環境の有効化前へ戻します。ファイルやDBは削除しません。
deactivate
```
