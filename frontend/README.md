# Minutes フロントエンド

ブラウザの UI は、React、Vite、TypeScript、Tailwind、生成した service worker でできている。

```bash
npm ci
npm run dev
```

開発サーバーは `/api` を `http://localhost:8000` へプロキシする。本番はフロントエンドイメージの `nginx.conf` を使い、同じ `/api` パスを保つ。

使うコマンド:

```bash
npm run test:unit
npm run lint
npm run build
npm run generate:api-types
```

依存のロックファイルは `package-lock.json` だけである。生成した OpenAPI の型は `src/api/generated.ts` にある。
