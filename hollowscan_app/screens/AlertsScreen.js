import React, { useState, useEffect, useContext } from 'react';
import { StyleSheet, View, Text, Switch, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Constants from '../Constants';
import { UserContext } from '../context/UserContext';

const AlertsScreen = () => {
    const { isDarkMode } = useContext(UserContext);
    const brand = Constants.BRAND;
    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        card: '#161618',
        text: '#FFFFFF',
        textSecondary: '#8E8E93',
        border: 'rgba(255,255,255,0.08)',
        accent: brand.BLUE
    } : {
        bg: '#F8F9FE',
        card: '#FFFFFF',
        text: '#1C1C1E',
        textSecondary: '#636366',
        border: 'rgba(0,0,0,0.05)',
        accent: brand.BLUE
    };

    // State
    const [categories, setCategories] = useState({ 'USA Stores': [], 'UK Stores': [], 'Canada Stores': [] });
    const [loading, setLoading] = useState(true);
    const [activeRegion, setActiveRegion] = useState('USA Stores');

    // Preferences State
    const [selectedSubs, setSelectedSubs] = useState({});

    useEffect(() => {
        fetchSubcategories();
    }, []);

    const fetchSubcategories = async () => {
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/categories`);
            const data = await response.json();
            const cats = data.categories || {};
            setCategories(cats);

            // Initialize all subs as enabled (MOCK: usually would fetch user's real prefs)
            const initialSubs = {};
            Object.keys(cats).forEach(country => {
                cats[country].forEach(sub => {
                    if (sub !== 'ALL') initialSubs[sub] = true;
                });
            });
            setSelectedSubs(initialSubs);
        } catch (e) {
            console.log(e);
        } finally {
            setLoading(false);
        }
    };

    const toggleSub = (sub) => {
        setSelectedSubs(prev => ({ ...prev, [sub]: !prev[sub] }));
    };

    const toggleAllInRegion = (region, value) => {
        const newSubs = { ...selectedSubs };
        categories[region]?.forEach(sub => {
            if (sub !== 'ALL') newSubs[sub] = value;
        });
        setSelectedSubs(newSubs);
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

    const StoreCard = ({ name }) => (
        <TouchableOpacity
            style={[styles.storeCard, { backgroundColor: colors.card, borderColor: colors.border }]}
            onPress={() => toggleSub(name)}
            activeOpacity={0.7}
        >
            <View style={styles.storeLogoContainer}>
                <Text style={styles.storeEmoji}>{getStoreEmoji(name)}</Text>
            </View>
            <View style={styles.storeInfo}>
                <Text style={[styles.storeName, { color: colors.text }]}>{name}</Text>
                <View style={styles.statusRow}>
                    <View style={[styles.statusDot, { backgroundColor: selectedSubs[name] ? '#10B981' : '#FF3B30' }]} />
                    <Text style={[styles.statusText, { color: colors.textSecondary }]}>
                        {selectedSubs[name] ? 'Alerts Active' : 'Paused'}
                    </Text>
                </View>
            </View>
            <Switch
                trackColor={{ false: '#767577', true: brand.BLUE }}
                thumbColor={'#FFF'}
                onValueChange={() => toggleSub(name)}
                value={selectedSubs[name] || false}
            />
        </TouchableOpacity>
    );

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]} edges={['top']}>
            <View style={[styles.header, { borderBottomColor: colors.border, backgroundColor: colors.card }]}>
                <Text style={[styles.headerTitle, { color: colors.text }]}>Dashboard</Text>
                <TouchableOpacity style={styles.saveBtn}>
                    <Text style={{ color: brand.BLUE, fontWeight: '700', fontSize: 16 }}>Save Changes</Text>
                </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                {/* REGION TABS */}
                <View style={[styles.tabsContainer, { backgroundColor: isDarkMode ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' }]}>
                    {['USA Stores', 'UK Stores', 'Canada Stores'].map(region => (
                        <TouchableOpacity
                            key={region}
                            style={[
                                styles.tab,
                                activeRegion === region && { backgroundColor: brand.BLUE, borderColor: brand.BLUE }
                            ]}
                            onPress={() => setActiveRegion(region)}
                        >
                            <Text style={[
                                styles.tabText,
                                activeRegion === region && { color: '#FFF' }
                            ]}>
                                {region === 'USA Stores' ? '🇺🇸 US' : region === 'UK Stores' ? '🇬🇧 UK' : '🇨🇦 CA'}
                            </Text>
                        </TouchableOpacity>
                    ))}
                </View>

                {/* BULK ACTIONS */}
                <View style={styles.bulkRow}>
                    <Text style={[styles.regionTitle, { color: colors.textSecondary }]}>
                        {activeRegion.toUpperCase()} MANAGEMENT
                    </Text>
                    <TouchableOpacity onPress={() => toggleAllInRegion(activeRegion, true)}>
                        <Text style={{ color: brand.BLUE, fontWeight: '700', fontSize: 13 }}>Enable All</Text>
                    </TouchableOpacity>
                </View>

                {/* STORE CARDS GRID */}
                {loading ? (
                    <ActivityIndicator color={brand.BLUE} style={{ marginTop: 40 }} />
                ) : (
                    <View style={styles.storeGrid}>
                        {categories[activeRegion]?.map(sub => (
                            sub !== 'ALL' && <StoreCard key={sub} name={sub} />
                        ))}
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
        borderBottomWidth: 1,
    },
    headerTitle: { fontSize: 28, fontWeight: '900', letterSpacing: -0.5 },
    saveBtn: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8 },

    scroll: { padding: 20, paddingBottom: 100 },

    tabsContainer: {
        flexDirection: 'row',
        backgroundColor: 'rgba(0,0,0,0.05)',
        borderRadius: 14,
        padding: 5,
        marginBottom: 25
    },
    tab: {
        flex: 1,
        paddingVertical: 10,
        alignItems: 'center',
        borderRadius: 10,
        borderWidth: 1,
        borderColor: 'transparent'
    },
    tabText: { fontSize: 14, fontWeight: '700', color: '#9CA3AF' },

    bulkRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 15,
        paddingHorizontal: 4
    },
    regionTitle: { fontSize: 11, fontWeight: '800', letterSpacing: 1.5 },

    storeGrid: { gap: 12 },
    storeCard: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 14,
        borderRadius: 18,
        borderWidth: 1,
        shadowColor: '#000',
        shadowOpacity: 0.03,
        shadowRadius: 10,
        shadowOffset: { width: 0, height: 4 }
    },
    storeLogoContainer: {
        width: 48,
        height: 48,
        borderRadius: 14,
        backgroundColor: '#F8F9FE',
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: 15
    },
    storeEmoji: { fontSize: 24 },
    storeInfo: { flex: 1 },
    storeName: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
    statusRow: { flexDirection: 'row', alignItems: 'center' },
    statusDot: { width: 6, height: 6, borderRadius: 3, marginRight: 6 },
    statusText: { fontSize: 12, fontWeight: '600' }
});

export default AlertsScreen;
