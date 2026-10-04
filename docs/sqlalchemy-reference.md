# RepoSpec Viewer SQLAlchemy利用ガイド

- 更新日: 2026-10-05
- 対象: SQLAlchemy 2系、非同期API、Alembic

本文書は、RepoSpec Viewerで実際に使用しているSQLAlchemyのクラス、関数、メソッドと、その処理内容をまとめた実装補足資料である。現在、SQLAlchemyは主にPhase 1のRepository情報管理で使用している。

主な実装箇所:

- `backend/app/db.py`: EngineとSession Factoryの作成、終了処理
- `backend/app/repositories/models.py`: ORMモデルとDB制約
- `backend/app/repositories/store.py`: Repositoryの追加、取得、状態更新
- `alembic/env.py`: 非同期Migration環境
- `alembic/versions/20261001_0001_create_repositories.py`: `repositories`テーブルのMigration

## 1. DB接続とSession

### `create_async_engine()`

```python
self.engine = create_async_engine(url, pool_pre_ping=True)
```

非同期DBエンジンを作成する。DB接続、SQL実行、Connection Pool管理の基盤となる。`pool_pre_ping=True`により、Poolから取得した接続が利用可能か、使用前に確認する。

### `async_sessionmaker()`

```python
self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
```

`AsyncSession`を生成するFactoryを作成する。`expire_on_commit=False`を指定しているため、`commit()`後もORMオブジェクトの属性値をそのまま参照できる。

### `self.sessions()`

```python
async with self.sessions() as session:
    ...
```

新しい`AsyncSession`を生成する。`async with`を抜けるとSessionは閉じられる。ただし、書き込み内容は自動Commitされないため、必要な箇所で`commit()`を明示的に呼ぶ。

### `engine.dispose()`

```python
await self.engine.dispose()
```

アプリ終了時にConnection Pool内のDB接続を解放する。

## 2. ORMモデル定義

### `DeclarativeBase`

```python
class Base(DeclarativeBase):
    pass
```

SQLAlchemy ORMモデル共通の基底クラスを定義する。`RepositoryModel`はこの`Base`を継承し、PythonクラスとDBテーブルを対応づける。

### `Mapped`

```python
owner: Mapped[str]
```

ORM属性がどのPython型を扱うかを型注釈で表す。例えば、`Mapped[str | None]`は文字列または`None`を保持できる属性を表す。

### `mapped_column()`

```python
id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
owner: Mapped[str] = mapped_column(String(39))
canonical_github_url: Mapped[str] = mapped_column(String(255), unique=True)
```

Pythonの属性とDBカラムを対応づける。

| 指定 | 処理内容 |
|---|---|
| `Uuid` | UUID型カラムを定義する |
| `String(39)` | 最大39文字の文字列カラムを定義する |
| `DateTime(timezone=True)` | タイムゾーン付き日時カラムを定義する |
| `primary_key=True` | 主キーにする |
| `unique=True` | 重複値を禁止する |

### `CheckConstraint`

```python
CheckConstraint(
    "status IN ('pending', 'cloning', 'ready', 'syncing', 'failed')",
    name="ck_repositories_status",
)
```

`status`へ許可されていない値を保存できないよう、DBのCHECK制約を定義する。

## 3. データ追加とTransaction

### `session.add()`

```python
session.add(repository)
```

`RepositoryModel`オブジェクトをSessionへ登録する。この時点ではDBへの保存は確定せず、その後の`commit()`でINSERTが確定する。

```python
session.add(repository)
await session.commit()
```

概念上は次のSQLに相当する。

```sql
INSERT INTO repositories (...) VALUES (...);
```

### `session.commit()`

```python
await session.commit()
```

現在のTransactionをDBへ確定する。本開発ではRepository登録、処理開始、成功、失敗、起動時の中断状態回復で使用する。

### `session.rollback()`

```python
await session.rollback()
```

