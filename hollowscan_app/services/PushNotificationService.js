import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import Constants from '../Constants';
import * as NavigationService from './NavigationService';

/**
 * Push Notification Service
 * Handles all push notification setup and permissions
 */

export const requestNotificationPermissions = async () => {
    if (!Device.isDevice) {
        console.log('[NOTIFICATIONS] Not a real device, skipping permission request');
        return false;
    }

    try {
        const { status: existingStatus } = await Notifications.getPermissionsAsync();
        let finalStatus = existingStatus;

        if (existingStatus !== 'granted') {
            const { status } = await Notifications.requestPermissionsAsync();
            finalStatus = status;
        }

        if (finalStatus !== 'granted') {
            console.log('[NOTIFICATIONS] Permission denied');
            return false;
        }

        if (Platform.OS === 'android') {
            await Notifications.setNotificationChannelAsync('default', {
                name: 'default',
                importance: Notifications.AndroidImportance.MAX,
                vibrationPattern: [0, 250, 250, 250],
                lightColor: '#FF231F7C',
                sound: 'default',
                enableVibrate: true,
                showBadge: true,
            });
        }

        console.log('[NOTIFICATIONS] Permission granted');
        return true;
    } catch (error) {
        console.log('[NOTIFICATIONS] Permission request error:', error);
        return false;
    }
};

export const setupNotificationHandler = () => {
    // Set how notifications should appear when app is in foreground
    Notifications.setNotificationHandler({
        handleNotification: async () => ({
            shouldShowBanner: true,
            shouldShowList: true,
            shouldPlaySound: true,
            shouldSetBadge: true,
        }),
    });

    // Listen for notifications when app is in foreground
    const notificationListener = Notifications.addNotificationReceivedListener(notification => {
        console.log('[NOTIFICATIONS] Notification received:', notification);

        // Handle notification data if needed
        const data = notification.request.content.data;
        if (data && data.product_id) {
            console.log('[NOTIFICATIONS] Product notification received in foreground');
        }
    });

    // Listen for notification responses (when user taps notification)
    const responseListener = Notifications.addNotificationResponseReceivedListener(response => {
        console.log('[NOTIFICATIONS] User tapped notification');
        const data = response.notification.request.content.data;

        // Navigate or handle the tap
        if (data && data.product_id) {
            console.log('[NOTIFICATIONS] Opening product:', data.product_id);
            NavigationService.navigate('ProductDetail', { productId: data.product_id });
        }
    });

    return () => {
        Notifications.removeNotificationSubscription(notificationListener);
        Notifications.removeNotificationSubscription(responseListener);
    };
};

export const sendLocalNotification = async (title, body, data = {}) => {
    try {
        await Notifications.scheduleNotificationAsync({
            content: {
                title,
                body,
                data,
                sound: 'default',
                priority: 'high',
            },
            trigger: null, // Send immediately
        });
        console.log('[NOTIFICATIONS] Local notification sent:', title);
    } catch (error) {
        console.log('[NOTIFICATIONS] Error sending local notification:', error);
    }
};

