# Vercel Environment Variable Setup

## Quick Setup (2 minutes)

### Step 1: Log in to Vercel Dashboard
1. Go to https://vercel.com/dashboard
2. Select your `QuantPulse` project (or search for it)

### Step 2: Add Environment Variable

1. Click on **Settings** in the top navigation
2. In the left sidebar, click **Environment Variables**
3. Click **Add New** button
4. Fill in the form:
   ```
   Name:  NEXT_PUBLIC_API_URL
   Value: https://quantpulse-backend-7e8o.onrender.com
   ```
5. Under "Environments to expose to:", select:
   - ✓ Production
   - ✓ Preview
   - ✓ Development
6. Click **Save**

### Step 3: Redeploy

1. Go to **Deployments** tab
2. Click the **...** (three dots) next to your latest deployment
3. Select **Redeploy**
4. Click **Redeploy** in the confirmation dialog

**Wait 2-3 minutes for deployment to complete.**

### Step 4: Verify

1. Open https://quant-pulse-seven.vercel.app
2. Click **Experiments** in the left sidebar
3. Should load without 404 error ✓

---

## What This Does

When you set `NEXT_PUBLIC_API_URL=https://quantpulse-backend-7e8o.onrender.com`:

- The frontend JavaScript (running in your browser) uses this URL to make API calls
- Instead of calling `http://localhost:8000` (which doesn't exist), it calls your actual deployed backend
- The backend at Render accepts and responds to these requests

---

## If You Don't See the Variable Saved

Sometimes Vercel requires you to be in the right scope. Make sure:
1. You're in the **Settings** section (not Deployments or Domains)
2. You selected the right project
3. The "Environments" checkboxes all have checkmarks

---

## Need to Update Later?

If you change your backend URL in the future:
1. Go to Settings → Environment Variables
2. Click the variable name or pencil icon to edit
3. Update the value
4. Click **Save** or **Update**
5. Redeploy as described in Step 3

---

## Backend Configuration (Render)

No action needed if your Render backend already has the environment variable set, but if you need to update CORS:

1. Go to https://dashboard.render.com
2. Select your backend service
3. Go to **Environment** tab
4. Find or add: `QUANTPULSE_CORS_ORIGINS=https://quant-pulse-seven.vercel.app`
5. Click **Save Changes**
6. Service will auto-redeploy in ~1 minute
