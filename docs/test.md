# テスト手順

## 自動チェック

リポジトリ直下で、プロジェクトの virtualenv を使う。

```bash
DATABASE_URL=sqlite:///./.pytest_fresh.db .venv/bin/python -m pytest -q
```

`DATABASE_URL` が未設定のとき、`tests/conftest.py` は `sqlite:///./.pytest_sqlite.db` に落ちる。この共有ファイルは以前の実行の行を残すので、一式を流すときは上のように新しいファイルを使う。`python` が無いことがある。テスト依存の入ったインタプリタは `.venv/bin/python` である。

フロントエンド:

```bash
cd frontend
npm ci
npm run test:unit
npm run lint
npm run build
```

変えたファイルをカバーするチェックを実行する。UI の変更は、単体テストに加えて、影響する操作をブラウザで通す。Compose やイメージの変更は、下のスモークテストが要る。

## Compose のスモークテスト

```bash
docker compose up --build -d
python3 scripts/smoke_compose.py
```

スモークテストは、必要なコンテナ、Alembic のリビジョン、Redis、フロントエンドの `/api` プロキシ、Cookie ログインを確認する。

## 手動のエンドツーエンド確認

1. <http://localhost> または <http://localhost:8080> を開き、`.env` の `ADMIN_USER` / `ADMIN_PASS` でログインする（既定は `demo` / `demo`）。
2. `docs/sample/demo-meeting.wav` か、別の短い発話の録音をアップロードする。
3. タスクが preprocess、transcribing、formatting、success まで進むことを確認する。
4. 結果を開き、文字起こし、要約、議事録をダウンロードする。
5. 履歴を開き、同じタスクがあることを確認する。
6. Ollama を止めるか `llm` プロファイルを外し、タスクが `[FALLBACK]` の出力で成功することを確認する。

SSE のフォールバックを試すときは、`/api/bg/events` へのリクエストをブロックしてから再読み込みし、既存の EventSource を破棄する。履歴は約 30 秒ごとに `GET /api/bg/tasks` を出す。進行中のアップロードは約 10 秒ごとに `GET /api/bg/status/{id}` を出す。Network は EventStream ではなく Fetch/XHR で絞る。