export const sendDealNotification = async (product) => {
    try {
        if (!product) return;

        const product_data = product.product_data || {};
        const region = product.region || 'USA Stores';
        const title = product_data.title || 'Deal Alert';
        const category_name = product.category_name || 'HollowScan';

        // 1. Determine Currency & Region
        const regionRaw = region || '';
        const regionLabel = regionRaw.replace(' Stores', '').trim();
        const currency = regionRaw.toUpperCase().includes('UK') ? '£' : '$';

        // 2. Calculate Discount or Profit for Title
        let discountInfo = '🎉 ';
        const price = product_data?.price;
        const wasPrice = product_data?.was_price;
        const resell = product_data?.resell;

        try {
            const p = parseFloat(String(price || '0').replace(/[^0-9.]/g, ''));

            // Case A: Profit (Resell > Price) - Highlight this first as it's higher value
            const r = parseFloat(String(resell || '0').replace(/[^0-9.]/g, ''));
            if (r > p && p > 0) {
                const profit = r - p;
                discountInfo = `💰 ${currency}${profit.toFixed(2)} Profit: `;
            }
            // Case B: Discount (Now < Was)
            else if (wasPrice) {
                const w = parseFloat(String(wasPrice || '0').replace(/[^0-9.]/g, ''));
                if (w > p && p > 0) {
                    const disc = Math.floor(((w - p) / w) * 100);
                    if (disc >= 5) discountInfo = `📉 ${disc}% OFF: `;
                }
            }
        } catch (e) {
            console.log('[NOTIFICATIONS] Parsing error:', e);
        }

        const finalTitle = `${discountInfo}${title.substring(0, 45)}${title.length > 45 ? '...' : ''}`;

        // 3. Build Body (Professional Format)
        const parts = [];

        try {
            const pStr = String(price || '').replace(/[^0-9.]/g, '');
            const pVal = parseFloat(pStr);
            const wStr = String(wasPrice || '').replace(/[^0-9.]/g, '');
            const wVal = parseFloat(wStr);
            const rStr = String(resell || '').replace(/[^0-9.]/g, '');
            const rVal = parseFloat(rStr);

            if (pVal > 0) {
                let priceStr = `Now: ${currency}${pStr}`;
                if (wVal > pVal) {
                    priceStr += ` (Was ${currency}${wStr})`;
                }
                parts.push(priceStr);
            } else if (rVal > 0) {
                parts.push(`Resell: ${currency}${rStr}`);
            }
        } catch (e) {
            console.log('[NOTIFICATIONS] Body formatting error:', e);
        }

        const storeLabel = category_name || 'HollowScan';
        parts.push(`Store: ${storeLabel}`);
        if (regionLabel) parts.push(`Reg: ${regionLabel}`);

        const finalBody = parts.join(' | ');

        await sendLocalNotification(finalTitle, finalBody, {
            product_id: product?.id || 'unknown',
            category: category_name,
            region: region,
            image: product_data?.image
        });
    } catch (error) {
        console.log('[NOTIFICATIONS] Error sending deal notification:', error);
    }
};

// Register for remote push notifications (for Telegram bot integration)
export const registerForPushNotifications = async (userId) => {
    try {
        const hasPermission = await requestNotificationPermissions();
        if (!hasPermission) return null;

        if (Device.isDevice) {
            const token = (await Notifications.getExpoPushTokenAsync({
                projectId: '7e28c380-d7d4-4f6d-82ab-4febe7aabf8e'
            })).data;
            console.log('[NOTIFICATIONS] Expo Push Token:', token);

            if (userId) {
                await savePushTokenToBackend(userId, token);
            }

            return token;
        }
    } catch (error) {
        console.log('[NOTIFICATIONS] Error getting push token:', error);
        return null;
    }
};

export const savePushTokenToBackend = async (userId, token) => {
    try {
        const response = await fetch(`${Constants.API_BASE_URL}/v1/user/push-token?user_id=${userId}&token=${token}`, {
            method: 'POST',
        });
        const data = await response.json();
        console.log('[NOTIFICATIONS] Save token response:', data);
        return data.success;
    } catch (error) {
        console.log('[NOTIFICATIONS] Error saving token to backend:', error);
        return false;
    }
};

export const unregisterPushToken = async (userId, token) => {
    try {
        const response = await fetch(`${Constants.API_BASE_URL}/v1/user/push-token?user_id=${userId}&token=${token}`, {
            method: 'DELETE',
        });
        const data = await response.json();
        console.log('[NOTIFICATIONS] Unregister token response:', data);
        return data.success;
    } catch (error) {
        console.log('[NOTIFICATIONS] Error unregistering token from backend:', error);
        return false;
    }
};

