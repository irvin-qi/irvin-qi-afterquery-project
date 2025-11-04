# Coding Interview Platform – Architecture Plan

> Goal: Build a Candidate Code–style take-home interview platform with Next.js (Vercel), Supabase (Postgres + Auth), and FastAPI (Railway). GitHub is the VCS backend; Resend handles email. This document specifies system architecture, schema, services, flows, and an MVP implementation plan tuned for a 10-hour take-home that can be extended over the next 3 months.

---

## 1) High-Level Architecture

### Frontend (Vercel / Next.js 14 App Router)

- Admin web app: create assessments, manage seeds, invite candidates, review submissions, send follow-ups.
- Candidate web app: start page, deadlines, submit, status.
- Auth: Supabase Auth (email magic link or OAuth) for admins; candidates use tokenized invite links, not full accounts.

### Backend (Railway / FastAPI + Workers)

- REST/GraphQL API consumed by Next.js server components & client.
- Job queue workers (Celery/Arq/RQ) for GitHub operations & emails.
- “Git Token Gateway” (MVP: token broker; Stretch: reverse-proxy for Git smart HTTP) to issue/validate tokens and gate pushes.

### Data (Supabase / Postgres)

- Core metadata (assessments, seeds, invitations, candidate repos, tokens, submissions, comments, emails, events).
- RLS for multi-tenant orgs.

### External Integrations

- GitHub App (via Probot or direct REST): repo create/from-template, permissions, webhooks, compare/diff, content read.
- Resend: transactional email (invites, reminders, follow-ups).
- (Optional later) Cloudflare Email Routing / domain for DKIM/SPF.

### Hosting

- Next.js → Vercel
- FastAPI API + workers → Railway
- Supabase managed
- GitHub App installed in a host org (e.g., `your-company-assessments`)

---

## 2) Git Strategy & Token Model

### 2.1 Seed Repos

- Admin pastes **source GitHub URL** (public or private; if private, the GitHub App must have access).
- Backend creates a **private seed repo** in your org using one of two modes:
  1. **Fork + Sync** (simple): create private fork, set default branch to `main`; use scheduled workflow or webhook to sync upstream `main` → seed `main`.
  2. **Mirror Action** (robust): a GitHub Action in the seed fetches upstream URL and force-updates `main` on upstream pushes.
- Store `seed_repo_id`, `default_branch = main`, and **current head SHA**.
- **Rule**: Candidates always pin to the seed’s `main` SHA at start time. Updating the upstream later will only affect *new* candidates.

### 2.2 Candidate Repos

- When candidate clicks **Start**, worker creates **private repo from seed**
  - Preferred: **Generate from template** API (seed must be marked template). Guarantees new repo at seed’s current `main` HEAD.
  - Alternative: Programmatic clone/push if template not available.
- Lock default branch to `main`.
- Record `seed_sha_pinned`, `candidate_repo_id/slug`, `started_at`.

### 2.3 Push/Clone Authentication

- Use a **GitHub App** (installation on the host org). App grants repo-scoped tokens (1-hour lifetime). We wrap this to satisfy “single URL, no login” requirement.

#### MVP (Token Broker – recommended for take-home)

- Candidate clones with URL like:
  ```
  https://git.yourdomain.com/r/<assignment-slug>.git?token=<opaque>
  ```
- Their Git client calls our **broker** endpoint `/git/credential` (documented in README) via Git’s credential helper (one-time provided command we show on Start page). The helper exchanges the opaque token → **short-lived GitHub App token**, then returns a credentialed URL like:
  ```
  https://x-access-token:<gh_app_token>@github.com/your-org/<candidate-repo>.git
  ```
- The helper re-invokes on credential expiry; broker checks assessment window and issues a new app token iff active.
- Advantage: no need to reverse-proxy Git smart-HTTP.

#### Stretch (Full Git Gateway)

- Implement reverse proxy speaking Git smart-HTTP (e.g., `git-http-backend` via a small Go/Node service). Validate `opaque` token, mint GH App token per request, and forward to GitHub. This allows stock Git to work with the opaque token URL without extra helpers.

#### Revocation

- On Submit/expiry, the **opaque token** is revoked in DB; broker stops issuing GitHub tokens → pushes fail immediately.

---

## 3) Data Model (Postgres / Supabase)

