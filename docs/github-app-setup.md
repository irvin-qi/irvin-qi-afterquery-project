# GitHub App setup

The Afterquery admin dashboard provisions repositories through an organization-scoped
GitHub App installation. Follow the steps below to create the app, wire the
credentials into the backend, and validate that admins can connect the app from
the product UI.

## 1. Create the GitHub App

1. Sign in with the GitHub organization owner account that will host mirrored
   repositories (for example `github.com/your-company`).
2. Go to **Settings → Developer settings → GitHub Apps** and click **New GitHub
   App**.
3. Provide a descriptive name such as `Afterquery Assessment Helper` and an
   informational homepage URL.
4. Leave webhooks disabled for now – the backend polls for repository status and
   does not require inbound events yet.
5. Set the **Callback URL** to the admin frontend callback route, e.g.
   `https://app.yourdomain.com/app/github/install/callback`. The app uses this
   URL when a user completes the installation flow.
6. (Optional) Set the **Setup URL** to the same callback route so the **Install
   App** button in GitHub also returns to Afterquery.
7. Under **Repository permissions** grant:
   - **Administration** – Read & write (to create repositories and set template
     defaults).
   - **Contents** – Read & write (to import starter code and push updates).
   - **Metadata** – Read.
   - **Pull requests** – Read & write (reserved for review tooling).
8. Leave **Organization permissions** at the defaults unless you plan to extend
   the automation later.
9. Enable the **Repository** event subscription for future webhook expansion.
10. Save the app and generate a private key. Download the PEM file – the backend
    consumes the raw key material.

## 2. Install the app on your organization

1. From the GitHub App settings page click **Install App** and choose the target
   organization.
2. Select **All repositories** so the backend can create new seed and candidate
   repositories on demand.
3. Finish the installation – Afterquery captures the installation identifier
   automatically, and the admin UI now records the page where the install began.
   After successful authorization the user is redirected back to that page so
   they can continue adding repositories without losing context.

## 3. Configure backend environment variables

Add the following variables to the FastAPI environment (for local development
place them in `backend/.env`):

```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
GITHUB_APP_SLUG=your-app-slug
# Optional overrides
# GITHUB_API_BASE_URL=https://api.github.com
# GITHUB_SEED_PREFIX=afterquery-seed
# GITHUB_CANDIDATE_PREFIX=afterquery-candidate
```

The helper automatically normalises newline-escaped or base64 encoded private
keys. Install the backend dependencies so the GitHub App client can mint
RS256-signed JWTs:

```bash
pip install -r backend/requirements.txt
```

Ensure the host running FastAPI has the `git` CLI available (version 2.30 or
newer is recommended).

## 4. Verify access

1. Start the backend with `uvicorn backend.app.main:app --reload`.
2. From the admin dashboard click **Connect GitHub App**. The flow will open
   GitHub, ask for the installation scope, and redirect to
   `/app/github/install/callback`.
3. After completing the flow you should land back on the page where you clicked
   **Connect GitHub App**. Adding a seed repository will now succeed, and future
   admin overview calls return the installation details.

Seeds and candidate repositories are created inside the connected GitHub
organization using the configured prefixes. The FastAPI callback stores the
installation metadata on the project so no manual copy/paste of installation IDs
is required.

## 5. Optional: branch protection & webhooks

To enforce branch protection rules or react to repository events, extend the
GitHub App permissions and configure the webhook URL to point at a FastAPI
endpoint (for example `/api/github/webhook`). The current backend does not
consume inbound events, but the app can be enhanced without schema changes when
needed.
