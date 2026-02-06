import React, { useState, useContext, useEffect, useRef } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, Alert, ActivityIndicator, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useIsFocused } from '@react-navigation/native';
import { UserContext } from '../context/UserContext';
import Constants from '../Constants';

const TelegramLinkScreen = ({ navigation }) => {
    const { user, isDarkMode, telegramLinked, unlinkTelegramAccount, checkTelegramStatus } = useContext(UserContext);
    const [isUnlinking, setIsUnlinking] = useState(false);
    const isFocused = useIsFocused();
    const pollInterval = useRef(null);

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

    // Poll for status while focused and NOT linked
    useEffect(() => {
        if (isFocused && !telegramLinked) {
            pollInterval.current = setInterval(() => {
                checkTelegramStatus();
            }, 3000);
        } else {
            if (pollInterval.current) clearInterval(pollInterval.current);
        }

        return () => {
            if (pollInterval.current) clearInterval(pollInterval.current);
        };
    }, [isFocused, telegramLinked]);

    const handleLinkTelegram = () => {
        // Correct link format as per user: https://t.me/HollowScan_Bot?start=link_<user_id>
        const telegramUrl = `https://t.me/HollowScan_Bot?start=link_${user.id}`;
        Linking.openURL(telegramUrl).catch(err => {
            Alert.alert("Error", "Could not open Telegram. Please search for @HollowScan_Bot manually.");
        });
    };

    const handleUnlink = async () => {
        Alert.alert(
            'Unlink Telegram?',
            'Are you sure you want to disconnect your Telegram account?',
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Unlink',
                    style: 'destructive',
                    onPress: async () => {
                        setIsUnlinking(true);
                        const result = await unlinkTelegramAccount();
                        setIsUnlinking(false);

                        if (result.success) {
                            Alert.alert('Success', 'Telegram account unlinked.');
                        } else {
                            Alert.alert('Error', result.message || 'Failed to unlink account.');
                        }
                    }
                }
            ]
        );
    };

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                    <Text style={[styles.backText, { color: colors.text }]}>← Back</Text>
                </TouchableOpacity>
                <Text style={[styles.title, { color: colors.text }]}>Telegram Bot</Text>
            </View>

            <View style={styles.content}>
                {telegramLinked ? (
                    <View style={styles.statusSection}>
                        <View style={[styles.successCard, { backgroundColor: 'rgba(34, 197, 94, 0.1)', borderColor: 'rgba(34, 197, 94, 0.3)' }]}>
                            <Text style={{ fontSize: 60, marginBottom: 15 }}>✅</Text>
                            <Text style={[styles.successText, { color: '#22C55E' }]}>Account Linked!</Text>
                            <Text style={[styles.successSubtext, { color: colors.textSecondary }]}>
                                You are now receiving notifications via Telegram.
                            </Text>
                        </View>

                        <TouchableOpacity
                            style={[styles.unlinkBtn, { backgroundColor: isDarkMode ? '#2C1010' : '#FEF2F2', borderColor: isDarkMode ? '#451010' : '#FECACA' }]}
                            onPress={handleUnlink}
                            disabled={isUnlinking}
                        >
                            {isUnlinking ? (
                                <ActivityIndicator color="#EF4444" />
                            ) : (
                                <Text style={styles.unlinkText}>Unlink Account</Text>
                            )}
                        </TouchableOpacity>
                    </View>
                ) : (
                    <View style={styles.linkSection}>
                        <View style={[styles.infoCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
                            <Text style={[styles.infoTitle, { color: colors.text }]}>🔗 Link your account</Text>
                            <Text style={[styles.infoText, { color: colors.textSecondary }]}>
                                1. Tap the button below to open Telegram
                            </Text>
                            <Text style={[styles.infoText, { color: colors.textSecondary }]}>
                                2. Send the pre-filled <Text style={{ fontWeight: '700' }}>/start</Text> command
                            </Text>
                            <Text style={[styles.infoText, { color: colors.textSecondary }]}>
                                3. Return here once the bot confirms your link
                            </Text>
                        </View>

                        <View style={styles.waitingContainer}>
                            <ActivityIndicator size="small" color={brand.BLUE} style={{ marginRight: 10 }} />
                            <Text style={[styles.waitingText, { color: colors.textSecondary }]}>Waiting for Telegram verification...</Text>
                        </View>

                        <TouchableOpacity
                            style={[styles.linkBtn, { backgroundColor: brand.BLUE }]}
                            onPress={handleLinkTelegram}
                        >
                            <Text style={styles.linkBtnText}>📱 Open @HollowScan_Bot</Text>
                        </TouchableOpacity>

                        <View style={[styles.noteCard, { backgroundColor: isDarkMode ? 'rgba(59, 130, 246, 0.1)' : 'rgba(59, 130, 246, 0.05)', borderColor: 'rgba(59, 130, 246, 0.2)' }]}>
                            <Text style={[styles.noteText, { color: colors.textSecondary }]}>
                                💡 <Text style={{ fontWeight: '700' }}>Tip:</Text> Linking your account syncs your Premium status across all devices and enables real-time deal alerts!
                            </Text>
                        </View>
                    </View>
                )}
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
        marginBottom: 10,
    },
    backBtn: { paddingRight: 20 },
    backText: { fontSize: 16, fontWeight: '600' },
    title: { fontSize: 24, fontWeight: '800' },
    content: { padding: 20 },
    infoCard: { borderRadius: 16, padding: 20, marginBottom: 25, borderWidth: 1 },
    infoTitle: { fontSize: 18, fontWeight: '700', marginBottom: 15 },
    infoText: { fontSize: 14, lineHeight: 22, marginBottom: 8 },
    linkBtn: {
        height: 55,
        borderRadius: 15,
        justifyContent: 'center',
        alignItems: 'center',
        shadowColor: '#000',
        shadowOpacity: 0.1,
        shadowRadius: 10,
        elevation: 5,
        marginBottom: 20,
    },
    linkBtnText: { color: '#FFF', fontSize: 18, fontWeight: '700' },
    noteCard: { borderRadius: 12, padding: 15, borderWidth: 1 },
    noteText: { fontSize: 13, lineHeight: 20 },
    statusSection: { alignItems: 'center' },
    successCard: { width: '100%', borderRadius: 16, padding: 40, alignItems: 'center', borderWidth: 1, marginBottom: 25 },
    successText: { fontSize: 24, fontWeight: '800', marginBottom: 10 },
    successSubtext: { fontSize: 15, textAlign: 'center' },
    unlinkBtn: { width: '100%', padding: 15, borderRadius: 12, alignItems: 'center', borderWidth: 1 },
    unlinkText: { color: '#EF4444', fontWeight: '700', fontSize: 16 },
    waitingContainer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
    waitingText: { fontSize: 13, fontStyle: 'italic' },
});

export default TelegramLinkScreen;
