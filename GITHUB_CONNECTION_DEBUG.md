# GitHub Connection Debugging Guide

## How to Debug GitHub Connection Issues

### Step 1: Check Browser Console

When you click "Connect GitHub App", check the browser console for:

1. **On the original tab:**
   - Look for: "GitHub installation callback URL: ..."
   - This should show the callback URL being sent

2. **On the callback page (new tab):**
   - Look for: "GitHub callback page - URL params: ..."
   - Check if `state` and `installation_id` are present
   - Look for: "Completing GitHub installation..." 
   - Look for: "GitHub installation completed successfully:" or errors

3. **After returning to original tab:**
   - Look for: "Received GitHub installation complete message, refreshing..." OR
   - Look for: "Window regained focus, checking GitHub connection..."

### Step 2: Check Network Tab

1. Open Browser DevTools → Network tab
2. Click "Connect GitHub App"
3. Complete installation on GitHub
4. Check the callback page's network requests:
   - Look for: `POST /api/github/installations/complete`
   - Check if it returns 200 (success) or an error
   - Check the response to see if `installation.connected: true`

### Step 3: Verify Installation in Database

The installation should be saved to the `github_installations` table. Check:

```sql
SELECT * FROM github_installations;
```

If the table is empty or the installation isn't there, the backend save is failing.

### Step 4: Common Issues

#### Issue: Missing URL Parameters
**Symptoms:** Console shows "Missing required parameters"
**Fix:** Make sure you clicked "Install" or "Update" on GitHub and completed the installation

#### Issue: State Token Not Found
**Symptoms:** Backend returns "Installation state not found"
**Fix:** The state token might have expired (30 minutes) or you're using a different browser session

#### Issue: Installation Not on Organization
**Symptoms:** Error message about "Organization" 
**Fix:** Make sure you selected your **organization** (not personal account) when installing

#### Issue: Callback Completes But Tab Doesn't Update
**Symptoms:** Callback page shows success but original tab still shows "not connected"
**Fix:** 
- Try clicking "Refresh Connection Status" button
- Check if window focus detection is working
- Make sure both tabs are in the same browser (not different browsers)

### Step 5: Manual Verification

1. After installation, click "Refresh Connection Status" button
2. Check the Network tab for `/api/admin/overview` request
3. In the response, look for `githubInstallation.connected: true`

### What the Code Does

1. **Start Installation:**
   - Creates a state token in database
   - Opens GitHub installation page in new tab
   - Sends callback URL: `{origin}/app/github/install/callback`

2. **Complete Installation (Callback Page):**
   - Receives `state` and `installation_id` from GitHub
   - Calls backend `/api/github/installations/complete`
   - Backend verifies state, fetches installation from GitHub, saves to database
   - Updates local state
   - Tries to notify original tab via `postMessage`
   - Redirects back to original page

3. **Original Tab Detection:**
   - Listens for `postMessage` from callback page
   - Listens for window `focus` event
   - Polls every 5 seconds if not connected
   - Refreshes admin data when connection detected

### Expected Behavior

1. Click "Connect GitHub App" → New tab opens
2. Install on GitHub → Redirected to callback page
3. Callback page shows "Success! You'll be redirected shortly"
4. Original tab automatically detects connection OR
5. When you switch back to original tab, it detects connection
6. "Save repository" button becomes enabled

If this isn't happening, check the console logs to see where it's failing.


