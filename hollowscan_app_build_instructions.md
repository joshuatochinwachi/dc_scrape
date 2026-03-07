# HollowScan Mobile App - Post-Implementation Steps

Following the implementation of push notification fixes, several native steps are required to apply the changes and verify functionality.

## 1. Install Required Dependencies
Ensure the `expo-notifications` library is correctly added to your project:

```bash
cd hollowscan_app
npx expo install expo-notifications
```

## 2. Generate Native Modules
Because we modified `app.json` (adding the `expo-notifications` plugin), you must rebuild the native Android and iOS administrative files. A standard development start (`npx expo start`) will not apply these native configurations.

```bash
npx expo prebuild --clean
```

## 3. Build & Run on Physical Devices
Push notifications **cannot be verified** on Expo Go or simulators (SDK 51+). You must build a development or production client and run it on a real phone.

**For Android:**
```bash
npx expo run:android
```

**For iOS:**
```bash
npx expo run:ios
```

---

## 4. Verification Workflow

### I. Check Token Registration
1. Launch the app on your physical device.
2. Log in with your account.
3. Observe your terminal/IDE logs. You should see:
   - `[PUSH] Expo Push Token: ExponentPushToken[...]`
   - `[PUSH] Saved token for user: [USER_ID]`

### II. Test Foreground Delivery
1. Keep the app open on the Home screen.
2. Use the [Expo Push Tool](https://expo.dev/notifications) to send a test message.
3. A notification banner should appear at the top of the screen.

### III. Test Background & Killed State
1. Swipe the app away to "kill" it.
2. Send another test notification via the Expo Push Tool, including data:
   - **Data Payload**: `{"product_id": "855164313006505994"}` (or any valid ID)
3. The notification should appear in the system notification tray.
4. Tap the notification.
5. **Success Criteria**: The app opens and automatically navigates to the Product Detail screen.

---

## 💡 Troubleshooting Tip
If notifications still don't appear in the background, ensure your phone doesn't have "Battery Saver" mode active for the app, as this can block background data delivery.
