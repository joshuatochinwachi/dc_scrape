# 📱 Testing Mobile App on Your Phone with Railway Backend

Follow these steps to test the HollowScan app on your phone with `main_api.py` running on Railway.

---

## 🚀 Step 1: Deploy main_api.py to Railway

### 1.1 Go to Railway Dashboard
- Open https://railway.app
- Sign in (or create account)

### 1.2 Create New Project
1. Click **"New Project"**
2. Select **"Deploy from GitHub"**
3. Search for your repo: `discord-archiver`
4. Click **"Import"** (or select the right branch)

### 1.3 Configure the Service
1. Railway auto-detects it's a Python project ✅
2. Click **"Settings"** tab
3. Set **Start Command:**
   ```
   python main_api.py
   ```

### 1.4 Add Environment Variables
Click **"Variables"** tab and add these:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-key
TELEGRAM_TOKEN=your-token
TELEGRAM_ADMIN_ID=your-id
HEADLESS=true
DEBUG=false
```

### 1.5 Get Your Railway URL
1. Click **"Networking"** tab
2. You'll see your domain: `https://your-service-xxxxx.railway.app`
3. **Copy this URL** - you'll need it next

✅ **Your backend is now live on Railway!**

---

## 📝 Step 2: Update Mobile App Config

### 2.1 Update Constants.js

Open: `hollowscan_app/Constants.js`

Replace the `API_BASE_URL`:

```javascript
const Constants = {
    API_BASE_URL: 'https://your-service-xxxxx.railway.app',  // ← Your Railway URL here
    
    BRAND: {
        BLUE: '#2D82FF',
        PURPLE: '#9B4DFF',
        DARK_BG: '#0A0A0B',
        LIGHT_BG: '#F8F9FE',
    }
};

export default Constants;
```

**Replace `your-service-xxxxx.railway.app` with your actual Railway domain.**

### 2.2 Commit and Push

```bash
cd hollowscan_app
git add Constants.js
git commit -m "Update API URL to Railway for testing"
git push origin main
```

---

## 📲 Step 3: Build APK for Phone Testing

### 3.1 Build with EAS (Easiest Option)

```bash
# From hollowscan_app directory
npm install -g eas-cli

# Login to Expo account
eas login

# Build APK for Android
eas build --platform android --profile preview
```

**Wait ~10-15 minutes for build to complete**

You'll get:
- A download link for the APK
- Or it's automatically uploaded to Expo

### 3.2 Install on Your Phone

**Android:**
1. Download APK from the link
2. Transfer to phone (or download directly from phone)
3. Open file manager → tap APK → Install

**iOS:**
1. Similar process but with .ipa file
2. Requires Apple Developer account (paid)

---

## 🔄 Step 4: Test on Your Phone

### 4.1 Open the App
- Launch HollowScan on your phone
- Wait for products to load (should connect to Railway)

### 4.2 Test These Features

✅ **Home Screen:**
- [ ] Products load from Railway
- [ ] Region selector works
- [ ] Category filter works

✅ **Product Detail:**
- [ ] Click product → detail page opens
- [ ] Free user: shows 4 daily limit
- [ ] Share button works

✅ **Telegram Linking:**
- [ ] Generate key → shows 6-char code
- [ ] Code appears in ProfileScreen

✅ **Deep Linking:**
- [ ] Share link: `hollowscan://product/[id]`
- [ ] Opens in app if installed

### 4.3 Monitor Backend

While testing, check Railway logs:
1. Go to Railway dashboard
2. Click your project
3. Click **"Logs"** tab
4. Should see API requests from your phone
```
GET /v1/feed?region=USA+Stores&category=ALL
GET /v1/products/xxx
```

---

## 🔧 Quick Testing Workflow

### If You Find a Bug:
1. Fix code locally (e.g., in `main_api.py`)
2. Commit: `git commit -m "fix: ..."`
3. Push: `git push origin main`
4. Railway **auto-deploys** (~2-3 minutes)
5. Refresh app on phone or force quit and reopen

### If You Update Constants.js:
1. After committing
2. Rebuild APK: `eas build --platform android --profile preview`
3. Reinstall on phone

---

## ⚡ Real-Time Testing (No Rebuild)

### Option: Use Expo Go (Instant Testing)

```bash
# From hollowscan_app directory
npx expo start

# On your phone:
# 1. Download "Expo Go" app from App Store/Play Store
# 2. Scan QR code in terminal
# 3. App loads instantly on phone
```

**Pros:**
- No build time (instant)
- Changes reload immediately (`r` key)
- Perfect for rapid iteration

**Cons:**
- Requires Expo Go app on phone
- Slower than native APK

---

## 📊 Debug Output on Phone

### See Console Logs

If using **Expo Go:**
```bash
# In terminal, press "j" to open debugger
# Logs appear in terminal as you use app
```

If using **APK:**
1. Connect phone to PC via USB
2. Enable Developer Mode on phone
3. Run: `adb logcat | grep -i "React"`

---

## ✅ Testing Checklist

- [ ] Railway deployment complete
- [ ] Railway URL copied
- [ ] Constants.js updated with Railway URL
- [ ] Git pushed
- [ ] APK built (or using Expo Go)
- [ ] App installed on phone
- [ ] Home screen loads products
- [ ] Region/category filters work
- [ ] Product detail page opens
- [ ] Telegram key generation works
- [ ] Check Railway logs show API requests

---

## 🚨 Troubleshooting

### App Can't Connect to Backend

**Check 1:** Railway URL in Constants.js
```javascript
// Should look like:
API_BASE_URL: 'https://your-service-12345.railway.app'

// NOT:
API_BASE_URL: 'https://your-service-12345.railway.app/'  // ← Extra slash
API_BASE_URL: 'http://localhost:5000'  // ← Still local
```

**Check 2:** Is Railway service running?
- Go to Railway dashboard
- See if deployment status is "Success" (green)
- Check "Logs" for any errors

**Check 3:** Test endpoint manually
```bash
curl https://your-service-12345.railway.app/health
# Should return: OK
```

### Products Not Loading

**Check:**
1. Is `/v1/feed` endpoint working?
   ```bash
   curl "https://your-service-12345.railway.app/v1/feed?region=USA+Stores&category=ALL"
   ```
2. Check Railway logs for errors
3. Verify Supabase connection (check .env vars)

### App Crashes on Open

**Check:**
1. Phone logs: `adb logcat | grep -i "error"`
2. Railway logs for backend errors
3. Expo Go console if using that

---

## 📞 Quick Commands

```bash
# View Railway logs (via CLI)
railway login
railway link
railway logs

# Rebuild APK
eas build --platform android --profile preview

# Force app reload on phone (Expo Go)
# Press 'r' in terminal where expo is running

# Test API endpoint
curl https://your-service-xxxxx.railway.app/v1/categories
```

---

**You're all set! 🎉 Test the app on your phone now!**

