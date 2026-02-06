import React, { createContext, useState, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import Constants from '../Constants';
import { registerForPushNotifications, setupNotificationHandler, unregisterPushToken } from '../services/PushNotificationService';



export const UserContext = createContext();

export const UserProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const userRef = useRef(null);

    // Keep userRef in sync with state
    useEffect(() => {
        userRef.current = user;
    }, [user]);

    const [isLoading, setIsLoading] = useState(true);
    const [isDarkMode, setIsDarkMode] = useState(false);
    const [telegramLinked, setTelegramLinked] = useState(false);
    const [isPremiumTelegram, setIsPremiumTelegram] = useState(false);
    const [premiumUntil, setPremiumUntil] = useState(null);
    const [showLimitModal, setShowLimitModal] = useState(false);
    const [countdown, setCountdown] = useState('');
    const [selectedRegion, setSelectedRegion] = useState('USA Stores');


    const [dailyViews, setDailyViews] = useState({
        date: new Date().toDateString(),
        products: [],
    });

    const FREE_PRODUCT_LIMIT = 4;

    // Load user data on mount
    useEffect(() => {
        const init = async () => {
            await loadUserData();
            await loadDailyViews();
            await loadTheme();
            await loadRegion();
            setupNotificationHandler(); // Initialize global notification listener
            setIsLoading(false);
        };


        init();
    }, []);

    const loadRegion = async () => {
        try {
            const stored = await AsyncStorage.getItem('selected_region');
            if (stored) {
                setSelectedRegion(stored);
            }
        } catch (error) {
            console.error('[REGION] Error loading region:', error);
        }
    };

    const updateRegion = async (newRegion) => {
        setSelectedRegion(newRegion);
        try {
            await AsyncStorage.setItem('selected_region', newRegion);
        } catch (error) {
            console.error('[REGION] Error saving region:', error);
        }
    };

    const loadTheme = async () => {
        try {
            const stored = await AsyncStorage.getItem('is_dark_mode');
            if (stored !== null) {
                setIsDarkMode(JSON.parse(stored));
            }
        } catch (error) {
            console.error('[THEME] Error loading theme:', error);
        }
    };

    const loadUserData = async () => {
        try {
            const stored = await AsyncStorage.getItem('user_data');
            if (stored) {
                const userData = JSON.parse(stored);
                // Simple validation to ensure it's a valid object with an ID
                if (userData && userData.id) {
                    setUser(userData);
                    // Register for push notifications
                    registerForPushNotifications(userData.id);
                    // Check telegram status
                    checkTelegramStatus(userData.id);
                    // Background refresh to catch up if DB state changed (e.g. verified on another device)
                    // We don't await this so startup is still fast
                    setTimeout(() => refreshUserStatus(userData), 1000);
                } else {


                    setUser(null);
                }
            } else {
                setUser(null);
            }
        } catch (error) {
            console.error('[USER] Error loading user data:', error);
            setUser(null);
        }
    };

    const login = async (email, password) => {
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });

            const data = await response.json();
            if (data.success && data.user) {
                await updateUser(data.user);
                return { success: true };
            } else {
                return { success: false, message: data.detail || 'Invalid credentials' };
            }
        } catch (error) {
            console.error('[AUTH] Login error:', error);
            return { success: false, message: 'Connection error. Please try again.' };
        }
    };

    const signup = async (email, password) => {
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/auth/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });

            const data = await response.json();
            if (data.success && data.user) {
                await updateUser(data.user);
                return { success: true };
            } else {
                return { success: false, message: data.detail || 'Signup failed' };
            }
        } catch (error) {
            console.error('[AUTH] Signup error:', error);
            return { success: false, message: 'Connection error. Please try again.' };
        }
    };


    const verifyCode = async (code) => {
        if (!user?.email || !code) return { success: false, message: 'Email and code required' };
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/auth/verify-code`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: user.email, code }),
            });
            const data = await response.json();
            if (data.success) {
                // Refresh status to update local user object
                await refreshUserStatus();
            }
            return { success: data.success, message: data.message };
        } catch (error) {
            console.error('[AUTH] Verify error:', error);
            return { success: false, message: 'Connection error' };
        }
    };

    const forgotPassword = async (email) => {
        if (!email) return { success: false, message: 'Email required' };
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            const data = await response.json();
            return { success: data.success, message: data.message };
        } catch (error) {
            console.error('[AUTH] Forgot password error:', error);
            return { success: false, message: 'Connection error' };
        }
    };

    const resetPassword = async (email, code, password) => {
        if (!email || !code || !password) return { success: false, message: 'All fields required' };
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/auth/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, code, password }),
            });
            const data = await response.json();
            return { success: data.success, message: data.message };
        } catch (error) {
            console.error('[AUTH] Reset password error:', error);
            return { success: false, message: 'Connection error' };
        }
    };

    const resendVerification = async () => {
        if (!user?.email) return { success: false, message: 'No email found' };
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/auth/resend-code`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: user.email }),
            });
            const data = await response.json();
            return { success: data.success || response.ok, message: data.message || data.detail || 'Code sent!' };
        } catch (error) {
            console.error('[AUTH] Resend verification error:', error);
            return { success: false, message: 'Connection error' };
        }
    };

    const refreshUserStatus = async (passedUser = null) => {
        const targetUser = passedUser || userRef.current;
        if (!targetUser?.id) return;

        try {
            const userIdBeforeFetch = targetUser.id;
            const response = await fetch(`${Constants.API_BASE_URL}/v1/user/status?user_id=${targetUser.id}`);
            const data = await response.json();

            // RACE CONDITION GUARD: Using live userRef.current
            if (!userRef.current || userRef.current.id !== userIdBeforeFetch) {
                console.log('[USER] Status refresh ignored: user changed or logged out during fetch');
                return;
            }

            // Update the user object with new status and verification
            const updatedUser = {
                ...userRef.current, // Use most recent ref as base
                isPremium: data.is_premium,
                email_verified: data.email_verified,
                subscription_status: data.status
            };

            setUser(updatedUser);
            await AsyncStorage.setItem('user_data', JSON.stringify(updatedUser));
            return data;
        } catch (error) {
            console.error('[USER] Status refresh error:', error);
        }
    };

    const syncPreferences = async (preferences) => {
        if (!user?.id) return { success: false, message: 'User not logged in' };
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/user/preferences?user_id=${user.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(preferences),
            });
            const data = await response.json();
            return { success: data.success };
        } catch (error) {
            console.error('[USER] Sync preferences error:', error);
            return { success: false };
        }
    };

    const logout = async () => {
        try {
            console.log('[AUTH] Logging out user:', userRef.current?.id);
            // Unregister push token from backend before logging out
            if (userRef.current?.id) {
                try {
                    const tokenData = await Notifications.getExpoPushTokenAsync({
                        projectId: '2f7823be-eb44-4956-8297-4969baf0a524'
                    });
                    if (tokenData && tokenData.data) {
                        await unregisterPushToken(userRef.current.id, tokenData.data);
                    }
                } catch (pushError) {
                    console.log('[AUTH] Error unregistering push token:', pushError);
                }
            }

            // IMMEDIATELY clear ref to stop background tasks
            userRef.current = null;
            setUser(null);
            setTelegramLinked(false);
            setIsPremiumTelegram(false);
            setPremiumUntil(null);

            // Clear storage
            await AsyncStorage.removeItem('user_data');
            console.log('[AUTH] Logout complete');
        } catch (error) {
            console.error('[AUTH] Logout error:', error);
        }
    };


    const loadDailyViews = async () => {

        try {
            const stored = await AsyncStorage.getItem('daily_views');
            if (stored) {
                const data = JSON.parse(stored);
                // Check if date needs reset (midnight reset)
                if (data.date !== new Date().toDateString()) {
                    // Reset for new day
                    const newData = {
                        date: new Date().toDateString(),
                        products: [],
                    };
                    setDailyViews(newData);
                    await AsyncStorage.setItem('daily_views', JSON.stringify(newData));
                } else {
                    setDailyViews(data);
                }
            } else {
                // First time - initialize
                const newData = {
                    date: new Date().toDateString(),
                    products: [],
                };
                setDailyViews(newData);
                await AsyncStorage.setItem('daily_views', JSON.stringify(newData));
            }
        } catch (error) {
            console.error('[USER] Error loading daily views:', error);
        }
    };

    const trackProductView = async (productId) => {
        try {
            // Check if premium - bypass limit
            // NEW: Use combined premium check (User subscription OR Telegram linking)
            const isUserPremium = user?.isPremium || isPremiumTelegram;

            if (isUserPremium) {
                console.log('[LIMIT] Premium user - unlimited views');
                return { allowed: true, remaining: Infinity };
            }

            // Get current daily views
            const stored = await AsyncStorage.getItem('daily_views');
            let current = stored ? JSON.parse(stored) : { date: new Date().toDateString(), products: [] };

            // Check if date changed (midnight reset)
            if (current.date !== new Date().toDateString()) {
                current = { date: new Date().toDateString(), products: [] };
            }

            // STRICT ENFORCEMENT: Check if limit reached FIRST
            // (User wants to block even already-viewed items once limit is hit)
            if (current.products.length >= FREE_PRODUCT_LIMIT) {
                console.log('[LIMIT] Daily limit reached (', current.products.length, '/', FREE_PRODUCT_LIMIT, ')');
                setShowLimitModal(true); // Trigger modal globally
                return { allowed: false, remaining: 0 };
            }

            // Check if product already viewed today
            if (current.products.includes(productId)) {
                console.log('[LIMIT] Product already viewed today');
                const remaining = FREE_PRODUCT_LIMIT - current.products.length;
                return { allowed: true, remaining };
            }


            // Add product to viewed list
            current.products.push(productId);
            setDailyViews(current);
            await AsyncStorage.setItem('daily_views', JSON.stringify(current));

            const remaining = FREE_PRODUCT_LIMIT - current.products.length;
            console.log('[LIMIT] View tracked. Remaining:', remaining);
            return { allowed: true, remaining };
        } catch (error) {
            console.error('[LIMIT] Error tracking view:', error);
            return { allowed: true, remaining: -1 };
        }
    };

    const getRemainingViews = () => {
        return Math.max(0, FREE_PRODUCT_LIMIT - dailyViews.products.length);
    };

    // TIMER LOGIC FOR MODAL
    useEffect(() => {
        let interval;
        if (showLimitModal) {
            const updateCountdown = () => {
                const now = new Date();
                const midnight = new Date();
                midnight.setHours(24, 0, 0, 0);
                const diff = midnight - now;

                if (diff <= 0) {
                    setCountdown('00:00:00');
                    return;
                }

                const hours = Math.floor(diff / (1000 * 60 * 60));
                const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((diff % (1000 * 60)) / 1000);

                setCountdown(
                    `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
                );
            };

            updateCountdown();
            interval = setInterval(updateCountdown, 1000);
        }
        return () => clearInterval(interval);
    }, [showLimitModal]);


    const linkTelegramAccount = async (code) => {
        if (!user?.id || !code) return { success: false, message: 'Invalid request' };
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/user/telegram/link`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: user.id, code }),
            });
            const data = await response.json();
            if (data.success) {
                // Refresh status
                checkTelegramStatus(user.id);
            }
            return { success: data.success, message: data.message };
        } catch (error) {
            console.error('[TELEGRAM] Link error:', error);
            return { success: false, message: 'Connection error' };
        }
    };

    const unlinkTelegramAccount = async () => {
        if (!user?.id) return { success: false, message: 'Not logged in' };
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/user/telegram/unlink`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: user.id }),
            });
            const data = await response.json();
            if (data.success) {
                setTelegramLinked(false);
                setIsPremiumTelegram(false);
                setPremiumUntil(null);
                refreshUserStatus();
            }
            return data;
        } catch (error) {
            console.error('[TELEGRAM] Unlink error:', error);
            return { success: false, message: 'Connection error' };
        }
    };

    const checkTelegramStatus = async (specificUserId = null) => {
        const idToCheck = specificUserId || user?.id;
        if (!idToCheck) return;

        console.log(`[DEBUG] checkTelegramStatus for ID: '${idToCheck}'`);

        try {
            const url = `${Constants.API_BASE_URL}/v1/user/telegram/link-status?user_id=${idToCheck}`;
            console.log(`[DEBUG] Fetching TG status from: ${url}`);
            const response = await fetch(url);

            if (!response.ok) {
                const text = await response.text();
                console.error(`[TELEGRAM] Status check failed (${response.status}):`, text);
                return { linked: false, error: `Server error: ${response.status}` };
            }

            let data;
            try {
                data = await response.json();
            } catch (err) {
                const text = await response.text();
                console.error('[TELEGRAM] JSON Parse Error. Response:', text);
                return { linked: false, error: 'Invalid response from server' };
            }

            if (!userRef.current || userRef.current.id !== idToCheck) {
                console.log('[TELEGRAM] Status check ignored: user changed or logged out during fetch');
                return { linked: false };
            }

            if (data.success && data.linked) {
                setTelegramLinked(true);
                setIsPremiumTelegram(data.is_premium || false);
                setPremiumUntil(data.premium_until || null);

                // Sync with main user state too
                refreshUserStatus();

                return { linked: true, isPremium: data.is_premium };
            } else {
                setTelegramLinked(false);
                setIsPremiumTelegram(false);
                setPremiumUntil(null);
                return { linked: false };
            }
        } catch (error) {
            console.error('[TELEGRAM] Status check error:', error);
            // Default to not-linked on error for safety
            setTelegramLinked(false);
            setIsPremiumTelegram(false);
            setPremiumUntil(null);
            return { linked: false, error: error.message };
        }
    };


    const updateUser = async (userData) => {
        try {
            if (!userData) {
                // Use logout for complete cleanup
                return;
            }

            setUser(userData);
            await AsyncStorage.setItem('user_data', JSON.stringify(userData));

            // Register for push notifications if we have a user
            if (userData.id) {
                registerForPushNotifications(userData.id);
                // Refresh all statuses for the new user
                checkTelegramStatus(userData.id);
                refreshUserStatus(userData);
            }
        } catch (error) {
            console.error('[USER] Error updating user:', error);
        }
    };


    const resetDailyViews = async () => {
        const newData = {
            date: new Date().toDateString(),
            products: [],
        };
        setDailyViews(newData);
        await AsyncStorage.setItem('daily_views', JSON.stringify(newData));
    };

    const toggleTheme = async () => {
        try {
            const newValue = !isDarkMode;
            setIsDarkMode(newValue);
            await AsyncStorage.setItem('is_dark_mode', JSON.stringify(newValue));
        } catch (error) {
            console.error('[THEME] Error saving theme:', error);
        }
    };

    const isPremium = user?.isPremium || isPremiumTelegram || false;


    return (
        <UserContext.Provider
            value={{
                user,
                isLoading,
                isDarkMode,
                toggleTheme,
                dailyViews,
                trackProductView,
                getRemainingViews,
                updateUser,
                resetDailyViews,
                isPremium,
                login,
                signup,
                logout,
                resendVerification,
                refreshUserStatus,
                verifyCode,
                forgotPassword,
                resetPassword,
                linkTelegramAccount,
                unlinkTelegramAccount,
                checkTelegramStatus,
                telegramLinked,
                isPremiumTelegram,
                premiumUntil,
                showLimitModal,
                setShowLimitModal,
                countdown,
                selectedRegion,
                updateRegion,
                syncPreferences
            }}
        >


            {children}
        </UserContext.Provider>
    );
};
