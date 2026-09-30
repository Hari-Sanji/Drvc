# Deploying DRCV with Vercel

Vercel hosts the website (frontend). The analysis engine (Python, OCR, PostgreSQL) runs on Render, because Vercel cannot run it (size limit, no permanent storage, no background jobs).

## Step 1 - Backend on Render
Follow DEPLOY.md. When it finishes, copy your Render link, e.g. `https://drcv-abcd.onrender.com`.

## Step 2 - Point Vercel at it
Open `frontend/vercel.json` and replace `https://YOUR-RENDER-APP.onrender.com` with your Render link (keep `/api/:path*` at the end).

## Step 3 - Frontend on Vercel
1. Upload the project to GitHub.
2. On https://vercel.com click **Add New -> Project**, import the repository.
3. Set **Root Directory** to `frontend`. Leave the other settings (Vite is detected). Click **Deploy**.
4. Open your `*.vercel.app` link and click **Launch Demo**.
