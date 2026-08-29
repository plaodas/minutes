# DB スキーマ（snapshot）

このプロジェクトの永続化は主に `minutes/models.py`（SQLAlchemy）と `alembic/versions/0001_initial.py`（初期マイグレーション）に定義されています。

## テーブル一覧（要約）

1. users
   - id: UUID (PK)
   - username: string, unique, not null
   - password_hash: string, not null
   - email: string, nullable
   - created_at: datetime (server_default now())

2. tasks
   - id: UUID (PK)
   - user_id: UUID (FK -> users.id), nullable
   - status: string, not null (indexed)
   - progress: numeric, default 0
   - result: JSONB, nullable
   - fail_count: integer, default 0
   - last_failure_ts: datetime, nullable
   - last_success_ts: datetime, nullable
   - created_at: datetime (server_default now())
   - updated_at: datetime (server_default now(), onupdate now())
   - schema_version: integer, default 1

   - インデックス: ix_tasks_status

3. task_history
   - id: integer (PK, autoincrement)
   - task_id: UUID (FK -> tasks.id), indexed
   - event_ts: datetime (server_default now())
   - event_type: string, nullable
   - payload: JSONB, nullable

## 実装箇所
- ORM: `minutes/models.py`（SQLAlchemy `declarative_base` を使用）
- Alembic migration: `alembic/versions/0001_initial.py`
- DB 接続/セッション: `minutes/db.py`（接続設定はこのファイルを参照してください）

## 運用メモ / 拡張候補
- `tasks.result` は JSON で汎用性が高いが、大容量ファイルパスなどは `outputs/` に保存して `result` に参照パスを置く設計になっている。
- bg ストアは `DATABASE_URL` の有無で DB 版とファイル版（`data/bg_tasks.json`）を切り替える。
- 将来的にはユーザー管理、アクセス制御、タスク所有権、履歴クエリ用に `task_history` を活用すると良い。