```sql
-- Tenancy
create table orgs (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz default now()
);

create table users (
  id uuid primary key,
  email text unique not null,
  name text,
  created_at timestamptz default now()
);

create table org_members (
  org_id uuid references orgs(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  role text check (role in ('owner','admin','viewer')) not null,
  primary key (org_id, user_id)
);

-- Assessments & Seeds
create table seeds (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references orgs(id) on delete cascade,
  source_repo_url text not null,
  seed_repo_full_name text not null, -- org/name
  default_branch text not null default 'main',
  is_template boolean not null default true,
  latest_main_sha text,
  created_at timestamptz default now()
);

create table assessments (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references orgs(id) on delete cascade,
  seed_id uuid references seeds(id) on delete restrict,
  title text not null,
  description text,
  instructions markdown,
  candidate_email_subject text,
  candidate_email_body markdown,
  time_to_start interval not null,   -- e.g., '72 hours'
  time_to_complete interval not null, -- e.g., '48 hours'
  created_by uuid references users(id),
  created_at timestamptz default now()
);

-- Invitations & Candidate Instances
create table invitations (
  id uuid primary key default gen_random_uuid(),
  assessment_id uuid references assessments(id) on delete cascade,
  candidate_email text not null,
  candidate_name text,
  status text check (status in ('sent','accepted','started','submitted','expired','revoked')) default 'sent',
  start_deadline timestamptz,  -- sent_at + time_to_start
  complete_deadline timestamptz, -- set on start: started_at + time_to_complete
  start_link_token text unique not null, -- opaque link token
  sent_at timestamptz default now(),
  started_at timestamptz,
  submitted_at timestamptz,
  expired_at timestamptz
);

create table candidate_repos (
  id uuid primary key default gen_random_uuid(),
  invitation_id uuid references invitations(id) on delete cascade,
  seed_sha_pinned text not null,
  repo_full_name text not null, -- org/candidate-X-uuid
  repo_html_url text,
  github_repo_id bigint,
  active boolean default true,
  archived boolean default false,
  created_at timestamptz default now()
);

-- Git Access Tokens (opaque)
create table access_tokens (
  id uuid primary key default gen_random_uuid(),
  invitation_id uuid references invitations(id) on delete cascade,
  repo_full_name text not null,
  opaque_token text unique not null,
  scope text check (scope in ('clone','push','clone+push')) default 'clone+push',
  expires_at timestamptz not null,
  revoked boolean default false,
  created_at timestamptz default now(),
  last_used_at timestamptz
);

-- Submissions & Review
create table submissions (
  id uuid primary key default gen_random_uuid(),
  invitation_id uuid references invitations(id) on delete cascade,
  final_sha text not null,
  repo_html_url text,
  created_at timestamptz default now()
);

create table review_comments (
  id uuid primary key default gen_random_uuid(),
  invitation_id uuid references invitations(id) on delete cascade,
  path text,
  line integer,
  body markdown not null,
  created_by uuid references users(id),
  created_at timestamptz default now()
);

create table review_feedback (
  id uuid primary key default gen_random_uuid(),
  invitation_id uuid references invitations(id) on delete cascade,
  summary markdown,
  rating int check (rating between 1 and 5),
  created_by uuid references users(id),
  created_at timestamptz default now()
);

-- Emails & Templates
create table email_templates (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references orgs(id) on delete cascade,
  key text unique, -- e.g., 'follow_up_default'
  subject text,
  body markdown,
  created_at timestamptz default now()
);

create table email_events (
  id uuid primary key default gen_random_uuid(),
  invitation_id uuid references invitations(id) on delete cascade,
  type text check (type in ('invite','reminder','follow_up')),
  provider_id text,
  to_email text,
  status text,
  created_at timestamptz default now()
);

-- Audit / Webhooks
create table audit_events (
  id bigserial primary key,
  kind text,
  actor text,
  meta jsonb,
  created_at timestamptz default now()
);
```

> Indexes: `access_tokens (opaque_token)`, `candidate_repos (repo_full_name)`, `invitations (start_link_token)`, `submissions (invitation_id)`, and btree on `created_at` for time-based queries.

---

## 4) Key Flows (Sequence)

### 4.1 Admin creates assessment

1. Admin logs in (Supabase Auth) → creates **Seed** by pasting source GitHub URL.
2. FastAPI calls GitHub App to create private seed repo + marks as **template**.
3. Sets up **sync** (fork sync or mirror action) and ensures default branch = `main`.
4. Admin fills assessment form (title/desc/instructions/email text/time windows).
5. System stores assessment & computes `start_deadline = now + time_to_start` for each invitation when sent.
6. Resend sends invitation with **Start link**: `https://app/assess/<invite-token>`.

### 4.2 Candidate opens Start link

