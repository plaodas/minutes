# Ollama モデルのオンデマンド配備と運用ガイド

このドキュメントは、ローカル環境／コンテナ環境で Ollama のモデルをオンデマンドで追加・運用するための手順と運用上の注意点を日本語でまとめたものです。

## 方針（今回の採用）
- モデルはホスト上で `ollama pull` してからコンテナを再起動する運用にします。
- 理由: ダウンロードとモデル登録をホスト側で管理すると、コンテナ起動時に確実にモデルが利用可能になり、ダウンロード中のコンテナ負荷や再起動の制御がしやすいため。

## 基本手順（オンデマンドでモデルを追加する）
1. ホスト上でモデルをプルする（推奨）:

```bash
ollama pull gemma4:e4b
```

2. Ollama コンテナを再起動してモデルを反映させる:

```bash
docker restart ollama-container
```

3. 動作確認（例）:

```bash
curl -v http://localhost:11435/
curl -X POST http://localhost:11435/api/chat -H "Content-Type: application/json" \
  -d '{"model":"gemma4:e4b","messages":[{"role":"user","content":"hello"}]}'
```

## コンテナ内で直接プルする（代替）
- コマンド:
```bash
docker exec -i ollama-container bash -lc "/bin/ollama pull gemma4:e4b"
```
- 注意点: 容量が大きくダウンロード時間・I/O を消費します。サーバのメモリ/ディスク/ネットワークに負荷がかかるため、本番ではホスト側か init-job での実行を推奨します。

## 自動化案
- Kubernetes: initContainer を用いてモデルを先にプルし、メインの `ollama` Pod を起動する。これにより Pod がモデル準備済みで開始される。
- docker-compose: `puller` サービスでモデルをダウンロードしてから `ollama` を起動する順序にする。
- 管理 API: 管理用の認証保護されたエンドポイントを用意し、必要時に `ollama pull` をトリガーする（実装可）。

## 運用上の注意
- ディスク容量: モデルは数GB〜十数GBになるため、事前に十分な空き容量を確保してください。
- OOM リスク: モデルロード時のメモリ消費でプロセスが OOM することがあるため、監視と適切なノードリソース設計を行ってください。
- 同時ダウンロード: 複数モデルの同時ダウンロードは I/O を圧迫するため順次実行するか専用ノードで行うこと。
- セキュリティ: 管理 API を作る場合は必ず認証（APIキー/ベーアラートークン）とアクセス制御を実装すること。

## トラブルシュート
- `model 'xxx' not found` が出る場合: モデルがマニフェストに存在するか `/usr/share/ollama/.ollama/models/manifests` を確認し、コンテナの再起動を行ってください。
- ダウンロード中に失敗する場合: ネットワーク、ディスク容量、権限（マウント先の所有者）を確認してください。

## 参考コマンドまとめ
- ホストでプル + 再起動（推奨）:

```bash
ollama pull gemma4:e4b
docker restart ollama-container
```

- コンテナ内でオンデマンドプル:

```bash
docker exec -i ollama-container bash -lc "/bin/ollama pull gemma4:e4b"
```

---
このファイルに追加してほしい項目（例: systemd unit の例、K8s initContainer マニフェスト、管理 API のサンプルなど）があれば教えてください。
