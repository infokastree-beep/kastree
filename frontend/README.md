# FinDraft frontend

Minimum Next.js 14 UI for the core loop: **upload → mapping review → statements dashboard**.

Product-level roadmap (three-product structure, build sequencing): [`../docs/product-roadmap.md`](../docs/product-roadmap.md). Granular technical gaps: [`../docs/tracked-gaps.md`](../docs/tracked-gaps.md).

## Prerequisites

- Node 20+
- Backend running (default `http://127.0.0.1:8000`) with CORS origins including this app
- Clerk application (publishable + secret keys). Org creation on signup is assumed to be handled by the existing Clerk webhook.

## Setup

```bash
cd frontend
cp .env.example .env.local
# Paste real Clerk keys, then set NEXT_PUBLIC_CLERK_READY=true
# Set NEXT_PUBLIC_API_BASE_URL to the FastAPI origin
npm install
npm run dev
```

App listens on [http://127.0.0.1:43123](http://127.0.0.1:43123).

With `NEXT_PUBLIC_CLERK_READY` unset or any value other than the string `true`,
Clerk middleware does **not** run and dashboard routes (`/upload`, `/mapping`,
`/dashboard`, …) **redirect to `/`**. There is no fake session and no preview
path into the authenticated app. Set real Clerk keys and
`NEXT_PUBLIC_CLERK_READY=true` to enable sign-in and protect those routes.

## Environment

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk browser SDK |
| `CLERK_SECRET_KEY` | Clerk middleware / server |
| `CLERK_TRUST_HOST` | Set `true` on Vercel |
| `NEXT_PUBLIC_CLERK_READY` | Must be exactly `true` to enable auth |
| `NEXT_PUBLIC_API_BASE_URL` | FastAPI base URL (no trailing slash) |

The header **Sign in** link is a plain `/sign-in` route (SSR-visible). The Clerk widget on that page only loads when the app is served from your **production domain** configured in Clerk (e.g. `https://kastree.ie`). Production keys (`pk_live_`) do not work on `*.vercel.app` — see Clerk’s [production deployment guide](https://clerk.com/docs/guides/development/deployment/production).

Backend must set `CORS_ORIGINS` to include `http://127.0.0.1:43123` (default in `app.config.Settings.cors_origins`).

## Auth note

API calls send the Clerk session JWT as `Authorization: Bearer …`. The backend accepts:

1. Local HS256 tokens (`AUTH_JWT_SECRET`) used by tests, or
2. Real Clerk RS256 session JWTs via JWKS (`CLERK_JWKS_URL` or derived from the publishable key).

The token must include an organisation id (`org_id` claim or Clerk’s nested `o.id`). Activate a Clerk Organization for the signed-in user after signup (webhook provisions the DB org).

## Routes in this slice

| Route | Role |
|-------|------|
| `/` | Public landing |
| `/sign-in`, `/sign-up` | Clerk hosted components |
| `/upload` | TB upload + parse |
| `/mapping/[tbId]` | Poll status, review/override mappings, confirm |
| `/dashboard/[tbId]` | SOPL / SOFP / SOCIE + generate |

Out of scope here: settings, billing UI, notifications UI, variance/risk tabs.
