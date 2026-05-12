# Deployment Guide (Render + Vercel + UptimeRobot)

This project deploys best as:
- Backend API + worker + Postgres on Render
- Frontend (Vite React SPA) on Vercel

## 1) Pre-deploy security checklist

1. Rotate all local secrets before production deploy:
   - GitHub OAuth client secret
   - Gemini API key
   - Firebase service account credentials
   - `TOKEN_ENCRYPTION_KEY`
   - `GITHUB_STATE_SECRET`
2. Never commit `.env` files. Keep only `.env.example` in git.
3. Ensure production URLs use HTTPS:
   - `FRONTEND_URL`
   - `GITHUB_OAUTH_REDIRECT_URI`
4. Keep Firebase Admin credentials in `FIREBASE_CREDENTIALS_JSON` (recommended), not in source files.

## 2) Deploy backend on Render

1. Commit and push `render.yaml` from repo root.
2. In Render dashboard, create from Blueprint:
   - `https://dashboard.render.com/blueprint/new?repo=https://github.com/Grihith-Reddy/MinorProject_Kavi-Github-Intelligence-Platform_Grihith`
3. Render will create:
   - `kavi-api` (web)
   - `kavi-ingestion-worker` (worker)
   - `kavi-postgres` (database)
4. Fill all `sync: false` env vars during setup.
5. Apply schema/migrations once to the created Postgres database:
   - `database/schema.sql`
   - `database/migrations/002_access_control_and_sync_jobs.sql`
   - `database/migrations/003_chat_memory.sql`
6. Verify health endpoints:
   - `GET /health/live`
   - `GET /health/ready`

Note:
- Render Free supports web + Postgres, but not worker plan. Worker is configured as `starter`.

## 3) Deploy frontend on Vercel

1. Import the same GitHub repository in Vercel.
2. Set project Root Directory to `frontend`.
3. Build settings:
   - Install: `npm ci`
   - Build: `npm run build`
   - Output: `dist`
4. Configure environment variables in Vercel:
   - `VITE_API_BASE_URL=https://<your-render-api-domain>/api`
   - `VITE_FIREBASE_API_KEY`
   - `VITE_FIREBASE_AUTH_DOMAIN`
   - `VITE_FIREBASE_PROJECT_ID`
   - `VITE_FIREBASE_APP_ID`
   - `VITE_FIREBASE_MESSAGING_SENDER_ID`
5. Deploy and validate route refreshes (SPA rewrite is set via `frontend/vercel.json`).

## 4) Final cross-platform wiring

1. Copy Vercel production URL and set Render `FRONTEND_URL` to it.
2. Set `GITHUB_OAUTH_REDIRECT_URI` to:
   - `https://<your-render-api-domain>/api/github/callback`
3. Redeploy Render web + worker.

## 5) UptimeRobot setup

1. Create an HTTP(s) monitor for:
   - `https://<your-render-api-domain>/health/live`
2. Optional second monitor for frontend:
   - `https://<your-vercel-domain>/`
3. Configure alert contacts and notification channels.
4. Start with 5-minute interval on Free plan.

## 6) Smoke test after go-live

1. Login with Google/Firebase.
2. Connect GitHub OAuth.
3. Trigger a repository sync.
4. Confirm worker processes queued jobs.
5. Open dashboard and run at least one chat query.
