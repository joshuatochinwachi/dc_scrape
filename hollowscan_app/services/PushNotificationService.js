import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
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
            shouldShowAlert: true,
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
        const { product_data, category_name, country_code } = product;
        const title = `🎉 New ${category_name?.toUpperCase() || 'Deal'} in ${country_code}`;
        const price = product_data?.price || 'N/A';
        const resell = product_data?.resell || 'N/A';
        const body = `${product_data?.title?.substring(0, 40) || 'New Product'}... | Buy: $${price} | Sell: $${resell}`;

        await sendLocalNotification(title, body, {
            product_id: product_data?.id || 'unknown',
            category: category_name,
            country: country_code,
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
            const token = (await Notifications.getExpoPushTokenAsync()).data;
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

