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
    const [telegramLinkKey, setTelegramLinkKey] = useState(null);
    const [isGeneratingKey, setIsGeneratingKey] = useState(false);
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
                setTelegramLinkKey(null);
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

    const handleGenerateLinkKey = async () => {
        const userId = user?.id || 'guest-user';
        setIsGeneratingKey(true);
        try {
            const response = await fetch(
                `${Constants.API_BASE_URL}/v1/user/telegram/generate-key?user_id=${userId}`,
                { method: 'POST', headers: { 'Content-Type': 'application/json' } }
            );
            const data = await response.json();
            if (data.success) {
                setTelegramLinkKey(data.link_key);
            }
        } catch (error) {
            console.error('[TELEGRAM] Error:', error);
        } finally {
            setIsGeneratingKey(false);
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
                            <>
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
                            </>
                        ) : (
                            <>
                                {!telegramLinkKey ? (
                                    <TouchableOpacity
                                        style={{ backgroundColor: brand.BLUE, padding: 16, borderRadius: 12, marginBottom: 16 }}
                                        onPress={handleGenerateLinkKey}
                                        disabled={isGeneratingKey}
                                    >
                                        {isGeneratingKey ? (
                                            <ActivityIndicator color="#FFF" />
                                        ) : (
                                            <Text style={{ color: '#FFF', fontSize: 16, fontWeight: '700', textAlign: 'center' }}>Generate Link Key</Text>
                                        )}
                                    </TouchableOpacity>
                                ) : (
                                    <View style={{ marginBottom: 20 }}>
                                        <View style={{ backgroundColor: isDarkMode ? 'rgba(255,255,255,0.05)' : '#F9FAFB', padding: 16, borderRadius: 12, alignItems: 'center', borderWidth: 1, borderColor: colors.border, marginBottom: 16 }}>
                                            <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>YOUR CODE</Text>
                                            <Text style={{ fontSize: 32, fontWeight: '800', color: brand.BLUE, letterSpacing: 2 }}>{telegramLinkKey}</Text>
                                        </View>

                                        <TouchableOpacity
                                            style={{ backgroundColor: '#0EA5E9', padding: 14, borderRadius: 12, marginBottom: 12 }}
                                            onPress={() => Linking.openURL('https://t.me/Hollowscan_bot')}
                                        >
                                            <Text style={{ color: '#FFF', fontWeight: '700', textAlign: 'center' }}>🤖 Open Telegram Bot</Text>
                                        </TouchableOpacity>

                                        <Text style={{ color: colors.textSecondary, fontSize: 12, textAlign: 'center', marginBottom: 16 }}>
                                            Send <Text style={{ fontWeight: '700' }}>/link {telegramLinkKey}</Text> to the bot
                                        </Text>

                                        <TouchableOpacity
                                            style={{ backgroundColor: '#10B981', padding: 16, borderRadius: 12 }}
                                            onPress={handleCheckLinkStatus}
                                            disabled={isCheckingStatus}
                                        >
                                            {isCheckingStatus ? (
                                                <ActivityIndicator color="#FFF" />
                                            ) : (
                                                <Text style={{ color: '#FFF', fontSize: 16, fontWeight: '700', textAlign: 'center' }}>Verify Connection</Text>
                                            )}
                                        </TouchableOpacity>
                                    </View>
                                )}

                                <TouchableOpacity
                                    style={{ padding: 12 }}
                                    onPress={() => {
                                        setShowTelegramFlow(false);
                                        setTelegramLinkKey(null);
                                    }}
                                >
                                    <Text style={{ color: colors.textSecondary, fontSize: 15, fontWeight: '600', textAlign: 'center' }}>
                                        Back
                                    </Text>
                                </TouchableOpacity>
                            </>
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
