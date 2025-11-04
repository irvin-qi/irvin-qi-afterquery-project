# Deployment Guide: Vercel (Frontend) + Railway (Backend)

This guide will walk you through deploying your project to production:
- **Frontend (Next.js)** → Vercel
- **Backend (FastAPI)** → Railway

---

## Prerequisites

1. **GitHub Account** - Your code should be in a GitHub repository
2. **Vercel Account** - Sign up at [vercel.com](https://vercel.com) (free tier available)
3. **Railway Account** - Sign up at [railway.app](https://railway.app) (free tier available)
4. **Supabase Project** - Already set up (from local development)
5. **All API Keys** - GitHub App, Resend, OpenAI, Cal.com, etc. (from local development)

---

## PART 1: Deploy Backend to Railway

### Step 1: Prepare Your Repository

1. Make sure your code is pushed to GitHub
2. Ensure your `backend/Dockerfile` is correct (it should be)
3. Verify your `backend/requirements.txt` is up to date

### Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Railway will detect the backend automatically

### Step 3: Configure Railway Service

1. **Set Root Directory and Dockerfile Path:**
   - Click on the service
   - Go to **Settings** → **Root Directory**
   - Set Root Directory to: `intern-project` (or the path to your project root)
   - Go to **Settings** → **Dockerfile Path**
   - Set Dockerfile Path to: `backend/Dockerfile`
   
   **Why?** Your Dockerfile expects the build context to be from the project root (it copies `backend/requirements.txt`, `backend/app`, and `db/`), so Railway needs to build from the root directory.

2. **Alternative: If Railway Auto-Detects:**
   - If Railway detects the Dockerfile automatically but builds from the wrong directory, you may need to adjust the Root Directory setting
   - The Dockerfile at `backend/Dockerfile` expects paths relative to the project root

3. **Set Build Command** (if needed):
   - Railway usually auto-detects Docker, but if not:
   - Go to **Settings** → **Build Command**: Leave empty (uses Dockerfile)
   - **Start Command**: Leave empty (uses Dockerfile CMD)

### Step 4: Configure Environment Variables

In Railway, go to your service → **Variables** tab and add:

```bash
# Database (Supabase)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxxx.supabase.co:5432/postgres

# Supabase Auth
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# GitHub App
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----\n"
GITHUB_APP_SLUG=your-app-name

# Email (Resend - optional)
RESEND_API_KEY=re_xxxxxxxxxxxxx
RESEND_FROM_EMAIL=noreply@yourdomain.com

# LLM (OpenAI)
OPENAI_API_KEY=sk-xxxxxxxxxxxxx
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4

# Cal.com (optional)
CAL_COM_API_KEY=your-cal-com-api-key
CAL_COM_API_URL=https://api.cal.com/v1

# URLs - IMPORTANT: Update these with your production URLs
# We'll set these after we get the Railway URL
FRONTEND_APP_URL=https://your-app.vercel.app
CANDIDATE_APP_URL=https://your-app.vercel.app
```

**Important Notes:**
- For `GITHUB_APP_PRIVATE_KEY`: Paste the entire PEM content, replacing newlines with `\n`
- Keep the private key in quotes `"..."` if it contains `\n`
- For `DATABASE_URL`: Use your Supabase connection string (same as local)
- Don't add `FRONTEND_APP_URL` and `CANDIDATE_APP_URL` yet - we'll add them after Vercel deployment

### Step 5: Deploy and Get Backend URL

1. Railway will automatically start building and deploying
2. Once deployed, go to **Settings** → **Networking**
3. Click **"Generate Domain"** to get a public URL
4. Your backend URL will be something like: `https://your-app.up.railway.app`
5. **Copy this URL** - you'll need it for the frontend!

### Step 6: Test Backend

1. Visit `https://your-backend-url.up.railway.app/` in your browser
2. You should see: `{"message": "Backend is running 🚀"}`
3. If you see this, your backend is working! ✅

### Step 7: Update CORS in Railway

After you get your Vercel URL (next section), come back and:
1. Update `FRONTEND_APP_URL` in Railway to your Vercel URL
2. Update `CANDIDATE_APP_URL` in Railway to your Vercel URL
3. Railway will automatically redeploy with the new CORS settings

---

## PART 2: Deploy Frontend to Vercel

### Step 1: Install Vercel CLI (Optional but Recommended)

```bash
npm install -g vercel
```

Or you can use the web interface (no CLI needed).

### Step 2: Deploy via Vercel Dashboard

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click **"Add New"** → **"Project"**
3. Import your GitHub repository
4. Vercel will auto-detect it's a Next.js project

### Step 3: Configure Project Settings

In the project configuration:

1. **Framework Preset**: Next.js (auto-detected)
2. **Root Directory**: `intern-project/frontend` (or wherever your frontend code is)
3. **Build Command**: `npm run build` (should be auto-detected)
4. **Output Directory**: `.next` (should be auto-detected)
5. **Install Command**: `npm install` (should be auto-detected)

### Step 4: Configure Environment Variables

In Vercel, go to **Settings** → **Environment Variables** and add:

```bash
# Supabase (same as local)
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# API - IMPORTANT: Use your Railway backend URL here!
NEXT_PUBLIC_API_BASE_URL=https://your-backend-url.up.railway.app

# App URLs
NEXT_PUBLIC_CANDIDATE_APP_URL=https://your-app.vercel.app
NEXT_PUBLIC_FRONTEND_APP_URL=https://your-app.vercel.app
```

**Important:**
- Replace `https://your-backend-url.up.railway.app` with your actual Railway backend URL from Part 1
- The `NEXT_PUBLIC_*` prefix makes these available in the browser
- Don't add these URLs yet - we'll update them after the first deployment

### Step 5: Deploy

1. Click **"Deploy"**
2. Vercel will build and deploy your frontend
3. Once complete, you'll get a URL like: `https://your-app.vercel.app`
4. **Copy this URL** - you'll need it for the backend!

### Step 6: Update Environment Variables

After the first deployment:

1. Go back to **Settings** → **Environment Variables**
2. Update `NEXT_PUBLIC_CANDIDATE_APP_URL` with your actual Vercel URL
3. Update `NEXT_PUBLIC_FRONTEND_APP_URL` with your actual Vercel URL
4. Go to **Deployments** → **Redeploy** the latest deployment to apply changes

---

## PART 3: Connect Frontend and Backend

### Step 1: Update Backend CORS

1. Go back to Railway
2. Update environment variables:
   - `FRONTEND_APP_URL` = `https://your-app.vercel.app`
   - `CANDIDATE_APP_URL` = `https://your-app.vercel.app`
3. Railway will automatically redeploy

### Step 2: Update Frontend API URL

1. Go back to Vercel
2. Ensure `NEXT_PUBLIC_API_BASE_URL` is set to your Railway backend URL
3. If you need to update it, redeploy

### Step 3: Test the Connection

1. Visit your Vercel frontend URL
2. Try logging in or using a feature that calls the API
3. Open browser DevTools → Network tab
4. Check if API calls are going to your Railway backend
5. If you see CORS errors, double-check your backend CORS settings

---

## PART 4: Configure Custom Domains (Optional)

### Vercel Custom Domain

1. Go to Vercel project → **Settings** → **Domains**
2. Add your custom domain (e.g., `app.yourdomain.com`)
3. Follow Vercel's DNS configuration instructions
4. Update environment variables with the new domain

### Railway Custom Domain

1. Go to Railway service → **Settings** → **Networking**
2. Add your custom domain
3. Configure DNS as instructed by Railway
4. Update environment variables with the new domain

---

## PART 5: Database Migrations

Your backend automatically runs migrations on startup (see `database.py`), but if you need to run them manually:

1. **Option 1: Via Railway Shell**
   - Go to Railway → Your service → **Deployments** → Click on a deployment
   - Open the **Shell** tab
   - Run migrations manually if needed

2. **Option 2: Local Migration**
   - Run migrations locally pointing to production database (not recommended for security)

3. **Option 3: SQL Scripts**
   - Apply migration SQL files directly in Supabase dashboard

---

## PART 6: Monitoring and Debugging

### Railway Logs

1. Go to Railway → Your service
2. Click **"View Logs"** to see real-time logs
3. Check for any startup errors or database connection issues

### Vercel Logs

1. Go to Vercel → Your project → **Deployments**
2. Click on a deployment to see build logs
3. Check **Runtime Logs** for runtime errors

### Common Issues

**Backend Issues:**
- **Database connection errors**: Check `DATABASE_URL` is correct
- **CORS errors**: Verify `FRONTEND_APP_URL` matches your Vercel URL exactly
- **GitHub App errors**: Check `GITHUB_APP_PRIVATE_KEY` formatting (newlines as `\n`)

**Frontend Issues:**
- **API calls failing**: Check `NEXT_PUBLIC_API_BASE_URL` is correct
- **Auth not working**: Verify Supabase environment variables
- **Build errors**: Check Node.js version compatibility

---

## PART 7: GitHub App Webhook Configuration

If your GitHub App uses webhooks:

1. Go to your GitHub App settings
2. Set **Webhook URL** to: `https://your-backend-url.up.railway.app/api/github/webhook`
3. Set **Webhook Secret** (if required) and add it to Railway environment variables

---

## PART 8: Environment-Specific Settings

### Production vs Development

You can use different environment variables for different environments:

**Vercel:**
- **Production**: Use for production deployments
- **Preview**: Use for pull request previews
- **Development**: Use for local development

**Railway:**
- Create separate environments or services for staging/production

### Recommended Setup

1. **Production**: Production Railway + Production Vercel
2. **Staging**: Separate Railway service + Vercel preview deployments
3. **Development**: Local Docker setup

---

## Quick Reference: Environment Variables Checklist

### Railway (Backend)
- [ ] `DATABASE_URL`
- [ ] `SUPABASE_URL`
- [ ] `SUPABASE_ANON_KEY`
- [ ] `SUPABASE_SERVICE_ROLE_KEY`
- [ ] `GITHUB_APP_ID`
- [ ] `GITHUB_APP_PRIVATE_KEY`
- [ ] `GITHUB_APP_SLUG`
- [ ] `RESEND_API_KEY` (optional)
- [ ] `RESEND_FROM_EMAIL` (optional)
- [ ] `OPENAI_API_KEY`
- [ ] `LLM_PROVIDER` (optional, default: openai)
- [ ] `OPENAI_MODEL` (optional, default: gpt-4)
- [ ] `CAL_COM_API_KEY` (optional)
- [ ] `CAL_COM_API_URL` (optional)
- [ ] `FRONTEND_APP_URL` (update after Vercel deploy)
- [ ] `CANDIDATE_APP_URL` (update after Vercel deploy)

### Vercel (Frontend)
- [ ] `NEXT_PUBLIC_SUPABASE_URL`
- [ ] `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- [ ] `NEXT_PUBLIC_API_BASE_URL` (Railway backend URL)
- [ ] `NEXT_PUBLIC_CANDIDATE_APP_URL` (update after first deploy)
- [ ] `NEXT_PUBLIC_FRONTEND_APP_URL` (update after first deploy)

---

## Troubleshooting

### Backend won't start
- Check Railway logs for errors
- Verify all required environment variables are set
- Check database connection string format

### Frontend can't connect to backend
- Verify `NEXT_PUBLIC_API_BASE_URL` is correct
- Check browser console for CORS errors
- Verify backend is running and accessible

### CORS errors
- Ensure `FRONTEND_APP_URL` in Railway matches Vercel URL exactly (including `https://`)
- Check backend logs to see which origins are allowed
- Redeploy backend after changing CORS settings

### Database connection issues
- Verify `DATABASE_URL` is correct
- Check Supabase connection settings
- Ensure your IP is allowed (or use Supabase connection pooling)

---

## Next Steps

1. ✅ Deploy backend to Railway
2. ✅ Deploy frontend to Vercel
3. ✅ Connect them together
4. ✅ Test all functionality
5. ✅ Set up custom domains (optional)
6. ✅ Configure monitoring/alerts
7. ✅ Set up CI/CD (automatic deployments on push)

---

## Additional Resources

- [Railway Documentation](https://docs.railway.app)
- [Vercel Documentation](https://vercel.com/docs)
- [Next.js Deployment](https://nextjs.org/docs/deployment)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)

---

**Congratulations! 🎉 Your app should now be live in production!**

