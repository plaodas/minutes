# Minutes Frontend (starter)

This is a starter React + Vite + TypeScript + Tailwind project for the audio-to-summary front-end.

Run locally:

```bash
cd frontend
npm install
npm run dev
```

Environment:

Notes:
PWA notes:
- `vite-plugin-pwa` is integrated in `vite.config.ts`. Service worker is only enabled in production builds by default.
- SW update events trigger a `swUpdated` event on `window`; the app shows a small update toast to apply the new version.
