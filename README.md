# Governance Continuity — Operating Model Tool

**Group 7 Impact Project** — Leadership Disruption as a New Operating Condition

A web application for mapping decision authority, defining AI governance boundaries, and maintaining organizational trust and compliance during leadership disruption.

## Features

- **Dashboard** — Real-time governance health score with leadership status overview
- **Leadership Roster** — Track leaders, availability status, and succession plans
- **Decision Domains** — Map decision authority, risk levels, and ownership
- **Disruption Events** — Flag, track, and manage leadership disruptions with interim authority transfer
- **AI Governance Matrix** — Visualize AI support boundaries across all decision domains
- **Audit Log** — Full compliance trail of every governance action

## Deploy to Railway

### 1. Push to GitHub

```bash
cd governance-app
git init
git add .
git commit -m "Initial commit - Governance Continuity app"
git remote add origin https://github.com/YOUR_USERNAME/governance-continuity.git
git push -u origin main
```

### 2. Deploy on Railway

1. Go to [railway.com](https://railway.com) and sign in with GitHub
2. Click **"New Project"** → **"Deploy from GitHub Repo"**
3. Select your `governance-continuity` repository
4. Railway will auto-detect the Python app and deploy it

### 3. Set Environment Variables (in Railway dashboard)

| Variable | Value |
|----------|-------|
| `SECRET_KEY` | A random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `PORT` | `8080` (Railway sets this automatically) |

### 4. (Optional) Add PostgreSQL

For persistent data, add a PostgreSQL plugin in Railway:

1. In your project, click **"New"** → **"Database"** → **"PostgreSQL"**
2. Railway will auto-set `DATABASE_URL` — the app handles this automatically

Without PostgreSQL, the app uses SQLite (data persists on the Railway volume but resets on redeploy).

## Run Locally

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000`

## Demo Data

The app seeds with demo leadership data on first run — 8 leaders, 10 decision domains, and 2 active disruption events — so you can explore the full functionality immediately.

## Architecture

- **Flask** + **SQLAlchemy** + **Flask-Login**
- **Gunicorn** for production serving
- **SQLite** (default) or **PostgreSQL** (Railway)
- No JavaScript frameworks — pure server-rendered HTML with CSS

---

*Group 7: Margaret Wood, Ronald C Owens Jr, Arsen Khanguieldyan, Craig Kallin*
