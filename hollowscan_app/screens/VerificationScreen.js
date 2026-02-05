import React, { useState, useContext, useRef, useEffect } from 'react';
import {
    StyleSheet,
    View,
    Text,
    TouchableOpacity,
    ActivityIndicator,
    StatusBar,
    Alert,
    TextInput,
    KeyboardAvoidingView,
    Platform,
    TouchableWithoutFeedback,
    Keyboard
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { UserContext } from '../context/UserContext';
import Constants from '../Constants';

const VerificationScreen = () => {
    const { user, isDarkMode, resendVerification, verifyCode, logout, refreshUserStatus } = useContext(UserContext);
    const [code, setCode] = useState('');
    const [isResending, setIsResending] = useState(false);
    const [isVerifying, setIsVerifying] = useState(false);
    const [cooldown, setCooldown] = useState(0);

    useEffect(() => {
        let timer;
        if (cooldown > 0) {
            timer = setInterval(() => {
                setCooldown(prev => prev - 1);
            }, 1000);
        }
        return () => clearInterval(timer);
    }, [cooldown]);

    const brand = Constants.BRAND;
    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        text: '#FFFFFF',
        textSecondary: '#8E8E93',
        inputBg: '#1C1C1E',
        inputBorder: '#2C2C2E'
    } : {
        bg: '#F2F4F8',
        text: '#1C1C1E',
        textSecondary: '#636366',
        inputBg: '#FFFFFF',
        inputBorder: '#E5E5EA'
    };

    const handleVerify = async () => {
        if (code.length !== 6) {
            Alert.alert('Invalid Code', 'Please enter the 6-digit verification code.');
            return;
        }
        setIsVerifying(true);
        const res = await verifyCode(code);
        setIsVerifying(false);
        if (!res.success) {
            Alert.alert('Verification Failed', res.message);
        }
    };

    const handleResend = async () => {
        setIsResending(true);
        const res = await resendVerification();
        setIsResending(false);
        if (res.success) {
            setCooldown(60);
            Alert.alert('Success', 'Verification code sent!');
        } else {
            Alert.alert('Error', res.message);
        }
    };

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]}>
            <StatusBar barStyle={isDarkMode ? "light-content" : "dark-content"} />
            <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
                <KeyboardAvoidingView
                    behavior={Platform.OS === "ios" ? "padding" : "height"}
                    style={{ flex: 1 }}
                >
                    <View style={styles.content}>
                        <LinearGradient
                            colors={[brand.PURPLE, brand.BLUE]}
                            style={styles.iconContainer}
                        >
                            <Text style={{ fontSize: 40, color: '#FFF' }}>📩</Text>
                        </LinearGradient>

                        <Text style={[styles.title, { color: colors.text }]}>Verify Your Email</Text>
                        <Text style={[styles.description, { color: colors.textSecondary }]}>
                            Enter the 6-digit code we sent to:
                        </Text>
                        <Text style={[styles.email, { color: colors.text }]}>{user?.email}</Text>

                        <View style={styles.codeContainer}>
                            <TextInput
                                style={[styles.codeInput, {
                                    backgroundColor: colors.inputBg,
                                    borderColor: colors.inputBorder,
                                    color: colors.text
                                }]}
                                value={code}
                                onChangeText={(val) => setCode(val.replace(/[^0-9]/g, '').slice(0, 6))}
                                placeholder="000000"
                                placeholderTextColor={isDarkMode ? '#3A3A3C' : '#C7C7CC'}
                                keyboardType="number-pad"
                                maxLength={6}
                                autoFocus={true}
                                selectionColor={brand.BLUE}
                            />
                        </View>

                        <View style={styles.actions}>
                            <TouchableOpacity
                                style={[styles.primaryBtn, { backgroundColor: brand.BLUE }]}
                                onPress={handleVerify}
                                disabled={isVerifying || code.length !== 6}
                            >
                                {isVerifying ? (
                                    <ActivityIndicator color="#FFF" size="small" />
                                ) : (
                                    <Text style={styles.primaryBtnText}>Verify Code</Text>
                                )}
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.secondaryBtn, {
                                    borderColor: isDarkMode ? brand.PURPLE : brand.PURPLE + '40',
                                    opacity: cooldown > 0 ? 0.5 : 1
                                }]}
                                onPress={handleResend}
                                disabled={isResending || cooldown > 0}
                            >
                                {isResending ? (
                                    <ActivityIndicator color={brand.PURPLE} size="small" />
                                ) : (
                                    <Text style={[styles.secondaryBtnText, { color: brand.PURPLE }]}>
                                        {cooldown > 0 ? `Resend Code (${cooldown}s)` : 'Resend Code'}
                                    </Text>
                                )}
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={styles.logoutBtn}
                                onPress={() => refreshUserStatus()}
                            >
                                <Text style={[styles.logoutBtnText, { color: brand.BLUE, textDecorationLine: 'none' }]}>I've already verified my email →</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={styles.logoutBtn}
                                onPress={logout}
                            >
                                <Text style={[styles.logoutBtnText, { color: colors.textSecondary }]}>Switch Account / Logout</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                </KeyboardAvoidingView>
            </TouchableWithoutFeedback>

            {/* DECORATIVE BACKGROUND ELEMENTS */}
            <View style={[styles.bgCircle, { backgroundColor: brand.BLUE + '05', top: -100, right: -100 }]} />
            <View style={[styles.bgCircle, { backgroundColor: brand.PURPLE + '05', bottom: -100, left: -100 }]} />
        </SafeAreaView>
    );
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
    },
    content: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: 30,
    },
    iconContainer: {
        width: 100,
        height: 100,
        borderRadius: 50,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 24,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.2,
        shadowRadius: 15,
        elevation: 10
    },
    title: {
        fontSize: 32,
        fontWeight: '900',
        marginBottom: 12,
        textAlign: 'center',
        letterSpacing: -0.5
    },
    description: {
        fontSize: 16,
        fontWeight: '500',
        textAlign: 'center',
        lineHeight: 24,
        marginBottom: 4
    },
    email: {
        fontSize: 18,
        fontWeight: '800',
        marginBottom: 32,
        textAlign: 'center'
    },
    codeContainer: {
        width: '100%',
        marginBottom: 32,
    },
    codeInput: {
        height: 70,
        borderRadius: 20,
        borderWidth: 2,
        fontSize: 36,
        fontWeight: '800',
        textAlign: 'center',
        letterSpacing: 8,
    },
    actions: {
        width: '100%',
        gap: 16
    },
    primaryBtn: {
        height: 56,
        borderRadius: 16,
        justifyContent: 'center',
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.1,
        shadowRadius: 8,
        elevation: 3
    },
    primaryBtnText: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '800',
        letterSpacing: 0.5
    },
    secondaryBtn: {
        height: 56,
        borderRadius: 16,
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 2
    },
    secondaryBtnText: {
        fontSize: 16,
        fontWeight: '800'
    },
    logoutBtn: {
        height: 56,
        justifyContent: 'center',
        alignItems: 'center',
        marginTop: 8
    },
    logoutBtnText: {
        fontSize: 15,
        fontWeight: '700',
        textDecorationLine: 'underline'
    },
    bgCircle: {
        position: 'absolute',
        width: 300,
        height: 300,
        borderRadius: 150,
        zIndex: -1
    }
});

export default VerificationScreen;
