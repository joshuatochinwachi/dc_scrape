import React, { useState, useEffect, useCallback, useContext, useRef } from 'react';
import {
    StyleSheet,
    View,
    Text,
    FlatList,
    ScrollView,
    TouchableOpacity,
    Image,
    Dimensions,
    StatusBar,
    Modal,
    ActivityIndicator,
    TextInput,
    Linking,
    Animated,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import Constants from '../Constants';
import { SavedContext } from '../context/SavedContext';
import { UserContext } from '../context/UserContext';
import LiveProductService from '../services/LiveProductService';
import { setupNotificationHandler, sendDealNotification } from '../services/PushNotificationService';

const { width } = Dimensions.get('window');

const getRelativeTime = (dateString) => {
    if (!dateString) return 'Just now';
    const date = new Date(dateString);
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);

    if (diffInSeconds < 60) return 'Just now';
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
    if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}d ago`;
    return date.toLocaleDateString();
};

const HomeScreen = () => {
    const navigation = useNavigation();
    const { isDarkMode } = useContext(UserContext);

    // CONFIG
    const LIMIT = 10;
    const USER_ID = '8923304e-657e-4e7e-800a-94e7248ecf7f';

    // REGIONS - Compact Format
    const regions = [
        { id: 'USA Stores', label: 'US', flag: '🇺🇸' },
        { id: 'UK Stores', label: 'UK', flag: '🇬🇧' },
        { id: 'Canada Stores', label: 'CA', flag: '🇨🇦' }
    ];

    // STATE
    const [selectedRegion, setSelectedRegion] = useState('USA Stores');
    const [selectedCategories, setSelectedCategories] = useState(['ALL']); // Main category selection
    const [searchQuery, setSearchQuery] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [isFilterVisible, setFilterVisible] = useState(false);

    const [dynamicCategories, setDynamicCategories] = useState({});
    const [alerts, setAlerts] = useState([]);
    const [quota, setQuota] = useState({ used: 0, limit: 4 });

    const [isLoading, setIsLoading] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(true);
    const [isPremium, setIsPremium] = useState(false);
    const [totalAvailable, setTotalAvailable] = useState(0);

    // BRAND
    const brand = Constants.BRAND;
    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        card: '#161618',
        text: '#FFFFFF',
        textSecondary: '#8E8E93',
        accent: brand.BLUE,
        border: 'rgba(255,255,255,0.08)',
        input: '#1C1C1E',
        badgeBg: 'rgba(79, 70, 229, 0.15)', // brand.BLUE with opacity
        tabActiveBg: brand.BLUE,
        tabInactiveBg: '#1C1C1E'
    } : {
        bg: '#F2F4F8',
        card: '#FFFFFF',
        text: '#1C1C1E',
        textSecondary: '#636366',
        accent: brand.BLUE,
        border: 'rgba(0,0,0,0.06)',
        input: '#FFFFFF',
        badgeBg: '#F0F0FF', // brand.BLUE light tint
        tabActiveBg: brand.BLUE,
        tabInactiveBg: '#FFFFFF'
    };

    // INITIAL FETCH
    useEffect(() => {
        fetchInitialData();
    }, [selectedRegion, selectedCategories]);

    // HANDLERS
    const handleSearch = async (query = searchQuery) => {
        if (!query || !query.trim()) return;
        setIsSearching(true);
        await fetchAlerts(0, true, query);
        setIsSearching(false);
    };

    const clearSearch = () => {
        setSearchQuery('');
        fetchAlerts(0, true, '');
    };

    // SETUP NOTIFICATIONS & LIVE UPDATES
    useEffect(() => {
        setupNotificationHandler();
        LiveProductService.resetLastProductTime();
        LiveProductService.startPolling({
            userId: USER_ID,
            country: selectedRegion,
            category: selectedCategories.includes('ALL') ? 'ALL' : selectedCategories[0],
            onlyNew: true,
            search: searchQuery,
        });

        const unsubscribe = LiveProductService.subscribe((newProducts) => {
            setAlerts(prev => {
                const existingIds = new Set(prev.map(a => a.id));
                const uniqueNew = newProducts.filter(p => !existingIds.has(p.id));
                const combined = [...uniqueNew, ...prev];
                if (!isPremium) {
                    return combined.slice(0, 4);
                }
                return combined;
            });
            newProducts.forEach(product => {
                sendDealNotification(product);
            });
        });

        return () => {
            unsubscribe();
            LiveProductService.stopPolling();
        };
    }, [selectedRegion, selectedCategories, searchQuery]);

    const fetchInitialData = async () => {
        setIsLoading(true);
        setOffset(0);
        setHasMore(true);

        await Promise.all([
            fetchCategories(),
            fetchUserStatus(),
            fetchAlerts(0, true)
        ]);

        setIsLoading(false);
    };

    const fetchCategories = async () => {
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/categories`);
            const data = await response.json();
            setDynamicCategories(data.categories || {});
        } catch (e) {
            setDynamicCategories({ 'USA Stores': [], 'UK Stores': [], 'Canada Stores': [] });
        }
    };

    const fetchUserStatus = async () => {
        try {
            const response = await fetch(`${Constants.API_BASE_URL}/v1/user/status?user_id=${USER_ID}`);
            const data = await response.json();
            setQuota({ used: data.views_used, limit: data.views_limit });
            if (data.is_premium !== undefined) setIsPremium(data.is_premium);
        } catch (e) { }
    };

    const fetchAlerts = async (currentOffset, reset = false, overrideSearch = null) => {
        try {
            const activeSearch = overrideSearch !== null ? overrideSearch : searchQuery;
            const catParam = selectedCategories.includes('ALL') ? 'ALL' : selectedCategories[0] || 'ALL';
            let url = `${Constants.API_BASE_URL}/v1/feed?user_id=${USER_ID}&region=${encodeURIComponent(selectedRegion)}&category=${encodeURIComponent(catParam)}&offset=${currentOffset}&limit=${LIMIT}`;

            if (activeSearch && activeSearch.trim()) {
                url += `&search=${encodeURIComponent(activeSearch.trim())}`;
            }

            const response = await fetch(url);
            if (!response.ok) throw new Error('Fetch failed');

            const result = await response.json();
            const data = Array.isArray(result) ? result : (result.products || []);
            const nextOffset = result.next_offset !== undefined ? result.next_offset : (currentOffset + LIMIT);

            if (result.is_premium !== undefined) setIsPremium(result.is_premium);
            if (result.total_count !== undefined) setTotalAvailable(result.total_count);

            if (data.length >= 0) {
                if (reset) {
                    setAlerts(data);
                    setOffset(0);
                } else {
                    setAlerts(prev => {
                        const existingIds = new Set(prev.map(a => a.id));
                        const newItems = data.filter(item => !existingIds.has(item.id));
                        return [...prev, ...newItems];
                    });
                }
                setOffset(nextOffset);
                setHasMore(data.length === LIMIT || (result.has_more !== undefined ? result.has_more : data.length > 0));
            } else {
                setHasMore(false);
            }
        } catch (e) {
            setHasMore(false);
        }
    };

    const handleLoadMore = () => {
        if (!hasMore || isLoadingMore || isLoading || alerts.length === 0) return;
        if (!isPremium && alerts.length >= 4) return;

        setIsLoadingMore(true);
        fetchAlerts(offset, false, searchQuery).then(() => {
            setIsLoadingMore(false);
        }).catch(() => setIsLoadingMore(false));
    };

    const onRefresh = async () => {
        setIsRefreshing(true);
        await fetchInitialData();
        setIsRefreshing(false);
    };

    // --- HELPERS ---
    const formatPriceDisplay = (value, region) => {
        if (!value || isNaN(value) || value === 0) {
            if (region === 'UK Stores') return '£0.00';
            if (region === 'Canada Stores') return 'CAD 0.00';
            return '$0.00';
        }

        const num = parseFloat(value);

        // Custom formatting for CAD to meet user requirement "CAD 74.00"
        if (region === 'Canada Stores') {
            const usd = (num * 0.73).toFixed(0);
            return `CAD ${num.toFixed(2)} (USD ${usd})`;
        }

        const formatted = new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: region === 'UK Stores' ? 'GBP' : 'USD',
            minimumFractionDigits: 2
        }).format(num);

        // Add USD equivalent for UK
        if (region === 'UK Stores') {
            const usd = (num * 1.25).toFixed(0);
            return `${formatted} (USD ${usd})`;
        }

        return formatted;
    };

    const currentSubcategories = Array.from(new Set(['ALL', ...(dynamicCategories[selectedRegion] || [])]));
    const { toggleSave, isSaved } = useContext(SavedContext);

    // --- ANIMATED PRODUCT CARD COMPONENT ---
    const ProductCard = ({ item }) => {
        if (!item) return null;
        const data = item.product_data || {};
        const catName = (item.category_name || "PROMO").toUpperCase();
        const resaleValRaw = String(data.resell || '0').replace(/[^0-9.]/g, '');
        const priceValRaw = String(data.price || '0').replace(/[^0-9.]/g, '');

        const resaleVal = parseFloat(resaleValRaw);
        const priceVal = parseFloat(priceValRaw);

        // Filter out items with 0 price (if not already filtered by API)
        if (priceVal === 0 && (!resaleVal || resaleVal === 0)) return null;

        const hasResell = !isNaN(resaleVal) && resaleVal > 0;
        const saved = isSaved(item.id);

        // Calculate ROI percentage
        const roiPercent = hasResell && priceVal > 0
            ? Math.round(((resaleVal - priceVal) / priceVal) * 100)
            : 0;

        // ANIMATION
        const scale = useRef(new Animated.Value(1)).current;
        const handlePressIn = () => {
            Animated.spring(scale, {
                toValue: 0.97,
                useNativeDriver: true,
                speed: 50,
                bounciness: 0
            }).start();
        };
        const handlePressOut = () => {
            Animated.spring(scale, {
                toValue: 1,
                useNativeDriver: true,
                speed: 40,
                bounciness: 10
            }).start();
        };

        const displayPrice = formatPriceDisplay(priceVal, item.region);
        const displayResale = hasResell ? formatPriceDisplay(resaleVal, item.region) : null;

        return (
            <Animated.View style={{ transform: [{ scale }] }}>
                <TouchableOpacity
                    style={[styles.card, { borderColor: colors.border, backgroundColor: colors.card }]}
                    onPress={() => navigation.navigate('ProductDetail', { product: item })}
                    onPressIn={handlePressIn}
                    onPressOut={handlePressOut}
                    activeOpacity={0.95}
                >
                    {/* IMAGE SECTION */}
                    <View style={styles.cardImageContainer}>
                        <Image
                            source={{ uri: data.image || 'https://via.placeholder.com/400' }}
                            style={styles.cardImage}
                        />
                        {/* HEART BUTTON */}
                        <TouchableOpacity
                            onPress={(e) => { e.stopPropagation(); toggleSave(item); }}
                            style={styles.heartButton}
                        >
                            <Text style={{ fontSize: 18 }}>{saved ? '❤️' : '🤍'}</Text>
                        </TouchableOpacity>
                    </View>

                    {/* CONTENT SECTION */}
                    <View style={styles.cardContent}>
                        {/* TITLE */}
                        <Text style={[styles.cardTitle, { color: colors.text }]} numberOfLines={2} ellipsizeMode="tail">
                            {data.title || 'Hollowscan Product'}
                        </Text>

                        {/* PRICE ROW */}
                        <View style={styles.priceRow}>
                            <View style={styles.priceLeft}>
                                {hasResell && (
                                    <Text style={[styles.retailPrice, { color: colors.textSecondary }]}>
                                        {displayPrice}
                                    </Text>
                                )}
                                <Text style={[styles.resalePrice, { color: '#10B981' }]}>
                                    {hasResell ? displayResale : displayPrice}
                                </Text>
                            </View>
                            {roiPercent > 0 && (
                                <View style={styles.roiBadge}>
                                    <Text style={styles.roiBadgeText}>+{roiPercent}%</Text>
                                </View>
                            )}
                        </View>

                        {/* TAGS ROW */}
                        <View style={styles.tagsRow}>
                            <View style={[styles.tag, { backgroundColor: colors.border }]}>
                                <Text style={[styles.tagText, { color: colors.textSecondary }]}>
                                    {item.region === 'USA Stores' ? '🇺🇸 US' : item.region === 'UK Stores' ? '🇬🇧 UK' : '🇨🇦 CA'}
                                </Text>
                            </View>
                            <View style={[styles.tag, { backgroundColor: colors.border }]}>
                                <Text style={[styles.tagText, { color: colors.textSecondary }]}>{catName}</Text>
                            </View>
                            <View style={[styles.tag, { backgroundColor: colors.border }]}>
                                <Text style={[styles.tagText, { color: colors.textSecondary }]}>{getRelativeTime(item.created_at)}</Text>
                            </View>
                        </View>
                    </View>

                    {/* LOCK OVERLAY */}
                    {item.is_locked && (
                        <BlurView intensity={80} tint={isDarkMode ? 'dark' : 'light'} style={styles.lockOverlay}>
                            <View style={styles.lockCenter}>
                                <Text style={{ fontSize: 24 }}>🔒</Text>
                                <Text style={[styles.lockText, { color: colors.text }]}>Premium</Text>
                            </View>
                        </BlurView>
                    )}
                </TouchableOpacity>
            </Animated.View>
        );
    };

    const renderProductCard = ({ item }) => <ProductCard item={item} />;

    // --- STICKY HEADER ---
    const StickyHeader = () => (
        <View style={[styles.stickyContainer, { backgroundColor: colors.bg }]}>
            {/* TOP ROW: SEARCH + LOGO + QUOTA */}
            <View style={styles.topRow}>
                <View style={styles.logoRow}>
                    <Image source={require('../assets/top-left-logo.png')} style={{ width: 28, height: 28, borderRadius: 8 }} />
                </View>

                <View style={[styles.searchBar, { backgroundColor: colors.input, borderColor: colors.border }]}>
                    <Text style={{ fontSize: 14, marginRight: 8 }}>🔍</Text>
                    <TextInput
                        placeholder="Search products..."
                        placeholderTextColor={colors.textSecondary}
                        style={[styles.searchInput, { color: colors.text }]}
                        value={searchQuery}
                        onChangeText={setSearchQuery}
                        onSubmitEditing={() => handleSearch()}
                        returnKeyType="search"
                    />
                    {searchQuery ? (
                        <TouchableOpacity onPress={clearSearch}>
                            <Text style={{ color: colors.textSecondary, fontSize: 16 }}>✕</Text>
                        </TouchableOpacity>
                    ) : null}
                </View>

                <LinearGradient
                    colors={[brand.PURPLE + '20', brand.BLUE + '10']}
                    style={styles.quotaPill}
                >
                    <Text style={[styles.quotaText, { color: brand.PURPLE }]}>{quota.limit - quota.used}</Text>
                    <Text style={{ fontSize: 10 }}>⚡</Text>
                </LinearGradient>
            </View>

            {/* ROW 2: CONTROLS (Common line for Regions and Categories) */}
            <View style={styles.controlsRow}>
                {/* COMPACT REGION SELECTOR */}
                <View style={styles.regionTabs}>
                    {regions.map(r => {
                        const isActive = selectedRegion === r.id;
                        return (
                            <TouchableOpacity
                                key={r.id}
                                onPress={() => setSelectedRegion(r.id)}
                                style={[
                                    styles.regionTab,
                                    isActive && { backgroundColor: isDarkMode ? '#333' : '#FFF', borderColor: brand.BLUE, borderWidth: 1 }
                                ]}
                            >
                                <Text style={{ fontSize: 16 }}>{r.flag}</Text>
                                <Text style={[
                                    styles.regionTabText,
                                    { color: isActive ? colors.text : colors.textSecondary, fontWeight: isActive ? '900' : '600' }
                                ]}>
                                    {r.label}
                                </Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>

                <View style={[styles.verticalDivider, { backgroundColor: colors.border }]} />

                <TouchableOpacity
                    onPress={() => setFilterVisible(true)}
                    activeOpacity={0.7}
                    style={[styles.filterBtn, { backgroundColor: colors.card, borderColor: colors.border }]}
                >
                    <Text style={{ fontSize: 16, marginRight: 6 }}>⚡</Text>
                    <Text style={[styles.filterBtnText, { color: colors.text }]}>
                        {selectedCategories.includes('ALL')
                            ? 'All Categories'
                            : `${selectedCategories.length} Selected`}
                    </Text>
                    <Text style={{ fontSize: 12, marginLeft: 6, color: brand.BLUE }}>▼</Text>
                </TouchableOpacity>
            </View>
        </View>
    );

    return (
        <SafeAreaView edges={['top']} style={[styles.container, { backgroundColor: colors.bg }]}>
            <StatusBar barStyle={isDarkMode ? 'light-content' : 'dark-content'} backgroundColor={colors.bg} />

            {/* STICKY HEADER AT TOP */}
            <StickyHeader />

            <FlatList
                data={alerts}
                keyExtractor={item => String(item.id)}
                renderItem={renderProductCard}
                contentContainerStyle={[styles.feedScroll, { paddingTop: 10 }]} // Add top padding for spacing from header
                showsVerticalScrollIndicator={false}
                onRefresh={onRefresh}
                refreshing={isRefreshing}
                onEndReached={handleLoadMore}
                onEndReachedThreshold={0.5}
                ListFooterComponent={() => {
                    if (isLoadingMore) return <ActivityIndicator color={brand.BLUE} style={{ marginVertical: 20 }} />;
                    if (!isPremium && alerts.length >= 4) {
                        // Compact Paywall for Horizontal Layout
                        return (
                            <View style={[styles.paywallCompact, { backgroundColor: colors.card, borderColor: colors.border }]}>
                                <Text style={[styles.paywallText, { color: colors.text }]}>
                                    🔒 <Text style={{ fontWeight: 'bold' }}>Unlock all {totalAvailable}+ deals</Text>
                                </Text>
                                <TouchableOpacity style={{ backgroundColor: brand.BLUE, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }}>
                                    <Text style={{ color: '#FFF', fontWeight: 'bold', fontSize: 12 }}>UPGRADE</Text>
                                </TouchableOpacity>
                            </View>
                        );
                    }
                    return <View style={{ height: 40 }} />;
                }}
                ListEmptyComponent={!isLoading ? (
                    <View style={styles.emptyContainer}>
                        <Text style={{ color: colors.textSecondary, fontSize: 14, textAlign: 'center' }}>
                            {searchQuery ? 'No results found.' : `No alerts in this region.`}
                        </Text>
                    </View>
                ) : null}
            />

            {isLoading && (
                <View style={styles.loadingOverlay}>
                    <ActivityIndicator size="large" color={brand.BLUE} />
                </View>
            )}

            <Modal visible={isFilterVisible} animationType="fade" transparent={true}>
                <BlurView intensity={90} tint={isDarkMode ? 'dark' : 'light'} style={styles.modalOverlay}>
                    <View style={styles.modalCenter}>
                        <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
                            <View style={styles.modalHeader}>
                                <Text style={[styles.modalTitle, { color: colors.text }]}>Filter Categories</Text>
                                <TouchableOpacity onPress={() => setFilterVisible(false)} style={styles.closeBtn}>
                                    <Text style={{ fontSize: 20, color: colors.textSecondary }}>✕</Text>
                                </TouchableOpacity>
                            </View>
                            <View style={[styles.modalDivider, { backgroundColor: colors.border }]} />
                            <ScrollView style={styles.modalScroll} showsVerticalScrollIndicator={false}>
                                <TouchableOpacity
                                    onPress={() => setSelectedCategories(['ALL'])}
                                    style={[
                                        styles.categoryOption,
                                        selectedCategories.includes('ALL') && styles.categoryOptionActive,
                                        selectedCategories.includes('ALL') && { backgroundColor: brand.PURPLE + '15' }
                                    ]}
                                >
                                    <Text style={{ fontSize: 16, marginRight: 10 }}>📁</Text>
                                    <View style={{ flex: 1 }}>
                                        <Text style={[styles.categoryOptionText, { color: colors.text }]}>All Categories</Text>
                                        <Text style={[styles.categoryOptionSub, { color: colors.textSecondary }]}>Show all available deals</Text>
                                    </View>
                                    <View style={[styles.checkbox, selectedCategories.includes('ALL') && { backgroundColor: brand.PURPLE, borderColor: brand.PURPLE }]}>
                                        {selectedCategories.includes('ALL') && <Text style={{ color: '#FFF', fontSize: 12 }}>✓</Text>}
                                    </View>
                                </TouchableOpacity>
                                {currentSubcategories.filter(s => s !== 'ALL').map((sub) => (
                                    <TouchableOpacity
                                        key={sub}
                                        onPress={() => {
                                            setSelectedCategories(prev => {
                                                if (prev.includes('ALL')) return [sub];
                                                if (prev.includes(sub)) {
                                                    const updated = prev.filter(c => c !== sub);
                                                    return updated.length === 0 ? ['ALL'] : updated;
                                                }
                                                return [...prev, sub];
                                            });
                                        }}
                                        style={[
                                            styles.categoryOption,
                                            selectedCategories.includes(sub) && styles.categoryOptionActive,
                                            selectedCategories.includes(sub) && { backgroundColor: brand.PURPLE + '15' }
                                        ]}
                                    >
                                        <Text style={{ fontSize: 16, marginRight: 10 }}>📍</Text>
                                        <View style={{ flex: 1 }}>
                                            <Text style={[styles.categoryOptionText, { color: colors.text }]}>{sub}</Text>
                                            <Text style={[styles.categoryOptionSub, { color: colors.textSecondary }]}>{selectedRegion} • Category</Text>
                                        </View>
                                        <View style={[styles.checkbox, selectedCategories.includes(sub) && { backgroundColor: brand.PURPLE, borderColor: brand.PURPLE }]}>
                                            {selectedCategories.includes(sub) && <Text style={{ color: '#FFF', fontSize: 12 }}>✓</Text>}
                                        </View>
                                    </TouchableOpacity>
                                ))}
                            </ScrollView>
                            <View style={[styles.modalFooter, { borderTopColor: colors.border }]}>
                                <TouchableOpacity onPress={() => setFilterVisible(false)} style={[styles.modalBtn, { backgroundColor: colors.tabInactiveBg, flex: 1 }]}>
                                    <Text style={[styles.modalBtnText, { color: colors.text }]}>Cancel</Text>
                                </TouchableOpacity>
                                <TouchableOpacity onPress={() => setFilterVisible(false)} style={[styles.modalBtn, { backgroundColor: brand.BLUE, flex: 1, marginLeft: 12 }]}>
                                    <Text style={[styles.modalBtnText, { color: '#FFF', fontWeight: '900' }]}>Apply Filters</Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                    </View>
                </BlurView>
            </Modal>
        </SafeAreaView>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1 },

    // STICKY HEADER
    stickyContainer: {
        width: '100%',
        paddingTop: 10,
        paddingBottom: 4,
        zIndex: 100,
        elevation: 4,
        // Bottom border for separation
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(0,0,0,0.05)'
    },
    topRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        marginBottom: 12,
        gap: 12
    },
    logoRow: {
        justifyContent: 'center',
        alignItems: 'center'
    },
    searchBar: {
        flex: 1,
        height: 40,
        borderRadius: 20,
        borderWidth: 1,
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 12
    },
    searchInput: { flex: 1, fontSize: 14, height: '100%' },
    quotaPill: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderRadius: 14,
        gap: 4
    },
    quotaText: { fontWeight: '900', fontSize: 13 },

    controlsRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingLeft: 16,
        height: 44
    },
    regionTabs: {
        flexDirection: 'row',
        gap: 4,
        alignItems: 'center'
    },
    regionTab: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 8,
        paddingVertical: 6,
        borderRadius: 8,
        gap: 4
    },
    regionTabText: { fontSize: 12 },
    verticalDivider: {
        width: 1,
        height: 24,
        marginHorizontal: 8
    },
    catPill: {
        paddingHorizontal: 14,
        paddingVertical: 6,
        borderRadius: 20,
        borderWidth: 1,
        marginRight: 8,
        justifyContent: 'center',
        alignItems: 'center'
    },
    catPillText: { fontSize: 12, fontWeight: '700' },

    // FILTER BTN
    filterBtn: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderRadius: 12,
        borderWidth: 1,
        marginRight: 16
    },
    filterBtnText: {
        fontSize: 13,
        fontWeight: '700',
        flex: 1
    },

    // MODAL STYLES (Restored)
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
        maxHeight: '70%',
        width: '100%',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.25,
        shadowRadius: 20,
        elevation: 10,
        overflow: 'hidden'
    },
    modalHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingTop: 20,
        paddingBottom: 16
    },
    modalTitle: { fontSize: 20, fontWeight: '900' },
    closeBtn: { padding: 4 },
    modalDivider: { height: 1, marginHorizontal: 0, opacity: 0.1 },
    modalScroll: { maxHeight: 400 },

    categoryOption: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingVertical: 16,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(0, 0, 0, 0.05)'
    },
    categoryOptionActive: {
        borderLeftWidth: 4,
        borderLeftColor: '#2D82FF',
        paddingLeft: 16
    },
    categoryOptionText: { fontSize: 15, fontWeight: '700', marginBottom: 2 },
    categoryOptionSub: { fontSize: 11, fontWeight: '500' },
    checkbox: {
        width: 22,
        height: 22,
        borderRadius: 6,
        borderWidth: 2,
        borderColor: '#CCC',
        justifyContent: 'center',
        alignItems: 'center',
        marginLeft: 12
    },
    modalFooter: {
        borderTopWidth: 1,
        padding: 16,
        flexDirection: 'row'
    },
    modalBtn: {
        height: 48,
        borderRadius: 12,
        justifyContent: 'center',
        alignItems: 'center'
    },
    modalBtnText: { fontWeight: '800', fontSize: 14 },

    // FEED
    feedScroll: { paddingHorizontal: 16 },

    // VERTICAL CARD (Screenshot Design)
    card: {
        borderRadius: 16,
        marginBottom: 12,
        overflow: 'hidden',
        borderWidth: 1,
        elevation: 2,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.05,
        shadowRadius: 6
    },
    cardImageContainer: {
        width: '100%',
        height: 160,
        backgroundColor: '#F7F7F7',
        position: 'relative'
    },
    cardImage: {
        width: '100%',
        height: '100%',
        resizeMode: 'contain'
    },
    heartButton: {
        position: 'absolute',
        top: 8,
        right: 8,
        width: 32,
        height: 32,
        borderRadius: 16,
        backgroundColor: 'rgba(255,255,255,0.9)',
        justifyContent: 'center',
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.1,
        shadowRadius: 2,
        elevation: 1
    },

    cardContent: {
        padding: 12
    },
    cardTitle: {
        fontSize: 14,
        fontWeight: '700',
        lineHeight: 18,
        marginBottom: 8
    },

    // PRICE ROW
    priceRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 8
    },
    priceLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6
    },
    retailPrice: {
        fontSize: 12,
        textDecorationLine: 'line-through',
        fontWeight: '500'
    },
    resalePrice: {
        fontSize: 15,
        fontWeight: '800'
    },
    roiBadge: {
        backgroundColor: '#10B981',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 6
    },
    roiBadgeText: {
        color: '#FFF',
        fontSize: 11,
        fontWeight: '800'
    },

    // TAGS ROW
    tagsRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 6
    },
    tag: {
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 4
    },
    tagText: {
        fontSize: 10,
        fontWeight: '600'
    },

    // LOCKED STATE
    lockOverlay: {
        ...StyleSheet.absoluteFillObject,
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 10
    },
    lockCenter: { alignItems: 'center' },
    lockText: { fontWeight: '900', fontSize: 14, marginTop: 8 },

    // PAYWALL FOOTER
    paywallCompact: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 16,
        borderRadius: 16,
        borderWidth: 1,
        marginBottom: 40
    },
    paywallText: { fontSize: 13 },

    emptyContainer: { alignItems: 'center', marginTop: 60, opacity: 0.6 },
    loadingOverlay: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(255,255,255,0.8)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 50
    }
});

export default HomeScreen;
