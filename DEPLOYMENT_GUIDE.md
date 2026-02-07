# Deploying HollowScan to App Stores

This guide outlines the steps to deploy your **HollowScan** app to the Google Play Store and Apple App Store using Expo Application Services (EAS).

## Prerequisites

1.  **Expo Account**: Ensure you are logged into your Expo account in the terminal (`npx expo login`).
2.  **EAS CLI**: Ensure EAS CLI is installed (`npm install -g eas-cli`).
3.  **Developer Accounts**:
    -   **Google Play Console**: $25 one-time fee.
    -   **Apple Developer Program**: $99/year.

---

## Deploying from Windows PC

**Good news!** You can deploy to both the Google Play Store and Apple App Store entirely from your Windows PC using Expo Application Services (EAS). No Mac required!

### How EAS Enables Windows-Based iOS Deployment

EAS builds your iOS app on **cloud-based macOS servers**, eliminating the need for local macOS hardware. This means:

- ✅ **Building iOS apps** works from Windows via `eas build --platform ios`
- ✅ **Submitting to App Store** works via `eas submit -p ios`
- ✅ **Managing certificates** is handled automatically by EAS
- ✅ **All configuration** is done through web browsers and CLI

### Creating an Apple Developer Account from Windows

You can create and manage your Apple Developer Account entirely from a web browser on Windows:

