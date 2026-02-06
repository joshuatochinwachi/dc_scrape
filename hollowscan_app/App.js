import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { Text, View, ActivityIndicator, Alert } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Linking from 'expo-linking';
import { SavedProvider } from './context/SavedContext';
import { UserProvider, UserContext } from './context/UserContext';
import Constants from './Constants';
import { navigationRef } from './services/NavigationService';

// Screens
import HomeScreen from './screens/HomeScreen';
import ProductDetailScreen from './screens/ProductDetailScreen';
import SavedScreen from './screens/SavedScreen';
import AlertsScreen from './screens/AlertsScreen';
import ProfileScreen from './screens/ProfileScreen';
import SplashScreen from './screens/SplashScreen';
import LoginScreen from './screens/LoginScreen';
import SignupScreen from './screens/SignupScreen';
import VerificationScreen from './screens/VerificationScreen';
import ForgotPasswordScreen from './screens/ForgotPasswordScreen';
import ChangePasswordScreen from './screens/ChangePasswordScreen';
import TelegramLinkScreen from './screens/TelegramLinkScreen';
import DailyLimitModal from './components/DailyLimitModal';



const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();
const AuthStack = createNativeStackNavigator();

function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={{ headerShown: false }}>
      <AuthStack.Screen name="Login" component={LoginScreen} />
      <AuthStack.Screen name="Signup" component={SignupScreen} />
      <AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
    </AuthStack.Navigator>
  );
}

function TabNavigator() {
  const brand = Constants.BRAND;
  const { isDarkMode } = React.useContext(UserContext);
  const insets = useSafeAreaInsets();

  // Combine inset with base padding for professional clearance
  const bottomPadding = Math.max(insets.bottom, 12);
  const barHeight = 55 + bottomPadding;

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: brand.BLUE,
        tabBarInactiveTintColor: isDarkMode ? '#444' : '#9CA3AF',
        tabBarStyle: {
          borderTopWidth: 1,
          borderTopColor: isDarkMode ? '#1C1C1E' : '#F3F4F6',
          height: barHeight,
          paddingBottom: bottomPadding,
          paddingTop: 10,
          elevation: 0,
          backgroundColor: isDarkMode ? brand.DARK_BG : '#FFF'
        },
        tabBarLabelStyle: {
          fontWeight: '700',
          fontSize: 10,
          marginTop: 5
        },
      })}
    >
      <Tab.Screen
        name="Home"
        component={HomeScreen}
        options={{ tabBarIcon: ({ color }) => <Text style={{ fontSize: 24, color }}>🏠</Text> }}
      />
      <Tab.Screen
        name="Saved"
        component={SavedScreen}
        options={{ tabBarIcon: ({ color }) => <Text style={{ fontSize: 24, color }}>❤️</Text> }}
      />
      <Tab.Screen
        name="Alerts"
        component={AlertsScreen}
        options={{ tabBarIcon: ({ color }) => <Text style={{ fontSize: 24, color }}>🔔</Text> }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{ tabBarIcon: ({ color }) => <Text style={{ fontSize: 24, color }}>👤</Text> }}
      />
    </Tab.Navigator>
  );
}

const NavigationRoot = ({ showSplash, setShowSplash, linking }) => {
  const { isDarkMode, user, isLoading, linkTelegramAccount } = React.useContext(UserContext);

  // Handle Deep Linking for Account Link
  React.useEffect(() => {
    const handleDeepLink = async (event) => {
      const url = event.url;
      if (!url) return;

      // Check for link pattern: hollowscan://link?code=XYZ
      if (url.includes('/link') && url.includes('code=')) {
        // Extract code
        try {
          const regex = /[?&]code=([^&#]+)/;
          const match = url.match(regex);

          if (match && match[1]) {
            const code = match[1];

            // Show loading indicator or toast? Alert is simplest for now.
            // Or better: Let UserContext handle it, but we need UI feedback.
            // Since we are outside a screen, Alert is good.

            if (!user) {
              Alert.alert('Login Required', 'Please log in to link your Telegram account.');
              return;
            }

            const result = await linkTelegramAccount(code);

            if (result.success) {
              Alert.alert('Success', 'Telegram account linked successfully! 🎉');
            } else {
              Alert.alert('Error', result.message || 'Failed to link account.');
            }
          }
        } catch (e) {
          console.error('Deep link error:', e);
        }
      }
    };

    const sub = Linking.addEventListener('url', handleDeepLink);

    // Check initial URL
    Linking.getInitialURL().then(url => {
      if (url) handleDeepLink({ url });
    });

    return () => {
      if (sub && sub.remove) sub.remove();
    };
  }, [user]); // Re-bind if user changes (so we have up-to-date user object)

  if (isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: isDarkMode ? Constants.BRAND.DARK_BG : '#FFF' }}>
        <ActivityIndicator size="large" color={Constants.BRAND.BLUE} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      {showSplash ? (
        <SplashScreen onComplete={() => setShowSplash(false)} />
      ) : (
        <NavigationContainer
          ref={navigationRef}
          linking={linking}
          fallback={<SplashScreen onComplete={() => { }} />}
        >
          <StatusBar style={isDarkMode ? "light" : "dark"} />
          <Stack.Navigator screenOptions={{ headerShown: false }}>
            {user ? (
              !user.email_verified ? (
                <Stack.Screen name="Verification" component={VerificationScreen} />
              ) : (
                <>
                  <Stack.Screen name="Root" component={TabNavigator} />
                  <Stack.Screen name="ProductDetail" component={ProductDetailScreen} options={{ presentation: 'card' }} />
                  <Stack.Screen name="ChangePassword" component={ChangePasswordScreen} />
                  <Stack.Screen name="TelegramLink" component={TelegramLinkScreen} />
                  <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
                </>
              )
            ) : (
              <Stack.Screen name="Auth" component={AuthNavigator} />
            )}

          </Stack.Navigator>
          <DailyLimitModal />
        </NavigationContainer>
      )}

    </SafeAreaProvider>
  );
};

export default function App() {
  const [showSplash, setShowSplash] = React.useState(true);

  // Deep linking configuration
  const prefix = Linking.createURL('/');
  const linking = {
    prefixes: [prefix, 'hollowscan://', 'https://hollowscan.com'],
    config: {
      screens: {
        Root: {
          screens: {
            Home: 'home',
            Saved: 'saved',
            Alerts: 'alerts',
            Profile: 'profile',
          },
        },
        Auth: {
          screens: {
            Login: 'login',
            Signup: 'signup',
            ForgotPassword: 'forgot-password',
          }
        },
        ProductDetail: 'product/:productId',
      },
    },
  };

  return (
    <UserProvider>
      <SavedProvider>
        <NavigationRoot showSplash={showSplash} setShowSplash={setShowSplash} linking={linking} />
      </SavedProvider>
    </UserProvider>
  );
}
