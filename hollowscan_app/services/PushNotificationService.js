import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import Constants from '../Constants';

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
            // Could navigate to product, show alert, etc.
        }
    });

    // Listen for notification responses (when user taps notification)
    const responseListener = Notifications.addNotificationResponseReceivedListener(response => {
        console.log('[NOTIFICATIONS] User tapped notification');
        const data = response.notification.request.content.data;

        // Navigate or handle the tap
        if (data && data.product_id) {
            console.log('[NOTIFICATIONS] Opening product:', data.product_id);
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
        const { product_data, category_name, region } = product;
        const title = product_data?.title || 'New Deal Detected!';

        // 1. Calculate Discount for Title
        let discountInfo = '🎉 ';
        const price = product_data?.price;
        const wasPrice = product_data?.was_price || product_data?.resell;

        if (price && wasPrice) {
            const p = parseFloat(String(price).replace(/[^0-9.]/g, ''));
            const w = parseFloat(String(wasPrice).replace(/[^0-9.]/g, ''));
            if (w > p && p > 0) {
                const disc = Math.round(((w - p) / w) * 100);
                if (disc >= 10) discountInfo = `📉 ${disc}% OFF: `;
            }
        }

        const finalTitle = `${discountInfo}${title.substring(0, 45)}${title.length > 45 ? '...' : ''}`;

        // 2. Build Body (Omit N/A and refine labels)
        const parts = [];
        if (price && price !== '0.0' && price !== 'N/A' && price !== '0') {
            parts.push(`Price: $${price}`);
        }
        if (wasPrice && wasPrice !== '0.0' && wasPrice !== 'N/A' && wasPrice !== '0' && wasPrice !== price) {
            parts.push(`Market: $${wasPrice}`);
        }

        // Region/Store
        const storeLabel = category_name || 'HollowScan';
        const regionLabel = region ? region.replace(' Stores', '') : '';
        parts.push(`${regionLabel} ${storeLabel}`.trim());

        const finalBody = parts.join(' | ');

        await sendLocalNotification(finalTitle, finalBody, {
            product_id: product?.id || 'unknown',
            category: category_name,
            region: region,
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
                projectId: '2f7823be-eb44-4956-8297-4969baf0a524'
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

