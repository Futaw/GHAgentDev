# Phase 2 一時領域の読取り制限

2026-11-04、`a67dd07`を基準に調査した。使用CLIは指定の`/Users/futaw/.local/bin/codex`（0.164.0）。Python 3.12.0、macOS 26.6.2。GENERATION_ENABLED=false、実ユーザー設定・認証情報・CLIは変更していない。

## 問題と切り分け

従来のcanonical Profileは`:root=deny`、`:minimal=read`、`:workspace_roots`の`.`をreadとしていた。このProfileでも、非機密fixture内の許可fileだけでなく、`/private/tmp`配下の兄弟・外部・専用homeのsentinelが読めた。

専用fixtureと空の専用homeを使い、従来Profileに一時領域aliasのdenyを1条件ずつ追加して比較した。以前の相対/絶対Repository path比較や`:minimal`除去の試験を、今回の修正証拠として流用していない。

| Profile条件 | 許可file | `/private/tmp`の範囲外3種類 | OSの一時directory | 一時領域外の専用file |
|---|---|---|---|---|
| 従来のcanonical | read | **read** | OS拒否 | OS拒否 |
| `:slash_tmp=deny`だけ追加 | read | OS拒否 | OS拒否 | OS拒否 |
| `:tmpdir=deny`だけ追加 | read | **read** | OS拒否 | OS拒否 |
| 両aliasをdeny | read | OS拒否 | OS拒否 | OS拒否 |

この実行では、従来Profileに残る`/private/tmp`配下の読取りを`:slash_tmp=deny`で閉じられることを実測した。`:root=deny`とRepository指定だけでは、一時領域の制限が十分でなかった。内部の許可展開元を直接dumpした証拠はなく、すべてが`:minimal`の特定の展開だけに由来すると断定しない。

[公式仕様](https://learn.chatgpt.com/docs/permissions#common-profiles)にも、workspaceだけのfile access例で`:tmpdir`と`:slash_tmp`を明示denyにする例がある。現在の公式資料は参考情報とし、CLI 0.164.0での受理・動作と組み合わせて判断した。

## 修正

Generationのcanonical filesystemへ`:tmpdir=deny`と`:slash_tmp=deny`を追加した。Repositoryのread、`:minimal=read`、network disabled、never approval、既存の外部tool禁止は維持する。より具体的なRepository real pathだけが一時領域deny内でも読み取り可能となる。

`security.py`は、この2つのaliasを認める場合もflatな`deny`だけを許可する。read/write、null、scoped tableは拒否する。任意の追加rootやProfile継承の禁止は維持する。policy versionは`repospec-generation-v1.3-2`へ更新した。

harnessのfixtureを拡充した。

- `/private/tmp`の兄弟fileと専用homeの認証path相当sentinel。
- OSが使用する一時directoryの専用sentinel。
- 一時領域外の専用sentinel。source workspaceの`.data`に新規一時directoryを作成し、その中のfileだけを対象とする。既存Repository・文書・DB・認証fileはprobeしない。
- 許可fileを正の対照として読む。すべてのsentinelを親が読めることも確認する。

全保護pathのhashとGit statusを比較し、3つのfixture directoryを終了時に削除する。一時領域外のfixtureを確保できない配置では、read gateをpassedにせずinconclusiveとする。今回のworkspace配置では`non_temp_fixture_control=true`だった。

## 確認結果

- Backend **143 passed**。canonical Profileのdeny、下位設定のread/write等の拒否、OS一時directoryの証拠欠落・読取り成功時の誤合格防止を検証。既存のChat・生成・timeout・TTY・cleanup回帰を含む。
- Ruff check / format、git diff --check: 成功。Frontend変更なし、今回再実行なし。
- 実CLIの条件比較では全fixtureが不変で、cleanup完了。
- 疑似端末から改修後の全体harnessを`--timeout 120`で実行。

| gate | 結果 |
|---|---|
| sandbox_read | **passed**。許可fileは読め、範囲外4種類はOS拒否 |
| non_modification | passed |
| command_network | passed。親の疎通対照もpassed |
| fixture_integrity | passed |
| 専用homeのprotocol/runtime | passed（補助検査） |
| 実ユーザー設定のprotocol_config | **failed: shell_environment_merge** |
| real_turn / external_tools / additional_permissions | not_run |
| process / fixture cleanup | passed |

全体のexitは**1**。read gateの合格を全体合格に置き換えない。実設定のset結合で停止しており、モデルTurnと実Viewer生成は開始していない。結果は[安全なJSON証拠](./2026-11-04-generation-temp-deny.json)へ保存した。

## 未完了

shell環境のset結合と、不要な変数が実際の子環境へ渡らないことを確認する設計・修正は別作業である。このPRではshell検査の完全一致条件を緩和していない。

実Turnでの読取り制限・構造化出力・外部tool非使用・非昇格、実Viewer保存、ブラウザ操作とPostgreSQLの完了確認は残る。native sandbox probeとThread metadata検査の成功だけで、実TurnやPhase 2全体を完了扱いにしない。全必須安全gateが合格するまでは生成を無効のままとする。
