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
    Alert,
    Image
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { UserContext } from '../context/UserContext';
import Constants from '../Constants';

const ForgotPasswordScreen = ({ navigation }) => {
    const { forgotPassword, resetPassword, isDarkMode } = useContext(UserContext);
    const [step, setStep] = useState(1); // 1: Email, 2: Code & New Password
    const [email, setEmail] = useState('');
    const [code, setCode] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [loading, setLoading] = useState(false);

    const brand = Constants.BRAND;
    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        text: '#FFFFFF',
        textSecondary: '#A1A1AA',
        input: '#1C1C1E',
        border: 'rgba(255,255,255,0.08)'
    } : {
        bg: '#F8F9FE',
        text: '#1C1C1E',
        textSecondary: '#636366',
        input: '#FFFFFF',
        border: 'rgba(0,0,0,0.05)'
    };

    const handleRequestCode = async () => {
        if (!email) {
            Alert.alert('Error', 'Please enter your email address');
            return;
        }
        setLoading(true);
        const res = await forgotPassword(email);
        setLoading(false);
        if (res.success) {
            setStep(2);
        } else {
            Alert.alert('Error', res.message);
        }
    };

    const handleResetPassword = async () => {
        if (!code || !newPassword) {
            Alert.alert('Error', 'Please fill in all fields');
            return;
        }
        if (newPassword.length < 6) {
            Alert.alert('Error', 'Password must be at least 6 characters');
            return;
        }
        setLoading(true);
        const res = await resetPassword(email, code, newPassword);
        setLoading(false);
        if (res.success) {
            Alert.alert('Success', 'Your password has been updated. Please log in.', [
                { text: 'OK', onPress: () => navigation.navigate('Login') }
            ]);
        } else {
            Alert.alert('Error', res.message);
        }
    };

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]}>
            <StatusBar barStyle={isDarkMode ? "light-content" : "dark-content"} />
            <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
                style={{ flex: 1 }}
            >
                <ScrollView contentContainerStyle={styles.scrollContent}>
                    <TouchableOpacity
                        style={styles.backBtn}
                        onPress={() => step === 1 ? navigation.goBack() : setStep(1)}
                    >
                        <Text style={[styles.backText, { color: colors.textSecondary }]}>← Back</Text>
                    </TouchableOpacity>

                    <View style={styles.header}>
                        <View style={[styles.iconContainer, { backgroundColor: brand.BLUE + '15' }]}>
                            <Text style={{ fontSize: 32 }}>🔑</Text>
                        </View>
                        <Text style={[styles.title, { color: colors.text }]}>
                            {step === 1 ? 'Forgot Password?' : 'Reset Password'}
                        </Text>
                        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                            {step === 1
                                ? "Enter your email and we'll send you a 6-digit code to reset your password."
                                : `Enter the 6-digit code sent to ${email} and your new password.`
                            }
                        </Text>
                    </View>

                    <View style={styles.form}>
                        {step === 1 ? (
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
                                    autoFocus
                                />
                                <TouchableOpacity
                                    style={[styles.primaryBtn, { backgroundColor: brand.BLUE, marginTop: 24 }]}
                                    onPress={handleRequestCode}
                                    disabled={loading}
                                >
                                    {loading ? <ActivityIndicator color="#FFF" /> : <Text style={styles.primaryBtnText}>Send Code</Text>}
                                </TouchableOpacity>
                            </View>
                        ) : (
                            <View>
                                <View style={styles.inputGroup}>
                                    <Text style={[styles.label, { color: colors.textSecondary }]}>6-DIGIT CODE</Text>
                                    <TextInput
                                        style={[styles.input, {
                                            backgroundColor: colors.input,
                                            borderColor: colors.border,
                                            color: colors.text,
                                            letterSpacing: 8,
                                            textAlign: 'center'
                                        }]}
                                        placeholder="000000"
                                        placeholderTextColor={isDarkMode ? '#52525B' : '#9CA3AF'}
                                        value={code}
                                        onChangeText={(val) => setCode(val.replace(/[^0-9]/g, '').slice(0, 6))}
                                        keyboardType="number-pad"
                                        maxLength={6}
                                        autoFocus
                                    />
                                </View>

                                <View style={styles.inputGroup}>
                                    <Text style={[styles.label, { color: colors.textSecondary }]}>NEW PASSWORD</Text>
                                    <TextInput
                                        style={[styles.input, {
                                            backgroundColor: colors.input,
                                            borderColor: colors.border,
                                            color: colors.text
                                        }]}
                                        placeholder="••••••••"
                                        placeholderTextColor={isDarkMode ? '#52525B' : '#9CA3AF'}
                                        value={newPassword}
                                        onChangeText={setNewPassword}
                                        secureTextEntry
                                    />
                                </View>

                                <TouchableOpacity
                                    style={[styles.primaryBtn, { backgroundColor: brand.BLUE, marginTop: 24 }]}
                                    onPress={handleResetPassword}
                                    disabled={loading}
                                >
                                    {loading ? <ActivityIndicator color="#FFF" /> : <Text style={styles.primaryBtnText}>Reset Password</Text>}
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>
                </ScrollView>
            </KeyboardAvoidingView>
        </SafeAreaView>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1 },
    scrollContent: {
        flexGrow: 1,
        paddingHorizontal: 30,
        paddingTop: 20
    },
    backBtn: {
        marginBottom: 40
    },
    backText: {
        fontSize: 16,
        fontWeight: '600'
    },
    header: {
        alignItems: 'center',
        marginBottom: 40
    },
    iconContainer: {
        width: 80,
        height: 80,
        borderRadius: 40,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 24
    },
    title: {
        fontSize: 28,
        fontWeight: '900',
        marginBottom: 12,
        letterSpacing: -0.5
    },
    subtitle: {
        fontSize: 16,
        fontWeight: '500',
        textAlign: 'center',
        lineHeight: 24
    },
    form: {
        width: '100%'
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
        fontSize: 18,
        fontWeight: '700',
        borderWidth: 1
    },
    primaryBtn: {
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
    primaryBtnText: {
        color: '#FFF',
        fontSize: 16,
        fontWeight: '800',
        letterSpacing: 0.5
    }
});

export default ForgotPasswordScreen;
