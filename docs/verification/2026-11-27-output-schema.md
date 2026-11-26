# Phase 2 送信用Schemaの互換性修正

2026-11-27、main `9f98164`を基準に、Viewer生成で発生した`CODEX_TURN_FAILED`を修正した。送信用Schemaだけを変更し、文書モデル、保存JSON、DB、権限policyの形式は変更していない。

## 原因と修正

対象Job `aa7699d4-a00f-4703-a036-41853490e9bd`と、その再試行元のThreadログを限定して照合した。両方とも調査開始から約1.5秒で失敗し、中止要求はなかった。原因はAPIの`invalid_json_schema`であり、`blocks/items`にある`oneOf`がstrict schemaでは未対応として拒否されていた。

Pydanticのblock用discriminated unionは、通常のSchema生成では`oneOf`とOpenAPIの`discriminator`を出力する。これをCodexへそのまま渡していた。送信用の生成クラスを`codex/output_schema.py`へ分け、tagged unionの生成時だけ`anyOf`へ変え、`discriminator`を除いた。12種の分岐は相異なる必須Literalの`type`を持つため重ならず、受け付ける値は変わらない。受信後のPydantic、参照、renderer、sanitizerの検証は維持した。

送信Schemaの拒否は`CODEX_OUTPUT_SCHEMA_INVALID / retryable:false`へ分類する。一般のTurn失敗は既存codeを維持し、画面・DB・SSEには固定の説明だけを返す。ログには安全な分類とJob/trace/Thread/Turn IDを残し、元のmessage、additionalDetails、秘密値を出さない。過去の失敗Jobの状態は書き換えない。

## 自動テスト

| 確認 | 結果 |
|---|---|
| Backend | 200 passed |
| Frontend | 34 passed |
| Ruff check / format check | 成功 |
| ESLint、TypeScript / Vite build | 成功。既存のZod由来annotation警告あり |
| Markdownのコードフェンス・ローカルリンク・末尾空白 | 確認済み |

送信Schemaの全階層、12種の分岐、必須field・追加field拒否・既存制約、通常のPydantic Schemaが不変であることを検査した。Fakeも送信Schemaを検査するようにし、旧Schemaを無条件に成功扱いしない。拒否時の非保存・ref回収・非retryable、一般失敗のretryable、再生成失敗時の本文保持、REST/SSE/ログへの秘密値非公開、UIの専用表示と再試行抑止を確認した。

## 実Codexと隔離したPostgreSQLでの保存

固定CLI `0.164.0`、policy `repospec-generation-v1.3-3`を使用した。専用の一時Git fixtureと、通常DB内の新規・一時PostgreSQL schemaだけに試験データを置き、修正後の`GenerationRunner`を実行した。通常Backendの再起動や、通常のViewer生成APIからのJob作成は行っていない。

| 確認 | 実測 |
|---|---|
| Schema受理・モデルTurn・Job | completed、errorなし |
| 保存 | revision 1、ソース参照1件、sanitize済みHTML 767 bytes |
| 生成元Commitと版別ref | 両方一致 |
| 専用fixtureの内容hash・Git status | 不変・クリーン |
| Generation一時ref | 残存なし |
| 通常ViewerのID・revision・Commit・本文/HTML hash | 試験前後で不変 |
| 一時schema、Git fixture、子プロセス | 後始末済み |

送信SchemaのSHA-256は、keyをsortした`json.dumps`のUTF8を基準に`2fc44a76707ae9d899b33ac2c81525e0f3a6d3c494f67a584f6ad36c5473d3e7`だった。生成された本文や認証情報は検証記録へ複製していない。

この試験の起動直後には`inspection_expired`のbaseline警告も観測した。Job開始前とJob固有の新しい検査は合格し、生成から保存までは成功した。警告を理由に検査条件を緩和していない。

## 安全性の回帰

全体harnessの初回は`real_turn / inspection_expired`で停止した。`account/read`がThreadの安全検査後にあり、認証通知による世代更新で検査が失効し得る順序だったため、全体検査の認証取得をThreadの検査前へ移した。通常の実行policyや、検査世代が失効した場合の拒否条件は変更していない。

修正後、専用fixtureで全体harnessを実行した。最終実行は親Pythonから終了コードも取得し、**exit 0、必須9gateすべてpassed**を確認した。途中失敗を合格に読み替えていない。

| gate | 結果 |
|---|---|
| protocol_config | passed |
| sandbox_read | passed |
| non_modification | passed |
| command_network | passed |
| real_turn | passed |
| shell_environment | passed |
| external_tools | passed |
| additional_permissions | passed |
| fixture_integrity | passed |

process_cleanupとfixture_cleanupもpassed。実RPCの承認要求はnot_observedであり、実際に拒否要求を観測した証拠とは区別する。

## Phase 3への影響と適用

Phase 3詳細設計をv1.2へ更新し、QaAnswerの送信用Schema生成とSchema拒否分類の共用、P3-00での実Schema受理確認を追記した。Conversation、版別履歴、固定Commit、snapshot、Source API、UI構成は変更しない。DB移行と既存Viewerの作り直しは不要である。QaAnswerの実装や実Turn検証を今回完了したことにはしない。

通常の`.env`、Codex設定・認証、CLI、保存済みViewerは変更していない。通常画面での再生成確認は、利用者が修正PRをマージしmainを取得してBackendを再起動した後に行う。今回の実保存成功と、通常画面での確認は分けて記録する。
