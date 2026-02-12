import Constants from '../Constants';

/**
 * Live Product Update Service
 * Polls the backend for new products and provides real-time updates
 */

class LiveProductService {
    constructor() {
        this.pollingInterval = null;
        this.pollDuration = 5000; // Poll every 5 seconds
        this.listeners = [];
        this.lastProductTime = new Date();
        this.isPolling = false;
        this.LIMIT = 10;
    }

    /**
     * Subscribe to product updates
     * @param {Function} callback - Called with new products
     * @returns {Function} - Unsubscribe function
     */
    subscribe(callback) {
        this.listeners.push(callback);
        console.log('[LIVE] Subscriber added. Total subscribers:', this.listeners.length);

        // Return unsubscribe function
        return () => {
            this.listeners = this.listeners.filter(cb => cb !== callback);
            console.log('[LIVE] Subscriber removed. Total subscribers:', this.listeners.length);
        };
    }

    /**
     * Notify all subscribers of new products
     */
    notifySubscribers(newProducts) {
        console.log('[LIVE] Notifying', this.listeners.length, 'subscribers of', newProducts.length, 'new products');
        this.listeners.forEach(callback => {
            try {
                callback(newProducts);
            } catch (error) {
                console.log('[LIVE] Error in subscriber callback:', error);
            }
        });
    }

    /**
     * Start polling for new products
     */
    startPolling(params) {
        if (this.isPolling) {
            console.log('[LIVE] Already polling');
            return;
        }

        this.isPolling = true;
        console.log('[LIVE] Starting polling with params:', params);

        // Poll immediately
        this.pollForNewProducts(params);

        // Then set up interval
        this.pollingInterval = setInterval(() => {
            this.pollForNewProducts(params);
        }, this.pollDuration);
    }

    /**
     * Stop polling for new products
     */
    stopPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isPolling = false;
            console.log('[LIVE] Stopped polling');
        }
    }

    /**
     * Poll backend for new products
     */
    async pollForNewProducts(params) {
        try {
            const {
                userId,
                country,
                category,
                onlyNew = true,
                search = '',
                forceRefresh = false
            } = params;

            // Build query to get only products created after lastProductTime
            const catParam = category === 'ALL' || !category ? '' : category;
            const limitParam = onlyNew ? this.LIMIT : 20;
            let url = `${Constants.API_BASE_URL}/v1/feed?user_id=${userId}&region=${encodeURIComponent(country)}&category=${encodeURIComponent(catParam)}&offset=0&limit=${limitParam}`;

            if (search && search.trim()) {
                url += `&search=${encodeURIComponent(search.trim())}`;
            }

            if (forceRefresh) {
                url += `&force_refresh=true`;
            }

            const response = await fetch(url, {
                timeout: 5000, // 5 second timeout
            });

            if (!response.ok) return;

            const result = await response.json();
            const productsList = Array.isArray(result) ? result : (result.products || []);

            if (productsList.length === 0) return;

            // Filter for products newer than our last known time
            const newProducts = productsList.filter(product => {
                const productTime = new Date(product.product_data?.created_at || product.created_at || new Date());
                return productTime > this.lastProductTime;
            });

            if (newProducts.length > 0) {
                console.log('[LIVE] Found', newProducts.length, 'new products');
                this.lastProductTime = new Date(); // Update last known time

                // Notify subscribers with NEW products at the top
                this.notifySubscribers(newProducts);
            }
        } catch (error) {
            console.log('[LIVE] Polling error:', error);
        }
    }

    /**
     * Manually refresh (for pull-to-refresh)
     */
    async manualRefresh(params) {
        console.log('[LIVE] Manual refresh triggered');
        await this.pollForNewProducts({ ...params, forceRefresh: true });
    }

    /**
     * Set polling interval (in milliseconds)
     */
    setPollingInterval(duration) {
        this.pollDuration = duration;
        console.log('[LIVE] Polling interval set to', duration, 'ms');
    }

    /**
     * Reset last product time (use when changing regions/categories)
     */
    resetLastProductTime() {
        this.lastProductTime = new Date();
        console.log('[LIVE] Reset last product time');
    }
}

// Export singleton instance
export default new LiveProductService();
