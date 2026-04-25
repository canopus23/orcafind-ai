## OrcaFind AI

Marketing site + authenticated studio for generating social posts, captions, and (Pro-only) post images.

**Frontend:** static HTML/CSS/JS in `frontend/` (pretty URLs via folder `index.html`).
**Backend:** FastAPI in `backend/app/` (auth via Supabase JWTs, billing via Dodo Payments).

### Local setup

1. Copy env template:

```bash
cp .env.example .env
```

2. Fill in at minimum:
- `SUPABASE_URL`
- `SUPABASE_JWT_SECRET` (only if your project uses HS256 JWTs)
- `OPENAI_API_KEY`

3. Install backend deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

4. Run backend:

```bash
cd backend
ENV=development uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Serve `frontend/` (any static server) and open:

```bash
cd frontend
python3 -m http.server 3000
```

- `/` marketing
- `/studio/` studio
- `/auth/` sign in
- `/profile/` profile
- `/checkout/` pricing + checkout

### Production notes

#### Favicons / brand icon
- `frontend/favicon.svg` is an SVG wrapper for the favicon image with rounded corners.
- `frontend/favicon.png` is a fallback used by browsers that don't render the SVG favicon reliably.
- The top-left brand icon on pages uses `favicon.png` as a background image.

#### SEO basics
- `frontend/robots.txt` points crawlers to `https://orcafind.com/sitemap.xml`.
- `frontend/sitemap.xml` is a simple XML sitemap for the public pages.

### Deploy (Vercel + FastAPI on Railway)

Frontend (Vercel):
- Set `window.__ORCAFIND_API_BASE_URL` (optional) to point to Railway FastAPI base URL.
- Set `window.__ORCAFIND_SUPABASE_URL` / `window.__ORCAFIND_SUPABASE_ANON_KEY` (optional) if you want to avoid hardcoding.

Backend (Railway):
- Set `ENV=production`.
- Set `CORS_ALLOW_ORIGINS` to your Vercel production domain(s).
- Optional: set `CORS_ALLOW_ORIGIN_REGEX=https://.*\\.vercel\\.app` for preview deploys.

Core services:
- Set `DATABASE_URL` (required in production for persistent subscriptions/usage and subscription entitlements).
- Set `OPENAI_API_KEY` (required for real text/image generation).

Recommended:
- Set `REDIS_URL` (rate limiting / abuse protection).
- Set `SENTRY_DSN` and `SENTRY_TRACES_SAMPLE_RATE`.

Supabase database networking:
- If your runtime cannot reach Supabase IPv6 endpoints, set `DB_FORCE_IPV4=true` and use a Supabase connection option that supports IPv4 (for example a dedicated IPv4 add-on or pooler where applicable).

Dodo Payments billing (subscriptions):
- Set `DODO_PAYMENTS_API_KEY`
- Set `DODO_PAYMENTS_API_BASE_URL` to `https://test.dodopayments.com` or `https://live.dodopayments.com`
- Set `DODO_PAYMENTS_WEBHOOK_KEY` (Svix/Standard Webhooks secret)
- Create subscription products in Dodo and set:
  - `DODO_PRODUCT_ID_STARTER` (or legacy: `DODO_PLAN_ID_STARTER`)
  - `DODO_PRODUCT_ID_PRO` (or legacy: `DODO_PLAN_ID_PRO`)
  - `DODO_PRODUCT_ID_BUSINESS` (or legacy: `DODO_PLAN_ID_BUSINESS`)
- Optional redirect URLs (otherwise derived from request Origin):
  - `DODO_CHECKOUT_RETURN_URL`
  - `DODO_CHECKOUT_CANCEL_URL`

Notes:
- If Cloudflare R2 is configured (`R2_*` vars), generated images are uploaded and the API returns public URLs; otherwise the API returns base64 data URLs.
