import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { Text, View, ActivityIndicator } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as Linking from 'expo-linking';
import { SavedProvider } from './context/SavedContext';
import { UserProvider, UserContext } from './context/UserContext';
import Constants from './Constants';

// Screens
import HomeScreen from './screens/HomeScreen';
import ProductDetailScreen from './screens/ProductDetailScreen';
import SavedScreen from './screens/SavedScreen';
import AlertsScreen from './screens/AlertsScreen';
import ProfileScreen from './screens/ProfileScreen';
import SplashScreen from './screens/SplashScreen';
import LoginScreen from './screens/LoginScreen';
import SignupScreen from './screens/SignupScreen';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();
const AuthStack = createNativeStackNavigator();

function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={{ headerShown: false }}>
      <AuthStack.Screen name="Login" component={LoginScreen} />
      <AuthStack.Screen name="Signup" component={SignupScreen} />
    </AuthStack.Navigator>
  );
}

function TabNavigator() {
  const brand = Constants.BRAND;
  const { isDarkMode } = React.useContext(UserContext);

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: brand.BLUE,
        tabBarInactiveTintColor: isDarkMode ? '#444' : '#9CA3AF',
        tabBarStyle: {
          borderTopWidth: 1,
          borderTopColor: isDarkMode ? '#1C1C1E' : '#F3F4F6',
          height: 85,
          paddingBottom: 20,
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
  const { isDarkMode, user, isLoading } = React.useContext(UserContext);

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
        <NavigationContainer linking={linking} fallback={<SplashScreen onComplete={() => { }} />}>
          <StatusBar style={isDarkMode ? "light" : "dark"} />
          <Stack.Navigator screenOptions={{ headerShown: false }}>
            {user ? (
              <>
                <Stack.Screen name="Root" component={TabNavigator} />
                <Stack.Screen name="ProductDetail" component={ProductDetailScreen} options={{ presentation: 'card' }} />
              </>
            ) : (
              <Stack.Screen name="Auth" component={AuthNavigator} />
            )}
          </Stack.Navigator>
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
