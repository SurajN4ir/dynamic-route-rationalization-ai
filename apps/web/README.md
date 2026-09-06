# apps/web

AURA's controller/passenger dashboard - Next.js (App Router) + TypeScript +
Tailwind CSS. Part of the [AURA monorepo](../../README.md); see
[docs/architecture](../../docs/architecture/README.md) for the approved
architecture this implements against.

Phase 1 scope: a system-status page (`src/app/page.tsx`) that calls the
backend's `/healthz`, `/readyz`, and `/api/v1/status` endpoints and reports
what it actually gets back - no mocked transportation data.

## Development

```bash
npm install
npm run dev
```

Requires `services/api` running and reachable at `NEXT_PUBLIC_API_URL`
(defaults to `http://localhost:8000`; see `.env.example`).

## Scripts

- `npm run dev` - start the dev server
- `npm run build` - production build (standalone output, see `Dockerfile`)
- `npm run lint` - ESLint
- `npx tsc --noEmit` - type check
