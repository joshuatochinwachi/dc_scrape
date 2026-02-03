import React, { useEffect, useRef } from 'react';
import { StyleSheet, View, Text, Image, Animated, Dimensions, Easing } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import Constants from '../Constants';

const { width } = Dimensions.get('window');

const SplashScreen = ({ onComplete }) => {
    const brand = Constants.BRAND;

    // Animation refs
    const logoScale = useRef(new Animated.Value(0.8)).current;
    const logoOpacity = useRef(new Animated.Value(0)).current;
    const textTranslateY = useRef(new Animated.Value(40)).current;
    const textOpacity = useRef(new Animated.Value(0)).current;
    const pulseAnim = useRef(new Animated.Value(1)).current;

    useEffect(() => {
        // 1. Entrance Animation
        Animated.sequence([
            // Logo POP
            Animated.parallel([
                Animated.spring(logoScale, {
                    toValue: 1,
                    friction: 6,
                    tension: 40,
                    useNativeDriver: true,
                }),
                Animated.timing(logoOpacity, {
                    toValue: 1,
                    duration: 800,
                    useNativeDriver: true,
                }),
            ]),
            // Text Slide Up
            Animated.parallel([
                Animated.timing(textTranslateY, {
                    toValue: 0,
                    duration: 800,
                    easing: Easing.out(Easing.back(1.5)),
                    useNativeDriver: true,
                }),
                Animated.timing(textOpacity, {
                    toValue: 1,
                    duration: 800,
                    useNativeDriver: true,
                }),
            ]),
        ]).start(() => {
            // 2. Continuous Pulse (Heartbeat)
            Animated.loop(
                Animated.sequence([
                    Animated.timing(pulseAnim, {
                        toValue: 1.05,
                        duration: 1000,
                        easing: Easing.inOut(Easing.ease),
                        useNativeDriver: true,
                    }),
                    Animated.timing(pulseAnim, {
                        toValue: 1,
                        duration: 1000,
                        easing: Easing.inOut(Easing.ease),
                        useNativeDriver: true,
                    }),
                ])
            ).start();

            // 3. Exit delay
            setTimeout(onComplete, 2500);
        });
    }, []);

    return (
        <View style={styles.container}>
            {/* Deep Dark Background */}
            <LinearGradient
                colors={['#0F1014', '#050508', '#000000']}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={StyleSheet.absoluteFill}
            />

            {/* Subtle Gradient Glow effect behind logo */}
            <Image
                source={require('../assets/welcome-hero.png')}
                style={styles.backgroundImage}
                blurRadius={60}
            />

            <SafeAreaView style={styles.contentContainer}>

                {/* HERO IMAGE */}
                <Animated.View style={{
                    opacity: logoOpacity,
                    transform: [{ scale: logoScale }]
                }}>
                    <View style={styles.heroCard}>
                        <Image
                            source={require('../assets/welcome-hero.png')}
                            style={styles.heroImage}
                            resizeMode="contain"
                        />
                        {/* Glossy Overlay for 'Card' look */}
                        <LinearGradient
                            colors={['rgba(255,255,255,0.1)', 'transparent', 'transparent']}
                            style={styles.glossOverlay}
                        />
                    </View>
                </Animated.View>

                {/* TEXT CONTENT */}
                <Animated.View style={[styles.textWrapper, {
                    opacity: textOpacity,
                    transform: [{ translateY: textTranslateY }]
                }]}>
                    <Text style={styles.appName}>HOLLOWSCAN</Text>

                    <Animated.View style={{ transform: [{ scale: pulseAnim }] }}>
                        <LinearGradient
                            colors={[brand.BLUE, brand.PURPLE]}
                            start={{ x: 0, y: 0 }}
                            end={{ x: 1, y: 0 }}
                            style={styles.taglineBadge}
                        >
                            <Text style={styles.taglineText}>ADVANCED DEAL HUNTER</Text>
                        </LinearGradient>
                    </Animated.View>

                    <Text style={styles.footerText}>Automated Arbitrage Intelligence</Text>
                </Animated.View>

            </SafeAreaView>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#050508',
    },
    backgroundImage: {
        position: 'absolute',
        width: width * 1.5,
        height: width * 1.5,
        top: -width * 0.2,
        opacity: 0.15,
        transform: [{ rotate: '45deg' }]
    },
    contentContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 2,
    },
    // Hero Card Professional Look
    heroCard: {
        width: width * 0.85,  // Much larger width
        height: width * 0.85, // Square aspect ratio
        borderRadius: 30,
        backgroundColor: '#0A0A0B',
        shadowColor: '#2D82FF',
        shadowOffset: { width: 0, height: 20 },
        shadowOpacity: 0.6, // Strong glow
        shadowRadius: 40,
        elevation: 25, // Android glow
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: 'rgba(45, 130, 255, 0.2)',
        overflow: 'hidden',
        marginBottom: 50,
    },
    heroImage: {
        width: '100%',
        height: '100%',
    },
    glossOverlay: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '40%',
    },
    // Typography
    textWrapper: {
        alignItems: 'center',
    },
    appName: {
        fontSize: 32,
        fontWeight: '900',
        color: '#FFFFFF',
        letterSpacing: 4, // Premium tracking
        marginBottom: 16,
        textShadowColor: 'rgba(45, 130, 255, 0.5)',
        textShadowOffset: { width: 0, height: 0 },
        textShadowRadius: 20,
    },
    taglineBadge: {
        paddingHorizontal: 16,
        paddingVertical: 6,
        borderRadius: 20,
        marginBottom: 20,
    },
    taglineText: {
        color: '#FFF',
        fontSize: 12,
        fontWeight: '800',
        letterSpacing: 1.5,
    },
    footerText: {
        color: 'rgba(255, 255, 255, 0.4)',
        fontSize: 11,
        letterSpacing: 1,
        marginTop: 20,
        textTransform: 'uppercase',
    },
});

export default SplashScreen;
