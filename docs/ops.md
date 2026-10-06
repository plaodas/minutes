# 運用メモ

このリポジトリで使う構成の正本は `docker-compose.yml` である。

## 起動と確認

```bash
docker compose up --build -d
docker compose ps
python3 scripts/smoke_compose.py
docker compose logs -f minutes worker
```

API と worker は、PostgreSQL のマイグレーションと demo ユーザーの作成が終わるまで待つ。フロントエンドは API の healthcheck を待つ。

## SSE

ブラウザは `/api/bg/events` に接続する。`frontend/nginx.conf` はこのパスだけ、バッファしないプロキシにし、読み取りと送信のタイムアウトを 1 時間にしている。

```bash
curl -sS -D - --max-time 3 http://localhost/api/bg/events -o /dev/null || true
```

レスポンスには `content-type: text/event-stream` が含まれる。SSE が使えないとき、フロントエンドは状態のポーリングに落ちる。

## データ

- PostgreSQL は名前付きボリューム `pgdata` を使う。
- アップロードファイルは `data/uploads/` にバインドマウントする。
- 生成した成果物は `data/outputs/` にバインドマウントする。
- Ollama のモデルは、任意の `llm` プロファイルを有効にしたとき、名前付きボリューム `ollama_data` を使う。
- Redis は名前付きボリューム `redisdata` を使い、`appendonly yes` でキューを残す。

`data/outputs/` 直下の `minutes_*` のうち、どのタスクの `result` も指していないファイルは、API が `data/outputs/deleted/` へ移す。対象は更新時刻が `OUTPUT_QUARANTINE_SECONDS`（既定 21600 秒）より古いものだけである。論理削除のタスクが指すファイルは残す。移動時に更新時刻を移した時刻へ直し、移動先に同じ名前があるときは上書きしない。`deleted/` へ移してから `OUTPUT_DELETED_RETENTION_SECONDS`（既定 86400 秒）を過ぎたファイルは消す。タスクの読み取りに失敗した回は移さない。この処理は成果物をタスクへ付けない。実行は起動時と、突き合わせと同じ `RECONCILE_INTERVAL_SECONDS`（既定 3600 秒）ごとで、突き合わせのあとである。

アップロードの期限は次のとおりである。

- 成功したアップロードと途中 wav（`_mono`、`_norm`、`_clean`）は、その場で削除する。
- `failed` と `cancelled` は `UPLOAD_RETENTION_SECONDS`（既定 86400 秒）。失敗は `last_failure_ts`、キャンセルは `updated_at` から数える。
- どのタスクも参照していないファイルは、更新時刻から同じ期限で削除する。
- `pending`、`preprocess`、`transcribing`、`formatting` は、回収が `failed` にするまで削除しない。

```bash
docker compose down
docker compose --profile llm down -v  # 名前付きボリュームも削除する
```

## 障害対応

進行中のタスクは、同じ `task_id` で最初からやり直せる。`process_audio` は処理が終わるまで ack しない。worker が完了前に死ぬと、そのジョブは Redis に戻り、文字起こしの途中からではなく最初から走る。`success`、`cancelled`、`deleted` はやり直さない。再実行の API はない。

Redis のボリュームが残る再起動では、未着手と未 ack が戻る。`down -v` でボリュームを消したとき、または worker と Redis が同時に消えたときは、API の起動時と `RECONCILE_INTERVAL_SECONDS`（既定 3600 秒）の回収が引き受ける。Redis に確認できないあいだは再投入しない。キュー、active、reserved、scheduled に同じ ID があるときも再投入しない。音声ファイルが残っていれば同じ ID で再投入する。ファイルが無ければ `failed` にし、利用者はアップロードし直す。

`GET /api/health` が見るのは API プロセスが生きていることだけである。PostgreSQL や Redis が止まっていても成功する。サービスの生死は `docker compose ps` で見る。`db` は `pg_isready`、`redis` は `PING`、`worker` は `celery inspect ping` である。

原因を切り分けているあいだは `docker compose down -v` と全体の再ビルドを使わない。`pgdata`、`redisdata`、`data/uploads/`、`data/outputs/` は `-v` 無しの `down` では残る。`-v` は Redis のキューも消す。

