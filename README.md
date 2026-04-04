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

- Add persistent storage for entitlements/subscriptions (current grants/usage counters are in-memory).
- Add rate limiting and abuse protection.
- Prefer uploading generated images to R2 (supported) to avoid large base64 payloads.
- Configure CORS origins via environment for staging/prod.
