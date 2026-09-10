#!/bin/bash
set -e

echo "Starting Ollama container..."
docker compose -f docker-compose.ollama.yml up -d

echo "Waiting for Ollama to be ready..."
sleep 5

# ダウンロードしたいモデルをここに並べる
MODELS=(
"gemma4:e4b"
"qwen3.5:4b"
)

for model in "${MODELS[@]}"; do
  echo "Pulling model: $model"
  docker exec ollama-container ollama pull "$model"
done

echo "Ollama setup complete."
