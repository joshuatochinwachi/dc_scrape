# hollowScan — Push Notification Fix
**Technical Implementation Guide — Based on Full Code Review**

| Field | Detail |
|---|---|
| Date | March 2026 |
| Platform | React Native (Expo Managed) — iOS & Android |
| Notification Library | expo-notifications (confirmed in PushNotificationService.js) |
| Backend | FastAPI — main_api.py (Python, async httpx) |
| Push Token Storage | Supabase users.push_tokens (JSONB array) + local data/push_tokens.json |
| Notification Dispatcher | background_notification_worker() — polls every 30s |
| Expo Push API | send_expo_push_notification() — already implemented in backend |
| Root Problem | Notifications only appear when app is in foreground |
| Priority | 🔴 Critical — Core app feature broken |

---

## 1. Code Review Findings

After a full review of `main_api.py`, `PushNotificationService.js`, and `app.json`, the situation is more advanced than originally assessed — but also more precisely diagnosable. Here is exactly what is in place and what is missing.

### 1.1 What Is Already Correctly Implemented

> ✅ **Good news — the backend push infrastructure is mostly in place.**

- `send_expo_push_notification()` exists and correctly calls the Expo Push API at `https://exp.host/--/api/v2/push/send`
- `background_notification_worker()` polls for new products every 30 seconds, filters users by their `notification_preferences`, and calls `send_expo_push_notification()` with the right payload
- The `/v1/user/push-token` POST and DELETE endpoints exist and correctly save/remove tokens from Supabase `users.push_tokens`
- The worker correctly reads `push_tokens` from the Supabase users table and matches per-user `notification_preferences` (regions, categories, min_discount_percent)
- Stale token auto-cleanup (`DeviceNotRegistered`) is handled inside `send_expo_push_notification()`

### 1.2 Status Summary — What Is Broken

| Component | Status | Problem |
|---|---|---|
| app.json plugins | ❌ Missing | expo-notifications plugin absent — Android channel not natively registered |
| PushNotificationService.js — sendDealNotification | ❌ Wrong approach | Sends local notifications only — these cannot show when app is killed |
| App.js — killed state handler | ❌ Missing | getLastNotificationResponse() never called at startup |
| Background worker token source | ⚠️ Partial | Worker reads from in-memory USER_PUSH_TOKENS dict, not from Supabase |
| Duplicate push-token endpoints | ⚠️ Conflict | Two POST /v1/user/push-token handlers defined — FastAPI uses the last one only |
| send_expo_push_notification() | ✅ Correct | Backend Expo API call is properly implemented |
| background_notification_worker() | ✅ Correct | Polling, filtering, and dispatch logic is sound |

---

## 2. Detailed Problem Analysis

### 2.1 Problem 1 — expo-notifications Plugin Missing from app.json

The `plugins` array in `app.json` only contains `expo-build-properties`. The `expo-notifications` plugin is not present. Without it:

- **Android:** the default notification channel is not registered natively in the app's `AndroidManifest.xml` at build time. FCM notifications have no channel to display in, so they are silently dropped in background/killed states
- **iOS:** the push notification entitlement and background modes may not be correctly embedded in the release build
- This affects **all** notification delivery in background and killed states, regardless of how correctly the backend sends the push

> ⚠️ **Important:** This is a build-time issue. Fixing `app.json` alone is not enough — the app must be rebuilt using EAS Build or `npx expo prebuild --clean` followed by a native build. A plain `npx expo start` will not apply this change.

---

### 2.2 Problem 2 — sendDealNotification Uses Local Notifications

In `PushNotificationService.js`, `sendDealNotification()` calls `sendLocalNotification()`, which calls `Notifications.scheduleNotificationAsync()`. Local notifications are created and displayed by the app process itself. When the app is killed, there is no running process — **local notifications can never appear**.

The backend already has the correct approach (`send_expo_push_notification` calls the Expo Push API). The mobile side should not be creating deal notifications at all — it should only receive and display them. The `sendDealNotification` function must be removed.

> ❌ **Root cause of the main symptom:** The app is sending deal alerts to itself via local notifications rather than receiving them from the server via remote push. Remote push (sent by the backend through Expo → FCM/APNs → OS) is the only mechanism that works when the app is closed.

