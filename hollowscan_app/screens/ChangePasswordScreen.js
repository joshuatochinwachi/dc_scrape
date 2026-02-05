import React, { useState, useContext } from 'react';
import { StyleSheet, View, Text, TextInput, TouchableOpacity, Alert, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { UserContext } from '../context/UserContext';
import Constants from '../Constants';

const ChangePasswordScreen = ({ navigation }) => {
    const { user, isDarkMode, logout } = useContext(UserContext);
    const [oldPassword, setOldPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const brand = Constants.BRAND;
    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        card: '#161618',
        text: '#FFFFFF',
        textSecondary: '#8E8E93',
        inputBg: '#2C2C2E',
        border: '#3A3A3C'
    } : {
        bg: '#F8F9FE',
        card: '#FFFFFF',
        text: '#1C1C1E',
        textSecondary: '#636366',
        inputBg: '#F3F4F6',
        border: '#E5E7EB'
    };

    const handleChangePassword = async () => {
        if (!oldPassword || !newPassword || !confirmPassword) {
            Alert.alert('Error', 'Please fill in all fields.');
            return;
        }

        if (newPassword !== confirmPassword) {
            Alert.alert('Error', 'New passwords do not match.');
            return;
        }

        if (newPassword.length < 6) {
            Alert.alert('Error', 'Password must be at least 6 characters.');
            return;
        }

        setIsLoading(true);
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/user/change-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: user?.id,
                    old_password: oldPassword,
                    new_password: newPassword
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                Alert.alert('Success', 'Password updated successfully! Please log in with your new password.', [
                    { text: 'OK', onPress: () => logout() }
                ]);
            } else {
                Alert.alert('Error', data.detail || 'Failed to update password.');
            }
        } catch (error) {
            Alert.alert('Error', 'Network error. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                    <Text style={[styles.backText, { color: colors.text }]}>← Back</Text>
                </TouchableOpacity>
                <Text style={[styles.title, { color: colors.text }]}>Change Password</Text>
            </View>

            <View style={styles.form}>
                <View style={styles.inputGroup}>
                    <Text style={[styles.label, { color: colors.textSecondary }]}>Current Password</Text>
                    <TextInput
                        style={[styles.input, { backgroundColor: colors.inputBg, color: colors.text, borderColor: colors.border }]}
                        value={oldPassword}
                        onChangeText={setOldPassword}
                        secureTextEntry
                        placeholder="Enter current password"
                        placeholderTextColor={colors.textSecondary}
                    />
                </View>

                <TouchableOpacity
                    onPress={() => navigation.navigate('ForgotPassword')}
                    style={{ alignSelf: 'flex-end', marginBottom: 20, marginTop: -10 }}
                >
                    <Text style={{ color: brand.BLUE, fontWeight: '600' }}>Forgot password?</Text>
                </TouchableOpacity>

                <View style={styles.inputGroup}>
                    <Text style={[styles.label, { color: colors.textSecondary }]}>New Password</Text>
                    <TextInput
                        style={[styles.input, { backgroundColor: colors.inputBg, color: colors.text, borderColor: colors.border }]}
                        value={newPassword}
                        onChangeText={setNewPassword}
                        secureTextEntry
                        placeholder="Enter new password"
                        placeholderTextColor={colors.textSecondary}
                    />
                </View>

                <View style={styles.inputGroup}>
                    <Text style={[styles.label, { color: colors.textSecondary }]}>Confirm New Password</Text>
                    <TextInput
                        style={[styles.input, { backgroundColor: colors.inputBg, color: colors.text, borderColor: colors.border }]}
                        value={confirmPassword}
                        onChangeText={setConfirmPassword}
                        secureTextEntry
                        placeholder="Confirm new password"
                        placeholderTextColor={colors.textSecondary}
                    />
                </View>

                <TouchableOpacity
                    style={[styles.submitBtn, { backgroundColor: brand.BLUE }]}
                    onPress={handleChangePassword}
                    disabled={isLoading}
                >
                    {isLoading ? (
                        <ActivityIndicator color="#FFF" />
                    ) : (
                        <Text style={styles.submitText}>Update Password</Text>
                    )}
                </TouchableOpacity>
            </View>
        </SafeAreaView>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1 },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 20,
        marginBottom: 20,
    },
    backBtn: {
        paddingRight: 20,
    },
    backText: {
        fontSize: 16,
        fontWeight: '600',
    },
    title: {
        fontSize: 24,
        fontWeight: '800',
    },
    form: {
        padding: 20,
    },
    inputGroup: {
        marginBottom: 20,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        marginBottom: 8,
        marginLeft: 4,
    },
    input: {
        height: 50,
        borderRadius: 12,
        paddingHorizontal: 15,
        fontSize: 16,
        borderWidth: 1,
    },
    submitBtn: {
        height: 55,
        borderRadius: 15,
        justifyContent: 'center',
        alignItems: 'center',
        marginTop: 20,
        shadowColor: '#000',
        shadowOpacity: 0.1,
        shadowRadius: 10,
        elevation: 5,
    },
    submitText: {
        color: '#FFF',
        fontSize: 18,
        fontWeight: '700',
    },
});

export default ChangePasswordScreen;
