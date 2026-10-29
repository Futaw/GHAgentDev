# RepoSpec Viewer Phase 2 詳細設計の引き継ぎ

- 更新日: 2026-10-30
- 引き継ぎ先: Phase 2の設計を扱う新しいチャット
- 作業対象: Phase 2「Viewer生成と保存」の詳細設計の確認・補完
- 実装: この引き継ぎでは行わない

この文書は、別のチャットでPhase 2の設計または実装作業をすぐ再開するための引き継ぎ資料である。現在の仕様は[Phase 2詳細設計書](./phase-2-detailed-design.md) v1.3を参照する。次の作業は同設計書21章の安全設定・表示・事前確認scriptの実装修正である。

## 1. 現在の状態

Phase 2詳細設計書v1.0はPull Request #16、v1.1はPull Request #22で`main`へマージ済みである。v1.2では、Codex CLI `0.164.0`の実装に合わせ、存在しない`sandboxPolicy.readOnly.access`を前提としたgateをPermission Profile方式へ変更した。Viewer構成、block catalog、状態遷移、Git refなどv1.1の設計方針は変更していない。

Phase 0のChat進捗表示、画面移動中のSession維持、Sessionエラー復帰を含むPull Request #20は、2026-10-21時点で`main`へマージ済みである。Phase 2の設計は最新の`main`を前提とする。

Phase 2実装はPR #24でmainへマージ済みであり、Fake Codex + SQLiteで生成・検証・保存を確認した。実Codexの事前確認は`config/read`、`configRequirements/read`の応答後、`plugin/list`でtimeoutした。動作gateは未実行であり、不合格と読み替えない。

v1.3は既存App ServerとPermission Profileを維持し、起動時の外部機能無効化、cwd別設定、ThreadのProfile/root・feature/MCP runtime検査へ改訂した。非認証fixtureでの限定確認はできたが、この改訂の実装修正と認証付き動作gateは未完了である。`GENERATION_ENABLED=false`を維持する。

## 2. これまでの話し合いで決めた方針

### 2.1 固定レイアウトにしない

すべてのViewerを同じ章立てや同じページ配置へ当てはめると、情報量や説明対象の違いを取り込みにくくなる。そのため、ページ全体は固定テンプレートにしない。

Codexは説明内容に応じてセクション、順序、見出し、block type、blockの内容を選ぶ。アプリのrendererは、その構造化データから表示幅、組み合わせ、レスポンシブ表示を決める。

### 2.2 一貫性は共通ルールで保つ

一貫性は、本文の章立てを同じにすることではなく、次の共通ルールで保つ。

- Viewer Header、目次、本文領域、ソース参照の操作
- blockごとの見た目、見出し、余白、表、code、diagramの表示規則
- block typeごとの必須項目、件数、文字数、参照関係
- rendererが管理する表示幅、2列表示、1列への切り替え
- Themeによる配色と書体、Densityによる余白と文字の密度

### 2.3 Codexが決める範囲を限定する

| Codexが選べるもの | アプリが決めるもの | Codexが出力できないもの |
|---|---|---|
| セクション数と順序 | 利用できるblock catalog | 任意のHTMLタグと属性 |
| 見出しと説明内容 | blockのDOM構造とclass | CSS、色、font、余白 |
| 意味に合うblock type | 表示幅とレスポンシブ配置 | JavaScriptとevent handler |
| ソース参照 | ThemeとDensity | 座標、幅、高さ、grid列数 |
| 調査上の制約や不明点 | 検証、サニタイズ、表示の操作 | 外部画像、外部script、未定義block |

### 2.4 `blocks[]`による差の扱い

`blocks[]`の選び方により、Viewerごとに情報の並べ方や見せ方の差は残る。これは内容に合わせて構成を変えるために必要な差であり、完全には無くさない。

一方で、Codexが任意の表現方法を作るわけではない。差が大きくなりすぎないように、次の制御を設ける。

1. block typeを12種類の型付きcatalogに限定する。
2. Document Typeは固定テンプレートではなく、推奨する説明観点を示すprofileとする。
3. Pydantic validatorで型、必須項目、上限、ID参照、block固有条件を検証する。
4. rendererがblock typeと情報量から配置を決め、Codexには配置を指定させない。
5. block単体だけでなく、複数blockの組み合わせ、長文、情報量の少ない文書、Desktop、Mobileをtestする。

したがって、残る可能性は「内容の選び方による構成の差」である。色、余白、任意のレイアウト、操作方法がViewerごとに無制限に変わる設計ではない。

## 3. 現行設計の要点

### 3.1 ViewerDocument