### まずやること

1. 症状を一つに決める。アップロードが 500、画面が進まない、タスクが `failed`、`success` なのに本文が空、のどれか。
2. 終了または unhealthy のサービスを見て、その直近ログを読む。

```bash
docker compose ps
docker compose logs --tail 200 minutes worker db redis
```

`llm` プロファイルを使っているときは、`docker compose --profile llm ps` と `docker compose --profile llm logs --tail 200 ollama worker` も実行する。

3. worker がまだそのタスクを実行しているかを見る。

```bash
docker compose exec worker celery -A minutes.celery_app.celery inspect active
```

一覧にあれば処理は続いている。一覧に無く、Redis にもその ID が無い終端でないタスクは、次の回収が同じ ID で再投入する。

4. PostgreSQL で段階を読む。Compose の既定はユーザー `minutes`、データベース `minutes` である。

```bash
docker compose exec db psql -U minutes -d minutes -c \
  "SELECT id, status, progress, fail_count, updated_at FROM tasks WHERE deleted = false AND status IN ('pending','preprocess','transcribing','formatting') ORDER BY updated_at;"
```

5. 落ちているサービスだけ起動する。スキーマや demo ユーザーを戻すのは、起動またはログインが失敗しているときだけにする。

```bash
docker compose run --rm migrate
docker compose run --rm bootstrap
```

どちらも繰り返し実行できる。パイプラインの途中で残ったタスクは直らない。

### どこを見るか

| 段階または症状 | 見ること |
| --- | --- |
| `pending` | Redis のキュー長 `docker compose exec redis redis-cli LLEN minutes` と、worker の起動ログ |
| `preprocess` または `transcribing` | worker ログ。Whisper は worker プロセスの中で動く |
| `formatting` | worker ログのロガー `minutes.ollama`。下の待つ基準の時間までは想定内 |
| `failed` | `task_history` の `failure` と、worker の例外 |
| `success` で本文が空、または `[FALLBACK]` で始まる | `data/outputs/` と worker ログ。区間が残っていても議事録本文は空のことがある |

画面だけが止まったときは SSE を見る。ブラウザは `/api/bg/events` を使い、そのストリームが切れると状態のポーリングに落ちる。worker と PostgreSQL が生きていれば処理は続く。

### 待つ基準

止まったように見えても、次のあいだは再起動しない。

| 対象 | 待つ | その後 |
| --- | --- | --- |
| 整形（Ollama） | モデルごとに 120 秒、240 秒、480 秒の 3 回。既定の `OLLAMA_TIMEOUT` なら 1 モデルあたり約 14 分 | `formatting` のままが正常。終わると `failed` ではなく、`[FALLBACK]` で始まる `success` |
| 文字起こし（ローカル Whisper） | 終わるまで。タイムアウトも再実行も無い | `transcribing` が長いこと自体は異常ではない。`celery inspect active` にタスクが無いときだけ、途中で落ちたと判断する |
| worker が完了前に死んだジョブ | 遅延 ack でキューへ戻る。やり直すときは最初からである | 文字起こしの途中からは再開しない。`CELERY_VISIBILITY_TIMEOUT`（既定 86400 秒）を超えて未 ack のジョブは、実行中でももう一度届く |
| 画面 | SSE は nginx が 1 時間維持する。切れたあとは、進行中タスクを最初 1.5 秒後、以降 10 秒間隔、履歴を 30 秒間隔でポーリングする。状態取得は 10 秒で打ち切り、最大 4 回試す。その失敗が 3 回続くと画面だけ失敗になる | DB の `status` は変わらない |

### Redis 停止

Redis は Celery のブローカー、結果バックエンド、SSE のチャネルである。worker 内で進んでいる文字起こしと整形は続き、段階の書き込みは PostgreSQL へ行く。イベント配信は Redis が戻るまで失敗するので、画面は遅れ、その後ポーリングになる。

新規アップロードはキュー投入で失敗し、タスク行は作られない。ファイルは `data/uploads/` に残る。キャンセルは API が PostgreSQL に届くなら行を `cancelled` にする。Celery の revoke には Redis が要る。

```bash
docker compose up -d redis
docker compose exec redis redis-cli ping
```

