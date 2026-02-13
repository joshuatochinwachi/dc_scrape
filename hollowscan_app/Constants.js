/**
 * HollowScan Global Constants
 */
const Constants = {
    // ⚠️ 'localhost' does not work on a physical phone.
    // We use your local IP so your phone can talk to your computer.
    API_BASE_URL: 'https://product.hollowscan.com',// 'https://web-production-18cf1.up.railway.app',
    // API_BASE_URL: 'http://10.175.204.243:8000',

    BRAND: {
        BLUE: '#4F46E5', // Vivid Indigo-Blue
        CYAN: '#06B6D4', // Electric Cyan from icon
        PURPLE: '#9333EA', // Magenta-Purple from icon
        DARK_BG: '#0A0A0B',
        LIGHT_BG: '#F8F9FE',
    },

    TELEGRAM_BOT: 'hollowscan_bot', // Replace with your bot's username
    SUPPORT_EMAIL: 'support@hollowscan.com'
};

export default Constants;
