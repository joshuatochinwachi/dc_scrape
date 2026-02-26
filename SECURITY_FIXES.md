# Security Analysis & Solution Roadmap 🔒

This document is for the development team. It outlines the current security issues discovered in the SmartyMetrics API and provides a clear plan to fix them.

---

## Part 1: The Problems (Why we are at risk)

### 🎒 The "Locker Problem" (Simple Explanation)
Imagine the app is like a school with hundreds of lockers.
- **Current Issue**: If someone wants to open a locker, they just tell the Janitor (the API) "I am student #5." The Janitor says "Okay!" and opens it. The Janitor **never checks** if they are *really* student #5. Anyone can lie and say they are someone else to peek at data or even empty (delete) the locker.

### 🛠️ Technical Details
1. **IDOR (Insecure Direct Object Reference)**:
   - Endpoints like `DELETE /v1/user/account?email=...` or `GET /v1/user/status?user_id=...` trust the input provided in the request without verifying the user's identity.
   - An attacker can scrape user emails and delete accounts or view private profiles by just changing the parameters.
2. **Missing JWT (Authentication Tokens)**:
   - The `login` and `signup` processes do not issue a secure "Digital Key" (JWT). 
   - Without this key, the backend has no way to prove a request is coming from a logged-in user.

---

## Part 2: The Solution (How we fix it)

We will move to **Token-Based Verification** (JWT).

### Step 1: Install Security Libraries
Add `python-jose[cryptography]` and `passlib[bcrypt]` to `requirements.txt`.

### Step 2: Configure Secrets
Add a `SECRET_KEY` to the `.env` file to sign our digital keys.

### Step 3: Implement JWT Helpers
Create functions in `main_api.py` to create and decode "Digital Keys" (Tokens).

### Step 4: Issue Tokens on Login
Update the `/v1/auth/login` and `/v1/auth/signup` endpoints to return an `access_token` upon success.

### Step 5: Create a Security "Janitor"
Create a FastAPI dependency that:
1. Extracts the token from the `Authorization` header.
2. Verifies it's real and hasn't expired.
3. Extracts the **trusted** `user_id` from the token.

### Step 6: Lock the Endpoints
Apply the dependency to all sensitive endpoints. The logic must use the `user_id` from the **Token**, ignoring any IDs passed in the URL or Query.

### Step 7: Update Mobile App
Update the mobile app to save the token and send it in the header. (See Part 3 below for details).

---

## Part 3: Mobile App Changes (What your co-dev needs to do)

To support the new security, the mobile app (React Native) needs a few updates in `UserContext.js` and any API services:

### 1. Store the "Digital Key" (Token)
After a successful login or signup, the app should save the `access_token` it gets from the backend.
- **Current**: Saves `user_data` to `AsyncStorage`.
- **New**: Save `access_token` to `AsyncStorage` (or even better, `SecureStore`).

### 2. Add the "Key" to Every Request
Every time the app talks to the backend, it must include the key in the settings (Headers).
- **Header to add**: `Authorization: Bearer <the_saved_token>`
- **Affected Files**: `UserContext.js` (for status, profile, telegram) and `LiveProductService.js` (for the product feed).

### 3. Handle "Locked Out" (401 Errors)
If the backend says "Unauthorized" (401), it means the token is old or wrong. The app should automatically run the `logout()` function to take the user back to the login screen.