#### Step 1: Create or Sign In with Apple ID
1. Visit [appleid.apple.com](https://appleid.apple.com/) in any browser
2. Create a new Apple ID or sign in with an existing one
3. Enable two-factor authentication (required)

#### Step 2: Enroll in Apple Developer Program
1. Go to [developer.apple.com/programs/enroll](https://developer.apple.com/programs/enroll/)
2. Sign in with your Apple ID
3. Click **"Start Your Enrollment"**
4. Choose your entity type:
   - **Individual**: For personal apps (most common, approved in 24-48 hours)
   - **Organization**: For company apps (requires D-U-N-S number, takes several days)
5. Fill out required information and agree to the license agreement
6. Pay the $99 annual fee using a credit/debit card

#### Step 3: Access Developer Resources
Once approved, you can access all Apple developer services through web browsers:
- **App Store Connect**: [appstoreconnect.apple.com](https://appstoreconnect.apple.com/)
- **Certificates & Profiles**: Managed automatically by EAS
- **TestFlight**: For beta testing your app

### What You'll Need
- Valid Apple ID with two-factor authentication
- Credit/debit card for payment ($99/year)
- Valid government-issued ID (for verification)
- Phone number for authentication

### Windows Deployment Workflow

```bash
# 1. Login to Expo (one-time setup)
npx expo login

# 2. Build for both platforms from Windows
eas build --platform android --profile production
eas build --platform ios --profile production

# 3. Submit to both stores from Windows
eas submit -p android
eas submit -p ios

# 4. Configure store listings in web browsers
# Google Play Console: https://play.google.com/console
# App Store Connect: https://appstoreconnect.apple.com
```

### Limitations and Workarounds

#### iOS Screenshots
You'll need iOS device screenshots for the App Store listing. Options:
- Use an iPhone if you have one
- Use online screenshot generators (search "iOS screenshot generator")
- Hire someone on Fiverr ($5-20)
- Ask a friend with a Mac to use the iOS Simulator

#### Testing on iOS
Without a Mac, you can still test your iOS app:
- **Expo Go**: Install on a physical iPhone for development testing
- **TestFlight**: Build a production version and distribute to testers
- **Development Builds**: Use `eas build --profile development` and install via TestFlight

**Bottom Line**: Everything you need for deployment can be done from Windows. EAS handles all macOS-specific tasks in the cloud!

---

## 1. Configuration Check

Your [app.json](file:///c:/Users/Jo$h/Desktop/Visual%20Studio%20Code/dc_scrape/hollowscan_app/app.json) is already configured with:
-   **iOS Bundle Identifier**: `com.kttylabs.app`
-   **Android Package Name**: `com.kttylabs.app`

Ensure your [eas.json](file:///c:/Users/Jo$h/Desktop/Visual%20Studio%20Code/dc_scrape/hollowscan_app/eas.json) is configured for production builds.

### Recommended [eas.json](file:///c:/Users/Jo$h/Desktop/Visual%20Studio%20Code/dc_scrape/hollowscan_app/eas.json) for Production

```json
{
  "cli": {
    "version": ">= 10.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal"
    },
    "preview": {
      "distribution": "internal"
    },
    "production": {
      "autoIncrement": true
    }
  },
  "submit": {
    "production": {}
  }
}
```

---

## 2. Deploying to Google Play Store (Android)

### Step 1: Build the App Bundle (AAB)

Run the following command to build the Android App Bundle:

```bash
eas build --platform android --profile production
```

-   **Credentials**: EAS will ask you to generate a Keystore. Select "Generate new keystore" if you haven't already.
-   **Wait**: The build will take some time. Once valid, you'll get a download link for an `.aab` file.

### Step 2: Upload to Google Play Console

1.  Go to [Google Play Console](https://play.google.com/console).
2.  **Create App**: Click "Create app" and fill in the details (App Name, Language, App/Game, Free/Paid).
3.  **Dashboard**: Complete the tasks in the "Set up your app" section (Privacy Policy, App Access, Content Ratings, Target Audience, News Apps, COVID-19 apps, Data Safety).
4.  **Production or Testing**:
    -   Go to **Testing > Internal testing** (recommended for first deploy).
    -   Create a new release.
    -   Upload the `.aab` file you downloaded from EAS.
    -   Add testers (email addresses).
5.  **Review**: Once you're ready, promote the release to **Production**.

---

## 3. Deploying to Apple App Store (iOS)

### Step 1: Build the IPA

Run the following command to build the iOS binary:

```bash
eas build --platform ios --profile production
```

-   **Credentials**: EAS will ask to log in to your Apple Developer account. It will handle certificates and provisioning profiles for you.
-   **Wait**: The build will complete and provide a download link (though we usually use EAS Submit).

### Step 2: Upload to App Store Connect

You can upload directly from the CLI using EAS Submit (easiest method):

```bash
eas submit -p ios
```

-   Select the build you just created.
-   This will upload the binary to **App Store Connect**.

Alternatively, you can use the **Transporter** app on macOS to upload the `.ipa` file manually.

### Step 3: Configure App Store Connect

1.  Go to [App Store Connect](https://appstoreconnect.apple.com/).
2.  **My Apps**: Click "+" -> "New App".
    -   **Bundle ID**: Select `com.kttylabs.app` (created by EAS).
    -   **SKU**: Use `hollowscan_app`.
3.  **App Information**: Fill in metadata, screenshots, description, keywords, support URL, etc.
4.  **Build**: Scroll down to the "Build" section and select the build you uploaded via EAS Submit.
5.  **Submit for Review**: Click "Add for Review" to submit your app to Apple's review team.

---

## 4. Automatic Updates (OTA)

Your app is now configured to check for updates automatically on launch.

### Pushing an Update

When you make changes to your JavaScript code (fixing bugs, updating UI, etc.) and want to ship them to users **immediately** without going through the App Store review process:

1.  **Publish the Check**:
    ```bash
    eas update --branch production --message "Description of changes"
    ```

2.  **User Experience**:
    -   Next time users open the app, it will check for this update.
    -   If found, they will see a prompt: **"A new version of HollowScan is available. Restart to apply updates?"**
    -   Clicking "Restart Now" will reload the app with the new code.

### When to use Store Builds vs OTA Updates

-   **Use OTA Updates (`eas update`)**: For JS changes, styling updates, text changes, bug fixes.
-   **Use Store Builds (`eas build`)**: When you install new **native libraries** (anything that requires `npx expo install`), change app icon, splash screen, or modify `android`/`ios` native project settings.

## Important Notes

-   **Privacy Policy**: robust privacy policy is required for both stores.
-   **Screenshots**: You need specific screenshot sizes for different devices (6.5" iPhone, 5.5" iPhone, 12.9" iPad, Android Phone, Android 7" Tablet, Android 10" Tablet).
-   **Support URL**: A website or landing page where users can get support.