1. Next.js loads invite by `start_link_token` and renders title/instructions, deadlines, and repo info.
2. Candidate clicks **Start** (if before `start_deadline`).
3. Worker reads seed’s latest `main` SHA; **generate repo from template** at `org/cand-<uuid>`; pin `seed_sha_pinned`.
4. Issue **opaque access token** with `expires_at = started_at + time_to_complete`.
5. Display clone commands and **Git credential helper** one-liner (MVP):
   ```bash
   # one-time install helper for this repo
   git config --global credential.helper "!f() { curl -sS 'https://api.yourdomain.com/git/credential?token=<opaque>' ; }; f"
   git clone https://git.yourdomain.com/r/<slug>.git
   ```
   (We also show raw GH URL for fallback.)

### 4.3 Pushes during window

- Broker API validates opaque token (not revoked, not expired, matches repo).
- Mints short-lived GitHub App token (1h) and returns a credentialed HTTPS URL.
- Candidate’s Git proceeds; subsequent operations refresh seamlessly.

### 4.4 Submit / Timeout

- **Submit** button calls API → record `final_sha` from candidate `main`, create `submissions` row, revoke token.
- Candidate repo optionally **archived** and write-protected.
- If window expires, a worker marks `expired`, captures `final_sha` if available, revokes token.

### 4.5 Review

- Admin UI shows:
  - **Diff vs seed**: GitHub Compare API between `seed_sha_pinned` and `final_sha` on candidate repo `main`.
  - **Commit list**: from candidate repo.
  - **Inline comments**: stored locally (optionally also create PR and review comments via GitHub API).
  - **Feedback** summary.

### 4.6 Follow-up

- Admin clicks **Send Follow-Up** on the candidate’s project.
- Uses org’s default follow-up template (editable in Settings) via Resend.

---

## 5) API Surface (FastAPI)

```
POST /api/seeds            {source_url}
POST /api/assessments      {...}
POST /api/invitations      {assessment_id, candidates[]}
GET  /api/invitations/:id  → invite detail (admin)
GET  /api/start/:token     → invite view (candidate)
POST /api/start/:token     → start assessment → creates repo + token
POST /api/submit/:token    → submit final → revoke token + archive
GET  /api/repos/:id/diff   → diff vs seed (admin)
GET  /api/repos/:id/commits
POST /api/followup         {invitation_id, template_id?}

-- Git broker (MVP)
GET  /git/credential?token=<opaque>
  → returns JSON or a `username=<user>\npassword=<token>\nprotocol=https\nhost=github.com\npath=...` payload understood by Git’s credential protocol
```

Auth:

- Admin endpoints → Supabase JWT (RLS enforced on org_id).
- Candidate endpoints → invite token.

---

## 6) Next.js Pages (App Router)

```
/app
  /login
  /dashboard
    /assessments [list]
    /assessments/new
    /assessments/[id]
      /preview-start
      /invites
  /candidates/[inviteToken]   -- public Start page
  /review/[invitationId]
  /settings/emails
```

UI stack:

- shadcn/ui + Tailwind
- tanstack/react-query for client fetching
- MDX/markdown renderer for instructions

Key components:

- SeedForm, AssessmentForm, InviteTable
- StartPage (shows deadlines + commands)
- ReviewDiff (embed GitHub compare or render via code viewer)
- CommentsPane & FeedbackCard

---

## 7) Webhooks & Jobs

### GitHub Webhooks (handled by FastAPI / Probot)

- `push` on seed → update `latest_main_sha`.
- `repository` created → verify default branch = main.
- (Optional) `push` on candidate → analytics (commit count).

### Cron / Schedulers (Railway/Worker)

- Nightly seed sync (if using mirror mode isn’t event-driven).
- Token expiry sweeper (mark expired, archive repos, send reminders).
- Email bounce/engagement polling (optional).

### Queueable jobs

- Create seed repo from source
- Generate candidate repo from template
- Archive/write-protect repo
- Compute diff metadata (cache compare JSON)
- Send emails (invite, reminder, follow-up)

---

## 8) Emails (Resend)

Templates stored per org; variables: `{candidate_name}`, `{assessment_title}`, `{start_link}`, `{start_deadline}`, `{complete_deadline}`.

- **Invite** – includes Start link and basic Git help.
- **Reminder** – N hours before start/complete deadline (optional nice-to-have).
- **Follow-Up** – one-click from review page using the default template.

---

## 9) Security & Compliance

- All invite/access tokens are random 32+ byte URL-safe. Store hashes at rest (bcrypt/argon2), compare via constant-time.
- Access tokens include `repo_full_name` binding and expiry. Revoke on submit/timeout.
- Least-privilege GitHub App permissions: `Contents: Read/Write`, `Metadata: Read`, `Administration: Read/Write (repo create)`, `Pull requests: Read/Write` (for review comments), `Members: Read`.
- RLS policies per `org_id` for all tenant data; admins only.
- Audit log for sensitive ops (token issue, submit, archive, follow-up send).
- PKCE for admin login via Supabase Auth.
- Set default branch protection on candidate repos to block force-push after submit.