---

### 2.3 Problem 3 — Background Worker Token Source

In `background_notification_worker()`, user push tokens are fetched correctly from Supabase:

```python
# This line in the worker correctly fetches from Supabase:
response = await http_client.get(
    f"{URL}/rest/v1/users?push_tokens=not.is.null&select=id,notification_preferences,push_tokens",
    headers=HEADERS
)
```

However, the separate `USER_PUSH_TOKENS` in-memory dict at the top of `main_api.py` is also maintained by the two `/v1/user/push-token` endpoints but is **never used** by the worker. This dict will be empty on server restart, meaning any logic that relied on it would fail silently. The worker correctly uses Supabase — this is fine. The in-memory dict is redundant.

---

### 2.4 Problem 4 — Duplicate POST /v1/user/push-token Endpoint

There are two separate `POST /v1/user/push-token` handler functions defined in `main_api.py`:

- **First definition (~line 480):** `register_push_token(user_id, token)` — updates both local dict and Supabase
- **Second definition (~line 1360):** `save_push_token(user_id, token)` — updates Supabase only, cleaner implementation

FastAPI registers both, but uses the last one. The first definition is silently ignored. This should be cleaned up to avoid confusion.

> ⚠️ **Action required:** Delete the first `register_push_token()` function (~line 475–500) entirely. Keep only the `save_push_token()` function near line 1360.

---

### 2.5 Problem 5 — Killed App Launch Not Handled on Mobile

When a user taps a notification and the app was killed, the notification response is not delivered via `addNotificationResponseReceivedListener` because the app was not running. Instead, it must be read at startup using `Notifications.getLastNotificationResponse()`. This is not currently called anywhere in `PushNotificationService.js` or `App.js`.

Without this, tapping a notification from a killed state opens the app but never navigates to the product.

---

## 3. Required Changes — Step by Step

### Fix 1 — app.json: Add expo-notifications Plugin
**File:** `app.json` | **Impact:** Critical

In the `plugins` array, add the `expo-notifications` plugin before `expo-build-properties`. Replace the entire plugins array with:

```json
"plugins": [
  [
    "expo-notifications",
    {
      "icon": "./assets/icon.png",
      "color": "#0A0A0B",
      "defaultChannel": "default",
      "sounds": []
    }
  ],
  [
    "expo-build-properties",
    {
      "android": {
        "compileSdkVersion": 35,
        "targetSdkVersion": 35,
        "buildToolsVersion": "35.0.0"
      },
      "ios": {
        "useFrameworks": "static"
      }
    }
  ]
]
```

> ⚠️ **After this change:** Run `npx expo install expo-notifications` (if not already installed), then rebuild the app with `npx eas build` or `npx expo prebuild --clean`. A regular `npx expo start` will NOT apply this.

---

### Fix 2 — PushNotificationService.js: Remove Local Deal Notifications, Add Killed-State Handler
**File:** `services/PushNotificationService.js` | **Impact:** Critical

Two changes are needed:
- Remove `sendDealNotification()` entirely — deal notifications come from the backend via remote push
- Add `handleKilledAppNotification()` to read the last notification response at app startup

Replace the entire file with:

