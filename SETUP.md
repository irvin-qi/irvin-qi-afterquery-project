# Setup Guide - Step by Step

This guide walks you through setting up the Afterquery coding interview platform using Docker. Follow each step in order.

## Prerequisites

- **Docker Desktop** installed and running
- **Supabase account** (free tier works)
- **GitHub account** with an organization (or create one)
- **Resend account** (optional, for emails)

---

## PART 1: Manual Setup Tasks

You need to complete these steps before running Docker containers.

### Step 1: Set Up Supabase (Database + Auth)

#### 1.1 Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up/login
2. Click **"New Project"**
3. Fill in:
   - **Name**: `afterquery-platform` (or your choice)
   - **Database Password**: Choose a strong password (SAVE THIS - you'll need it)
   - **Region**: Choose closest to you
4. Click **"Create new project"** (takes 1-2 minutes)

#### 1.2 Get Your Supabase Credentials

Once the project is ready:

1. Go to **Settings** (gear icon) → **API**
2. Copy these values (you'll use them later):
   - **Project URL**: `https://xxxxxxxxxxxxx.supabase.co` 
     - This is listed as "Project URL" on the API settings page
   - **anon/public key**: Long string starting with `eyJ...`
     - This is listed as "Project API keys" → "anon public"
   - **service_role key**: Long string starting with `eyJ...`
     - This is listed as "Project API keys" → "service_role" (click "Reveal" to see it)
     - ⚠️ **Important**: Keep this secret! It has admin privileges.

3. Go to **Settings** → **Database**
4. Scroll down to **Connection string** → **URI**
5. Copy the connection string, it looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxxx.supabase.co:5432/postgres
   ```
   - Replace `[YOUR-PASSWORD]` with the database password you created in step 1.1
   - This is your `DATABASE_URL`

#### 1.3 Run Database Schema

1. In Supabase dashboard, go to **SQL Editor** (left sidebar)
2. Click **"New query"**
3. Open the file `db/schema.sql` from this project
4. Copy **ALL** the contents (it's about 194 lines)
5. Paste into the SQL Editor
6. Click **"Run"** (or press Cmd/Ctrl + Enter)
7. You should see "Success. No rows returned" - this means it worked!

#### 1.4 Configure Email Auth (Optional but Recommended)

1. Go to **Authentication** → **URL Configuration**
2. Add to **Redirect URLs**:
   ```
   http://localhost:3000/**
   ```
3. Click **Save**

---

### Step 2: Set Up GitHub App

#### 2.1 Create GitHub Organization (if you don't have one)

1. Go to [github.com](https://github.com)
2. Click your profile → **Settings**
3. Click **Organizations** → **New organization**
4. Choose a plan (free is fine)
5. Name your org (e.g., `my-company-assessments`)
6. Complete setup

#### 2.2 Create the GitHub App

1. In your GitHub organization, go to **Settings**
2. Scroll down to **Developer settings** (bottom left)
3. Click **GitHub Apps** → **New GitHub App**

4. Fill in the form:
   - **GitHub App name**: `Afterquery Assessment Helper` (or your choice)
   - **Homepage URL**: `http://localhost:3000` (for local dev)
   - **User authorization callback URL**: `http://localhost:3000/app/github/install/callback`
   - **Webhook**: 
     - ❌ Uncheck **Active** (leave webhooks disabled for now)
   
5. Scroll to **Repository permissions**:
   - **Administration**: `Read and write`
   - **Contents**: `Read and write`
   - **Metadata**: `Read-only` (default)
   - **Pull requests**: `Read and write`

6. Scroll to **Subscribe to events**:
   - ✅ Check **Repository** (optional, for future use)

7. Click **Create GitHub App** at the bottom

#### 2.3 Get GitHub App Credentials

1. On the GitHub App settings page, you'll see:
   - **App ID**: A number like `123456` - COPY THIS
   - **App slug**: The URL-friendly name in the URL
     - If URL is `github.com/settings/apps/your-app-name`, then slug is `your-app-name` - COPY THIS

2. Scroll down to **Private keys**
3. Click **Generate a private key**
4. Download the `.pem` file that downloads
5. Open the `.pem` file in a text editor
6. Copy the entire contents (including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`)
   - It should look like:
     ```
     -----BEGIN RSA PRIVATE KEY-----
     MIIEpAIBAAKCAQEA...
     ...many lines...
     -----END RSA PRIVATE KEY-----
     ```

#### 2.4 Install GitHub App on Your Organization

1. On the GitHub App settings page, click **Install App** (top right)
2. Select your organization
3. Choose **All repositories** (or specific ones if preferred)
4. Click **Install**
5. ✅ Done! The app is now installed (you don't need the installation ID manually)

---

### Step 3: Set Up Resend (Optional - for emails)

If you want email functionality:

1. Go to [resend.com](https://resend.com) and sign up
2. Go to **API Keys** → **Create API Key**
3. Name it `afterquery-local` and create
4. Copy the API key (starts with `re_...`)
5. You'll also need an email domain, or use Resend's test domain for development

---

### Step 3b: Set Up OpenAI (Required for LLM Analysis feature)

The LLM Analysis feature provides AI-powered code reviews. You'll need an OpenAI API key:

1. Go to [platform.openai.com](https://platform.openai.com) and sign up/login
2. Go to **API keys** (or visit [platform.openai.com/api-keys](https://platform.openai.com/api-keys))
3. Click **Create new secret key**
4. Name it `afterquery-llm-analysis` (or any name you prefer)
5. Copy the API key (starts with `sk-...`)
   - ⚠️ **Important**: Save this key immediately - you won't be able to see it again!
6. You'll add this to your `.env` file in Step 4

**Note:**
- OpenAI charges per API usage (see [pricing](https://openai.com/api/pricing/))
- The LLM Analysis feature uses GPT-4 by default (you can change this with `OPENAI_MODEL`)
- You can also use Anthropic Claude by setting `LLM_PROVIDER=anthropic` (requires `ANTHROPIC_API_KEY`)

---

## PART 2: Configure Environment Variables

Now that you have all your credentials, create the environment files.

### Step 4: Create Backend Environment File

Create a file named `.env` in the **project root** (same level as `docker-compose.yml`):

```bash
# Database (Supabase)
# Replace [YOUR-PASSWORD] with your Supabase database password
# Replace xxxxxxxxxxxxx with your Supabase project reference ID
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxxx.supabase.co:5432/postgres

# Supabase Auth
# Replace xxxxxxxxxxxxx with your Supabase project reference ID
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# GitHub App
# Replace with values from Step 2.3
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n...all lines...\n-----END RSA PRIVATE KEY-----\n"
GITHUB_APP_SLUG=your-app-name

# Email (Resend - optional)
# If you set up Resend, uncomment and fill these:
# RESEND_API_KEY=re_xxxxxxxxxxxxx
# RESEND_FROM_EMAIL=noreply@yourdomain.com

# LLM (for AI-powered code analysis)
# Required for the LLM Analysis feature in code reviews
# Get your API key from https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-xxxxxxxxxxxxx
# Optional: Change provider (default: "openai")
# LLM_PROVIDER=openai
# Optional: Change model (default: "gpt-4")
# OPENAI_MODEL=gpt-4

# URLs (for local development - don't change these)
CANDIDATE_APP_URL=http://localhost:3000
FRONTEND_APP_URL=http://localhost:3000
```

**Important Notes:**
- For `GITHUB_APP_PRIVATE_KEY`: You can paste the PEM file content as-is, OR replace newlines with `\n`
- Make sure the private key is wrapped in quotes `"..."` if it has `\n` characters
- Don't add spaces around the `=` sign
- Don't add quotes around URLs or simple values (except the private key if using `\n`)

### Step 5: Create Frontend Environment File

Create a file named `.env.local` in the `frontend/` directory:

```bash
# Supabase (same values from Step 1.2)
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# API (don't change these for local dev)
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_CANDIDATE_APP_URL=http://localhost:3000
```

---

## PART 3: Run with Docker

Now you're ready to run everything!

### Step 6: Start Docker Desktop

1. Make sure Docker Desktop is installed and running
2. You should see the Docker whale icon in your system tray/menu bar

### Step 7: Build and Run Containers

Open a terminal in the project root directory and run:

```bash
# For development (with hot-reload)
docker-compose -f docker-compose.dev.yml up --build
```

**What this does:**
- Builds both backend and frontend Docker images
- Installs all dependencies
- Starts both services
- Hot-reloads on code changes (development mode)

**First time:** This takes 2-5 minutes as it downloads images and installs dependencies.

**You'll see logs from both services.** Wait until you see:
```
backend  | INFO:     Uvicorn running on http://0.0.0.0:8000
frontend | ▲ Next.js 14.2.4
frontend | - Local:        http://localhost:3000
```

### Step 8: Verify Everything Works

1. **Backend Health Check:**
   - Open browser: http://localhost:8000
   - Should see: `{"message":"Backend is running 🚀"}`

2. **Frontend:**
   - Open browser: http://localhost:3000
   - Should see the login page

3. **API Docs:**
   - Open browser: http://localhost:8000/docs
   - Should see interactive API documentation

### Step 9: First-Time Login

1. Go to http://localhost:3000
2. Enter your email address
3. Click **"Send magic link"**
4. Check your email for the magic link
5. Click the link to sign in
6. You'll be redirected to create an organization
7. Create your organization
8. You'll see the dashboard

---

## Useful Docker Commands

```bash
# Stop all services (Ctrl+C if running in foreground)
docker-compose -f docker-compose.dev.yml down

# Run in background (detached mode)
docker-compose -f docker-compose.dev.yml up --build -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f

# View logs for specific service
docker-compose -f docker-compose.dev.yml logs -f backend
docker-compose -f docker-compose.dev.yml logs -f frontend

# Rebuild after changing dependencies
docker-compose -f docker-compose.dev.yml up --build --force-recreate

# Stop and remove everything
docker-compose -f docker-compose.dev.yml down -v
```

---

## Troubleshooting

### ❌ "DATABASE_URL not found" or connection errors

**Check:**
- Did you create `.env` file in the project root (not in a subdirectory)?
- Is `DATABASE_URL` spelled correctly?
- Did you replace `[YOUR-PASSWORD]` with your actual Supabase password?
- Is your Supabase project active (not paused)?

**Fix:**
```bash
# Check if .env file exists
ls -la .env

# View contents (check for typos)
cat .env
```

### ❌ "GitHub App authentication failed"

**Check:**
- Is `GITHUB_APP_ID` a number (not in quotes)?
- Is `GITHUB_APP_PRIVATE_KEY` wrapped in quotes and has `\n` for newlines?
- Is `GITHUB_APP_SLUG` correct (matches the URL slug)?
- Did you install the GitHub App on your organization?

**Fix:**
```bash
# Check your GitHub App settings
# Make sure the app is installed on your organization
```

### ❌ Frontend can't connect to backend (CORS errors)

**Check:**
- Are `FRONTEND_APP_URL` and `CANDIDATE_APP_URL` set to `http://localhost:3000`?
- Is backend running and accessible at http://localhost:8000?

**Fix:**
- Verify backend is running: `curl http://localhost:8000`
- Check `.env` file has correct URLs

### ❌ "Module not found" or build errors

**Fix:**
```bash
# Stop containers
docker-compose -f docker-compose.dev.yml down

# Rebuild from scratch
docker-compose -f docker-compose.dev.yml build --no-cache

# Start again
docker-compose -f docker-compose.dev.yml up
```

### ❌ Email magic link not working

**Check:**
- Is your email address correct?
- Check spam folder
- In Supabase: **Authentication** → **Providers** → **Email** is enabled
- Did you add `http://localhost:3000/**` to Redirect URLs?

---

## Next Steps After Setup

1. **Connect GitHub App:**
   - In the dashboard, click **"Connect GitHub App"**
   - Authorize the app you created
   - You should see it connected

2. **Create Your First Seed:**
   - Go to **Assessments** → **New Assessment**
   - Create a seed repository (paste any GitHub repo URL)
   - This creates a template repository

3. **Create an Assessment:**
   - Fill in assessment details
   - Set time windows (e.g., 72h to start, 48h to complete)

4. **Invite a Candidate:**
   - Add candidate email
   - System sends invitation email (if Resend is configured)

5. **Test the Flow:**
   - Click the invitation link as a candidate
   - Start the assessment
   - See your private repository created

---

## Production Deployment

For production, you'll need to:
- Update all URLs to your production domain
- Set up a production Supabase project
- Configure production GitHub App callback URLs
- Use production email service (Resend with verified domain)
- Run with `docker-compose up --build` (production mode)

---

## Summary Checklist

Before running Docker, make sure you have:

- [ ] Created Supabase project
- [ ] Got Supabase credentials (URL, anon key, service_role key, DATABASE_URL)
- [ ] Ran database schema in Supabase SQL Editor
- [ ] Created GitHub App
- [ ] Got GitHub App credentials (App ID, Private Key, Slug)
- [ ] Installed GitHub App on organization
- [ ] Created OpenAI API key (for LLM Analysis feature)
- [ ] Created `.env` file in project root with all backend variables (including `OPENAI_API_KEY`)
- [ ] Created `frontend/.env.local` file with frontend variables
- [ ] Docker Desktop is running
- [ ] Ready to run `docker-compose -f docker-compose.dev.yml up --build`

Once all checked, you're ready to go! 🚀
