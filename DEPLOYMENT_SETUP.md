# QuantPulse Deployment Setup Guide

## Current Deployment URLs

- **Frontend (Vercel):** https://quant-pulse-seven.vercel.app
- **Backend (Render):** https://quantpulse-backend-7e8o.onrender.com

## What Was Changed

### 1. Backend CORS Configuration (`backend/app/main.py`)
Updated CORS to allow requests from the deployed Vercel frontend:
- `http://localhost:3000` - Local development
- `http://localhost:8000` - Local development
- `https://quant-pulse-seven.vercel.app` - Production Vercel frontend

### 2. Docker Compose (`docker-compose.yml`)
Fixed `NEXT_PUBLIC_API_URL` to use Docker internal hostname for local development:
- Changed from `http://localhost:8000` to `http://backend:8000`
- This allows the frontend container to communicate with the backend container

## How to Complete the Deployment Setup

### Step 1: Set Environment Variable on Vercel

You need to set the backend API URL on your Vercel project:

**Option A: Using Vercel Dashboard (Easiest)**
1. Go to https://vercel.com/dashboard
2. Select your `QuantPulse` project
3. Go to **Settings** → **Environment Variables**
4. Add a new variable:
   - **Name:** `NEXT_PUBLIC_API_URL`
   - **Value:** `https://quantpulse-backend-7e8o.onrender.com`
   - **Environments:** Check "Production", "Preview", and "Development"
5. Click **Save**
6. Redeploy your project (or wait for the next automatic deployment from GitHub)

**Option B: Using Vercel CLI**
```bash
npm install -g vercel
vercel env add NEXT_PUBLIC_API_URL
# When prompted, enter: https://quantpulse-backend-7e8o.onrender.com
vercel env pull  # to sync locally
vercel redeploy  # to trigger a new deployment
```

### Step 2: Configure Backend CORS (If Needed)

If your Render backend isn't picking up the updated CORS settings, set an environment variable:

On Render:
1. Go to your backend service on https://render.com
2. Go to **Environment** settings
3. Add/Update: `QUANTPULSE_CORS_ORIGINS=https://quant-pulse-seven.vercel.app`
4. Click **Save Changes**
5. Service will auto-redeploy

### Step 3: Verify the Fix

After deployment:
1. Open https://quant-pulse-seven.vercel.app
2. Navigate to **Experiments** page
3. It should now load without a 404 error

If you still see a 404:
- Open browser DevTools (F12 or Cmd+Option+I)
- Go to **Network** tab
- Refresh the page
- Look for failed requests to `https://quantpulse-backend-7e8o.onrender.com/api/experiments`
- Check the response for CORS or connection errors

## Local Development

To run locally with Docker:
```bash
docker compose up --build
```

The frontend will connect to the backend via the Docker network at `http://backend:8000` (internal to containers).

## Troubleshooting

### 404 on Experiments Page
- **Cause:** API URL not set or wrong
- **Fix:** Verify `NEXT_PUBLIC_API_URL` is set on Vercel to `https://quantpulse-backend-7e8o.onrender.com`
- **Check:** Open browser console and look for network errors

### CORS Errors
- **Cause:** Backend not allowing requests from frontend domain
- **Fix:** Set `QUANTPULSE_CORS_ORIGINS` on Render backend
- **Check:** Network tab in DevTools should show response headers like `Access-Control-Allow-Origin`

### Backend Returns 500 Error
- **Cause:** Database or data issue
- **Fix:** Check Render backend logs and verify PostgreSQL is running
- **Check:** Go to Render dashboard → Logs tab

## API Contract

All API endpoints are now accessible at:
```
https://quantpulse-backend-7e8o.onrender.com/api/*
```

Key endpoints used by the frontend:
- `GET /api/experiments` - List all experiments
- `GET /api/experiments/{id}` - Get experiment details
- `DELETE /api/experiments/{id}` - Delete an experiment
- `GET /api/datasets` - List datasets
- `POST /api/datasets/upload` - Upload CSV data
- `POST /api/research/run` - Run research
