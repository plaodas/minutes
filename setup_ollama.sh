#!/usr/bin/env bash
set -euo pipefail

# The llm profile starts Ollama and waits for it before pulling OLLAMA_MODEL.
docker compose --profile llm up --build -d ollama ollama-pull
docker compose --profile llm logs ollama-pull