現在のTransactionを取り消す。Repository登録時に`IntegrityError`が発生した場合、Sessionを利用可能な状態へ戻して既存Repositoryを検索するために呼び出す。

## 4. SELECT文の構築

### `select()`

```python
select(RepositoryModel)
```

SELECT文を構築する。この時点ではSQLは実行されず、`session.scalar()`、`session.scalars()`などへ渡した時点で実行される。

概念上は次のSQLに相当する。

```sql
SELECT * FROM repositories;
```

### `.where()`

```python
select(RepositoryModel).where(
    RepositoryModel.canonical_github_url == canonical_url
)
```

SQLのWHERE条件を設定する。

```sql
SELECT *
FROM repositories
WHERE canonical_github_url = :canonical_url;
```

本開発ではcanonical URLによる検索や、Repository IDと現在状態を指定した条件付き更新に使用する。

### `.order_by()`

```python
select(RepositoryModel).order_by(RepositoryModel.updated_at.desc())
```

検索結果の並び順を指定する。Repository一覧は更新日時の新しい順で取得する。

### `.desc()`

```python
RepositoryModel.updated_at.desc()
```

降順を指定する。日時の場合は新しい値から古い値の順となる。

### `.in_()`

```python
RepositoryModel.status.in_([
    "pending",
    "cloning",
    "syncing",
])
```

SQLの`IN`条件を構築する。

```sql
WHERE status IN ('pending', 'cloning', 'syncing')
```

本開発では主に、許可された現在状態からだけ次の状態へ遷移させるために使用する。

## 5. SELECTの実行と結果取得

### `session.get()`

```python
repository = await session.get(RepositoryModel, repository_id)
```

主キーを指定して1件取得する。存在しない場合は`None`を返す。本開発ではRepository詳細の取得と、状態更新後のデータ取得に使用する。

### `session.scalar()`

```python
repository = await session.scalar(
    select(RepositoryModel).where(...)
)
```

検索結果の先頭行について、最初の要素を返す。ORMモデルをSELECTしている場合は`RepositoryModel`が1件返り、該当データがなければ`None`となる。

本開発ではcanonical URLによる1件検索に使用する。

### `session.scalars()`

```python
result = await session.scalars(
    select(RepositoryModel).order_by(RepositoryModel.updated_at.desc())
)
return list(result)
```

検索結果からORMオブジェクトだけを取り出せる`ScalarResult`を返す。本開発ではRepository一覧の取得に使用する。

| メソッド | 主な結果 |
|---|---|
| `scalar()` | 先頭の1件、または`None` |
| `scalars()` | 複数件を扱える`ScalarResult` |

## 6. UPDATE文の構築と実行

### `update()`

```python
update(RepositoryModel)
```

UPDATE文を構築する。

### `.values()`

```python
update(RepositoryModel).values(
    status=new_status.value,
    last_error_code=None,
    last_error_message=None,
    updated_at=now,
)
```

更新対象のカラムと値を指定する。本開発では以下に使用する。

- `pending`から`cloning`への変更
- `ready`から`syncing`への変更
- CloneまたはSync成功時の`ready`への変更
- 処理失敗時の`failed`への変更
- 起動時の`OPERATION_INTERRUPTED`への回復

### 条件付きUPDATE

```python
update(RepositoryModel)
.where(
    RepositoryModel.id == repository_id,
    RepositoryModel.status.in_(["ready", "failed"]),
)
.values(status="syncing")
```

Repository IDだけでなく現在状態もWHERE条件に含める。同じRepositoryに対する別処理がすでに状態を変更していた場合は更新されないため、多重実行の防止に利用できる。

### `session.execute()`

```python
result = await session.execute(
    update(RepositoryModel).where(...).values(...)
)
```

構築したSQL文を実行する。本開発では主にUPDATE文の実行に使用する。更新を確定するには、その後に`commit()`が必要となる。

### `result.rowcount`

```python
if result.rowcount != 1:
    return None
```

UPDATEなどで影響を受けた行数を取得する。

