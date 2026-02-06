import React, { useState, useEffect, useContext } from 'react';
import { StyleSheet, View, Text, Switch, ScrollView, TouchableOpacity, ActivityIndicator, Alert, Animated } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from '../Constants';
import { UserContext } from '../context/UserContext';
import { requestNotificationPermissions } from '../services/PushNotificationService';

const STORAGE_KEY_NOTIFICATIONS = '@hollowscan_notifications_enabled';
const STORAGE_KEY_SUBS = '@hollowscan_subscriptions';

const AlertsScreen = () => {
    const { isDarkMode, selectedRegion, updateRegion, syncPreferences } = useContext(UserContext);
    const brand = Constants.BRAND;

    // Theme setup
    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        card: '#161618',
        text: '#FFFFFF',
        textSecondary: '#A1A1AA',
        border: 'rgba(255,255,255,0.08)',
        accent: brand.BLUE,
        success: '#10B981',
        danger: '#EF4444'
    } : {
        bg: '#F8F9FE',
        card: '#FFFFFF',
        text: '#1F2937',
        textSecondary: '#6B7280',
        border: 'rgba(0,0,0,0.05)',
        accent: brand.BLUE,
        success: '#059669',
        danger: '#DC2626'
    };

    // State
    const [categories, setCategories] = useState({ 'USA Stores': [], 'UK Stores': [], 'Canada Stores': [] });
    const [loading, setLoading] = useState(true);
    const [notificationsEnabled, setNotificationsEnabled] = useState(false); // Master Toggle
    const [selectedSubs, setSelectedSubs] = useState({});

    useEffect(() => {
        loadPreferences();
    }, []);

    const loadPreferences = async () => {
        try {
            // Load Settings
            const enabled = await AsyncStorage.getItem(STORAGE_KEY_NOTIFICATIONS);
            const subs = await AsyncStorage.getItem(STORAGE_KEY_SUBS);

            if (enabled !== null) setNotificationsEnabled(JSON.parse(enabled));
            if (subs !== null) setSelectedSubs(JSON.parse(subs));

            await fetchSubcategories(subs ? JSON.parse(subs) : null);
        } catch (e) {
            console.error('Failed to load preferences', e);
        }
    };

    const fetchSubcategories = async (persistedSubs) => {
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/categories`);
            const data = await response.json();
            const cats = data.categories || {};
            setCategories(cats);

            // If no persisted subs, initialize default
            if (!persistedSubs) {
                const initialSubs = {};
                Object.keys(cats).forEach(country => {
                    cats[country].forEach(sub => {
                        if (sub !== 'ALL') initialSubs[sub] = true;
                    });
                });
                setSelectedSubs(initialSubs);
            }
        } catch (e) {
            console.log(e);
        } finally {
            setLoading(false);
        }
    };

    // Save preferences logic
    const [isSyncing, setIsSyncing] = useState(false);

    const savePreferences = async (enabled, subs) => {
        try {
            await AsyncStorage.setItem(STORAGE_KEY_NOTIFICATIONS, JSON.stringify(enabled));
            if (subs) await AsyncStorage.setItem(STORAGE_KEY_SUBS, JSON.stringify(subs));

            // Debounced or direct cloud sync
            syncWithCloud(enabled, subs || selectedSubs);
        } catch (e) {
            console.error('Failed to save preferences', e);
        }
    };

    const syncWithCloud = async (enabled, subs) => {
        setIsSyncing(true);
        try {
            const regionalPrefs = {};
            Object.keys(categories).forEach(region => {
                const activeInRegion = categories[region]
                    .filter(sub => subs[sub])
                    .map(sub => sub);
                if (activeInRegion.length > 0) {
                    regionalPrefs[region] = activeInRegion;
                }
            });

            await syncPreferences({
                enabled: enabled,
                regions: regionalPrefs
            });
        } catch (error) {
            console.error('[ALERTS] Sync error:', error);
        } finally {
            setIsSyncing(false);
        }
    };

    // Master Toggle Handler (Migrated from Profile)
    const handleNotificationsToggle = async (value) => {
        if (value) {
            const hasPermission = await requestNotificationPermissions();
            if (hasPermission) {
                setNotificationsEnabled(true);
                savePreferences(true, selectedSubs);
                Alert.alert('✓ Notifications Active', 'You will now receive alerts for your selected stores.');
            } else {
                Alert.alert('Permission Required', 'Please enable notifications in system settings.');
            }
        } else {
            setNotificationsEnabled(false);
            savePreferences(false, selectedSubs);
        }
    };

    const toggleSub = (sub) => {
        if (!notificationsEnabled) {
            Alert.alert('Notifications Disabled', 'Enable "Allow Notifications" at the top to subscribe to stores.');
            return;
        }
        setSelectedSubs(prev => {
            const newSubs = { ...prev, [sub]: !prev[sub] };
            savePreferences(notificationsEnabled, newSubs);
            return newSubs;
        });
    };

    const toggleAllInRegion = (region, value) => {
        if (!notificationsEnabled) return;
        const newSubs = { ...selectedSubs };
        categories[region]?.forEach(sub => {
            if (sub !== 'ALL') newSubs[sub] = value;
        });
        setSelectedSubs(newSubs);
        savePreferences(notificationsEnabled, newSubs);
    };

    const getStoreEmoji = (name) => {
        const n = name.toLowerCase();
        if (n.includes('amazon')) return '📦';
        if (n.includes('walmart')) return '🔵';
        if (n.includes('argos')) return '🔴';
        if (n.includes('pokemon')) return '⚡';
        if (n.includes('hobby')) return '🎮';
        if (n.includes('target')) return '🎯';
        if (n.includes('currys')) return '🔌';
        return '🏪';
    };

    const StoreCard = ({ name }) => {
        const isActive = selectedSubs[name] && notificationsEnabled;

        return (
            <TouchableOpacity
                style={[styles.storeCard, { backgroundColor: colors.card, borderColor: isActive ? colors.accent : colors.border, opacity: notificationsEnabled ? 1 : 0.6 }]}
                onPress={() => toggleSub(name)}
                activeOpacity={0.7}
            >
                <View style={[styles.storeIconBox, { backgroundColor: isDarkMode ? 'rgba(255,255,255,0.05)' : '#F3F4F6' }]}>
                    <Text style={{ fontSize: 22 }}>{getStoreEmoji(name)}</Text>
                </View>

                <View style={{ flex: 1, paddingHorizontal: 12 }}>
                    <Text style={[styles.storeName, { color: colors.text }]}>{name}</Text>
                    <Text style={[styles.storeStatus, { color: isActive ? colors.success : colors.textSecondary }]}>
                        {isActive ? '● Live Alerts' : '○ Paused'}
                    </Text>
                </View>

                <Switch
                    trackColor={{ false: isDarkMode ? '#333' : '#E5E7EB', true: brand.BLUE }}
                    thumbColor={'#FFF'}
                    onValueChange={() => toggleSub(name)}
                    value={selectedSubs[name] && notificationsEnabled}
                    disabled={!notificationsEnabled}
                />
            </TouchableOpacity>
        );
    };

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]} edges={['top']}>

            {/* HEADER */}
            <View style={styles.header}>
                <Text style={[styles.headerTitle, { color: colors.text }]}>Alerts & Preferences</Text>
                <TouchableOpacity style={[styles.saveBtn, { backgroundColor: brand.BLUE + '15' }]}>
                    <Text style={{ color: brand.BLUE, fontWeight: '700', fontSize: 13 }}>
                        {isSyncing ? 'Syncing...' : 'Saved ✓'}
                    </Text>
                </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>

                {/* UX NOTE / MASTER TOGGLE */}
                <View style={[styles.masterCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
                    <View style={{ flex: 1 }}>
                        <Text style={[styles.masterTitle, { color: colors.text }]}>Allow Notifications</Text>
                        <Text style={[styles.masterDesc, { color: colors.textSecondary }]}>
                            Turn this on to receive instant push notifications for deals.
                        </Text>
                    </View>
                    <Switch
                        trackColor={{ false: isDarkMode ? '#333' : '#E5E7EB', true: brand.BLUE }}
                        thumbColor={'#FFF'}
                        onValueChange={handleNotificationsToggle}
                        value={notificationsEnabled}
                        style={{ transform: [{ scale: 1.1 }] }}
                    />
                </View>

                {/* INFO BANNER */}
                <View style={[styles.infoBanner, { backgroundColor: brand.BLUE + '08', borderColor: brand.BLUE + '15' }]}>
                    <Text style={{ fontSize: 14, marginRight: 8 }}>💡</Text>
                    <Text style={[styles.infoText, { color: colors.text }]}>
                        Select the stores you want to watch. We'll only notify you when high-value items drop.
                    </Text>
                </View>

                {/* REGION TABS */}
                <View style={[styles.tabsContainer, { backgroundColor: isDarkMode ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)' }]}>
                    {['USA Stores', 'UK Stores', 'Canada Stores'].map(region => {
                        const isTabActive = selectedRegion === region;
                        return (
                            <TouchableOpacity
                                key={region}
                                style={[
                                    styles.tab,
                                    isTabActive && { backgroundColor: brand.BLUE, shadowColor: brand.BLUE, shadowOpacity: 0.3 }
                                ]}
                                onPress={() => updateRegion(region)}
                            >
                                <Text style={[styles.tabText, { color: isTabActive ? '#FFF' : colors.textSecondary }]}>
                                    {region.split(' ')[0]} {/* USA / UK / Canada (shortened) */}
                                </Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>

                {/* BULK ACTIONS ROW */}
                <View style={styles.bulkRow}>
                    <Text style={[styles.sectionHeader, { color: colors.textSecondary }]}>
                        {selectedRegion.toUpperCase()}
                    </Text>
                    <View style={{ flexDirection: 'row', gap: 15 }}>
                        <TouchableOpacity onPress={() => toggleAllInRegion(selectedRegion, false)} disabled={!notificationsEnabled}>
                            <Text style={{ color: notificationsEnabled ? colors.textSecondary : '#9CA3AF', fontWeight: '600', fontSize: 13 }}>
                                Disable All
                            </Text>
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => toggleAllInRegion(selectedRegion, true)} disabled={!notificationsEnabled}>
                            <Text style={{ color: notificationsEnabled ? brand.BLUE : colors.textSecondary, fontWeight: '700', fontSize: 13 }}>
                                Enable All
                            </Text>
                        </TouchableOpacity>
                    </View>
                </View>

                {/* STORE LIST */}
                {loading ? (
                    <ActivityIndicator color={brand.BLUE} style={{ marginTop: 40 }} />
                ) : (
                    <View style={styles.grid}>
                        {categories[selectedRegion]?.map(sub => (
                            sub !== 'ALL' && <StoreCard key={sub} name={sub} />
                        ))}
                        <View style={{ height: 100 }} />
                    </View>
                )}

            </ScrollView>
        </SafeAreaView>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1 },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingVertical: 15,
    },
    headerTitle: { fontSize: 24, fontWeight: '800', letterSpacing: -0.5 },
    saveBtn: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 20 },

    scroll: { padding: 20 },

    // Master Switch Card
    masterCard: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 20,
        borderRadius: 24,
        borderWidth: 1,
        marginBottom: 16,
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.05,
        shadowRadius: 10,
        elevation: 2
    },
    masterTitle: { fontSize: 17, fontWeight: '700', marginBottom: 4 },
    masterDesc: { fontSize: 13, lineHeight: 18, paddingRight: 10 },

    // Info Banner
    infoBanner: {
        flexDirection: 'row',
        padding: 14,
        borderRadius: 16,
        borderWidth: 1,
        marginBottom: 24,
        alignItems: 'flex-start'
    },
    infoText: { fontSize: 13, lineHeight: 20, flex: 1 },

    // Tabs
    tabsContainer: {
        flexDirection: 'row',
        padding: 4,
        borderRadius: 16,
        marginBottom: 20
    },
    tab: {
        flex: 1,
        paddingVertical: 10,
        alignItems: 'center',
        borderRadius: 12,
    },
    tabText: { fontSize: 14, fontWeight: '700' },

    // Grid
    grid: { gap: 12 },
    bulkRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, paddingHorizontal: 4 },
    sectionHeader: { fontSize: 12, fontWeight: '800', letterSpacing: 1 },

    // Store Card
    storeCard: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 16,
        borderRadius: 20,
        borderWidth: 1,
        // Cozy shadow
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.03,
        shadowRadius: 6,
    },
    storeIconBox: { width: 44, height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
    storeName: { fontSize: 16, fontWeight: '700', marginBottom: 2 },
    storeStatus: { fontSize: 12, fontWeight: '600' }
});

export default AlertsScreen;
