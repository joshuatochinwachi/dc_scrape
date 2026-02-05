import React, { useContext, useState, useEffect } from 'react';
import { StyleSheet, View, Text, ScrollView, TouchableOpacity, Image, Switch, Modal, TextInput, ActivityIndicator, Linking, Alert, Clipboard, ImageBackground } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { SavedContext } from '../context/SavedContext';
import { UserContext } from '../context/UserContext';
import Constants from '../Constants';


const ProfileScreen = ({ navigation }) => {
    const { savedProducts } = useContext(SavedContext);
    const { user, isDarkMode, toggleTheme, logout, telegramLinked, isPremiumTelegram, premiumUntil, checkTelegramStatus, selectedRegion, updateRegion } = useContext(UserContext);
    const brand = Constants.BRAND;

    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        card: '#161618',
        text: '#FFFFFF',
        textSecondary: '#8E8E93',
        border: 'rgba(255,255,255,0.08)',
        groupBg: '#1C1C1E'
    } : {
        bg: '#F8F9FE',
        card: '#FFFFFF',
        text: '#1C1C1E',
        textSecondary: '#636366',
        border: 'rgba(0,0,0,0.05)',
        groupBg: '#FFFFFF'
    };

    // State Management
    // const [country, setCountry] = useState('US'); // REMOVED LOCAL STATE
    const [telegramModalVisible, setTelegramModalVisible] = useState(false);
    const [telegramLinkKey, setTelegramLinkKey] = useState(null);
    const [isGeneratingKey, setIsGeneratingKey] = useState(false);
    const [isCheckingStatus, setIsCheckingStatus] = useState(false);
    const [countryModalVisible, setCountryModalVisible] = useState(false);
    const userId = user?.id || 'guest-user';


    // Calculate generic stats
    const savedCount = savedProducts.length;
    const potentialProfit = savedProducts.reduce((acc, p) => {
        const buy = parseFloat(String(p.product_data?.price || '0').replace(/[^0-9.]/g, ''));
        const sell = parseFloat(String(p.product_data?.resell || '0').replace(/[^0-9.]/g, ''));

        // Only calculate profit if there's a valid sell price
        if (isNaN(sell) || sell <= 0) return acc;

        const fees = sell * 0.15;
        const profit = sell - buy - fees;
        return acc + (profit > 0 ? profit : 0);
    }, 0).toFixed(0);

    // Handlers

    const handleTelegramLinkPress = () => {
        if (telegramLinked) {
            setTelegramModalVisible(true);
        } else {
            // Open Telegram bot with deep link parameter
            const botUsername = Constants.TELEGRAM_BOT;
            const telegramUrl = `https://t.me/${botUsername}?start=link_account`;

            Linking.openURL(telegramUrl).catch(err => {
                Alert.alert('Error', 'Could not open Telegram. Please make sure Telegram is installed.');
                console.error('Failed to open Telegram:', err);
            });
        }
    };

    const handleCheckLinkStatus = async () => {
        setIsCheckingStatus(true);
        try {
            console.log('[TELEGRAM] Checking link status...');

            const result = await checkTelegramStatus();
            if (result && result.linked) {
                setTelegramLinkKey(null);
            } else {
                Alert.alert('⏳ Not Linked Yet', 'Send the command to the bot first, then try again.');
            }

        } catch (error) {
            console.error('[TELEGRAM] Error:', error);
            Alert.alert('Error', `Failed to check status: ${error.message}`);
        } finally {
            setIsCheckingStatus(false);
        }
    };

    const handleTelegramUnlink = () => {
        Alert.alert(
            'Unlink Telegram?',
            'You will stop receiving Telegram notifications',
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Unlink',
                    style: 'destructive',
                    onPress: () => {
                        setTelegramLinked(false);
                        Alert.alert('Unlinked', 'Your Telegram account has been unlinked');
                    }
                }
            ]
        );
    };

    const openTelegramBot = () => {
        Linking.openURL('https://t.me/Hollowscan_bot').catch(() => {
            Alert.alert('Error', 'Could not open Telegram. Please install Telegram first.');
        });
    };

    const handleSignOut = () => {
        Alert.alert(
            'Sign Out',
            'Are you sure you want to sign out?',
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Sign Out',
                    style: 'destructive',
                    onPress: async () => {
                        await logout();
                    }
                }
            ]
        );
    };


    const StatBox = ({ label, value }) => (
        <View style={[styles.statBox, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
            <Text style={[styles.statValue, { color: colors.text }]}>{value}</Text>
            <Text style={[styles.statLabel, { color: colors.textSecondary }]}>{label}</Text>
        </View>
    );

    const SettingRowWithSwitch = ({ icon, label, value, onValueChange }) => (
        <View style={[styles.settingRow, { borderBottomColor: colors.border }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Text style={{ marginRight: 15, fontSize: 18, width: 25, textAlign: 'center', color: colors.text }}>{icon}</Text>
                <Text style={[styles.settingLabel, { color: colors.text }]}>{label}</Text>
            </View>
            <Switch
                value={value}
                onValueChange={onValueChange}
                trackColor={{ false: '#D1D5DB', true: brand.BLUE }}
                thumbColor={'#FFF'}
            />
        </View>
    );

    const SettingRow = ({ icon, label, value, onPress, isDestructive, status }) => (
        <TouchableOpacity
            style={[styles.settingRow, { borderBottomColor: colors.border }]}
            onPress={onPress}
            disabled={!onPress}
        >
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Text style={{ marginRight: 15, fontSize: 18, width: 25, textAlign: 'center', color: colors.text }}>{icon}</Text>
                <View>
                    <Text style={[styles.settingLabel, { color: isDestructive ? '#EF4444' : colors.text }]}>{label}</Text>
                    {status && <Text style={[styles.statusText, { color: colors.textSecondary }]}>{status}</Text>}
                </View>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                {value && <Text style={[styles.settingValue, { color: colors.textSecondary }]}>{value}</Text>}
                {onPress && <Text style={{ color: colors.textSecondary, fontSize: 16, marginLeft: 10 }}>›</Text>}
            </View>
        </TouchableOpacity>
    );

    const SectionHeader = ({ title }) => (
        <View style={styles.sectionHeader}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>{title}</Text>
        </View>
    );

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]} edges={['top']}>
            <ScrollView contentContainerStyle={styles.scroll}>
                {/* PROFILE HEADER - SLEEK COVER IMAGE */}
                <ImageBackground
                    source={require('../assets/profile_cover.png')}
                    style={styles.profileHeader}
                    resizeMode="cover"
                >
                    <LinearGradient
                        colors={['rgba(0,0,0,0.1)', 'rgba(0,0,0,0.6)']}
                        style={StyleSheet.absoluteFill}
                    />
                    <View style={styles.avatarContainer}>
                        <Text style={styles.avatarText}>H</Text>
                    </View>
                    <Text style={styles.userName}>{user?.email || 'HollowScan User'}</Text>
                    <View style={styles.planBadge}>
                        <Text style={styles.planText}>👑 {(user?.isPremium || isPremiumTelegram) ? 'Premium' : 'Free'} Plan</Text>
                    </View>

                    <TouchableOpacity style={styles.upgradeBtn}>
                        <LinearGradient
                            colors={[brand.CYAN, brand.BLUE]}
                            start={{ x: 0, y: 0 }}
                            end={{ x: 1, y: 1 }}
                            style={styles.upgradeGradient}
                        >
                            <Text style={styles.upgradeText}>Upgrade to Premium</Text>
                        </LinearGradient>
                    </TouchableOpacity>
                </ImageBackground>

                {/* STATS ROW */}
                <View style={styles.statsRow}>
                    <StatBox label="Saved" value={savedCount} />
                    <StatBox label="Profit" value={`$${potentialProfit}`} />
                    <StatBox label="Alerts" value="3" />
                </View>

                {/* NOTIFICATION & PREFERENCES */}
                <SectionHeader title="SETTINGS" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>

                    <SettingRowWithSwitch
                        icon="🌙"
                        label="Dark Mode"
                        value={isDarkMode}
                        onValueChange={toggleTheme}
                    />
                    <SettingRow
                        icon="🌍"
                        label="Preferred Country"
                        value={selectedRegion === 'USA Stores' ? 'US' : selectedRegion === 'UK Stores' ? 'UK' : 'CA'}
                        status="Region for deals"
                        onPress={() => setCountryModalVisible(true)}
                    />
                </View>

                {/* INTEGRATIONS */}
                <SectionHeader title="INTEGRATIONS" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow
                        icon="📱"
                        label="Telegram Bot"
                        value={telegramLinked ? '✓ Linked' : 'Not linked'}
                        status={
                            isPremiumTelegram
                                ? `👑 Premium until ${new Date(premiumUntil).toLocaleDateString()}`
                                : (telegramLinked ? 'Receiving notifications' : 'Connect for alerts')
                        }
                        onPress={handleTelegramLinkPress}
                    />

                </View>

                {/* ACCOUNT */}
                <SectionHeader title="ACCOUNT" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow icon="👤" label="Profile Information" onPress={() => { }} />
                    <SettingRow icon="🔒" label="Change Password" onPress={() => navigation.navigate('ChangePassword')} />
                    <SettingRow icon="✉️" label="Email Verification" value={user?.email_verified ? "Verified" : "Unverified"} />

                </View>

                {/* SUPPORT */}
                <SectionHeader title="SUPPORT" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow icon="❓" label="Help & FAQ" onPress={() => { }} />
                    <SettingRow icon="📞" label="Contact Support" onPress={() => { }} />
                    <SettingRow icon="⭐" label="Rate the App" onPress={() => { }} />
                </View>

                {/* LEGAL */}
                <SectionHeader title="LEGAL" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow icon="📄" label="Terms of Service" onPress={() => { }} />
                    <SettingRow icon="🛡️" label="Privacy Policy" onPress={() => { }} />
                </View>

                {/* SIGN OUT */}
                <TouchableOpacity
                    style={[styles.signOutBtn, isDarkMode && { backgroundColor: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.2)' }]}
                    onPress={handleSignOut}
                >
                    <Text style={styles.signOutText}>→ Sign Out</Text>
                </TouchableOpacity>

                <Text style={styles.version}>Version 1.0.0 (Build 1)</Text>
                <View style={{ height: 50 }} />
            </ScrollView>

            {/* TELEGRAM MODAL - SIMPLIFIED */}
            <Modal
                visible={telegramModalVisible}
                transparent={true}
                animationType="fade"
                onRequestClose={() => !isGeneratingKey && !isCheckingStatus && setTelegramModalVisible(false)}
            >
                <BlurView intensity={90} style={styles.blurContainer}>
                    <View style={styles.centeredView}>
                        <View style={styles.modalView}>
                            <View style={styles.modalHeader}>
                                <Text style={styles.modalTitle}>
                                    {telegramLinked ? '✅ Connected' : '📱 Connect Telegram'}
                                </Text>
                                <TouchableOpacity
                                    onPress={() => {
                                        setTelegramModalVisible(false);
                                        setTelegramLinkKey(null);
                                    }}
                                    disabled={isGeneratingKey || isCheckingStatus}
                                >
                                    <Text style={styles.closeBtn}>✕</Text>
                                </TouchableOpacity>
                            </View>

                            {!telegramLinked ? (
                                <View style={{ alignItems: 'center', paddingVertical: 20 }}>
                                    <Text style={styles.modalDescription}>
                                        Tap "Telegram Bot" in Profile to connect.{'\n'}
                                        You'll be taken directly to the bot!
                                    </Text>
                                </View>
                            ) : (
                                <>
                                    <View style={styles.successContainer}>
                                        <Text style={styles.successEmoji}>🎉</Text>
                                        <Text style={styles.successText}>Connected!</Text>
                                        {isPremiumTelegram && (
                                            <Text style={{ fontSize: 12, color: '#D97706', marginTop: 5 }}>👑 Premium Status Synced</Text>
                                        )}
                                    </View>

                                    <View style={styles.benefitsContainer}>
                                        <Text style={styles.benefitTitle}>Getting notifications for:</Text>
                                        <Text style={styles.benefit}>✓ New deals</Text>
                                        <Text style={styles.benefit}>✓ Price drops</Text>
                                        <Text style={styles.benefit}>✓ High ROI items</Text>
                                    </View>

                                    <View style={styles.modalButtonsContainer}>
                                        <TouchableOpacity
                                            style={styles.unlinkBtn}
                                            onPress={handleTelegramUnlink}
                                        >
                                            <Text style={styles.unlinkBtnText}>Disconnect</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={styles.doneBtn}
                                            onPress={() => setTelegramModalVisible(false)}
                                        >
                                            <Text style={styles.doneBtnText}>Done</Text>
                                        </TouchableOpacity>
                                    </View>
                                </>
                            )}
                        </View >
                    </View >
                </BlurView >
            </Modal >

            {/* COUNTRY SELECTOR MODAL */}
            < Modal
                visible={countryModalVisible}
                transparent={true}
                animationType="fade"
                onRequestClose={() => setCountryModalVisible(false)}
            >
                <BlurView intensity={90} style={styles.blurContainer}>
                    <View style={styles.centeredView}>
                        <View style={[styles.modalView, { width: '80%', maxWidth: 300 }]}>
                            <Text style={styles.modalTitle}>Select Country</Text>
                            <Text style={styles.modalTitle}>Select Country</Text>
                            {[
                                { id: 'USA Stores', code: 'US', label: '🇺🇸 United States' },
                                { id: 'UK Stores', code: 'UK', label: '🇬🇧 United Kingdom' },
                                { id: 'Canada Stores', code: 'CA', label: '🇨🇦 Canada' }
                            ].map(c => (
                                <TouchableOpacity
                                    key={c.code}
                                    style={[
                                        styles.countryOption,
                                        selectedRegion === c.id && styles.countryOptionActive
                                    ]}
                                    onPress={() => {
                                        updateRegion(c.id);
                                        setCountryModalVisible(false);
                                    }}
                                >
                                    <Text style={[
                                        styles.countryOptionText,
                                        selectedRegion === c.id && styles.countryOptionTextActive
                                    ]}>
                                        {c.label}
                                    </Text>
                                </TouchableOpacity>
                            ))}
                        </View>
                    </View>
                </BlurView>
            </Modal >
        </SafeAreaView >
    );
};

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#FAFAF8' },
    scroll: { paddingBottom: 40 },

    // Profile Header
    profileHeader: {
        alignItems: 'center',
        paddingTop: 60,
        paddingBottom: 40,
        paddingHorizontal: 20,
        overflow: 'hidden',
    },
    avatarContainer: {
        width: 90,
        height: 90,
        borderRadius: 45,
        backgroundColor: 'rgba(255,255,255,0.15)',
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 12,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.3)',
        shadowColor: '#000',
        shadowOpacity: 0.2,
        shadowRadius: 15,
        elevation: 10,
    },
    avatarText: { fontSize: 36, color: '#FFF', fontWeight: '900' },
    userName: { fontSize: 24, fontWeight: '900', color: '#FFF', marginBottom: 4, letterSpacing: -0.5 },
    planBadge: {
        backgroundColor: 'rgba(255,255,255,0.25)',
        paddingHorizontal: 14,
        paddingVertical: 6,
        borderRadius: 20,
        marginBottom: 20,
        borderWidth: 0.5,
        borderColor: 'rgba(255,255,255,0.4)',
    },
    planText: { fontSize: 12, fontWeight: '600', color: '#FFF' },
    upgradeBtn: {
        overflow: 'hidden',
        borderRadius: 25,
        shadowColor: '#000',
        shadowOpacity: 0.2,
        shadowRadius: 10,
    },
    upgradeGradient: {
        paddingHorizontal: 40,
        paddingVertical: 12,
        alignItems: 'center',
        justifyContent: 'center',
    },
    upgradeText: { color: '#FFF', fontWeight: '700', fontSize: 15 },

    // Stats
    statsRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        padding: 15,
        marginTop: -25,
        paddingHorizontal: 15,
    },
    statBox: {
        flex: 1,
        backgroundColor: '#FFF',
        padding: 15,
        borderRadius: 20,
        alignItems: 'center',
        marginHorizontal: 5,
        shadowColor: '#000',
        shadowOpacity: 0.08,
        shadowRadius: 12,
        shadowOffset: { width: 0, height: 4 },
        elevation: 4,
    },
    statValue: { fontSize: 18, fontWeight: '800', color: '#1F2937', marginBottom: 2 },
    statLabel: { fontSize: 12, fontWeight: '600', color: '#9CA3AF' },

    // Sections
    sectionHeader: { paddingHorizontal: 20, marginTop: 25, marginBottom: 12 },
    sectionTitle: { fontSize: 11, fontWeight: '900', letterSpacing: 2 },

    // Groups
    group: {
        borderWidth: 1,
        borderColor: 'rgba(0,0,0,0.03)',
        marginHorizontal: 15,
        marginBottom: 10,
        borderRadius: 20,
        overflow: 'hidden',
        shadowColor: '#000',
        shadowOpacity: 0.02,
        shadowRadius: 10,
    },
    settingRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        paddingLeft: 20,
        paddingRight: 20,
        borderBottomWidth: 1,
        borderBottomColor: '#F3F4F6',
    },
    settingLabel: { fontSize: 16, fontWeight: '600' },
    statusText: { fontSize: 12, marginTop: 4 },
    settingValue: { fontSize: 14 },

    // Sign Out
    signOutBtn: {
        marginHorizontal: 20,
        marginTop: 15,
        marginBottom: 20,
        backgroundColor: '#FEF2F2',
        padding: 15,
        borderRadius: 12,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: '#FECACA',
    },
    signOutText: { color: '#EF4444', fontWeight: '700', fontSize: 16 },
    version: { textAlign: 'center', color: '#D1D5DB', fontSize: 12 },

    // Modal Styles
    blurContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    centeredView: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    modalView: {
        backgroundColor: '#FFF',
        borderRadius: 20,
        padding: 25,
        width: '90%',
        maxWidth: 400,
        shadowColor: '#000',
        shadowOpacity: 0.25,
        shadowRadius: 4,
        elevation: 5,
    },
    modalHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 15,
    },
    modalTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#1F2937',
    },
    closeBtn: {
        fontSize: 24,
        color: '#9CA3AF',
    },
    modalDescription: {
        fontSize: 14,
        color: '#6B7280',
        marginBottom: 20,
        lineHeight: 20,
    },

    // Telegram Modal
    botLinkBtn: {
        backgroundColor: '#0EA5E9',
        padding: 15,
        borderRadius: 12,
        alignItems: 'center',
        marginBottom: 20,
    },
    botLinkText: {
        color: '#FFF',
        fontWeight: '700',
        fontSize: 16,
    },
    orDivider: {
        textAlign: 'center',
        color: '#D1D5DB',
        fontSize: 12,
        marginBottom: 15,
        fontWeight: '600',
    },
    telegramInput: {
        borderWidth: 1,
        borderColor: '#E5E7EB',
        borderRadius: 10,
        padding: 12,
        fontSize: 14,
        marginBottom: 20,
        color: '#1F2937',
    },
    modalButtonsContainer: {
        flexDirection: 'row',
        gap: 10,
    },
    cancelBtn: {
        flex: 1,
        padding: 12,
        borderRadius: 10,
        backgroundColor: '#F3F4F6',
        alignItems: 'center',
    },
    cancelBtnText: {
        color: '#6B7280',
        fontWeight: '700',
        fontSize: 15,
    },
    linkBtn: {
        flex: 1,
        padding: 12,
        borderRadius: 10,
        backgroundColor: '#4F46E5', // Changed from FF8A65
        alignItems: 'center',
        justifyContent: 'center',
    },
    linkBtnText: {
        color: '#FFF',
        fontWeight: '700',
        fontSize: 15,
    },
    unlinkBtn: {
        flex: 1,
        padding: 12,
        borderRadius: 10,
        backgroundColor: '#FEE2E2',
        alignItems: 'center',
    },
    unlinkBtnText: {
        color: '#DC2626',
        fontWeight: '700',
        fontSize: 15,
    },
    doneBtn: {
        flex: 1,
        padding: 12,
        borderRadius: 10,
        backgroundColor: '#10B981',
        alignItems: 'center',
    },
    doneBtnText: {
        color: '#FFF',
        fontWeight: '700',
        fontSize: 15,
    },

    // Success State
    successContainer: {
        alignItems: 'center',
        marginBottom: 25,
    },
    successEmoji: {
        fontSize: 48,
        marginBottom: 10,
    },
    successText: {
        fontSize: 16,
        fontWeight: '700',
        color: '#1F2937',
    },
    benefitsContainer: {
        backgroundColor: '#F0FDF4',
        padding: 15,
        borderRadius: 10,
        marginBottom: 20,
    },
    benefitTitle: {
        fontSize: 14,
        fontWeight: '700',
        color: '#1F2937',
        marginBottom: 10,
    },
    benefit: {
        fontSize: 13,
        color: '#059669',
        marginVertical: 4,
    },

    // Country Modal
    countryOption: {
        padding: 15,
        borderBottomWidth: 1,
        borderBottomColor: '#F3F4F6',
        borderRadius: 8,
        marginVertical: 5,
        backgroundColor: '#F9FAFB',
    },
    countryOptionActive: {
        backgroundColor: '#FF8A65',
    },
    countryOptionText: {
        fontSize: 16,
        color: '#374151',
        fontWeight: '500',
    },
    countryOptionTextActive: {
        color: '#FFF',
        fontWeight: '700',
    },

    // Telegram Link Key Generation
    stepContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 20,
        paddingBottom: 15,
        borderBottomWidth: 1,
        borderBottomColor: '#E5E7EB',
    },
    stepNumber: {
        fontSize: 20,
        fontWeight: '800',
        color: '#FF8A65',
        marginRight: 12,
        backgroundColor: '#FFF3E0',
        width: 40,
        height: 40,
        borderRadius: 20,
        textAlign: 'center',
        textAlignVertical: 'center',
    },
    stepText: {
        fontSize: 16,
        fontWeight: '700',
        color: '#1F2937',
        flex: 1,
    },
    primaryBtn: {
        backgroundColor: '#FF8A65',
        padding: 14,
        borderRadius: 10,
        alignItems: 'center',
        marginBottom: 20,
    },
    primaryBtnText: {
        color: '#FFF',
        fontWeight: '700',
        fontSize: 15,
    },
    infoBox: {
        backgroundColor: '#FFF3E0',
        padding: 15,
        borderRadius: 10,
        marginBottom: 15,
        borderLeftWidth: 4,
        borderLeftColor: '#FF8A65',
    },
    infoTitle: {
        fontSize: 13,
        fontWeight: '700',
        color: '#E65100',
        marginBottom: 8,
    },
    infoText: {
        fontSize: 12,
        color: '#BF360C',
        marginVertical: 3,
        lineHeight: 18,
    },
    keyDisplay: {
        backgroundColor: '#F9FAFB',
        padding: 15,
        borderRadius: 12,
        marginBottom: 15,
    },
    keyLabel: {
        fontSize: 11,
        fontWeight: '700',
        color: '#9CA3AF',
        marginBottom: 8,
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
    keyBox: {
        backgroundColor: '#F9FAFB',
        padding: 15,
        borderRadius: 10,
        marginBottom: 15,
        borderWidth: 1,
        borderColor: '#E5E7EB',
        alignItems: 'center',
    },
    keyText: {
        fontSize: 28,
        fontWeight: '800',
        color: '#FF8A65',
        letterSpacing: 2,
        marginBottom: 12,
    },
    copyBtn: {
        backgroundColor: '#FFF',
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: '#E5E7EB',
    },
    copyBtnText: {
        color: '#374151',
        fontWeight: '600',
        fontSize: 12,
    },
    instructionBox: {
        backgroundColor: '#F0F9FF',
        padding: 12,
        borderRadius: 10,
        marginBottom: 15,
        borderLeftWidth: 4,
        borderLeftColor: '#0EA5E9',
    },
    instructionTitle: {
        fontSize: 11,
        fontWeight: '700',
        color: '#0369A1',
        marginBottom: 8,
    },
    commandBox: {
        backgroundColor: '#FFF',
        padding: 10,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: '#E0F2FE',
    },
    commandText: {
        fontSize: 13,
        fontFamily: 'monospace',
        fontWeight: '600',
        color: '#0369A1',
    },
});

export default ProfileScreen;