| 値 | 本開発での判断 |
|---:|---|
| `1` | 想定したRepositoryの状態更新に成功 |
| `0` | 現在状態が想定と異なる、または対象が存在しない |

起動時には、中断状態から`failed`へ変更したRepository数の取得にも使用する。

## 7. SQLAlchemy例外

### `IntegrityError`

DBの整合性制約に違反した場合に発生する。想定される例は次のとおり。

- `canonical_github_url`の重複
- `workspace_key`の重複
- 主キーの重複
- CHECK制約違反

Repository登録時は`IntegrityError`を捕捉し、`rollback()`後に既存Repositoryを検索して、アプリ独自の`DuplicateRepositoryError`へ変換する。

### `SQLAlchemyError`

SQLAlchemy関連例外の基底クラスである。Service層で捕捉し、アプリ独自の`DatabaseUnavailableError`へ変換する。最終的なAPI応答は`503 DATABASE_UNAVAILABLE`となる。

## 8. Alembicで使用するSQLAlchemy API

MigrationではSQLAlchemyのカラム型と制約定義を使用する。

### `sa.Column()`

```python
sa.Column("owner", sa.String(length=39), nullable=False)
```

Migrationでテーブルのカラムを定義する。

### `sa.String()`、`sa.Uuid()`、`sa.DateTime()`

| 型 | 用途 |
|---|---|
| `sa.String(length=N)` | 最大N文字の文字列 |
| `sa.Uuid()` | UUID |
| `sa.DateTime(timezone=True)` | タイムゾーン付き日時 |

### `sa.PrimaryKeyConstraint()`

```python
sa.PrimaryKeyConstraint("id")
```

主キー制約を定義する。

### `sa.UniqueConstraint()`

```python
sa.UniqueConstraint("canonical_github_url")
```

一意制約を定義し、重複値を禁止する。

### `sa.CheckConstraint()`

```python
sa.CheckConstraint(
    "status IN ('pending', 'cloning', 'ready', 'syncing', 'failed')",
    name="ck_repositories_status",
)
```

許可された状態値だけを保存できるようにする。

## 9. 非同期Alembic環境

### `async_engine_from_config()`

```python
connectable = async_engine_from_config(
    config.get_section(config.config_ini_section, {}),
    prefix="sqlalchemy.",
    poolclass=pool.NullPool,
)
```

Alembic設定から非同期Engineを作成する。Migrationは一時的な処理なので、`NullPool`を指定して通常のConnection Poolを保持しない。

### `connectable.connect()`

```python
async with connectable.connect() as connection:
```

Migration用の非同期DB接続を開始する。

### `connection.run_sync()`

```python
await connection.run_sync(do_run_migrations)
```

非同期Connection上で、Alembicが使用する同期形式のMigration処理を実行する。

### `connectable.dispose()`

```python
await connectable.dispose()
```

Migration完了後にEngineと接続資源を解放する。

### Alembic固有メソッド

以下はSQLAlchemyそのものではなくAlembicのメソッドである。

| メソッド | 処理内容 |
|---|---|
| `op.create_table()` | Migration適用時にテーブルを作成する |
| `op.drop_table()` | Migrationを戻すときにテーブルを削除する |
| `context.configure()` | Migration実行方法、接続、metadataなどを設定する |
| `context.begin_transaction()` | Migration用Transactionを開始する |
| `context.run_migrations()` | Migrationを実行する |

## 10. 現在使用していない代表的な機能

現時点では次の機能を使用していない。

- `delete()`による行削除
- JOIN
- ORM Relationship
- Foreign Key
- `limit()`、`offset()`によるページング
- `flush()`
- `refresh()`
- `merge()`
- ORM属性の直接変更によるUPDATE
- `begin()`による明示的なTransaction block

現在は`repositories`テーブル1つだけであるため、SQLAlchemyの利用範囲もRepositoryの作成、一覧、1件取得、状態更新に限定されている。
