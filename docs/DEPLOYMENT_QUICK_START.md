# Quick Start Deployment Guide

A condensed version for experienced developers who want to deploy quickly.

## Backend (Railway)

1. **Create Railway Project**
   - Go to [railway.app](https://railway.app)
   - New Project → Deploy from GitHub repo
   - Select your repository
   - **Important:** In Settings → Root Directory: Set to `intern-project` (or project root if repo is just intern-project)
   - **Important:** In Settings → Dockerfile Path: Set to `backend/Dockerfile`

2. **Set Environment Variables**
   ```
   DATABASE_URL=postgresql://...
   SUPABASE_URL=https://xxx.supabase.co
   SUPABASE_ANON_KEY=...
   SUPABASE_SERVICE_ROLE_KEY=...
   GITHUB_APP_ID=...
   GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
   GITHUB_APP_SLUG=...
   OPENAI_API_KEY=...
   FRONTEND_APP_URL=https://xxx.vercel.app  # Set after Vercel deploy
   CANDIDATE_APP_URL=https://xxx.vercel.app  # Set after Vercel deploy
   ```

3. **Get Backend URL**
   - Settings → Networking → Generate Domain
   - Copy URL: `https://xxx.up.railway.app`

## Frontend (Vercel)

1. **Deploy to Vercel**
   - Go to [vercel.com](https://vercel.com)
   - Add New Project → Import GitHub repo
   - Set Root Directory: `intern-project/frontend`

2. **Set Environment Variables**
   ```
   NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=...
   NEXT_PUBLIC_API_BASE_URL=https://xxx.up.railway.app  # Your Railway URL
   NEXT_PUBLIC_CANDIDATE_APP_URL=https://xxx.vercel.app  # Update after first deploy
   NEXT_PUBLIC_FRONTEND_APP_URL=https://xxx.vercel.app  # Update after first deploy
   ```

3. **Deploy & Get URL**
   - Click Deploy
   - Copy URL: `https://xxx.vercel.app`

## Connect Them

1. Update Railway: Set `FRONTEND_APP_URL` and `CANDIDATE_APP_URL` to Vercel URL
2. Update Vercel: Set `NEXT_PUBLIC_CANDIDATE_APP_URL` and `NEXT_PUBLIC_FRONTEND_APP_URL` to Vercel URL
3. Redeploy both

## Test

- Backend: Visit `https://xxx.up.railway.app/` → Should see `{"message": "Backend is running 🚀"}`
- Frontend: Visit `https://xxx.vercel.app` → Should load your app
- Check browser console for CORS errors

---

**Full guide with troubleshooting:** [DEPLOYMENT.md](./DEPLOYMENT.md)

