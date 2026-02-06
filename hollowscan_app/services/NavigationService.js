import { createNavigationContainerRef } from '@react-navigation/native';

export const navigationRef = createNavigationContainerRef();

export function navigate(name, params) {
    if (navigationRef.isReady()) {
        navigationRef.navigate(name, params);
    } else {
        // You can decide what to do if the app hasn't mounted
        // You could queue the navigation, but for now we'll just log
        console.log('[NAVIGATION] Navigation ref not ready yet');
    }
}
