import React, { useState, useContext } from 'react';
import {
    StyleSheet,
    View,
    Text,
    TextInput,
    TouchableOpacity,
    ActivityIndicator,
    KeyboardAvoidingView,
    Platform,
    ScrollView,
    StatusBar,
    Dimensions,
    Image
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import { UserContext } from '../context/UserContext';
import Constants from '../Constants';

const { width, height } = Dimensions.get('window');

const LoginScreen = ({ navigation }) => {
    const { login, isDarkMode } = useContext(UserContext);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const brand = Constants.BRAND;
    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        card: '#161618',
        text: '#FFFFFF',
        textSecondary: '#A1A1AA',
        input: '#1C1C1E',
        border: 'rgba(255,255,255,0.08)'
    } : {
        bg: '#F8F9FE',
        card: '#FFFFFF',
        text: '#1C1C1E',
        textSecondary: '#636366',
        input: '#FFFFFF',
        border: 'rgba(0,0,0,0.05)'
    };

    const handleLogin = async () => {
        if (!email || !password) {
            setError('Please fill in all fields');
            return;
        }

        setLoading(true);
        setError('');

        const result = await login(email, password);
        setLoading(false);

        if (!result.success) {
            setError(result.message);
        }
    };

    return (
        <View style={[styles.container, { backgroundColor: colors.bg }]}>
            <StatusBar barStyle={isDarkMode ? "light-content" : "dark-content"} />
            <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
                style={{ flex: 1 }}
            >
                <ScrollView contentContainerStyle={styles.scrollContent}>
                    <View style={styles.header}>
                        <Image
                            source={require('../assets/app_logo.png')}
                            style={styles.logoBadge}
                            resizeMode="contain"
                        />
                        <Text style={[styles.title, { color: colors.text }]}>Welcome Back</Text>
                        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                            Login to track your flips and alerts
                        </Text>
                    </View>

                    <View style={styles.form}>
                        {error ? (
                            <View style={styles.errorBox}>
                                <Text style={styles.errorText}>{error}</Text>
                            </View>
                        ) : null}

                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.textSecondary }]}>EMAIL</Text>
                            <TextInput
                                style={[styles.input, {
                                    backgroundColor: colors.input,
                                    borderColor: colors.border,
                                    color: colors.text
                                }]}
                                placeholder="name@example.com"
                                placeholderTextColor={isDarkMode ? '#52525B' : '#9CA3AF'}
                                value={email}
                                onChangeText={setEmail}
                                keyboardType="email-address"
                                autoCapitalize="none"
                            />
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={[styles.label, { color: colors.textSecondary }]}>PASSWORD</Text>
                            <TextInput
                                style={[styles.input, {
                                    backgroundColor: colors.input,
                                    borderColor: colors.border,
                                    color: colors.text
                                }]}
                                placeholder="••••••••"
                                placeholderTextColor={isDarkMode ? '#52525B' : '#9CA3AF'}
                                value={password}
                                onChangeText={setPassword}
                                secureTextEntry
                            />
                        </View>

                        <TouchableOpacity
                            style={styles.forgotBtn}
                            onPress={() => navigation.navigate('ForgotPassword')}
                        >
                            <Text style={[styles.forgotText, { color: brand.BLUE }]}>Forgot Password?</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                            style={[styles.loginBtn, { backgroundColor: brand.BLUE }]}
                            onPress={handleLogin}
                            disabled={loading}
                        >
                            {loading ? (
                                <ActivityIndicator color="#FFF" />
                            ) : (
                                <Text style={styles.loginBtnText}>Login</Text>
                            )}
                        </TouchableOpacity>

                        <View style={styles.signupContainer}>
                            <Text style={[styles.noAccountText, { color: colors.textSecondary }]}>
                                Don't have an account?
                            </Text>
                            <TouchableOpacity onPress={() => navigation.navigate('Signup')}>
                                <Text style={[styles.signupText, { color: brand.BLUE }]}> Sign Up</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1 },
    scrollContent: {
        flexGrow: 1,
        justifyContent: 'center',
        paddingHorizontal: 30,
        paddingTop: 60,
        paddingBottom: 40
    },
    header: {
        alignItems: 'center',
        marginBottom: 40
    },
    logoBadge: {
        width: 60,
        height: 60,
        borderRadius: 18,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 20,
        shadowColor: '#4F46E5',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.3,
        shadowRadius: 15,
        elevation: 10
    },
    logoText: {
        fontSize: 32,
        fontWeight: '900',
        color: '#FFF'
    },
    title: {
        fontSize: 28,
        fontWeight: '900',
        marginBottom: 8,
        letterSpacing: -0.5
    },
    subtitle: {
        fontSize: 16,
        fontWeight: '500',
        textAlign: 'center'
    },
    form: {
        width: '100%'
    },
    errorBox: {
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        padding: 12,
        borderRadius: 12,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: 'rgba(239, 68, 68, 0.2)'
    },
    errorText: {
        color: '#EF4444',
        fontSize: 14,
        fontWeight: '600',
        textAlign: 'center'
    },
    inputGroup: {
        marginBottom: 20
    },
    label: {
        fontSize: 12,
        fontWeight: '800',
        marginBottom: 8,
        letterSpacing: 1,
        marginLeft: 4
    },
    input: {
        height: 55,
        borderRadius: 15,
        paddingHorizontal: 16,
        fontSize: 16,
        fontWeight: '600',
        borderWidth: 1
    },
    forgotBtn: {
        alignSelf: 'flex-end',
        marginBottom: 30
    },
    forgotText: {
        fontSize: 14,
        fontWeight: '700'
    },
    loginBtn: {
        height: 55,
        borderRadius: 15,
        justifyContent: 'center',
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.1,
        shadowRadius: 8,
        elevation: 3
    },
    loginBtnText: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '800',
        letterSpacing: 0.5
    },
    signupContainer: {
        flexDirection: 'row',
        justifyContent: 'center',
        marginTop: 30
    },
    noAccountText: {
        fontSize: 14,
        fontWeight: '500'
    },
    signupText: {
        fontSize: 14,
        fontWeight: '700'
    }
});

export default LoginScreen;
