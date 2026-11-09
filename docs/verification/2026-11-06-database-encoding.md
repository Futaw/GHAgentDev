# Phase 2 通常環境のDB文字コード

2026-11-06、main `4bbc728`で、利用者が`.env`へ`GENERATION_ENABLED=true`を1行設定しBackendを再起動した後の確認。

設定は重複なしで有効だった。Backend接続・認証・Public Repositoryのready、同期Commitを確認し、画面からJobを作成した。文書・ソース参照・HTMLの検証後、saving_viewerでGENERATION_FAILEDとなり、Viewerは保存されなかった。

## 実測と原因

- 対象: Futaw/GHAgentDev、管理ID `92ea0a32-90ee-4635-b641-e6d5feb8a900`、main `4bbc728`。
- 画面で作成したJob: `3e986578-b5df-49b9-8686-6d11643a8a44`。診断用の同条件Job: `0eca5352-89b5-4ff7-a9f8-ee28ec166faf`。どちらもfailed、Viewerなし。診断側のCodexは停止済み。
- 通常DBのmigration head、列型、timezone、外部キー、テーブル権限は想定どおりだった。保存単体は専用UUIDの合成行を外側transactionでrollbackして確認し、行の残存なし。専用Git refの作成・解決・削除も成功。
- 同じRepository・通常DBのGenerationRunnerで再現し、DBAPIError / SQLSTATE **22P05**を記録。例外message・SQL値・生モデル出力は記録していない。
- DBは**EUC_JP**、clientはUTF8、server version_numは170000。固定文字のSELECTで、普通の日本語は通り、絵文字とem dashは同じ22P05で拒否された。既存レコードを変更する再現試験は不要だった。
- 診断時の保存入力はtitle 21文字・summary 105文字・HTML 12,411文字。NULは検出されなかった。実際に失敗した生成本文の特定文字を記録したものではない。

EUC_JPで表現できないUnicodeを保存しようとしたことが、通常環境の保存阻害要因である。`client_encoding=UTF8`だけを設定しても、server側の文字集合は広がらない。[PostgreSQLの文字コード仕様](https://www.postgresql.org/docs/17/multibyte.html)と[JSONの制約](https://www.postgresql.org/docs/17/datatype-json.html)も参照。

過去の専用PostgreSQL schemaの実保存成功は、その試験内容が保存できた証拠である。schemaはDBの文字コードを共有するため、あらゆるUnicodeを保存できる根拠にはならない。安全性の9gate合格と、保存先DBの適合性は分けて確認する。

## 修正

- Generationの受付前とrunner開始時に、PostgreSQLのserver_encodingがUTF8か確認する。非UTF8はJob作成・モデルTurn前に止める。保存済みRepository/Viewerの閲覧やChatを一律停止する変更ではない。
- `503 DATABASE_ENCODING_UNSUPPORTED`、retryable falseとtrace IDを返す。画面はCodex sandboxの問題と混同せず、入力を保持する。SQLiteは隔離test向けUnicode環境として扱う。
- 予期しないrunner例外は、固定のoperation、例外class、5桁のSQLSTATEだけをログへ追加。message、statement、params、生成本文、接続文字列は出さない。
- DB準備コマンドを追加。既定はdry run。`--create`を付けた場合だけ、別名の空DBをtemplate0 / UTF8 / libc C localeで作る。旧DBの変更、行のコピー、認証・権限変更、`.env`の書換えはしない。既存targetの上書き・削除も行わない。

## 自動・実機確認

Backend **184 passed**、Frontend **30 passed**、Ruff/format・ESLint・TypeScript/Vite build成功。依存Zod由来のannotation警告あり。結果は[JSON記録](./2026-11-06-database-encoding.json)を参照。非UTF8時の受付拒否・Jobなし・Turnなし、UTF8/SQLiteの受理、SQL値の非公開、画面の入力保持・POST自動再試行なし、DB名のSQL注入拒否、dry runの無変更、既存target・権限不足の拒否を検証する。

現在の実EUC_JP DBに対する事前検査はモデル実行前の拒否となった。準備コマンドの実dry runでは、旧DBはrepospec_viewer_manual、新DB名repospec_viewer_utf8は未使用、接続roleは作成権限あり。DB作成は利用者操作待ちで、実作成・UTF8環境への切替・その後の実Viewer成功はまだ確認していない。

## 利用者にお願いする手順

この修正PRをマージしてmainをPullした後に行う。現在の通常DBはRepository 1件、Viewer 0件。旧DBの登録・失敗Jobと旧Workspaceは残し、新DBへ自動コピーしない。

1. Backendを起動したターミナルでCtrl+Cを押す。Frontendは起動中のままでよい。
2. Repositoryのルートで、確認後に新しいDBを作成する。

   ```bash
   .venv/bin/python -m backend.scripts.prepare_utf8_database
   .venv/bin/python -m backend.scripts.prepare_utf8_database --create
   ```

   dry runで`target_exists: false`、`can_create_database: true`を確認する。作成後は`created: true`と`target_encoding: UTF8`を確認する。失敗した場合は止め、認証情報やDATABASE_URL全文を共有せず、出力された固定分類だけを伝える。既存DBがある場合に削除してやり直さない。

3. ご自身で`.env`のDATABASE_URLの**DB名部分だけ**を`repospec_viewer_manual`から`repospec_viewer_utf8`へ変更する。driver・user・password・host・portは変えない。`GENERATION_ENABLED`は一旦falseへ戻し、重複行は作らない。`.env`の内容は共有しなくてよい。
4. 新しい接続先へtableを作成する。

   ```bash
   .venv/bin/alembic upgrade head
   ```

5. Backendを再起動する。

   ```bash
   .venv/bin/python -m uvicorn backend.app.main:app \
     --workers 1 --host 127.0.0.1 --port 8000
   ```

完了後「UTF8 DBへ切り替えて再起動済み」と連絡する。新DBは空なので、旧Repositoryが一覧から消えるが、旧DB・Workspaceを削除したためではない。Codex側で接続・encoding・migrationを確認し、同じPublic URLを再登録して新しい管理IDを案内する。その後に生成を再有効化し、画面E2Eを再開する。

旧DBはこの手順では変更・削除しない。必要なら接続先を旧名へ戻すと旧登録を参照できる。既存データの移行が必要になった場合は別途計画し、dump/restoreや旧DB削除をこの手順へ追加しない。template0とlocaleの指定は[CREATE DATABASE公式仕様](https://www.postgresql.org/docs/17/sql-createdatabase.html)に基づく。

## 残る確認

通常画面からの生成・保存、再生成、中止、削除、Desktop/Mobileの全block確認は、UTF8への切替後に再開する。Phase 2は未完了。Codexが起動した診断processと専用ref・rollback行は後始末済みで、利用者の通常Backendは停止していない。生成フラグtrueへの変更は利用者自身の操作であり、今回の修正作業では`.env`を変更していない。

通常画面での保存失敗は[画面記録](./2026-11-06-viewer-save-failure.png)へ保存した。見出しが生成中のままでも、statusとエラーはfailedであり、成功扱いにはしていない。
