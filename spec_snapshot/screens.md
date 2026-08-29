# 画面一覧（snapshot）

このファイルはフロントエンドの画面（ビュー）と主要コンポーネント、責務の一覧です。AI エージェントが画面実装や UI 追加の起点として読むことを想定しています。

プロジェクトのフロントエンドは `frontend/src` にあり、主要な画面は `App.tsx` の `NavigationView` に基づいて切り替わります。

## 画面一覧

- Upload / Audio workspace
  - 表示箇所: `activeView === 'upload'`（`App.tsx`）
  - 主要コンポーネント: `Dropzone`, `ProcessingSteps`, `ResultCards`
  - 概要: 音声ファイルをアップロードして処理を開始。進捗（アップロード→前処理→文字起こし→フォーマット）を表示し、結果（転写・要約・アクション項目）をカードで確認・コピー・ダウンロードできる。

- History
  - 表示箇所: `HistoryView`（`WorkspaceViews.tsx`）
  - 概要: 作成済みの議事録一覧（サンプルUI）。現状はサンプルデータで、API 接続は未実装。

- Settings
  - 表示箇所: `SettingsView`（`WorkspaceViews.tsx`）
  - 概要: トランスクリプト言語、アクションアイテム抽出のオンオフなどローカル設定を変更する UI。永続化は未実装（将来設定APIを追加予定）。

## グローバル UI 要素 / 補助コンポーネント

- `Sidebar` (`Sidebar.tsx`)
  - ナビゲーション（upload/history/settings）、モバイル/デスクトップ両対応の折りたたみ式サイドバー。

- `Dropzone` (`Dropzone.tsx`)
  - ファイル選択／ドラッグ＆ドロップ、アップロード進捗表示、背景処理のポーリング管理。

- `ProcessingSteps` (`ProcessingSteps.tsx`)
  - ステップ表現（Uploading → preprocess → transcribing → formatting）。モバイルではコンパクト表示。

- `ResultCards` (`ResultCards.tsx`)
  - Transcript / Summary / Action Items をカードで表示。コピー・ダウンロード操作が UI にあるが、ダウンロードはプレースホルダ実装。

- `Toasts` / `UpdateToast`
  - アプリ内通知・サービスワーカー更新通知。

## 注意点 / 開発の起点メモ
- History のデータは現状サンプル。バックエンドの履歴 API（例: `/history`）は未実装のため、追加時は `bg/result` や DB の `tasks` を参照して一覧化するエンドポイントを用意すると良い。
- 設定の永続化は `localStorage` かサーバーサイド設定 API のどちらかを選択する必要あり（現状は `useLocalStorage` を利用）。
