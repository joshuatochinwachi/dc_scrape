import React, { createContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from '../Constants';

export const UserContext = createContext();

export const UserProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isDarkMode, setIsDarkMode] = useState(false);

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
            setIsLoading(false);
        };
        init();
    }, []);

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

    const logout = async () => {
        try {
            setUser(null);
            await AsyncStorage.removeItem('user_data');
            // We keep theme and daily views even if logged out
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
            if (user?.isPremium) {
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

            // Check if product already viewed today
            if (current.products.includes(productId)) {
                console.log('[LIMIT] Product already viewed today');
                const remaining = FREE_PRODUCT_LIMIT - current.products.length;
                return { allowed: true, remaining };
            }

            // Check if limit reached
            if (current.products.length >= FREE_PRODUCT_LIMIT) {
                console.log('[LIMIT] Daily limit reached (', current.products.length, '/', FREE_PRODUCT_LIMIT, ')');
                return { allowed: false, remaining: 0 };
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

    const updateUser = async (userData) => {
        try {
            setUser(userData);
            await AsyncStorage.setItem('user_data', JSON.stringify(userData));
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

    const isPremium = user?.isPremium || false;

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
            }}
        >
            {children}
        </UserContext.Provider>
    );
};
