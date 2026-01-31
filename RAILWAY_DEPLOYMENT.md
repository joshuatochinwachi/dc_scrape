# 🚀 Railway Deployment Guide - HollowScan

## 📋 Prerequisites

- [x] GitHub account with code pushed
- [x] Railway account (https://railway.app - free tier available)
- [x] Environment variables ready

---

## 🛠️ Step 1: Prepare Your GitHub Repo

### Ensure These Files Exist:

```
discord/
├── Dockerfile              ✅
├── requirements.txt        ✅
├── render.yaml            (ignore for Railway)
├── wsgi.py               ✅
├── main_api.py           ✅ (THIS IS DEPLOYED ON RAILWAY)
├── app.py                (already running on Contabo)
├── telegram_bot.py       ✅
└── .env.example          (optional)
```

**Note:** `app.py` is already hosted on Contabo, so we only deploy `main_api.py` to Railway.

### Check requirements.txt

```bash
# From discord/ directory
pip freeze > requirements.txt
```

Ensure it includes:
```
flask==3.0.0
flask-socketio==5.3.4
python-dotenv==1.0.0
requests==2.31.0
supabase==2.3.0
stripe==7.4.0
python-telegram-bot==20.0
playwright==1.40.0
gunicorn==21.2.0
eventlet==0.33.3
```

### Create .env.example (for reference)
```bash
cat > .env.example << EOF
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-key

# Telegram
TELEGRAM_TOKEN=your-token
TELEGRAM_ADMIN_ID=your-id

# Stripe (optional)
STRIPE_SECRET_KEY=your-key
STRIPE_WEBHOOK_SECRET=your-secret

# Server
HEADLESS=true
DEBUG=false
EOF
```

### Commit and Push
```bash
git add .
git commit -m "Add deployment configs"
git push origin main
```

---

## 🚂 Step 2: Deploy on Railway

### 2.1 Connect GitHub Repo

1. Go to https://railway.app
2. Click **"New Project"**
3. Select **"Deploy from GitHub"**
4. Search for your repo (e.g., `discord-archiver`)
5. Click **"Import"**

### 2.2 Configure Service

Railway will auto-detect Python project.

**In Railway Dashboard:**

1. Click on your project
2. Click **"Settings"** tab
3. Set **Start Command:**
   ```
   gunicorn --worker-class eventlet -w 1 --timeout 300 --bind 0.0.0.0:$PORT wsgi:app --app main_api:app
   ```
   
   **Or simpler:**
   ```
   python main_api.py
   ```

4. Set **Environment Variables** (add all from your .env):
   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-key
   TELEGRAM_TOKEN=your-token
   TELEGRAM_ADMIN_ID=your-id
   STRIPE_SECRET_KEY=your-key
   HEADLESS=true
   DEBUG=false
   PORT=5000
   ```

### 2.3 Configure Port

1. Click **"Networking"** tab
2. Click **"Generate Domain"**
3. Railway auto-assigns a domain: `your-service-xxxxx.railway.app`

✅ **Your backend is now live!**

---

## 🏗️ Your Infrastructure

| Service | URL | Purpose |
|---------|-----|---------|
| **app.py** | Contabo | Discord alerts, Telegram bot, webhook processing |
| **main_api.py** | Railway | Mobile app backend (categories, feed, products) |
| **Mobile App** | Expo | HollowScan React Native |
| **Database** | Supabase | Users, categories, products, subscriptions |

---

### Update Constants.js

```javascript
// Constants.js
const Constants = {
    API_BASE_URL: 'https://your-service-xxxxx.railway.app',  // Your Railway URL
    
    BRAND: {
        BLUE: '#2D82FF',
        PURPLE: '#9B4DFF',
        DARK_BG: '#0A0A0B',
        LIGHT_BG: '#F8F9FE',
    }
};

export default Constants;
```

### Commit and Push
```bash
cd hollowscan_app
git add Constants.js
git commit -m "Update API URL to Railway"
git push origin main
```

---

## 🏃 Step 4: Running Locally

### 4.1 Setup Python Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate
```

### 4.2 Install Dependencies

```bash
pip install -r requirements.txt
```

### 4.3 Setup .env File

```bash
# Copy example
cp .env.example .env

# Edit .env with your actual values
# SUPABASE_URL=...
# SUPABASE_KEY=...
# etc
```

### 4.4 Run Backend

```bash
python main_api.py
```

**Output:**
```
* Running on http://127.0.0.1:5000
* WARNING in app context, prefer app.app_context()
```

**Note:** `app.py` is already running on Contabo, so only run `main_api.py` locally for development.

### 4.5 Run Mobile App (separate terminal)

```bash
cd hollowscan_app

# For LOCAL development (points to your machine)
# Update Constants.js:
# API_BASE_URL: 'http://localhost:5000'

# For RAILWAY development (points to Railway)
# Update Constants.js:
# API_BASE_URL: 'https://your-service-xxxxx.railway.app'

npx expo start --tunnel
```

---

## 🧪 Testing Endpoints

### Health Check (Verify Deployment)

```bash
curl https://your-service-xxxxx.railway.app/health
# Response: OK
```

### Test Categories Endpoint

```bash
curl https://your-service-xxxxx.railway.app/v1/categories
# Returns: { "UK Stores": [...], "USA Stores": [...], ... }
```

### Test Feed Endpoint

```bash
curl "https://your-service-xxxxx.railway.app/v1/feed?user_id=test&region=USA+Stores&limit=5"
# Returns: [{ product objects }]
```

---

## 📊 Railway Dashboard

### Monitor Your App

1. **Deployments Tab** - See deployment history
2. **Logs Tab** - Real-time logs
3. **Metrics Tab** - CPU, Memory, Network usage
4. **Environment Tab** - Manage variables
5. **Settings Tab** - Update configs

### View Logs

```bash
# Via Railway CLI (optional)
railway login
railway link
railway logs
```

---

## 🔄 Workflow: Make Changes → Deploy

### Option A: Auto-Deploy (Recommended)

1. Make changes locally
2. Commit: `git commit -m "message"`
3. Push: `git push origin main`
4. **Railway auto-deploys** (~2-3 minutes)
5. Check deployment status in Railway dashboard

### Option B: Manual Redeploy

1. Go to Railway dashboard
2. Click project
3. Click **"Deployments"** tab
4. Click **"Redeploy"** on latest deployment

---

## 🚨 Troubleshooting

### App Not Starting

**Check logs in Railway:**
```
View Logs tab → Look for error messages
Common issues:
- Missing environment variables
- Port already in use
- Missing dependencies in requirements.txt
```

### API Not Responding

```bash
# Test health endpoint
curl https://your-service-xxxxx.railway.app/health

# Should return: OK
# If fails, check Railway logs
```

### Mobile App Can't Connect

**Verify:**
1. Update `Constants.js` with correct Railway URL
2. Reload mobile app: `r` key in expo terminal
3. Check if API_BASE_URL is correct
4. Test endpoint manually: `curl <your-railway-url>/health`

### Database Connection Failed

**Check:**
1. `SUPABASE_URL` environment variable set correctly
2. `SUPABASE_KEY` is correct
3. Supabase project is active
4. Network access allowed from Railway IP

---

## 💾 Environment Variables Reference

| Variable | Example | Required |
|----------|---------|----------|
| `SUPABASE_URL` | `https://xyzabc.supabase.co` | ✅ Yes |
| `SUPABASE_KEY` | `eyJhbGc...` | ✅ Yes |
| `TELEGRAM_TOKEN` | `123456:ABC-DEF1234ghIkl-zyx` | ✅ Yes |
| `TELEGRAM_ADMIN_ID` | `123456789` | ✅ Yes |
| `STRIPE_SECRET_KEY` | `sk_test_...` | ❌ Optional |
| `HEADLESS` | `true` | ❌ Default: true |
| `DEBUG` | `false` | ❌ Default: false |

---

## 📝 Quick Commands

```bash
# Clone repo (for other developers)
git clone https://github.com/YOUR_USER/discord-archiver.git
cd discord-archiver

# Setup environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your values

# Run locally (main_api.py for mobile backend development)
python main_api.py

# Run mobile app (different terminal)
cd hollowscan_app
npx expo start --tunnel
```

---

## 🎯 Final Checklist

- [ ] Code pushed to GitHub
- [ ] Railway account created
- [ ] GitHub repo connected to Railway
- [ ] Environment variables set in Railway
- [ ] Start command configured
- [ ] Domain generated
- [ ] Health check working
- [ ] Mobile app API URL updated
- [ ] Mobile app tested
- [ ] Other developers can access

---

## 📞 Support

**Railway Status:** https://status.railway.app
**Railway Docs:** https://docs.railway.app
**Common Issues:** https://docs.railway.app/troubleshoot

---

**Deployment Live:** ✅ Your app is now accessible worldwide!
**Mobile App Ready:** ✅ Other developers can test immediately!

