import React, { createContext, useState, useEffect, useContext } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserContext } from './UserContext';
import Constants from '../Constants';

export const SavedContext = createContext();

export const SavedProvider = ({ children }) => {
    const { user } = useContext(UserContext);
    const [savedProducts, setSavedProducts] = useState([]);

    useEffect(() => {
        if (user?.id) {
            loadSavedProducts();
        } else {
            setSavedProducts([]);
        }
    }, [user?.id]);

    const loadSavedProducts = async () => {
        try {
            // First load from local for speed
            const stored = await AsyncStorage.getItem('savedProducts');
            if (stored) {
                setSavedProducts(JSON.parse(stored));
            }

            // Then sync with backend if user is logged in
            if (user?.id) {
                const response = await fetch(`${Constants.API_BASE_URL}/v1/deals/saved?user_id=${user.id}`);
                const data = await response.json();
                if (data.success && data.deals) {
                    setSavedProducts(data.deals);
                    await AsyncStorage.setItem('savedProducts', JSON.stringify(data.deals));
                    console.log(`[SAVED] Synced ${data.deals.length} deals from backend`);
                }
            }
        } catch (e) {
            console.log("Failed to load saved products", e);
        }
    };

    const toggleSave = async (product) => {
        if (!user?.id) return;

        try {
            const exists = savedProducts.some(p => p.id === product.id);
            let newSaved;

            if (exists) {
                // Delete from backend
                setSavedProducts(prev => prev.filter(p => p.id !== product.id)); // Optimistic UI
                const response = await fetch(`${Constants.API_BASE_URL}/v1/deals/saved?user_id=${user.id}&alert_id=${product.id}`, {
                    method: 'DELETE'
                });
                const data = await response.json();
                if (!data.success) {
                    // Rollback if failed
                    loadSavedProducts();
                    return;
                }
                newSaved = savedProducts.filter(p => p.id !== product.id);
            } else {
                // Save to backend
                setSavedProducts(prev => [...prev, product]); // Optimistic UI
                const response = await fetch(`${Constants.API_BASE_URL}/v1/deals/save`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: user.id,
                        alert_id: product.id,
                        alert_data: product
                    }),
                });
                const data = await response.json();
                if (!data.success) {
                    // Rollback if failed
                    loadSavedProducts();
                    return;
                }
                newSaved = [...savedProducts, product];
            }

            await AsyncStorage.setItem('savedProducts', JSON.stringify(newSaved));
        } catch (e) {
            console.log("Failed to toggle save", e);
            loadSavedProducts(); // Reset on error
        }
    };

    const isSaved = (productId) => {
        return savedProducts.some(p => p.id === productId);
    };

    return (
        <SavedContext.Provider value={{ savedProducts, toggleSave, isSaved, refreshSaved: loadSavedProducts }}>
            {children}
        </SavedContext.Provider>
    );
};
