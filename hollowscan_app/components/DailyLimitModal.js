import React, { useContext, useState } from 'react';
import { StyleSheet, View, Text, Modal, TouchableOpacity, ActivityIndicator, Linking, Alert } from 'react-native';

import { BlurView } from 'expo-blur';
import { UserContext } from '../context/UserContext';
import Constants from '../Constants';
import { useNavigation } from '@react-navigation/native';

const DailyLimitModal = () => {
    const {
        showLimitModal,
        setShowLimitModal,
        countdown,
        isDarkMode,
        telegramLinked,
        checkTelegramStatus,
        user
    } = useContext(UserContext);
    const navigation = useNavigation();
    const brand = Constants.BRAND;

    // Local state for the Telegram flow within the modal
    const [showTelegramFlow, setShowTelegramFlow] = useState(false);
    const [isCheckingStatus, setIsCheckingStatus] = useState(false);

    const colors = isDarkMode ? {
        card: '#161618',
        text: '#FFFFFF',
        textSecondary: '#8E8E93',
        border: 'rgba(255,255,255,0.08)',
    } : {
        card: '#FFFFFF',
        text: '#1C1C1E',
        textSecondary: '#636366',
        border: 'rgba(0,0,0,0.05)',
    };

    const handleCheckLinkStatus = async () => {
        setIsCheckingStatus(true);
        try {
            const result = await checkTelegramStatus();
            if (result && result.linked) {
                setShowTelegramFlow(false);
                setShowTelegramFlow(false);
                setShowLimitModal(false);
                Alert.alert('🎉 Success', 'Telegram account linked and premium status synced!');
            } else {
                Alert.alert('⏳ Not Linked Yet', 'Send the command to the bot first, then try again.');
            }

        } catch (error) {
            console.error('[TELEGRAM] Error:', error);
        } finally {
            setIsCheckingStatus(false);
        }
    };


    if (!showLimitModal) return null;

    return (
        <Modal visible={showLimitModal} animationType="fade" transparent={true}>
            <BlurView intensity={90} tint={isDarkMode ? 'dark' : 'light'} style={styles.modalOverlay}>
                <View style={styles.modalCenter}>
                    <View style={[styles.modalContent, { backgroundColor: colors.card, maxWidth: 360 }]}>
                        {/* Icon */}
                        <View style={{ alignItems: 'center', marginBottom: 20 }}>
                            <View style={{ width: 80, height: 80, borderRadius: 40, backgroundColor: brand.BLUE + '15', justifyContent: 'center', alignItems: 'center', marginBottom: 16 }}>
                                <Text style={{ fontSize: 40 }}>{showTelegramFlow ? '📱' : '⏰'}</Text>
                            </View>
                            <Text style={[styles.modalTitle, { color: colors.text, fontSize: 22, textAlign: 'center' }]}>
                                {showTelegramFlow ? 'Connect Telegram' : 'Daily Limit Reached'}
                            </Text>
                            <Text style={{ color: colors.textSecondary, fontSize: 14, textAlign: 'center', marginTop: 8, lineHeight: 20 }}>
                                {showTelegramFlow
                                    ? 'Link your Telegram to sync premium status and get instant deal alerts!'
                                    : "You've viewed your 4 free products for today. Come back tomorrow or upgrade to Premium!"}
                            </Text>
                        </View>

                        {!showTelegramFlow ? (
                            <View>
                                {/* Countdown Timer */}
                                <View style={{ backgroundColor: isDarkMode ? 'rgba(255,255,255,0.05)' : '#F3F4F6', padding: 20, borderRadius: 16, marginBottom: 20 }}>
                                    <Text style={{ color: colors.textSecondary, fontSize: 12, textAlign: 'center', marginBottom: 8, fontWeight: '600' }}>
                                        RESETS IN
                                    </Text>
                                    <Text style={{ color: colors.text, fontSize: 36, textAlign: 'center', fontWeight: '800', letterSpacing: 2 }}>
                                        {countdown}
                                    </Text>
                                </View>

                                {/* Premium CTA */}
                                <TouchableOpacity
                                    style={{ backgroundColor: brand.BLUE, padding: 16, borderRadius: 12, marginBottom: 12 }}
                                    onPress={() => {
                                        setShowLimitModal(false);
                                        navigation.navigate('Profile');
                                    }}
                                >
                                    <Text style={{ color: '#FFF', fontSize: 16, fontWeight: '700', textAlign: 'center' }}>
                                        👑 Upgrade to Premium
                                    </Text>
                                </TouchableOpacity>

                                {/* Telegram CTA */}
                                {!telegramLinked && (
                                    <TouchableOpacity
                                        style={{ backgroundColor: '#0EA5E9', padding: 16, borderRadius: 12, marginBottom: 12 }}
                                        onPress={() => setShowTelegramFlow(true)}
                                    >
                                        <Text style={{ color: '#FFF', fontSize: 16, fontWeight: '700', textAlign: 'center' }}>
                                            📱 Connect Telegram
                                        </Text>
                                    </TouchableOpacity>
                                )}

                                {/* Close Button */}
                                <TouchableOpacity
                                    style={{ padding: 12 }}
                                    onPress={() => setShowLimitModal(false)}
                                >
                                    <Text style={{ color: colors.textSecondary, fontSize: 15, fontWeight: '600', textAlign: 'center' }}>
                                        Close
                                    </Text>
                                </TouchableOpacity>
                            </View>
                        ) : (
                            <View style={{ marginBottom: 20 }}>
                                <View style={{ backgroundColor: isDarkMode ? 'rgba(255,255,255,0.05)' : '#F9FAFB', padding: 20, borderRadius: 16, alignItems: 'center', borderWidth: 1, borderColor: colors.border, marginBottom: 20 }}>
                                    <Text style={{ fontSize: 40, marginBottom: 16 }}>🤖</Text>
                                    <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text, textAlign: 'center', marginBottom: 8 }}>Ready to Connect?</Text>
                                    <Text style={{ fontSize: 13, color: colors.textSecondary, textAlign: 'center', lineHeight: 18 }}>We'll open Telegram for you. Just tap "Connect" in the bot to link your account!</Text>
                                </View>

                                <TouchableOpacity
                                    style={{ backgroundColor: '#0EA5E9', padding: 16, borderRadius: 12, marginBottom: 12 }}
                                    onPress={() => {
                                        // New Direct Link: App -> Telegram with user ID
                                        const telegramUrl = `https://t.me/HollowScanBot?start=link_${user.id}`;
                                        Linking.openURL(telegramUrl).catch(() => {
                                            Alert.alert('Error', 'Could not open Telegram. Please install Telegram first.');
                                        });

                                        // Auto-check status after delay
                                        setTimeout(async () => {
                                            const result = await checkTelegramStatus();
                                            if (result && result.linked) {
                                                setShowTelegramFlow(false);
                                                setShowLimitModal(false);
                                                Alert.alert('🎉 Success!', 'Telegram account linked and premium status synced!');
                                            }
                                        }, 5000);
                                    }}
                                >
                                    <Text style={{ color: '#FFF', fontWeight: '800', textAlign: 'center', fontSize: 16 }}>🚀 Open Telegram Bot</Text>
                                </TouchableOpacity>

                                <TouchableOpacity
                                    style={{ backgroundColor: '#10B981', padding: 16, borderRadius: 12 }}
                                    onPress={handleCheckLinkStatus}
                                    disabled={isCheckingStatus}
                                >
                                    {isCheckingStatus ? (
                                        <ActivityIndicator color="#FFF" />
                                    ) : (
                                        <Text style={{ color: '#FFF', fontSize: 16, fontWeight: '700', textAlign: 'center' }}>Already Linked? Verify</Text>
                                    )}
                                </TouchableOpacity>

                                <TouchableOpacity
                                    style={{ padding: 12, marginTop: 16 }}
                                    onPress={() => setShowTelegramFlow(false)}
                                >
                                    <Text style={{ color: colors.textSecondary, fontSize: 15, fontWeight: '600', textAlign: 'center' }}>
                                        Back
                                    </Text>
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>
                </View>
            </BlurView>
        </Modal>
    );
};

const styles = StyleSheet.create({
    modalOverlay: {
        flex: 1,
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.5)'
    },
    modalCenter: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: 16
    },
    modalContent: {
        borderRadius: 24,
        padding: 24,
        width: '100%',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.25,
        shadowRadius: 20,
        elevation: 10,
    },
    modalTitle: { fontSize: 20, fontWeight: '900' },
});

export default DailyLimitModal;