`PONG` を待つ。ボリュームが残っていれば未着手と未 ack は戻る。`down -v` のあとで `LLEN minutes` が 0 かつタスクが途中のままなら、次の回収が音声ファイルから再投入する。ファイルが無ければ `failed` になる。

### worker 停止

Redis に残っているジョブは、worker が戻ったあとに消化される。完了前に死んだジョブは ack されていないのでキューへ戻り、最初からやり直す。

```bash
docker compose up -d worker
docker compose logs --tail 200 worker
```

`inspect active` に出ず、Redis にもジョブが無い途中タスクは、次の回収が再投入する。元のファイルは `data/uploads/` に残る。途中の wav（`_mono`、`_norm`、`_clean`）が消えるのは成功したあとだけである。worker イメージの再ビルドでも進行中タスクは落ち、そのコンテナにキャッシュされた Whisper モデルは次の文字起こしで取り直す。

### Ollama 停止・タイムアウト

Ollama は任意である（`llm` プロファイル）。worker は常に `OLLAMA_HOST`（Compose では `http://ollama:11434`）を呼ぶ。Ollama が停止している、または存在しないときも、タスクは `failed` にならない。整形はモデルごとに 3 回待ち、タイムアウトは `OLLAMA_TIMEOUT`、その 2 倍、その 4 倍（既定では 120 秒、240 秒、480 秒）である。その後タスクは `success` になり、議事録本文は `[FALLBACK] Ollama call failed:` で始まる。`message.content` が空のときも `success` として保存される。成果物ファイルは空、履歴のタイトルは未設定、議事録本文は空白のままになる。fallback で終わったタスクは、もう一度整形されない。

```bash
docker compose --profile llm up -d ollama
docker compose --profile llm logs --tail 100 ollama ollama-pull
```

モデルが無いときは `ollama-pull` を見る。プロファイルを上げていないと、整形のたびにこの fallback になる。

### PostgreSQL 停止

ログイン、一覧、段階の更新が失敗する。API の healthcheck は成功したままである。PostgreSQL が戻ったあとの次の接続取得で、`pool_pre_ping` が張り直す。

段階の書き込みに失敗しても worker はパイプラインを続け、`data/outputs/minutes_*.txt` を書くことがある。API の突き合わせがこのファイルをタスクへ付けるのは、`pending` がちょうど 1 件で、未参照の `minutes_*.txt` もちょうど 1 件のときだけである。すでに `preprocess`、`transcribing`、`formatting` のタスクはそのまま残る。突き合わせのあと、猶予を過ぎた未参照ファイルは `data/outputs/deleted/` へ移る。猶予内のファイルは直下に残り、次の突き合わせの未参照件数に入る。

```bash
docker compose up -d db
docker compose exec db pg_isready -U minutes -d minutes
```

`pgdata` ボリュームはそのまま残す。

### Whisper 失敗

Whisper は独立したサービスではない。`faster-whisper` は worker の中で動く（`TRANSCRIBE_MODEL_SIZE`、既定は `small`）。パイプラインが捕捉したエラーはタスクを `failed` にし、`fail_count` を増やし、`result` には `upload_path` だけを残す。文字起こしは保存されない。失敗とキャンセルのアップロードは `UPLOAD_RETENTION_SECONDS`（既定 86400 秒）のあいだ残り、その後 API の定期削除が消す。

worker ログで `preprocess failed` か Whisper の例外を見る。コンテナが殺されたとき（メモリ不足など）は `failed` にならない。worker 停止として扱う。段階は止まった場所のまま残る。

### 処理途中での再起動

| 再起動したサービス | 実行中のタスク |
| --- | --- |
| `worker` | 未 ack のジョブはキューへ戻り、最初からやり直す。Redis に残っている未着手も worker 復帰後に処理される |
| `minutes` | worker は続行する。SSE は切れ、画面はポーリングで追いつく。起動時の回収は、Redis 上に無い途中タスクだけを再投入する |
| `db` | 段階の書き込みは短時間失敗し、その後 `pool_pre_ping` が再接続する。停止中に成功を書けなかった場合、成果物ファイルだけが残り `success` の行は付かない |
| `redis` | 実行中の処理は続く。ボリュームが残る再起動ではキューも残る。`down -v` でボリュームが消えると、起動時の回収が DB とアップロードから再投入する |
| スタック全体の `up -d` | 各サービスを再起動したときと同じ。`-v` を付けると PostgreSQL、Redis のキュー、Ollama のモデルも消える |

