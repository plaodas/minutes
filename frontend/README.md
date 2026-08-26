# Minutes Frontend (starter)

This is a starter React + Vite + TypeScript + Tailwind project for the audio-to-summary front-end.

Run locally:

```bash
cd frontend
npm install
npm run dev
```

Environment:
- `VITE_API_BASE` can be used to point to your backend (default http://localhost:8000)

Notes:
- Service worker and push flow are provided as stubs; real push subscription requires backend VAPID keys.
- API endpoints in `src/api/client.ts` are placeholders — adapt to your backend OpenAPI paths.