Viewer本文の正本は、Codexが生成する`ViewerDocument`構造化JSONとする。HTMLは検証済みの`ViewerDocument`から生成する導出データである。

初期catalogは次の12種類である。

`paragraph`、`bullet_list`、`key_value`、`table`、`code`、`callout`、`steps`、`flow`、`state_diagram`、`comparison`、`component_map`、`source_evidence`

### 3.2 HTML renderer

rendererは完全なHTML documentではなく、Viewer本文のHTML fragmentを作る。ReactはViewer Header、目次、操作、将来のQ&A領域を管理する。HTML fragmentはThemeとDensityに依存させない。

Desktopではblockの種類と情報量により全幅または最大2列で表示する。Viewer本文containerが1,024px未満の場合はすべてを1列にする。blockの順序は並べ替えない。

### 3.3 生成と保存

- ViewerはGeneration Job成功時だけ作成する。
- 進捗はSSEで通知する。
- 再生成中も現在のViewerは表示できる。成功時だけ内容を置き換える。
- ThemeとDensityの変更ではCodexとrendererを再実行しない。
- Viewerの生成元CommitはGit refで保持する。
- SourceReferenceは生成元Commitの実ファイルと行範囲に対して再検証する。

### 3.4 安全性

Codexが返したHTML、CSS、JavaScriptは表示しない。バックエンドは検証済みの構造化データからHTMLを作り、サーバー側でサニタイズする。フロントエンドは受信したHTMLにDOMPurifyを再適用する。

### 3.5 Phase 2の対象外

Viewer内Q&A、ConversationとMessageの永続化、Source Code Viewer、共有URL、ユーザー定義テーマ、版管理、PDF・HTMLエクスポートはPhase 2に含めない。

## 4. 現行設計と当初案の違い

| 当初案 | 現行設計 |
|---|---|
| 全Viewerに共通の固定構成を当てはめる | 内容に合わせてセクションとblockを選ぶ |
| テンプレート全体で見た目を揃える | block、共通shell、rendererの配置規則で揃える |
| Document Typeが章立てを固定する | Document Typeは推奨する説明観点を示す |
| Codexがレイアウトも出力する余地がある | Codexは意味構造だけを出力し、配置はrendererが決める |
| テーマだけを切り替える | ThemeとDensityを分け、本文と切り離す |
| 画面モックを実装形とする | 画面モックは生成結果の一例として扱う |

## 5. 精査で確認したこと

現行設計の方針を保ちながら、次の点を確認し、Phase 2詳細設計書v1.1へ反映した。

1. 12種類のblockは維持し、似た型の選択規則と重複禁止を追加した。
2. block typeごとのcompact判定と、隣接blockを2列化する規則を数値で定義した。
3. diagramを表形式へ切り替える条件をnode数、edge数、次数、段階、group数で定義した。
4. Document Type profileを調査時の確認項目とし、根拠がない観点と明示要求時のlimitationsを定義した。
5. Job状態更新をcompare-and-setとし、queued中を含むSync・Generation・削除の競合制御を定義した。
6. Viewer revisionごとの不変Git refへ変更し、DB失敗時に既存Viewerを巻き戻さない方式にした。
7. Viewer本文containerのCSS Container Queryにより、Phase 3のQ&A pane追加時もrenderer HTMLを変更せず1列化できるようにした。
8. SSEと5秒間隔のREST確認を併用し、in-memory buffer喪失後の復帰を定義した。

## 6. 次の実装修正の注意点

ローカルにはChatGPTデスクトップアプリ同梱の`0.154.0-alpha.6.2`と、`/Users/futaw/.local/bin/codex`の`0.164.0`が併存する。Phase 2 Generationは後者を`CODEX_EXECUTABLE`で明示し、前者へfallbackしない。

`0.164.0`で生成したApp Server schemaにも`readOnly.access.readableRoots`は存在しない。v1.2はこれをCLI更新待ちとせず、`thread/start.params.config`でJob固有のPermission Profileを渡す。Profileはfilesystem全体をdenyとし、必要最小限のruntime pathと対象Repositoryのみread、networkはdisabledとする。旧sandbox設定との併用、外部toolの残留、設定の不受理はすべてfail closedとする。

CLI 0.164.0の生成型定義で`plugin/list`の現在の引数は有効だが、`disabledPluginIds`は保存用でPlugin機能をfilterしないと確認した。一覧取得は安全性の必須経路から除き、起動feature無効化とThread runtimeの検査で代替する。取得失敗を空一覧へ変換しない。timeoutの内部原因は未特定である。