---

## 10) MVP vs. Stretch

### MVP (fits ~10 hours)

- Seeds via “template generate” flow
- Invitations + Start/Submit UX
- Token **broker** (credential helper) rather than full Git reverse proxy
- Candidate repo creation, finalization, and admin diff (use GitHub Compare URL embed)
- Resend emails (invite + follow-up)
- Deploy: Vercel + Railway + Supabase

### Stretch / 3-month roadmap

- Full Git gateway proxy (no helper needed)
- Inline diff viewer with code annotations, stored + synced to PR review
- Auto-grading/CI runner per assessment, scorecards, analytics dashboard
- Customizable token refresh policies, pause/resume windows
- Team roles, SSO (Google/O365), multi-org switcher
- Rate-limits, WebAuthn for admins, on-call runbooks

---

## 11) Environment Configuration

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY= (PEM)
GITHUB_APP_SLUG=

RESEND_API_KEY=
APP_BASE_URL= https://yourapp.vercel.app
API_BASE_URL= https://api.yourapp.com
GIT_BROKER_URL= https://api.yourapp.com/git/credential

JWT_SECRET=
```

Ensure the GitHub App callback/webhook URL points to the FastAPI endpoint and secrets validated via HMAC.

---

## 12) Admin Review UX Details

- **Repo header**: candidate name, repo link, pinned seed SHA, final SHA, duration.
- **Commit timeline** with timestamps; optional charts.
- **Diff vs seed**: link to GitHub compare (`https://github.com/org/repo/compare/<seedSha>...main`) and cached JSON for quick inline snippets.
- **Comments** stored locally with path+line; later sync to GH as PR comments.
- **Export**: Snapshot a ZIP of candidate repo at final SHA (optional nice-to-have).

---

## 13) Operational Notes

- For live demo, pre-provision a seed using the provided `FullStackBoilerplate` or your own small template.
- Validate cloning on macOS/Linux & Windows (credential helper snippet includes PowerShell variant in docs).
- Set up DKIM/SPF (Resend/Cloudflare) so emails don’t go to spam.
- Add health checks for API and worker; alert on job failures.

---

## 14) Pseudocode Highlights

### Create Candidate Repo

```python
# worker
seed = db.get_seed(seed_id)
sha = github.get_branch_sha(seed.repo, seed.default_branch)
repo = github.generate_from_template(template_repo=seed.repo, name=f"{slug}-{uuid4().hex[:8]}")
github.set_default_branch(repo, 'main')
opaque = secrets.token_urlsafe(48)
expires = started_at + assessment.time_to_complete
store_access_token(invitation_id, repo.full_name, opaque, expires)
```

### Broker Credential Exchange

```python
# GET /git/credential?token=OPAQUE
inv = db.get_invitation_by_token(OPAQUE)
assert inv and not expired and not revoked
app_token = github.create_installation_token(scopes=["repo"], repositories=[inv.repo])
return as_git_credential_protocol(username="x-access-token", password=app_token)
```

### Submit

```python
final_sha = github.get_branch_sha(inv.repo, 'main')
db.insert_submission(inv.id, final_sha)
db.revoke_access_token(inv.id)
github.archive_repo(inv.repo)
```

---

## 15) README Snippets (for your repo)

**Clone Command shown to candidates**

```bash
git config --global credential.helper "!f() { curl -sS '${GIT_BROKER_URL}?token=${OPAQUE}' ; }; f"

git clone https://git.yourdomain.com/r/${SLUG}.git
cd ${SLUG}
# work ...

git add -A && git commit -m "WIP" && git push origin main
```

**Admin Preview**

- Start page preview shows:
  - Title, instructions, deadlines
  - Redacted commands (tokens masked)
  - Repo info (branch: main, seed link)

---

## 16) Risks & Mitigations

- **Git proxy complexity** → Start with broker + credential helper; upgrade later.
- **Template sync drift** → Use webhook to update `latest_main_sha`; display it in UI.
- **Private upstream** → Require GitHub App access; otherwise prompt admin to grant.
- **Email deliverability** → Configure domain & DMARC early.

---

## 17) What to Demo for Submission

1. Create Assessment (seed from provided boilerplate repo)
2. Send invite to a test email
3. Open Start link, click Start → see commands
4. Clone locally, make a change, push
5. Click Submit
6. As admin, open review page, view diff & commits
7. Send follow-up email

---

*End of Architecture Plan*
