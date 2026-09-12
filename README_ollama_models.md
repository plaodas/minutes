# Ollama profile

Ollama は Portfolio MVP の optional service です。起動しない場合も worker はローカル要約へ fallback し、タスクを完了します。

## 起動とモデル取得

```bash
docker compose --profile llm up --build -d
docker compose --profile llm logs -f ollama-pull
```

`ollama-pull` one-shot job が Ollama の healthcheck 完了後にモデルを取得します。既定値は `qwen2.5:3b` です。

別モデルを使う場合:

```bash
OLLAMA_MODEL=llama3.2:3b docker compose --profile llm up --build -d
```

永続化先は Compose の named volume `ollama_data` です。モデルも削除する場合:

```bash
docker compose --profile llm down -v
```

モデル取得には数 GB の通信とディスク容量が必要になる場合があります。
