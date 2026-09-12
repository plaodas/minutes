# Minutes frontend

React, Vite, TypeScript, Tailwind, and a generated service worker provide the Minutes browser UI.

```bash
npm ci
npm run dev
```

The development server proxies `/api` to `http://localhost:8000`. Production uses `nginx.conf` in the frontend image and preserves the same `/api` paths.

Useful commands:

```bash
npm run test:unit
npm run lint
npm run build
npm run generate:api-types
```

`package-lock.json` is the only dependency lockfile. Generated OpenAPI types live in `src/api/generated.ts`.
