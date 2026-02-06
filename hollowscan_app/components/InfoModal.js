import React from 'react';
import { Modal, View, Text, StyleSheet, ScrollView, TouchableOpacity, Dimensions } from 'react-native';
import { BlurView } from 'expo-blur';
import { SafeAreaView } from 'react-native-safe-area-context';
import Constants from '../Constants';

const { height } = Dimensions.get('window');
const brand = Constants.BRAND;

const InfoModal = ({ visible, onClose, title, content, isDarkMode }) => {
    const colors = isDarkMode ? {
        bg: '#1C1C1E',
        text: '#FFFFFF',
        textSecondary: '#8E8E93',
        card: '#2C2C2E',
        border: 'rgba(255,255,255,0.1)'
    } : {
        bg: '#FFFFFF',
        text: '#000000',
        textSecondary: '#666666',
        card: '#F2F2F7',
        border: 'rgba(0,0,0,0.1)'
    };

    return (
        <Modal
            visible={visible}
            animationType="slide"
            presentationStyle="pageSheet"
            onRequestClose={onClose}
        >
            <SafeAreaView style={[styles.container, { backgroundColor: colors.bg }]}>
                {/* HEADER */}
                <View style={[styles.header, { borderBottomColor: colors.border }]}>
                    <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
                    <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                        <Text style={{ fontSize: 16, fontWeight: '600', color: brand.BLUE }}>Done</Text>
                    </TouchableOpacity>
                </View>

                {/* CONTENT */}
                <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
                    {content && content.map((section, index) => (
                        <View key={index} style={styles.section}>
                            {section.heading && (
                                <Text style={[styles.heading, { color: colors.text }]}>
                                    {section.heading}
                                </Text>
                            )}
                            {section.body && (
                                <Text style={[styles.body, { color: colors.textSecondary }]}>
                                    {section.body}
                                </Text>
                            )}
                            {section.list && section.list.map((item, i) => (
                                <View key={i} style={styles.listItem}>
                                    <Text style={{ marginRight: 8, fontSize: 6 }}>•</Text>
                                    <Text style={[styles.body, { color: colors.textSecondary, flex: 1 }]}>{item}</Text>
                                </View>
                            ))}
                            {section.questions && section.questions.map((q, i) => (
                                <View key={i} style={[styles.faqItem, { backgroundColor: colors.card, borderColor: colors.border }]}>
                                    <Text style={[styles.question, { color: colors.text }]}>{q.q}</Text>
                                    <View style={[styles.divider, { backgroundColor: colors.border }]} />
                                    <Text style={[styles.answer, { color: colors.textSecondary }]}>{q.a}</Text>
                                </View>
                            ))}
                        </View>
                    ))}
                    <View style={{ height: 40 }} />
                </ScrollView>
            </SafeAreaView>
        </Modal>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1 },
    header: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        paddingVertical: 16,
        borderBottomWidth: 1,
        position: 'relative'
    },
    title: { fontSize: 18, fontWeight: '700' },
    closeBtn: { position: 'absolute', right: 20, padding: 5 },
    scrollContent: { padding: 20 },
    section: { marginBottom: 24 },
    heading: { fontSize: 18, fontWeight: '700', marginBottom: 12 },
    body: { fontSize: 15, lineHeight: 22, marginBottom: 10 },
    listItem: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 6, paddingLeft: 4 },
    faqItem: { borderRadius: 12, borderWidth: 1, padding: 16, marginBottom: 12 },
    question: { fontSize: 16, fontWeight: '700', marginBottom: 8 },
    answer: { fontSize: 14, lineHeight: 20 },
    divider: { height: 1, marginVertical: 8 }
});

export default InfoModal;