## 変更が反映される場所

Compose はソースをイメージへコピーする。ホストでファイルを保存しても、動いているコンテナには届かない。変えたコードを import するサービスだけを再ビルドする。

```bash
docker compose up --build -d --no-deps frontend
docker compose up --build -d --no-deps minutes
docker compose up --build -d --no-deps worker
```

- `frontend`: React の UI、ラベル、クライアント側の描画。
- `minutes`: FastAPI のルート、ダウンロード、レスポンスの形。
- `worker`: Whisper、Ollama 呼び出し、プロンプト、完了したタスクを保存するパイプライン。
- API と worker の両方が import するモジュール（例: `minutes/pipeline/formatting.py`）は、`minutes` と `worker` の両方を再ビルドする。

この種の変更でスタック全体は再ビルドしない。

## タスクが保存するもの

Whisper は整形の前に `segments` と `transcript` を書く。Ollama の `message.content` が `minutes` になり、`data/outputs/` にも書かれる。`summary` と `action_items` はその議事録本文から導出する。`search_text` はタスク名、文字起こし、要約、議事録を連結する。

履歴のタイトルが入るのは、タスクに名前が無いときだけである。成果物ファイルの最初の文を使う。議事録画面はそのファイルを読む。ファイルが空だと、`segments` にテキストがあってもタイトルは未設定で本文は空白になる。`result.minutes` はファイルの代わりにならない。

## モデルの違い

`OLLAMA_MODEL` は、整形の各呼び出しで使うモデルを選ぶ。fallback のモデルも同じである。リクエストに `think: false` を付けるのは、モデル名に `qwen3` が含まれるときだけである。`qwen2.5` ではそのフィールドを付けない。議事録本文は `message.content` である。thinking のテキストは保存しない。

## 画面とコードが食い違うとき

- フロントエンドを再ビルドしたあと、service worker が前の SPA を保持することがある。DevTools で登録を解除して再読み込みする。ログイン時の注意は [README.md](../README.md) を見る。
- ホストから使う `DATABASE_URL` は `localhost` と `postgresql+psycopg2://` スキームである。コンテナはホスト名 `db` を使う。Compose はコンテナの URL を `POSTGRES_*` から組み立て、`.env` の `DATABASE_URL` は読まない。
- タスクが成功しても、Ollama が空の `content` を返すと `minutes` は空文字のままになる。文字起こしを議事録本文として扱う前に、worker ログと成果物ファイルを確認する。

## バックアップとリストア

対象は PostgreSQL、`data/uploads/`、`data/outputs/`（`deleted/` を含む）である。Redis のキューと Ollama のモデルは含めない。キューは再投入で戻り、モデルは `ollama-pull` で取り直す。

```bash
python3 scripts/backup.py
python3 scripts/restore.py backups/<timestamp>
```

`backup.py` は `backups/<UTC timestamp>/` に `db.sql`、`uploads/`、`outputs/` を書く。`BACKUP_DIR` で出力先を変えられる。`restore.py` は worker を止めてから DB と二つのディレクトリを戻し、worker を起動する。`docker compose down -v` は使わない。リストア後の未完了タスクは、起動時の回収に任せる。

## ローカル限定のセキュリティ

`.env.example` の既定値は、ローカルのデモ用である。Docker Compose は `.env` を `docker-compose.yml` へ展開する。ファイル全体をコンテナへは読み込まない。localhost の外へ出す前に `ADMIN_PASS`、`JWT_SECRET`、`PROVISION_SECRET`、PostgreSQL の認証情報を変える。TLS と複数ホストへの配置は MVP の範囲外である。

外部サービスの呼び出し手順は [external.md](external.md) にある。`PROVISION_SECRET` が未設定のとき、発行口は 404 である。値は `JWT_SECRET` とは別にする。秘密とサービストークンは呼び出し側が保持し、minutes の管理者資格は渡さない。