```javascript
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import Constants from '../Constants';

// Controls how notifications appear when the app IS in foreground
export const setupNotificationHandler = () => {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
    }),
  });

  // Fires when notification arrives and app is in foreground
  const notificationListener = Notifications.addNotificationReceivedListener(notification => {
    console.log('[PUSH] Notification received in foreground:', notification);
  });

  // Fires when user TAPS a notification (foreground or background)
  const responseListener = Notifications.addNotificationResponseReceivedListener(response => {
    handleNotificationTap(response.notification.request.content.data);
  });

  return () => {
    Notifications.removeNotificationSubscription(notificationListener);
    Notifications.removeNotificationSubscription(responseListener);
  };
};

// Call this in App.js useEffect on mount.
// Handles tap on a notification that opened the app from KILLED state.
export const handleKilledAppNotification = () => {
  const response = Notifications.getLastNotificationResponse();
  if (response) {
    console.log('[PUSH] App opened via notification tap from killed state');
    handleNotificationTap(response.notification.request.content.data);
  }
};

const handleNotificationTap = (data) => {
  if (!data) return;
  if (data.product_id) {
    console.log('[PUSH] Navigate to product:', data.product_id);
    // NavigationService.navigate('ProductDetail', { productId: data.product_id });
    // Uncomment line above once NavigationService is confirmed ready
  }
};

// Requests permission + registers Expo push token + saves to backend
export const registerForPushNotifications = async (userId) => {
  try {
    if (!Device.isDevice) {
      console.log('[PUSH] Not a real device — skipping registration');
      return null;
    }

    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') {
      console.log('[PUSH] Permission denied');
      return null;
    }

    // Android: ensure the 'default' channel exists
    // Must match channelId sent by backend in send_expo_push_notification()
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'Default',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        sound: 'default',
        enableVibrate: true,
        showBadge: true,
      });
    }

    const token = (await Notifications.getExpoPushTokenAsync({
      projectId: '7e28c380-d7d4-4f6d-82ab-4febe7aabf8e'  // matches EAS projectId
    })).data;

    console.log('[PUSH] Expo Push Token:', token);
    if (userId) await savePushTokenToBackend(userId, token);
    return token;
  } catch (error) {
    console.log('[PUSH] Error registering:', error);
    return null;
  }
};

// Saves token to backend — calls POST /v1/user/push-token
export const savePushTokenToBackend = async (userId, token) => {
  try {
    const response = await fetch(
      `${Constants.API_BASE_URL}/v1/user/push-token?user_id=${userId}&token=${token}`,
      { method: 'POST' }
    );
    const data = await response.json();
    return data.success;
  } catch (error) {
    console.log('[PUSH] Error saving token to backend:', error);
    return false;
  }
};

// Removes token on logout — calls DELETE /v1/user/push-token
export const unregisterPushToken = async (userId, token) => {
  try {
    const response = await fetch(
      `${Constants.API_BASE_URL}/v1/user/push-token?user_id=${userId}&token=${token}`,
      { method: 'DELETE' }
    );
    const data = await response.json();
    return data.success;
  } catch (error) {
    console.log('[PUSH] Error unregistering token:', error);
    return false;
  }
};
```

---

### Fix 3 — App.js: Wire Up Notification Handlers at App Startup
**File:** `App.js` or root `_layout.js` | **Impact:** Critical

Add the following to your root component:

```javascript
import {
  setupNotificationHandler,
  handleKilledAppNotification,
  registerForPushNotifications
} from './services/PushNotificationService';

export default function App() {
  useEffect(() => {
    // 1. Set up foreground display + background tap listener
    const cleanup = setupNotificationHandler();

    // 2. Handle case where app was KILLED and user tapped a notification
    //    Must be called on mount so navigation can react
    handleKilledAppNotification();

    return cleanup;
  }, []);

  // 3. Register push token once user is logged in
  useEffect(() => {
    if (userId) {
      registerForPushNotifications(userId);
    }
  }, [userId]);

  // ... rest of your app
}
```

---

### Fix 4 — main_api.py: Remove Duplicate Push Token Endpoint
**File:** `main_api.py` | **Impact:** Medium (code correctness)

There are two `POST /v1/user/push-token` handlers. FastAPI only uses the last one. Delete the first block (~lines 475–502):

```python
# ❌ DELETE THIS ENTIRE FUNCTION BLOCK:

@app.post("/v1/user/push-token")
async def register_push_token(user_id: str = Query(...), token: str = Query(...)):
    if not user_id or not token: raise HTTPException(status_code=400, ...)
    
    # 1. Update local cache/file (fallback)
    if user_id not in USER_PUSH_TOKENS: USER_PUSH_TOKENS[user_id] = []
    if token not in USER_PUSH_TOKENS[user_id]:
        USER_PUSH_TOKENS[user_id].append(token)
        ...
    
    # 2. Update Supabase (Primary)
    user = await get_user_by_id(user_id)
    ...
    return {"success": True}

# ✅ KEEP the save_push_token() function defined later in the file (~line 1360)
```

> Note: `LAST_PUSH_CHECK_TIME` and `RECENT_ALERTS_LOG` are still used by `background_notification_worker` — keep those. Only delete the `register_push_token` function itself.

---

### Fix 5 — main_api.py: Verify channelId Matches Android Channel (Confirm Only)
**File:** `main_api.py` | **Impact:** Android background/killed notifications

