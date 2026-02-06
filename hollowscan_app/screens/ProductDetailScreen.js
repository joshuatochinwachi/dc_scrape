import React, { useContext, useState, useEffect } from 'react';
import { StyleSheet, View, Text, ScrollView, Image, TouchableOpacity, Linking, Share, Dimensions } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { SavedContext } from '../context/SavedContext';
import { UserContext } from '../context/UserContext';
import { formatPriceDisplay } from '../utils/format';
import Constants from '../Constants';

const { width } = Dimensions.get('window');

const ProductDetailScreen = ({ route, navigation }) => {
    const [product, setProduct] = React.useState(null);
    const [loading, setLoading] = React.useState(false);
    const [copiedLabel, setCopiedLabel] = useState(null);
    const { toggleSave, isSaved } = useContext(SavedContext);
    const { isDarkMode } = useContext(UserContext);
    const brand = Constants.BRAND;

    const colors = isDarkMode ? {
        bg: brand.DARK_BG,
        card: '#1C1C1E',
        subCard: '#2C2C2E',
        text: '#FAFAFA',
        textSecondary: '#A1A1AA',
        border: 'rgba(255,255,255,0.08)',
        divider: 'rgba(255,255,255,0.04)',
        noteBg: 'rgba(251, 191, 36, 0.08)',
        noteBorder: 'rgba(251, 191, 36, 0.15)',
        noteText: '#FCD34D',
        accent: brand.BLUE,
        profitCard: '#242426'
    } : {
        bg: '#F2F4F8',
        card: '#FFFFFF',
        subCard: '#F9FAFB',
        text: '#1C1C1E',
        textSecondary: '#6B7280',
        border: 'rgba(0,0,0,0.04)',
        divider: 'rgba(0,0,0,0.03)',
        noteBg: '#FFFAED',
        noteBorder: '#FCD34D',
        noteText: '#92400E',
        accent: brand.BLUE,
        profitCard: '#FFFFFF'
    };

    // Handle both direct navigation and deep link
    React.useEffect(() => {
        if (route.params?.product) {
            // Direct navigation from app
            setProduct(route.params.product);
            setLoading(false);
        } else if (route.params?.productId) {
            // Deep link navigation
            const productId = route.params.productId;
            setLoading(true);
            const fetchProduct = async () => {
                try {
                    const response = await fetch(`${Constants.API_BASE_URL}/v1/product/detail?product_id=${productId}`);
                    const data = await response.json();
                    if (data.success && data.product) {
                        setProduct(data.product);
                    } else {
                        console.error('[DEEPLINK] Product not found:', data.message);
                    }
                } catch (error) {
                    console.error('[DEEPLINK] Fetch error:', error);
                } finally {
                    setLoading(false);
                }
            };
            fetchProduct();
        }
    }, [route.params]);

    if (loading) {
        return (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg }}>
                <ActivityIndicator size="large" color={brand.BLUE} />
                <Text style={{ marginTop: 12, color: colors.textSecondary }}>Loading product...</Text>
            </View>
        );
    }

    if (!product) {
        return (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
                <Text>Loading product...</Text>
            </View>
        );
    }

    const data = product.product_data || {};
    const saved = isSaved(product.id);

    // Helper to parse price data from API (handles "Was: X Now: Y" formats)
    const parsePriceData = (productData, region) => {
        let currentPrice = 0;
        let originalPrice = 0;
        let discountPercent = 0;

        // Try to handle various discount price formats
        const rawPriceString = String(productData.price || '');

        // Pattern 1: "Was: 29.99 Now: 19.99" (robust for currency symbols/spaces)
        let match = rawPriceString.match(/Was[:\s]+[^\d\.]*([\d.]+).*?Now[:\s]+[^\d\.]*([\d.]+)/i);
        if (match) {
            originalPrice = parseFloat(match[1]);
            currentPrice = parseFloat(match[2]);
        } else {
            // Pattern 2: "Now: 19.99 Was: 29.99" (reversed)
            match = rawPriceString.match(/Now[:\s]+[^\d\.]*([\d.]+).*?Was[:\s]+[^\d\.]*([\d.]+)/i);
            if (match) {
                currentPrice = parseFloat(match[1]);
                originalPrice = parseFloat(match[2]);
            } else {
                // Pattern 3: Separate fields or plain number
                currentPrice = parseFloat(String(productData.price || '0').replace(/[^0-9.]/g, '')) || 0;
                originalPrice = parseFloat(String(productData.was_price || '0').replace(/[^0-9.]/g, '')) || 0;
            }
        }

        // FALLBACK: If price is still 0, check details array for "PRICING INFORMATION"
        if (currentPrice === 0 && productData.details && Array.isArray(productData.details)) {
            const pricingDetail = productData.details.find(d =>
                (d.label || '').toLowerCase().includes('pricing') ||
                (d.label || '').toLowerCase().includes('price')
            );

            if (pricingDetail && pricingDetail.value) {
                const detailString = String(pricingDetail.value);
                // Try Pattern 1 
                let match = detailString.match(/Was[:\s]+[^\d\.]*([\d.]+).*?Now[:\s]+[^\d\.]*([\d.]+)/i);
                if (match) {
                    originalPrice = parseFloat(match[1]);
                    currentPrice = parseFloat(match[2]);
                } else {
                    // Try Pattern 2
                    match = detailString.match(/Now[:\s]+[^\d\.]*([\d.]+).*?Was[:\s]+[^\d\.]*([\d.]+)/i);
                    if (match) {
                        currentPrice = parseFloat(match[1]);
                        originalPrice = parseFloat(match[2]);
                    }
                }
            }
        }

        const resellPrice = parseFloat(String(productData.resell || '0').replace(/[^0-9.]/g, '')) || 0;

        // Calculate discount percentage
        if (originalPrice > currentPrice && currentPrice > 0) {
            discountPercent = Math.round(((originalPrice - currentPrice) / originalPrice) * 100);
        }

        return { currentPrice, originalPrice, resellPrice, discountPercent };
    };

    // Parse price data
    const { currentPrice: buyPrice, originalPrice: wasPrice, resellPrice: sellPrice, discountPercent } = parsePriceData(data, product.region);

    // Calculate Fees & Profit

    // Default fees ~15% if not specified
    const feePercent = 15;
    const fees = (sellPrice * feePercent) / 100;
    const netProfit = sellPrice - buyPrice - fees;
    const roi = buyPrice > 0 ? ((netProfit / buyPrice) * 100).toFixed(0) : 0;

    const formattedProfit = netProfit.toFixed(2);
    const profitColor = netProfit > 0 ? '#10B981' : '#EF4444';

    const handleShare = async () => {
        try {
            // Create deep link for the product
            const deepLink = `hollowscan://product/${product.id}`;

            // Create share message with deep link
            const message = `🔥 Check out this deal from HollowScan!\n\n📦 ${data.title}\n💵 Buy: ${formatPriceDisplay(buyPrice, product.region)}\n💰 Sell: ${formatPriceDisplay(sellPrice, product.region)}\n📈 Profit: ${formatPriceDisplay(netProfit, product.region)} (ROI: ${roi}%)\n\nOpen in app: ${deepLink}`;

            await Share.share({
                message: message,
                url: deepLink,
                title: `${brand} Deal - ${data.title}`
            });
        } catch (error) {
            console.log(error);
        }
    };


    const LinkRow = ({ icon, label, url }) => (
        <TouchableOpacity
            style={styles.linkRow}
            onPress={() => url && Linking.openURL(url)}
            activeOpacity={0.7}
        >
            <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
                <Text style={{ marginRight: 10, fontSize: 16 }}>{icon}</Text>
                <Text style={[styles.linkText, { color: colors.text }]}>{label}</Text>
            </View>
            <Text style={{ color: colors.textSecondary, fontSize: 16, fontWeight: '700' }}>›</Text>
        </TouchableOpacity>
    );

    // Dynamic categorized links or default fallbacks
    const links = data.links || { buy: [], ebay: [], fba: [], other: [] };

    const ebayLink = links.ebay?.[0]?.url || `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(data.title)}&_sacat=0&LH_Sold=1&LH_Complete=1`;
    const amazonLink = links.fba?.[0]?.url || `https://www.amazon.com/s?k=${encodeURIComponent(data.title)}`;
    const googleLink = `https://www.google.com/search?q=${encodeURIComponent(data.title)}`;

    const copyToClipboard = async (text, label) => {
        if (!text) return;
        await Clipboard.setStringAsync(text);
        setCopiedLabel(label);
        setTimeout(() => setCopiedLabel(null), 2000);
    };

    const isCopyable = (label) => {
        const lowerLabel = (label || '').toLowerCase();
        return ['pid', 'sku', 'barcode', 'id', 'ean', 'upc', 'asin'].some(k => lowerLabel.includes(k));
    };

    // --- HELPERS ---

    // Helper to render price with strikethrough
    const renderPriceValue = (value) => {
        if (!value) return null;

        // Check for discount pattern: "Was: 10.50 Now: 4.50"
        const wasNowMatch = value.match(/Was:\s*([\d.]+)\s*Now:\s*([\d.]+)/i);
        if (wasNowMatch) {
            const was = parseFloat(wasNowMatch[1]);
            const now = parseFloat(wasNowMatch[2]);
            return (
                <Text>
                    <Text style={{ textDecorationLine: 'line-through', opacity: 0.6 }}>{formatPriceDisplay(was, product.region)}</Text>
                    <Text style={{ fontWeight: '900', color: '#EF4444' }}> {formatPriceDisplay(now, product.region)}</Text>
                </Text>
            );
        }

        // Generic pattern matching for other formats
        if (value.includes('~~')) {
            const parts = value.split('~~');
            return (
                <Text>
                    {parts[0]}
                    <Text style={{ textDecorationLine: 'line-through', opacity: 0.6 }}>{parts[1]}</Text>
                    {parts[2]}
                </Text>
            );
        }

        return <Text>{value}</Text>;
    };

    // Filter out redundant fields that are already in the top card or hero section
    const visibleDetails = data.details ? data.details.filter(d => {
        const label = (d.label || '').toLowerCase();
        return !d.is_redundant && !label.includes('price') && !label.includes('pricing');
    }) : [];

    return (
        <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]} edges={['top']}>
            {copiedLabel ? (
                <View style={styles.copiedToast}>
                    <Text style={styles.copiedToastText}>Copied {copiedLabel} To Clipboard!</Text>
                </View>
            ) : null}

            <View style={[styles.header, { borderBottomColor: colors.border, backgroundColor: colors.card }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={{ padding: 8 }}>
                    <Text style={{ fontSize: 24, color: colors.text }}>✕</Text>
                </TouchableOpacity>
                <Text style={[styles.headerTitle, { color: colors.text }]}>Deal Details</Text>
                <TouchableOpacity onPress={handleShare} style={{ padding: 8 }}>
                    <Text style={{ fontSize: 22 }}>📤</Text>
                </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
                {/* IMAGE HERO */}
                <View style={[styles.imageContainer, { backgroundColor: colors.card, borderColor: colors.border }]}>
                    <Image source={{ uri: data.image || data.thumbnail || 'https://via.placeholder.com/300' }} style={styles.image} resizeMode="contain" />
                    <TouchableOpacity
                        style={[styles.saveBtn, { backgroundColor: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.8)' }]}
                        onPress={() => toggleSave(product)}
                    >
                        <Text style={{ fontSize: 24, color: saved ? '#EF4444' : (isDarkMode ? '#444' : '#9CA3AF') }}>{saved ? '❤️' : '🤍'}</Text>
                    </TouchableOpacity>
                    <View style={[styles.regionBadge, { backgroundColor: brand.BLUE }]}>
                        <Text style={styles.regionText}>{product.region === 'UK Stores' ? '🇬🇧 UK Store' : product.region === 'Canada Stores' ? '🇨🇦 Canada' : '🇺🇸 USA Store'}</Text>
                    </View>
                </View>

                {/* PRODUCT TITLE */}
                <View style={styles.titleSection}>
                    <Text style={[styles.title, { color: colors.text }]}>{data.title || 'Product Name'}</Text>
                    <View style={styles.metaRow}>
                        <Text style={[styles.retailer, { color: brand.BLUE }]}>{data.retailer || 'Unknown Retailer'}</Text>
                        <View style={[styles.statusBadge, { backgroundColor: isDarkMode ? 'rgba(16, 185, 129, 0.1)' : '#F0FDF4' }]}>
                            <Text style={[styles.statusText, { color: '#10B981' }]}>✓ In Stock</Text>
                        </View>
                    </View>
                </View>

                {/* PREMIUM DISCOUNT SECTION (E-COMMERCE HERO) */}
                {wasPrice > buyPrice && buyPrice > 0 ? (
                    <View style={{ marginHorizontal: 16, marginBottom: 16 }}>
                        <LinearGradient
                            colors={['#FF6B6B', '#EE5A6F']}
                            start={{ x: 0, y: 0 }}
                            end={{ x: 1, y: 1 }}
                            style={styles.heroDiscountCard}
                        >
                            {/* Large Discount Badge */}
                            <View style={styles.heroDiscountBadge}>
                                <Text style={styles.heroDiscountPercent}>
                                    -{discountPercent}%
                                </Text>
                                <Text style={styles.heroDiscountLabel}>OFF</Text>
                            </View>

                            {/* Savings Display */}
                            {(wasPrice - buyPrice) > 0 && formatPriceDisplay(wasPrice - buyPrice, product.region) && (
                                <View style={styles.heroSavingsRow}>
                                    <Text style={styles.heroSavingsLabel}>🎉 You Save</Text>
                                    <Text style={styles.heroSavingsAmount}>
                                        {formatPriceDisplay(wasPrice - buyPrice, product.region)}
                                    </Text>
                                </View>
                            )}

                            {/* Price Comparison */}
                            <View style={styles.heroPriceRow}>
                                <View style={{ flex: 1 }}>
                                    <Text style={styles.heroNowLabel}>Now</Text>
                                    <Text style={styles.heroNowPrice}>{formatPriceDisplay(buyPrice, product.region) || 'Check Price'}</Text>
                                </View>
                                <View style={styles.heroPriceDivider} />
                                <View style={{ flex: 1, alignItems: 'flex-end' }}>
                                    <Text style={styles.heroWasLabel}>Was</Text>
                                    <Text style={styles.heroWasPrice}>{formatPriceDisplay(wasPrice, product.region) || '—'}</Text>
                                </View>
                            </View>
                        </LinearGradient>
                    </View>
                ) : null}


                {/* PROFIT ANALYSIS BOX - REVAMPED FOR SLEEK/COZY FEEL */}
                {sellPrice > 0 ? (
                    <View style={[styles.profitAnalysisCard, { backgroundColor: colors.profitCard, borderColor: colors.border }]}>
                        <View style={styles.profitAnalysisHeader}>
                            <View style={[styles.profitIconBox, { backgroundColor: brand.BLUE + '15' }]}>
                                <Text style={{ fontSize: 18 }}>📊</Text>
                            </View>
                            <View style={{ flex: 1, marginLeft: 12 }}>
                                <Text style={[styles.profitAnalysisTitle, { color: colors.text }]}>
                                    {buyPrice > 0 && sellPrice > buyPrice ? 'Deal Sustainability' : 'Market Overview'}
                                </Text>
                                <Text style={[styles.profitAnalysisSub, { color: colors.textSecondary }]}>
                                    {buyPrice > 0 && sellPrice > buyPrice ? 'Based on latest market data' : 'Estimated current value'}
                                </Text>
                            </View>
                            {buyPrice > 0 && roi > 0 && (
                                <LinearGradient
                                    colors={[brand.BLUE, '#8B5CF6']}
                                    start={{ x: 0, y: 0 }}
                                    end={{ x: 1, y: 1 }}
                                    style={styles.roiBadgeLarge}
                                >
                                    <Text style={styles.roiTextLarge}>{roi}% ROI</Text>
                                </LinearGradient>
                            )}
                        </View>

                        <View style={[styles.profitStatsGrid, { borderTopColor: colors.divider }]}>
                            <View style={styles.profitStatItem}>
                                <Text style={[styles.profitStatLabel, { color: colors.textSecondary }]}>Cost Price</Text>
                                <Text style={[styles.profitStatValue, { color: colors.text }]}>
                                    {formatPriceDisplay(buyPrice, product.region) || 'Check Price'}
                                </Text>
                            </View>
                            <View style={[styles.profitStatDivider, { backgroundColor: colors.divider }]} />
                            <View style={styles.profitStatItem}>
                                <Text style={[styles.profitStatLabel, { color: colors.textSecondary }]}>Market Value</Text>
                                <Text style={[styles.profitStatValue, { color: '#10B981' }]}>
                                    {formatPriceDisplay(sellPrice, product.region) || 'Check Price'}
                                </Text>
                            </View>
                        </View>

                        {buyPrice > 0 && sellPrice > 0 && (
                            <View style={[styles.netProfitRow, { backgroundColor: isDarkMode ? 'rgba(255,255,255,0.03)' : '#F9FBFF' }]}>
                                <View style={{ flex: 1 }}>
                                    <Text style={[styles.netProfitLabel, { color: colors.textSecondary }]}>Potential Profit (Net)</Text>
                                    <Text style={[styles.netProfitDesc, { color: colors.textSecondary }]}>After 15% estimated marketplace fees</Text>
                                </View>
                                <Text style={[styles.netProfitValue, { color: netProfit > 0 ? '#10B981' : '#EF4444' }]}>
                                    {netProfit > 0 ? '+' : ''}{formatPriceDisplay(netProfit, product.region)}
                                </Text>
                            </View>
                        )}
                    </View>
                ) : null}

                {/* DESCRIPTION SECTION */}
                {data.description ? (
                    <View style={styles.section}>
                        <Text style={[styles.sectionTitle, { color: colors.text }]}>📝 Description</Text>
                        <Text style={[styles.descriptionText, { color: colors.textSecondary }]}>{data.description}</Text>
                    </View>
                ) : null}

                {/* PRODUCT DETAILS (FIELDS) */}
                {visibleDetails.length > 0 && (
                    <View style={styles.section}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                            <Text style={[styles.sectionTitle, { color: colors.text, marginBottom: 0 }]}>📋 Product Details</Text>
                            <Text style={{ fontSize: 11, color: colors.textSecondary, fontWeight: '600' }}>Tap Item to Copy</Text>
                        </View>
                        <View style={[styles.detailsContainer, { backgroundColor: colors.subCard, borderColor: colors.border }]}>
                            {visibleDetails.map((detail, idx) => {
                                const copyable = isCopyable(detail.label);
                                return (
                                    <TouchableOpacity
                                        key={idx}
                                        activeOpacity={copyable ? 0.6 : 1}
                                        onPress={() => copyable && copyToClipboard(detail.value, detail.label)}
                                        style={[styles.detailRow, idx === visibleDetails.length - 1 && { borderBottomWidth: 0 }]}
                                    >
                                        <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>{detail.label}</Text>
                                        <View style={{ flex: 1, flexDirection: 'row', justifyContent: 'flex-end', alignItems: 'center' }}>
                                            <Text style={[styles.detailValue, { color: colors.text }]}>{detail.value}</Text>
                                            {copyable && <Text style={{ marginLeft: 6, fontSize: 12, opacity: 0.3, color: colors.textSecondary }}>📋</Text>}
                                        </View>
                                    </TouchableOpacity>
                                );
                            })}
                        </View>
                    </View>
                )}

                {/* RESEARCH LINKS SECTION */}
                <View style={styles.section}>
                    <Text style={[styles.sectionTitle, { color: colors.text }]}>🔍 Research This Product</Text>
                    <View style={[styles.linksContainer, { backgroundColor: colors.card, borderColor: colors.border }]}>
                        {/* eBay Link */}
                        <LinkRow icon="🏷️" label="eBay Sold Listings" url={ebayLink} />
                        {/* Amazon Link */}
                        <LinkRow icon="📦" label="Amazon Pricing" url={amazonLink} />
                        {/* Google Link */}
                        <LinkRow icon="🌐" label="Google Search" url={googleLink} />
                        {/* Additional Product Links */}
                        {data.links && data.links.other && data.links.other.length > 0 && (
                            data.links.other.map((link, idx) => (
                                <LinkRow
                                    key={idx}
                                    icon="🔗"
                                    label={link.text || `Link ${idx + 1}`}
                                    url={link.url}
                                />
                            ))
                        )}
                    </View>
                </View>

                {/* WHERE TO BUY SECTION - ALL OPTIONS */}
                <View style={styles.section}>
                    <Text style={[styles.sectionTitle, { color: colors.text }]}>🛒 Where to Buy</Text>
                    <View style={[styles.linksContainer, { backgroundColor: colors.card, borderColor: colors.border }]}>
                        {/* Primary Buy Link */}
                        {data.buy_url && (
                            <TouchableOpacity
                                style={styles.buyRow}
                                onPress={() => Linking.openURL(data.buy_url)}
                                activeOpacity={0.7}
                            >
                                <View>
                                    <Text style={[styles.buyLabel, { color: colors.text }]}>Buy Now</Text>
                                    <Text style={[styles.buySource, { color: colors.textSecondary }]}>Retail Price</Text>
                                </View>
                                <Text style={[styles.buyPrice, { color: '#10B981' }]}>
                                    {formatPriceDisplay(buyPrice, product.region)}
                                </Text>
                            </TouchableOpacity>
                        )}

                        {/* Buy Links from Product Data */}
                        {data.links && data.links.buy && data.links.buy.length > 0 && (
                            data.links.buy.map((link, idx) => (
                                <View key={idx}>
                                    {idx > 0 && <View style={[styles.divider, { marginVertical: 8, backgroundColor: colors.divider }]} />}
                                    <TouchableOpacity
                                        style={styles.buyRow}
                                        onPress={() => Linking.openURL(link.url)}
                                        activeOpacity={0.7}
                                    >
                                        <View>
                                            <Text style={[styles.buyLabel, { color: colors.text }]}>{link.text || 'Buy Here'}</Text>
                                            <Text style={[styles.buySource, { color: colors.textSecondary }]}>Retail Retailer</Text>
                                        </View>
                                        <Text style={[styles.buyPrice, { color: '#10B981' }]}>
                                            Visit ›
                                        </Text>
                                    </TouchableOpacity>
                                </View>
                            ))
                        )}

                        {/* Resale Options */}
                        <View style={[styles.divider, { marginVertical: 12, backgroundColor: colors.divider }]} />
                        <TouchableOpacity
                            style={styles.buyRow}
                            onPress={() => Linking.openURL(ebayLink)}
                            activeOpacity={0.7}
                        >
                            <View>
                                <Text style={[styles.buyLabel, { color: colors.text }]}>Resell on eBay</Text>
                                <Text style={[styles.buySource, { color: colors.textSecondary }]}>View Similar Sales</Text>
                            </View>
                            <Text style={[styles.buyPrice, { color: sellPrice > 0 ? brand.PURPLE : colors.textSecondary }]}>
                                {sellPrice > 0 ? formatPriceDisplay(sellPrice, product.region) : 'Visit ›'}
                            </Text>
                        </TouchableOpacity>

                        {/* FBA Links */}
                        {data.links && data.links.fba && data.links.fba.length > 0 && (
                            <>
                                <View style={[styles.divider, { marginVertical: 8, backgroundColor: colors.divider }]} />
                                {data.links.fba.map((link, idx) => (
                                    <TouchableOpacity
                                        key={idx}
                                        style={styles.buyRow}
                                        onPress={() => Linking.openURL(link.url)}
                                        activeOpacity={0.7}
                                    >
                                        <View>
                                            <Text style={[styles.buyLabel, { color: colors.text }]}>{link.text || 'Amazon FBA'}</Text>
                                            <Text style={[styles.buySource, { color: colors.textSecondary }]}>Alternative Source</Text>
                                        </View>
                                        <Text style={[styles.buyPrice, { color: brand.BLUE }]}>
                                            Check ›
                                        </Text>
                                    </TouchableOpacity>
                                ))}
                            </>
                        )}
                    </View>
                </View>

                {/* NOTES */}
                <View style={styles.section}>
                    <Text style={[styles.sectionTitle, { color: colors.text }]}>📝 Deal Info</Text>
                    <View style={[styles.noteCard, { backgroundColor: colors.noteBg, borderColor: colors.noteBorder }]}>
                        <Text style={{ fontSize: 20, marginRight: 10 }}>💡</Text>
                        <View style={{ flex: 1 }}>
                            <Text style={[styles.noteText, { color: colors.noteText }]}>
                                This deal was posted in {product.category_name}. Verify prices and stock before committing.
                            </Text>
                        </View>
                    </View>
                </View>

                <View style={{ height: 120 }} />
            </ScrollView>

            {/* BOTTOM ACTION BAR */}
            <View style={[styles.bottomBar, { backgroundColor: colors.card, borderTopColor: colors.border }]}>
                <TouchableOpacity
                    style={[styles.actionBtn, { backgroundColor: colors.subCard, flex: 1 }]}
                    onPress={() => toggleSave(product)}
                >
                    <Text style={[styles.actionBtnText, { color: colors.text }]}>{saved ? '❤️ Saved' : '🤍 Save'}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                    style={[styles.actionBtn, { backgroundColor: brand.BLUE, flex: 1, marginLeft: 10 }]}
                    onPress={handleShare}
                >
                    <Text style={[styles.actionBtnText, { color: '#FFF', fontWeight: '900' }]}>📤 Share</Text>
                </TouchableOpacity>
                <TouchableOpacity
                    style={[styles.viewSourceBtn, { backgroundColor: brand.BLUE }]}
                    onPress={() => data.buy_url && Linking.openURL(data.buy_url)}
                >
                    <Text style={styles.viewSourceText}>🔗 View Source</Text>
                </TouchableOpacity>
            </View>
        </SafeAreaView>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1 },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 14,
        borderBottomWidth: 1,
        elevation: 2,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.05,
        shadowRadius: 2,
    },
    headerTitle: {
        fontSize: 17,
        fontWeight: '800',
        flex: 1,
        textAlign: 'center'
    },
    scrollContent: { paddingHorizontal: 16, paddingTop: 16 },

    // IMAGE HERO
    imageContainer: {
        width: '100%',
        height: 340,
        borderRadius: 24,
        marginBottom: 24,
        overflow: 'hidden',
        borderWidth: 1,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.1,
        shadowRadius: 20,
        elevation: 8
    },
    image: { width: '100%', height: '100%' },
    saveBtn: {
        position: 'absolute',
        top: 16,
        right: 16,
        width: 48,
        height: 48,
        borderRadius: 24,
        justifyContent: 'center',
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.1,
        shadowRadius: 8,
        elevation: 4
    },
    regionBadge: {
        position: 'absolute',
        bottom: 16,
        left: 16,
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderRadius: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.2,
        shadowRadius: 8,
    },
    regionText: { color: '#FFF', fontSize: 13, fontWeight: '800' },

    // TITLE SECTION
    titleSection: { marginBottom: 24, paddingHorizontal: 4 },
    title: { fontSize: 24, fontWeight: '900', marginBottom: 12, lineHeight: 32, letterSpacing: -0.5 },
    metaRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' },
    retailer: { fontSize: 15, fontWeight: '800', marginRight: 12 },
    statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
    statusText: { fontSize: 13, fontWeight: '700' },

    // REVAMPED PROFIT ANALYSIS CARD
    profitAnalysisCard: {
        borderRadius: 24,
        padding: 24,
        borderWidth: 1,
        marginBottom: 32,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.05,
        shadowRadius: 12,
        elevation: 3
    },
    profitAnalysisHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 24
    },
    profitIconBox: {
        width: 44,
        height: 44,
        borderRadius: 14,
        justifyContent: 'center',
        alignItems: 'center'
    },
    profitAnalysisTitle: { fontSize: 17, fontWeight: '900' },
    profitAnalysisSub: { fontSize: 13, marginTop: 2 },
    roiBadgeLarge: {
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderRadius: 12,
    },
    roiTextLarge: { color: '#FFF', fontWeight: '900', fontSize: 14 },

    profitStatsGrid: {
        flexDirection: 'row',
        paddingTop: 20,
        borderTopWidth: 1,
        marginBottom: 24
    },
    profitStatItem: { flex: 1 },
    profitStatLabel: { fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
    profitStatValue: { fontSize: 20, fontWeight: '900' },
    profitStatDivider: { width: 1, height: '80%', alignSelf: 'center', marginHorizontal: 20 },

    netProfitRow: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 20,
        borderRadius: 20,
    },
    netProfitLabel: { fontSize: 14, fontWeight: '800' },
    netProfitDesc: { fontSize: 11, marginTop: 2 },
    netProfitValue: { fontSize: 22, fontWeight: '900' },

    // SECTION STYLES
    section: { marginBottom: 32 },
    sectionTitle: { fontSize: 18, fontWeight: '900', marginBottom: 16 },

    // LINKS & DETAILS
    linksContainer: { borderRadius: 24, overflow: 'hidden', borderWidth: 1 },
    linkRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16,
        borderBottomWidth: 1,
    },
    linkText: { fontSize: 15, fontWeight: '600' },

    detailsContainer: { borderRadius: 24, padding: 8, borderWidth: 1 },
    detailRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        padding: 14,
        borderBottomWidth: 1,
    },
    detailLabel: { fontSize: 12, fontWeight: '800', textTransform: 'uppercase', opacity: 0.8 },
    detailValue: { fontSize: 14, fontWeight: '700', flex: 1, textAlign: 'right', marginLeft: 16 },

    buyRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 16
    },
    buyLabel: { fontSize: 16, fontWeight: '800' },
    buySource: { fontSize: 12, marginTop: 2 },
    buyPrice: { fontSize: 17, fontWeight: '900' },

    divider: { height: 1 },

    descriptionText: { fontSize: 15, lineHeight: 24, fontWeight: '500' },

    noteCard: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 20,
        borderRadius: 20,
        borderWidth: 1
    },
    noteText: { fontSize: 14, fontWeight: '600', lineHeight: 20 },

    // BOTTOM BAR
    bottomBar: {
        flexDirection: 'row',
        padding: 16,
        paddingBottom: 32,
        borderTopWidth: 1,
        gap: 12
    },
    actionBtn: {
        height: 56,
        borderRadius: 16,
        justifyContent: 'center',
        alignItems: 'center',
        flex: 1
    },
    actionBtnText: { fontWeight: '800', fontSize: 15 },
    viewSourceBtn: {
        height: 56,
        borderRadius: 16,
        justifyContent: 'center',
        alignItems: 'center',
        flex: 2,
        shadowColor: Constants.BRAND.BLUE,
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
        elevation: 4
    },
    viewSourceText: { fontWeight: '900', fontSize: 16, color: '#FFF' },

    copiedToast: {
        position: 'absolute',
        top: 100,
        left: 24,
        right: 24,
        backgroundColor: 'rgba(0,0,0,0.9)',
        padding: 16,
        borderRadius: 16,
        zIndex: 9999,
        alignItems: 'center'
    },
    copiedToastText: { color: '#FFF', fontWeight: '800' },

    // HERO DISCOUNT STYLES
    heroDiscountCard: {
        borderRadius: 24,
        padding: 24,
        marginBottom: 24,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.2,
        shadowRadius: 16,
        elevation: 8
    },
    heroDiscountBadge: { alignItems: 'center', marginBottom: 20 },
    heroDiscountPercent: { fontSize: 56, fontWeight: '900', color: '#FFF', letterSpacing: -2 },
    heroDiscountLabel: { fontSize: 18, fontWeight: '800', color: '#FFF', letterSpacing: 4, marginTop: -8 },
    heroSavingsRow: {
        alignItems: 'center',
        marginBottom: 24,
        paddingBottom: 20,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(255,255,255,0.2)'
    },
    heroSavingsLabel: { fontSize: 15, fontWeight: '700', color: 'rgba(255,255,255,0.9)', marginBottom: 8 },
    heroSavingsAmount: { fontSize: 36, fontWeight: '900', color: '#FFF' },
    heroPriceRow: { flexDirection: 'row', alignItems: 'center' },
    heroPriceDivider: { width: 1, height: 48, backgroundColor: 'rgba(255,255,255,0.2)', marginHorizontal: 24 },
    heroNowLabel: { fontSize: 12, fontWeight: '800', color: 'rgba(255,255,255,0.8)', marginBottom: 4, textTransform: 'uppercase' },
    heroNowPrice: { fontSize: 24, fontWeight: '900', color: '#FFF' },
    heroWasLabel: { fontSize: 12, fontWeight: '800', color: 'rgba(255,255,255,0.7)', marginBottom: 4, textTransform: 'uppercase' },
    heroWasPrice: { fontSize: 20, fontWeight: '700', color: 'rgba(255,255,255,0.8)', textDecorationLine: 'line-through' }
});

export default ProductDetailScreen;
