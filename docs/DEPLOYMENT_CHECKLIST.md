# Deployment Checklist

A quick reference checklist for deploying to Vercel (Frontend) + Railway (Backend).

## Pre-Deployment

- [ ] Code is pushed to GitHub
- [ ] All environment variables documented
- [ ] Database migrations tested locally
- [ ] API keys and secrets ready

## Backend Deployment (Railway)

### Initial Setup
- [ ] Created Railway account and project
- [ ] Connected GitHub repository
- [ ] Railway detected Dockerfile correctly

### Environment Variables (Railway)
- [ ] `DATABASE_URL` - Supabase connection string
- [ ] `SUPABASE_URL` - Supabase project URL
- [ ] `SUPABASE_ANON_KEY` - Supabase anonymous key
- [ ] `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- [ ] `GITHUB_APP_ID` - GitHub App ID
- [ ] `GITHUB_APP_PRIVATE_KEY` - GitHub App private key (with `\n` for newlines)
- [ ] `GITHUB_APP_SLUG` - GitHub App slug/name
- [ ] `RESEND_API_KEY` - Resend API key (if using email)
- [ ] `RESEND_FROM_EMAIL` - Resend sender email (if using email)
- [ ] `OPENAI_API_KEY` - OpenAI API key
- [ ] `LLM_PROVIDER` - LLM provider (default: openai)
- [ ] `OPENAI_MODEL` - OpenAI model (default: gpt-4)
- [ ] `CAL_COM_API_KEY` - Cal.com API key (if using scheduling)
- [ ] `CAL_COM_API_URL` - Cal.com API URL (if using scheduling)
- [ ] `FRONTEND_APP_URL` - **Set after Vercel deployment**
- [ ] `CANDIDATE_APP_URL` - **Set after Vercel deployment**

### Deployment
- [ ] Railway build completed successfully
- [ ] Backend URL generated (e.g., `https://xxx.up.railway.app`)
- [ ] Tested backend endpoint: `GET /` returns `{"message": "Backend is running 🚀"}`
- [ ] Backend logs show no errors

## Frontend Deployment (Vercel)

### Initial Setup
- [ ] Created Vercel account
- [ ] Connected GitHub repository
- [ ] Set root directory to `intern-project/frontend` (or correct path)

### Environment Variables (Vercel)
- [ ] `NEXT_PUBLIC_SUPABASE_URL` - Supabase project URL
- [ ] `NEXT_PUBLIC_SUPABASE_ANON_KEY` - Supabase anonymous key
- [ ] `NEXT_PUBLIC_API_BASE_URL` - Railway backend URL
- [ ] `NEXT_PUBLIC_CANDIDATE_APP_URL` - **Update after first deploy**
- [ ] `NEXT_PUBLIC_FRONTEND_APP_URL` - **Update after first deploy**

### Deployment
- [ ] Vercel build completed successfully
- [ ] Frontend URL generated (e.g., `https://xxx.vercel.app`)
- [ ] Frontend loads without errors

## Post-Deployment Configuration

### Update URLs
- [ ] Updated `FRONTEND_APP_URL` in Railway to Vercel URL
- [ ] Updated `CANDIDATE_APP_URL` in Railway to Vercel URL
- [ ] Updated `NEXT_PUBLIC_CANDIDATE_APP_URL` in Vercel
- [ ] Updated `NEXT_PUBLIC_FRONTEND_APP_URL` in Vercel
- [ ] Redeployed backend after URL changes
- [ ] Redeployed frontend after URL changes

### Testing
- [ ] Frontend loads correctly
- [ ] Can log in via Supabase auth
- [ ] API calls work (check browser Network tab)
- [ ] No CORS errors in browser console
- [ ] Database operations work
- [ ] GitHub integration works (if applicable)
- [ ] Email sending works (if applicable)
- [ ] LLM analysis works (if applicable)

### Optional: Custom Domains
- [ ] Configured custom domain in Vercel
- [ ] Configured DNS records for Vercel
- [ ] Configured custom domain in Railway
- [ ] Configured DNS records for Railway
- [ ] Updated environment variables with custom domains
- [ ] Tested custom domains

### Optional: GitHub Webhooks
- [ ] Updated GitHub App webhook URL to Railway backend
- [ ] Tested webhook delivery

## Monitoring & Maintenance

- [ ] Set up Railway monitoring/alerts
- [ ] Set up Vercel monitoring/alerts
- [ ] Documented deployment process
- [ ] Set up CI/CD (automatic deployments on push)

## Troubleshooting Reference

### Backend Issues
- Check Railway logs for errors
- Verify all environment variables are set
- Test database connection
- Check CORS settings match frontend URL exactly

### Frontend Issues
- Check Vercel build logs
- Verify environment variables are set
- Check browser console for errors
- Verify API calls are going to correct backend URL

### Connection Issues
- Verify `NEXT_PUBLIC_API_BASE_URL` matches Railway URL
- Check CORS settings in backend
- Verify backend is accessible (try opening URL in browser)

---

**Quick Links:**
- Railway Dashboard: https://railway.app
- Vercel Dashboard: https://vercel.com
- Full Deployment Guide: [DEPLOYMENT.md](./DEPLOYMENT.md)