No code change needed here. Confirm that `send_expo_push_notification()` still contains `"channelId": "default"` — this matches the channel registered in `PushNotificationService.js`. The current implementation is correct:

```python
# Current implementation — CORRECT, no changes needed:
message = {
    "to": token,
    "sound": "default",
    "title": title,
    "body": body,
    "data": data or {},
    "badge": 1,
    "priority": "high",
    "channelId": "default",   # Must match Android channel registered on mobile
    "ttl": 2419200
}
```

---

## 4. How Notifications Will Work After These Fixes

| App State | What Happens | Handler |
|---|---|---|
| Foreground (app open) | NotificationHandler intercepts, displays banner via shouldShowBanner: true | expo-notifications setNotificationHandler |
| Background (minimised) | OS receives remote push from FCM/APNs, displays in tray automatically | Android OS / iOS OS |
| Killed (app closed) | OS receives remote push from FCM/APNs, displays in tray automatically | Android OS / iOS OS |
| User taps — foreground or background | addNotificationResponseReceivedListener fires → handleNotificationTap() | PushNotificationService.js responseListener |
| User taps — app was killed | App launches, getLastNotificationResponse() returns tap → handleNotificationTap() | handleKilledAppNotification() in App.js |

### 4.1 End-to-End Flow After Fixes

1. A new product appears in the `discord_messages` table
2. `background_notification_worker()` detects it (polls every 30 seconds)
3. Worker filters users by their `notification_preferences` (region, category, min_discount_percent)
4. Worker calls `send_expo_push_notification()` with matching users' `push_tokens` from Supabase
5. `send_expo_push_notification()` posts to `https://exp.host/--/api/v2/push/send`
6. Expo Push Service delivers to FCM (Android) or APNs (iOS)
7. FCM/APNs delivers to the device OS
8. OS displays the notification in the tray — regardless of app state
9. User taps — app opens and `handleNotificationTap()` navigates to the product

---

## 5. Implementation Checklist

- [ ] Add `expo-notifications` to plugins array in `app.json` (Fix 1)
- [ ] Run: `npx expo install expo-notifications`
- [ ] Rebuild app: `npx eas build` OR `npx expo prebuild --clean` then build natively
- [ ] Replace `PushNotificationService.js` with the updated version (Fix 2)
- [ ] Add `setupNotificationHandler()` and `handleKilledAppNotification()` calls to root `App.js` (Fix 3)
- [ ] Delete the first `register_push_token()` endpoint from `main_api.py` (Fix 4)
- [ ] Confirm `channelId` in `send_expo_push_notification()` is still `"default"` (Fix 5 — verify only)
- [ ] Deploy updated `main_api.py` to server
- [ ] Test on a physical Android device using a release or dev build — NOT Expo Go
- [ ] Test on a physical iOS device using TestFlight or a dev build
- [ ] Verify all three states: foreground (banner shows), background (minimise app), killed (swipe away app)
- [ ] Check `push_debug.log` on server for `[PUSH] Worker` and `[PUSH] Sent` messages to confirm dispatch

> ⚠️ **Testing tip:** Push notifications do not work in Expo Go (SDK 51+) and do not work reliably on emulators or simulators. Always test on a real physical device. To trigger a test push manually without waiting for the 30s worker, call the Expo Push API directly with curl or Postman using a real `ExponentPushToken` from your device logs.

---

## 6. Summary of All Files Changed

| File | Change | Reason |
|---|---|---|
| `app.json` | Add expo-notifications to plugins array | Registers native Android channel and iOS entitlement at build time |
| `PushNotificationService.js` | Full replacement — remove sendDealNotification, add handleKilledAppNotification | Local notifications cannot show when app is killed; killed-state tap was never handled |
| `App.js` / root layout | Add setupNotificationHandler() + handleKilledAppNotification() on mount | Required to handle notification taps from all three app states |
| `main_api.py` | Delete first register_push_token() duplicate endpoint (~line 475) | Duplicate route silently shadowed; in-memory USER_PUSH_TOKENS not used by worker |

---

*Document prepared by Claude for hollowScan development team — March 2026. Based on full review of main_api.py, PushNotificationService.js, and app.json.*
