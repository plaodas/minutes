このプロジェクトの Alembic マイグレーションの骨組み。

クイックスタート:

1. 依存を入れる。

```bash
pip install alembic sqlalchemy psycopg2-binary
```

2. データベース URL を設定する（Postgres の例）。

```bash
export DATABASE_URL=postgresql://user:password@localhost/minutes
```

3. 同梱の初期リビジョンでマイグレーションを実行する。

```bash
alembic -c alembic.ini upgrade head
```

注意:

- `alembic/env.py` は `target_metadata` のために `minutes.models.Base` を import する。
- モデルのモジュールパスを変えたら、`env.py` も合わせる。

## 推奨する作業手順

1) 依存を入れる（ローカル、または `minutes` コンテナの中）。

```bash
# ローカル（venv）
python3 -m pip install -r requirements.txt

# またはアプリを動かす compose コンテナの中
docker compose exec minutes bash -lc "python3 -m pip install -r requirements.txt"
```

2) マイグレーションを適用する（例）。

```bash
# 推奨: Alembic を直接実行する
alembic -c alembic.ini upgrade head

# または同梱の実行スクリプト（DATABASE_URL を読む）
python3 scripts/run_alembic_head.py

# minutes コンテナの中（ホストの名前解決の問題を避ける）
docker compose exec minutes python3 scripts/run_alembic_head.py
```

3) 新しいリビジョンを作る。

```bash
# 空のリビジョンを作る
alembic -c alembic.ini revision -m "add new column"

# autogenerate のリビジョンを作る（env.py が target metadata を公開していること）
alembic -c alembic.ini revision --autogenerate -m "autogen"
```

## 切り分け

- Postgres が Docker Compose の中で動いているときは、同じ compose ネットワークの中から Alembic を実行する（`docker compose exec minutes ...`）。ホストからだと `could not translate host name 'db'` になる。
- コンテナに `alembic` が無いときは、`pip install alembic` か `pip install -r requirements.txt` で入れる。
- 生の SQL を流す例は `scripts/migrations_legacy/001_add_minutes_text.sql` にある。

## 安全

- `alembic/versions/` のマイグレーションは、可能な箇所で冪等な SQL（例: `IF NOT EXISTS`）を使う。本番のデータベースへ適用する前に、生成された SQL を確認する。
