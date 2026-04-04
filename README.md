## OrcaFind AI

Marketing site + authenticated studio for generating social posts and post images.

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
ENV=development uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Serve `frontend/` (any static server) and open:
- `/` marketing
- `/studio/` studio
- `/checkout/` pricing (coming soon)

### Production notes

### Deploy (Vercel + FastAPI on Railway)

Frontend (Vercel):
- Set `window.__ORCAFIND_API_BASE_URL` (optional) to point to Railway FastAPI base URL.
- Set `window.__ORCAFIND_SUPABASE_URL` / `window.__ORCAFIND_SUPABASE_ANON_KEY` (optional) if you want to avoid hardcoding.

Backend (Railway):
- Add a Railway Postgres and set `DATABASE_URL` (required for persistent subscriptions/usage).
- Add a Railway Redis and set `REDIS_URL` (recommended for rate limiting).
- Set `ENV=production`.
- Set `CORS_ALLOW_ORIGINS` to your Vercel production domain(s).
- Optional: set `CORS_ALLOW_ORIGIN_REGEX=https://.*\\.vercel\\.app` for preview deploys.
- Optional: set `SENTRY_DSN` for monitoring.

Notes:
- Generated images are automatically uploaded to R2 if configured; otherwise the API returns base64 data URLs.