起動・Threadの限定確認と、その証拠の限界は詳細設計14.2、採用設定と確認順序は14.3〜14.5、改修後harnessの合否基準と有効化条件は14.6に従う。実装済み、Fakeで検証済み、実Codexで検証済みを分け、実動作の読み取り範囲・非変更・command network拒否・実生成を完了扱いしない。変更対象ファイルと実装後の手動確認は21章を正本とする。

## 7. 参照順序

1. `AGENTS.md`
2. `WORKLOG.md`
3. [概要仕様](./README.md)
4. [Phase 2詳細設計書](./phase-2-detailed-design.md)
5. [フロントエンド仕様](./frontend-spec.md)
6. [バックエンド仕様](./backend-spec.md)
7. [Phase 1詳細設計書](./phase-1-detailed-design.md)
8. `backend/app/`と`frontend/src/`の実装
9. [完成時の画面モック・操作ガイド](./mockups/repospec-viewer-screen-guide.html)

画面モックは表示例であり、本文を固定レイアウトにする根拠として扱わない。

## 8. 2026-10-22の精査で実施した作業手順（過去の記録）

1. 作業ツリーと現在のブランチを確認した。
2. `main`を`origin/main`の最新状態へ更新した。
3. 参照順序に従って設計書と実装を読んだ。
4. 現行設計の矛盾、未定義、過剰な複雑さを根拠とともに整理した。
5. `codex/refine-phase-2-design`ブランチで設計書だけを更新した。
6. 上位仕様と詳細設計の整合性、Markdown、リンク、例示の構文を確認した。
7. Pull Requestを作成し、変更点、確認結果、残る注意点を報告する。Pull Requestはマージしない。

## 9. 精査開始時に使用したプロンプト

以下は2026-10-22の設計精査を開始したときの記録である。精査は完了しているため、次回作業の開始プロンプトとしては使用しない。

```text
RepoSpec ViewerのPhase 2「Viewer生成と保存」の詳細設計を確認・補完してください。作業リポジトリは `/Users/futaw/Documents/ChatGPT/ソース解説AIエージェント作成` です。

最初に `AGENTS.md`、`WORKLOG.md`、`docs/README.md`、`docs/phase-2-design-handoff.md`、`docs/phase-2-detailed-design.md`、`docs/frontend-spec.md`、`docs/backend-spec.md` を読んでください。必要に応じてPhase 1の詳細設計と実装も確認してください。

Phase 2詳細設計書v1.0はPR #16でmainへマージ済みです。白紙から作り直さず、現行設計を基準にしてください。

決定済みの方針は次のとおりです。

- Viewer本文を全Viewer共通の固定レイアウトにしない。
- Codexは内容に応じてセクションと定義済みblockを選ぶ。
- アプリのrendererがblockのDOM、見た目、表示幅、組み合わせ、レスポンシブ配置を決める。
- 一貫性は固定章ではなく、共通shell、block catalog、renderer規則、Theme、Densityで保つ。
- Codexに任意のHTML、CSS、JavaScript、class名、座標、配置値を出力させない。
- ViewerDocument構造化JSONを正本とし、検証とサニタイズ後のHTMLだけを表示する。
- blocks[]による構成の差は柔軟性のために残す。ただし、型付きcatalog、Document Type profile、validator、renderer、組み合わせtestで差を制御する。

今回の作業では、現行設計とPhase 0・1の実装を照合し、矛盾、未定義、テストで判定できない条件、初期実装に対する過剰な複雑さを精査してください。特にblock catalogの必要性と重複、情報量による配置判定、diagramの表形式への切り替え条件、Document Type profile、ViewerDocumentの上限値、Generation Jobの状態遷移、Phase 1との競合制御、Phase 3向けの分離を確認してください。

設計時と現在のローカルCodex CLIは `0.154.0-alpha.6.2` で、制限付きread-only accessの受理を確認できていません。今回は実装やCLI更新を行わず、実装開始条件と確認方法を設計として確定してください。

設計の選択によって結果が大きく変わる場合は、変更前に選択肢と推奨案を分かりやすく説明してください。それ以外は合理的な前提を置いて進めてください。

変更が必要な場合は、AGENTS.mdのGit運用に従って最新mainから新しい `codex/<task-name>` ブランチを作り、設計文書だけを更新してください。実装はまだ行わないでください。必要な確認後にcommit、push、main向けPull Request作成まで行い、Pull Requestはマージせずに報告してください。

最終報告には、現行設計の評価、変更した文書と内容、変更しなかった重要方針、確認結果、未解決の注意点、Pull Request URLを含めてください。
```
