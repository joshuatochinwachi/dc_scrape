import {
    StyleSheet,
    View,
    Text,
    Image,
    TouchableOpacity,
    ScrollView,
    Switch,
    Dimensions,
    Alert,
    SafeAreaView,
    Modal,
    TextInput,
    ImageBackground,
    Linking
} from 'react-native';
import React, { useContext, useState, useEffect, useCallback } from 'react';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import Constants from '../Constants';
import { UserContext } from '../context/UserContext';
import InfoModal from '../components/InfoModal';

const { width } = Dimensions.get('window');

const ProfileScreen = () => {
    const navigation = useNavigation();
    const { user, isDarkMode, toggleTheme, logout, selectedRegion, updateRegion, updateUserProfile, isPremium, linkTelegramAccount, telegramLinked, isPremiumTelegram, premiumUntil, checkTelegramStatus, refreshUserStatus } = useContext(UserContext);
    const brand = Constants.BRAND;

    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        text: '#FFFFFF',
        textSecondary: '#A1A1AA',
        groupBg: '#1C1C1E',
        border: 'rgba(255,255,255,0.08)',
    } : {
        bg: '#F2F4F8',
        text: '#1F2937',
        textSecondary: '#6B7280',
        groupBg: '#FFFFFF',
        border: 'rgba(0,0,0,0.06)',
    };

    // --- MODAL STATE ---
    const [editModalVisible, setEditModalVisible] = useState(false);
    const [countryModalVisible, setCountryModalVisible] = useState(false);
    const [infoModalVisible, setInfoModalVisible] = useState(false);

    // --- INFO MODAL CONTENT STATE ---
    const [infoModalTitle, setInfoModalTitle] = useState('');
    const [infoModalContent, setInfoModalContent] = useState([]);

    // --- EDIT PROFILE STATE ---
    const [editName, setEditName] = useState(user?.name || '');
    const [editBio, setEditBio] = useState(user?.bio || '');
    const [editLocation, setEditLocation] = useState(user?.location || '');
    const [selectedAvatar, setSelectedAvatar] = useState(user?.avatar_url || null);
    const [isSaving, setIsSaving] = useState(false);

    // AVATAR PRESETS (DiceBear)
    const avatarPresets = [
        "https://api.dicebear.com/7.x/avataaars/png?seed=Felix",
        "https://api.dicebear.com/7.x/avataaars/png?seed=Aneka",
        "https://api.dicebear.com/7.x/avataaars/png?seed=Baby",
        "https://api.dicebear.com/7.x/avataaars/png?seed=Rocky",
        "https://api.dicebear.com/7.x/avataaars/png?seed=Pumpkin",
        "https://api.dicebear.com/7.x/avataaars/png?seed=Jack",
        "https://api.dicebear.com/7.x/avataaars/png?seed=Callie",
        "https://api.dicebear.com/7.x/avataaars/png?seed=Garfield"
    ];

    // Refresh Telegram status when screen loads or gains focus
    useFocusEffect(
        useCallback(() => {
            const refreshStatus = async () => {
                if (user?.id) {
                    console.log('[PROFILE] Refreshing status on focus...');
                    await checkTelegramStatus();
                    await refreshUserStatus();
                }
            };
            refreshStatus();
        }, [user?.id])
    );

    const saveProfile = async () => {
        setIsSaving(true);
        const result = await updateUserProfile({
            name: editName,
            bio: editBio,
            location: editLocation,
            avatar_url: selectedAvatar
        });
        setIsSaving(false);
        if (result.success) {
            setEditModalVisible(false);
        } else {
            Alert.alert("Error", result.message || "Failed to update profile");
        }
    };

    // --- CONTENT DEFINITIONS ---

    const faqContent = [
        {
            heading: "General",
            questions: [
                { q: "What is HollowScan?", a: "HollowScan is a powerful arbitrage tool that helps you discover underpriced products across multiple regions (US, UK, CA) for resale profit." },
                { q: "How often are deals updated?", a: "Our scanners run 24/7. New deals appear in your feed within seconds of being detected on retailer sites." },
                { q: "Why are some prices 'Check on Site'?", a: "We fetch live data, but sometimes retailers hide prices or require a cart addition. Always verify the final price on the retailer's site before buying." },
                { q: "How do I contact support?", a: `You can reach us anytime at ${Constants.SUPPORT_EMAIL} for account issues, bug reports, or feedback.` }
            ]
        },
        {
            heading: "Account & Premium",
            questions: [
                { q: "How do I link my Telegram Account?", a: "It's easy! Go to Profile > Telegram Bot in this app, tap 'Open @HollowScan_Bot', and send the pre-filled /start command. Your accounts will link instantly!" },
                { q: "What are the benefits of Telegram linking?", a: "Linking enables real-time push alerts via Telegram, allows you to sync your Premium status across platforms, and gives you access to exclusive bot commands." },
                { q: "How does Premium work?", a: "Premium removes the daily limit, giving you unlimited access to our real-time feed and allowing you to see high-value deals immediately across all regions." }
            ]
        }
    ];

    const tosContent = [
        {
            heading: "1. Acceptance of Terms",
            body: "By accessing and using HollowScan, you agree to be bound by these Terms of Service. If you do not agree to these terms, you may not use our services."
        },
        {
            heading: "2. Data Accuracy & Liability",
            body: "HollowScan serves as a data aggregator. We display product information found across various retailers. We do not sell these products directly.",
            list: [
                "We do not guarantee the accuracy of pricing, stock status, or product details.",
                "Real-time data may fluctuate. The final price is always what is displayed on the retailer's checkout page.",
                "HollowScan is not responsible for any financial losses, missed deals, or order cancellations by retailers."
            ]
        },
        {
            heading: "3. User Responsibility",
            body: "Any purchases made are at the sole discretion and risk of the user. You are responsible for verifying all product details before purchasing for resale."
        }
    ];

    const privacyContent = [
        {
            heading: "Information We Collect",
            body: "We collect minimal data to provide our services:",
            list: [
                "Account Information: Email address and Name for identification.",
                "Usage Data: Product views and search preferences to improve the feed.",
                "Device Tokens: For sending push notifications (which you can disable)."
            ]
        },
        {
            heading: "How We Use Data",
            body: "We do not sell your personal data to third parties. Data is used strictly for authentication, service improvement, and delivering alerts."
        },
        {
            heading: "Data Security",
            body: "We implement industry-standard security measures to protect your information. Your passwords are never stored in plain text."
        }
    ];

    const openSupport = () => {
        Linking.openURL(`mailto:${Constants.SUPPORT_EMAIL}`).catch(err => {
            Alert.alert("Error", "Could not open mail app. Please email us at " + Constants.SUPPORT_EMAIL);
        });
    };

    const openInfoModal = (title, content) => {
        setInfoModalTitle(title);
        setInfoModalContent(content);
        setInfoModalVisible(true);
    };


    const SettingRow = ({ icon, label, value, onPress, status, isDestructive }) => (
        <TouchableOpacity style={styles.settingRow} onPress={onPress}>
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

    const SettingRowWithSwitch = ({ icon, label, value, onValueChange }) => (
        <View style={styles.settingRow}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Text style={{ marginRight: 15, fontSize: 18, width: 25, textAlign: 'center', color: colors.text }}>{icon}</Text>
                <Text style={[styles.settingLabel, { color: colors.text }]}>{label}</Text>
            </View>
            <Switch
                trackColor={{ false: '#767577', true: brand.BLUE }}
                thumbColor={'#f4f3f4'}
                ios_backgroundColor="#3e3e3e"
                onValueChange={onValueChange}
                value={value}
            />
        </View>
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
                        colors={['rgba(0,0,0,0.1)', 'rgba(0,0,0,0.8)']}
                        style={StyleSheet.absoluteFill}
                    />

                    <TouchableOpacity onPress={() => setEditModalVisible(true)} activeOpacity={0.8}>
                        <View style={styles.avatarContainer}>
                            {user?.avatar_url ? (
                                <Image source={{ uri: user.avatar_url }} style={styles.avatarImage} />
                            ) : (
                                <Text style={styles.avatarText}>{user?.name ? user.name.charAt(0).toUpperCase() : (user?.email ? user.email.charAt(0).toUpperCase() : 'H')}</Text>
                            )}
                            <View style={styles.editBadge}>
                                <Text style={{ fontSize: 10 }}>✏️</Text>
                            </View>
                        </View>
                    </TouchableOpacity>

                    <Text style={styles.userName}>{user?.name || 'HollowScan User'}</Text>
                    <Text style={styles.userEmail}>{user?.email}</Text>

                    {user?.location && (
                        <View style={styles.locationContainer}>
                            <Text style={styles.locationText}>📍 {user.location}</Text>
                        </View>
                    )}

                    {user?.bio && (
                        <View style={styles.bioContainer}>
                            <Text style={styles.bioText}>{user.bio}</Text>
                        </View>
                    )}

                    <View style={styles.planBadge}>
                        <Text style={styles.planText}>👑 {(user?.isPremium || isPremiumTelegram) ? 'Premium' : 'Free'} Plan</Text>
                    </View>

                    {(user?.isPremium || isPremiumTelegram) && (premiumUntil || user?.subscription_end) && (
                        <View style={styles.daysLeftContainer}>
                            <Text style={styles.daysLeftText}>
                                {(() => {
                                    const end = new Date(premiumUntil || user?.subscription_end);
                                    const now = new Date();
                                    const diffTime = Math.abs(end - now);
                                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                                    return `${diffDays} Day${diffDays !== 1 ? 's' : ''} Remaining`;
                                })()}
                            </Text>
                        </View>
                    )}

                    {/* Only show upgrade button if not premium */}
                    {!(user?.isPremium || isPremiumTelegram) && (
                        <View style={{ gap: 12, width: '100%', marginTop: 15 }}>
                            <TouchableOpacity
                                style={styles.upgradeBtn}
                                onPress={() => Alert.alert('Payment Method', 'Google Pay integration is coming soon! Please link your Telegram account to subscribe via our automated bot for now.')}
                            >
                                <LinearGradient
                                    colors={['#111111', '#222222']}
                                    start={{ x: 0, y: 0 }}
                                    end={{ x: 1, y: 1 }}
                                    style={styles.upgradeGradient}
                                >
                                    <Text style={styles.upgradeText}>Pay with Google Pay</Text>
                                </LinearGradient>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={styles.upgradeBtn}
                                onPress={() => navigation.navigate('TelegramLink')}
                            >
                                <LinearGradient
                                    colors={['#0088cc', '#00acee']}
                                    start={{ x: 0, y: 0 }}
                                    end={{ x: 1, y: 1 }}
                                    style={styles.upgradeGradient}
                                >
                                    <Text style={styles.upgradeText}>Link Telegram Premium</Text>
                                </LinearGradient>
                            </TouchableOpacity>
                        </View>
                    )}
                </ImageBackground>

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

                {/* ACCOUNT SECTION */}
                <SectionHeader title="ACCOUNT" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow
                        icon="👤"
                        label="Profile Information"
                        onPress={() => setEditModalVisible(true)}
                    />
                    <SettingRow
                        icon="🔐"
                        label="Change Password"
                        onPress={() => navigation.navigate('ChangePassword')}
                    />
                    <SettingRow
                        icon="✉️"
                        label="Email Verification"
                        value={user?.email_verified ? "Verified" : "Not Verified"}
                        status={user?.email_verified ? "Your email is verified" : "Verify to unlock features"}
                    />
                </View>

                {/* INTEGRATIONS */}
                <SectionHeader title="INTEGRATIONS" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow
                        icon="📱"
                        label="Telegram Bot"
                        value={telegramLinked ? '✓ Connected' : 'Not linked'}
                        status={
                            telegramLinked
                                ? (isPremiumTelegram ? 'Premium Status Sync Active' : 'Linked (Free Plan)')
                                : 'Link to sync Premium status'
                        }
                        onPress={() => navigation.navigate('TelegramLink')}
                    />
                </View>

                {/* SUPPORT SECTION */}
                <SectionHeader title="SUPPORT" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow
                        icon="❓"
                        label="Help & FAQ"
                        onPress={() => openInfoModal('Help & FAQ', faqContent)}
                    />
                    <SettingRow
                        icon="🎧"
                        label="Contact Support"
                        status={Constants.SUPPORT_EMAIL}
                        onPress={openSupport}
                    />
                </View>

                {/* LEGAL SECTION */}
                <SectionHeader title="LEGAL" />
                <View style={[styles.group, { backgroundColor: colors.groupBg, borderColor: colors.border }]}>
                    <SettingRow
                        icon="📜"
                        label="Terms of Service"
                        onPress={() => openInfoModal('Terms of Service', tosContent)}
                    />
                    <SettingRow
                        icon="🔒"
                        label="Privacy Policy"
                        onPress={() => openInfoModal('Privacy Policy', privacyContent)}
                    />
                </View>


                <TouchableOpacity
                    style={[styles.signOutBtn, { backgroundColor: isDarkMode ? '#2C1010' : '#FEF2F2', borderColor: isDarkMode ? '#451010' : '#FECACA' }]}
                    onPress={() => {
                        Alert.alert(
                            "Sign Out",
                            "Are you sure you want to sign out?",
                            [
                                { text: "Cancel", style: "cancel" },
                                { text: "Sign Out", style: "destructive", onPress: () => logout() }
                            ]
                        );
                    }}
                >
                    <Text style={styles.signOutText}>Sign Out</Text>
                </TouchableOpacity>

                <Text style={styles.version}>Version 1.0.4 • Build 152</Text>
            </ScrollView>

            {/* INFO MODAL */}
            <InfoModal
                visible={infoModalVisible}
                onClose={() => setInfoModalVisible(false)}
                title={infoModalTitle}
                content={infoModalContent}
                isDarkMode={isDarkMode}
            />


            {/* COUNTRY MODAL */}
            <Modal
                visible={countryModalVisible}
                animationType="fade"
                transparent={true}
                onRequestClose={() => setCountryModalVisible(false)}
            >
                <BlurView intensity={90} tint={isDarkMode ? 'dark' : 'light'} style={styles.blurContainer}>
                    <TouchableOpacity style={{ flex: 1, width: '100%' }} onPress={() => setCountryModalVisible(false)} />
                    <View style={[styles.modalView, { backgroundColor: colors.groupBg }]}>
                        <Text style={[styles.modalTitle, { color: colors.text }]}>Select Region</Text>
                        <View style={{ height: 1, backgroundColor: colors.border, marginVertical: 15 }} />

                        {['USA Stores', 'UK Stores', 'Canada Stores'].map((region) => (
                            <TouchableOpacity
                                key={region}
                                style={{ paddingVertical: 15, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: 'row', justifyContent: 'space-between' }}
                                onPress={() => {
                                    updateRegion(region);
                                    setCountryModalVisible(false);
                                }}
                            >
                                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                                    <Text style={{ fontSize: 24, marginRight: 10 }}>
                                        {region === 'USA Stores' ? '🇺🇸' : region === 'UK Stores' ? '🇬🇧' : '🇨🇦'}
                                    </Text>
                                    <Text style={{ fontSize: 16, color: colors.text }}>{region}</Text>
                                </View>
                                {selectedRegion === region && <Text style={{ color: brand.BLUE, fontWeight: 'bold' }}>✓</Text>}
                            </TouchableOpacity>
                        ))}
                    </View>
                    <TouchableOpacity style={{ flex: 1, width: '100%' }} onPress={() => setCountryModalVisible(false)} />
                </BlurView>
            </Modal>


            {/* EDIT PROFILE MODAL */}
            <Modal
                animationType="slide"
                transparent={true}
                visible={editModalVisible}
                onRequestClose={() => setEditModalVisible(false)}
            >
                <BlurView intensity={100} tint={isDarkMode ? 'dark' : 'light'} style={styles.blurContainer}>
                    <View style={[styles.editModalView, { backgroundColor: colors.groupBg }]}>
                        <View style={styles.modalHeaderRow}>
                            <Text style={[styles.modalTitle, { color: colors.text }]}>Edit Profile</Text>
                            <TouchableOpacity onPress={() => setEditModalVisible(false)}>
                                <Text style={styles.closeBtn}>✕</Text>
                            </TouchableOpacity>
                        </View>

                        <ScrollView>
                            {/* AVATAR SELECTOR */}
                            <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>Choose Avatar</Text>
                            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.avatarScroll}>
                                {avatarPresets.map((url, index) => (
                                    <TouchableOpacity
                                        key={index}
                                        onPress={() => setSelectedAvatar(url)}
                                        style={[
                                            styles.avatarOption,
                                            selectedAvatar === url && styles.avatarOptionSelected
                                        ]}
                                    >
                                        <Image source={{ uri: url }} style={styles.avatarOptionImage} />
                                    </TouchableOpacity>
                                ))}
                            </ScrollView>

                            <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>Full Name</Text>
                            <TextInput
                                style={[styles.input, { backgroundColor: isDarkMode ? '#2C2C2E' : '#F3F4F6', color: colors.text }]}
                                value={editName}
                                onChangeText={setEditName}
                                placeholder="Enter your name"
                                placeholderTextColor="#9CA3AF"
                            />

                            <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>Location</Text>
                            <TextInput
                                style={[styles.input, { backgroundColor: isDarkMode ? '#2C2C2E' : '#F3F4F6', color: colors.text }]}
                                value={editLocation}
                                onChangeText={setEditLocation}
                                placeholder="e.g. New York, USA"
                                placeholderTextColor="#9CA3AF"
                            />

                            <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>Bio</Text>
                            <TextInput
                                style={[styles.input, { backgroundColor: isDarkMode ? '#2C2C2E' : '#F3F4F6', color: colors.text, height: 80, textAlignVertical: 'top' }]}
                                value={editBio}
                                onChangeText={setEditBio}
                                placeholder="Tell us about yourself..."
                                placeholderTextColor="#9CA3AF"
                                multiline
                            />

                            <TouchableOpacity
                                style={[styles.saveBtn, { backgroundColor: brand.BLUE, opacity: isSaving ? 0.7 : 1 }]}
                                onPress={saveProfile}
                                disabled={isSaving}
                            >
                                <Text style={styles.saveBtnText}>{isSaving ? 'Saving...' : 'Save Changes'}</Text>
                            </TouchableOpacity>
                        </ScrollView>
                    </View>
                </BlurView>
            </Modal>
        </SafeAreaView>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#FAFAF8' },
    scroll: { paddingBottom: 40 },
    profileHeader: { alignItems: 'center', paddingTop: 60, paddingBottom: 40, paddingHorizontal: 20, overflow: 'hidden' },
    avatarContainer: { width: 100, height: 100, borderRadius: 50, backgroundColor: 'rgba(255,255,255,0.15)', justifyContent: 'center', alignItems: 'center', marginBottom: 12, borderWidth: 2, borderColor: '#FFF', shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 15, elevation: 10, overflow: 'visible' },
    avatarImage: { width: 96, height: 96, borderRadius: 48 },
    avatarText: { fontSize: 36, color: '#FFF', fontWeight: '900' },
    editBadge: { position: 'absolute', bottom: 0, right: 0, backgroundColor: '#FFF', borderRadius: 12, width: 24, height: 24, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: '#DDD' },
    userName: { fontSize: 26, fontWeight: '800', color: '#FFF', marginBottom: 2, letterSpacing: -0.5, textShadowColor: 'rgba(0,0,0,0.3)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 4 },
    userEmail: { fontSize: 14, color: 'rgba(255,255,255,0.8)', marginBottom: 8 },
    locationContainer: { backgroundColor: 'rgba(0,0,0,0.3)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, marginBottom: 15 },
    locationText: { color: '#FFF', fontSize: 12, fontWeight: '600' },
    bioContainer: { backgroundColor: 'rgba(255,255,255,0.15)', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12, marginBottom: 12, marginTop: 8, maxWidth: '90%' },
    bioText: { color: 'rgba(255,255,255,0.95)', fontSize: 13, lineHeight: 18, textAlign: 'center', fontStyle: 'italic' },
    planBadge: { backgroundColor: 'rgba(255,255,255,0.25)', paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20, marginBottom: 5, borderWidth: 0.5, borderColor: 'rgba(255,255,255,0.4)', marginTop: 5 },
    planText: { fontSize: 12, fontWeight: '600', color: '#FFF' },
    daysLeftContainer: {
        backgroundColor: 'rgba(255, 215, 0, 0.2)', // Gold tint
        paddingHorizontal: 12,
        paddingVertical: 4,
        borderRadius: 12,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: 'rgba(255, 215, 0, 0.5)',
    },
    daysLeftText: {
        color: '#FCD34D', // Gold text
        fontWeight: '700',
        fontSize: 12,
        letterSpacing: 0.5,
    },
    upgradeBtn: { overflow: 'hidden', borderRadius: 25, shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 10 },
    upgradeGradient: { paddingHorizontal: 40, paddingVertical: 12, alignItems: 'center', justifyContent: 'center' },
    upgradeText: { color: '#FFF', fontWeight: '700', fontSize: 15 },
    sectionHeader: { paddingHorizontal: 20, marginTop: 25, marginBottom: 12 },
    sectionTitle: { fontSize: 11, fontWeight: '900', letterSpacing: 2 },
    group: { borderWidth: 1, borderColor: 'rgba(0,0,0,0.03)', marginHorizontal: 15, marginBottom: 10, borderRadius: 20, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.02, shadowRadius: 10 },
    settingRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, paddingLeft: 20, paddingRight: 20, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' },
    settingLabel: { fontSize: 16, fontWeight: '600' },
    statusText: { fontSize: 12, marginTop: 4 },
    settingValue: { fontSize: 14 },
    signOutBtn: { marginHorizontal: 20, marginTop: 15, marginBottom: 20, backgroundColor: '#FEF2F2', padding: 15, borderRadius: 12, alignItems: 'center', borderWidth: 1, borderColor: '#FECACA' },
    signOutText: { color: '#EF4444', fontWeight: '700', fontSize: 16 },
    version: { textAlign: 'center', color: '#D1D5DB', fontSize: 12 },
    blurContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    centeredView: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    modalView: { backgroundColor: '#FFF', borderRadius: 20, padding: 25, width: '90%', maxWidth: 400, shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 4, elevation: 5 },

    // Edit Modal Styles
    editModalView: { width: '90%', maxWidth: 400, borderRadius: 24, padding: 24, maxHeight: '80%', shadowColor: '#000', shadowOpacity: 0.3, shadowRadius: 10 },
    modalHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
    modalTitle: { fontSize: 20, fontWeight: '800' },
    closeBtn: { fontSize: 24, color: '#9CA3AF' },
    inputLabel: { fontSize: 13, fontWeight: '700', marginBottom: 8, marginTop: 15, textTransform: 'uppercase' },
    input: { padding: 15, borderRadius: 12, fontSize: 16, marginBottom: 5 },
    saveBtn: { padding: 16, borderRadius: 14, alignItems: 'center', marginTop: 30, marginBottom: 10 },
    saveBtnText: { color: '#FFF', fontWeight: '800', fontSize: 16 },
    avatarScroll: { marginVertical: 10, paddingVertical: 10 },
    avatarOption: { width: 70, height: 70, borderRadius: 35, marginRight: 15, borderWidth: 3, borderColor: 'transparent', padding: 2 },
    avatarOptionSelected: { borderColor: '#4F46E5', transform: [{ scale: 1.1 }] },
    avatarOptionImage: { width: '100%', height: '100%', borderRadius: 35 },

    modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 },
    successContainer: { alignItems: 'center', marginBottom: 25 },
    successEmoji: { fontSize: 48, marginBottom: 10 },
});

export default ProfileScreen;
