"""
cache_utils.py - OPTIMIZED Caching utilities for hollowScan API
Provides in-memory caching with TTL to reduce database queries

KEY IMPROVEMENTS:
1. Separate cache for full product lists vs paginated results
2. Memory-efficient storage with size limits
3. Better cache key generation without offset (cache entire result set)
4. Automatic cleanup of expired entries
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import hashlib
import sys


class FeedCache:
    """In-memory cache for feed data with automatic expiration and size management"""
    
    def __init__(self, ttl_seconds: int = 30, max_entries: int = 1000):
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.last_db_update = datetime.now(timezone.utc)
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            age = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if age < self.ttl_seconds:
                self.hits += 1
                return data
            else:
                # Expired, remove it
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, key: str, value: Any):
        """Store value with current timestamp, enforce size limits"""
        # If cache is full, remove oldest entries
        if len(self.cache) >= self.max_entries:
            self._evict_oldest()
        
        self.cache[key] = (value, datetime.now(timezone.utc))
    
    def _evict_oldest(self):
        """Remove the oldest 20% of cache entries to make room"""
        if not self.cache:
            return
        
        # Sort by timestamp and remove oldest 20%
        sorted_items = sorted(
            self.cache.items(),
            key=lambda x: x[1][1]  # Sort by timestamp
        )
        
        num_to_remove = max(1, len(sorted_items) // 5)  # Remove 20%
        for i in range(num_to_remove):
            del self.cache[sorted_items[i][0]]
        
        print(f"[CACHE] Evicted {num_to_remove} old entries. Cache size: {len(self.cache)}")
    
    def invalidate(self, pattern: Optional[str] = None):
        """Invalidate cache entries matching pattern, or all if None"""
        if pattern is None:
            self.cache.clear()
            self.last_db_update = datetime.now(timezone.utc)
            print("[CACHE] Full cache invalidation")
        else:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for k in keys_to_delete:
                del self.cache[k]
            print(f"[CACHE] Invalidated {len(keys_to_delete)} entries matching '{pattern}'")
    
    def cleanup_expired(self):
        """Remove all expired entries"""
        now = datetime.now(timezone.utc)
        expired_keys = []
        
        for key, (data, timestamp) in self.cache.items():
            age = (now - timestamp).total_seconds()
            if age >= self.ttl_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            print(f"[CACHE] Cleaned up {len(expired_keys)} expired entries")
    
    def get_base_cache_key(self, user_id: str, region: str, category: str, search: str) -> str:
        """
        Generate cache key WITHOUT offset - this caches the entire filtered product list
        All pagination requests with same filters will use this cached list
        """
        # Normalize inputs
        region = (region or "ALL").strip().upper()
        category = (category or "ALL").strip().upper()
        search = (search or "").strip().lower()
        
        # Create hash for long search terms to keep keys manageable
        if len(search) > 50:
            search_hash = hashlib.md5(search.encode()).hexdigest()[:8]
        else:
            search_hash = search.replace(" ", "_")
        
        # NOTE: No offset in the key - we cache ALL products for this filter combination
        return f"feed_all:{user_id}:{region}:{category}:{search_hash}"
    
    def get_cache_key(self, user_id: str, region: str, category: str, search: str, offset: int) -> str:
        """
        DEPRECATED: Keep for backward compatibility but prefer get_base_cache_key
        This old method created separate cache entries for each page offset
        """
        base_key = self.get_base_cache_key(user_id, region, category, search)
        return f"{base_key}:{offset}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = datetime.now(timezone.utc)
        valid_entries = 0
        expired_entries = 0
        total_size = 0
        
        for key, (data, timestamp) in self.cache.items():
            age = (now - timestamp).total_seconds()
            if age < self.ttl_seconds:
                valid_entries += 1
            else:
                expired_entries += 1
            
            # Estimate size (rough approximation)
            try:
                total_size += sys.getsizeof(data)
            except:
                pass
        
        hit_rate = (self.hits / (self.hits + self.misses) * 100) if (self.hits + self.misses) > 0 else 0
        
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "estimated_size_bytes": total_size,
            "last_db_update": self.last_db_update.isoformat()
        }


class ProductListCache:
    """
    Specialized cache for storing complete product lists
    Optimized for pagination scenarios where we cache ALL products once
    """
    
    def __init__(self, ttl_seconds: int = 60, max_products_per_entry: int = 5000):
        self.cache: Dict[str, tuple[List[Dict], datetime, int, bool]] = {}  # key -> (products, timestamp, next_sql_offset, db_end_reached)
        self.ttl_seconds = ttl_seconds
        self.max_products_per_entry = max_products_per_entry
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[tuple[List[Dict], int, bool]]:
        """Get cached product list. Returns (products, next_sql_offset, db_end_reached)"""
        if key in self.cache:
            products, timestamp, next_sql_offset, db_end_reached = self.cache[key]
            age = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if age < self.ttl_seconds:
                self.hits += 1
                return products, next_sql_offset, db_end_reached
            else:
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, key: str, products: List[Dict], next_sql_offset: int, db_end_reached: bool):
        """Store complete product list with metadata"""
        # Limit products to prevent memory issues
        if len(products) > self.max_products_per_entry:
            print(f"[CACHE] Warning: Truncating {len(products)} products to {self.max_products_per_entry}")
            products = products[:self.max_products_per_entry]
        
        self.cache[key] = (products, datetime.now(timezone.utc), next_sql_offset, db_end_reached)
        status = "END REACHED" if db_end_reached else "PARTIAL"
        print(f"[CACHE] Stored {len(products)} products (Next SQL Offset: {next_sql_offset}, Status: {status})")
    
    def invalidate(self, pattern: Optional[str] = None):
        """Invalidate cache entries"""
        if pattern is None:
            self.cache.clear()
        else:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for k in keys_to_delete:
                del self.cache[k]

    def get_base_cache_key(self, region: str, category: str, search: str) -> str:
        """
        Generate a GLOBAL cache key - this caches results shared across ALL users
        """
        # Normalize inputs
        region = (region or "ALL").strip().upper()
        category = (category or "ALL").strip().upper()
        search = (search or "").strip().lower()
        
        # Create hash for long search terms to keep keys manageable
        if len(search) > 50:
            search_hash = hashlib.md5(search.encode()).hexdigest()[:8]
        else:
            search_hash = search.replace(" ", "_")
        
        # NOTE: No user_id here. This cache is SHARED globally for efficiency.
        return f"feed_global:{region}:{category}:{search_hash}"

    def get_cache_key(self, region: str, category: str, search: str, offset: int) -> str:
        """DEPRECATED: Prefer get_base_cache_key"""
        base_key = self.get_base_cache_key(region, category, search)
        return f"{base_key}:{offset}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = datetime.now(timezone.utc)
        valid_entries = 0
        total_products = 0
        
        for key, (products, timestamp, next_sql_offset, db_end_reached) in self.cache.items():
            age = (now - timestamp).total_seconds()
            if age < self.ttl_seconds:
                valid_entries += 1
                total_products += len(products)
        
        hit_rate = (self.hits / (self.hits + self.misses) * 100) if (self.hits + self.misses) > 0 else 0
        
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "total_cached_products": total_products,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "ttl_seconds": self.ttl_seconds
        }


# Initialize global cache instances
# feed_cache - For backward compatibility and general caching
feed_cache = FeedCache(ttl_seconds=30, max_entries=1000)

# product_list_cache - NEW: Optimized for caching complete product lists
product_list_cache = ProductListCache(ttl_seconds=20, max_products_per_entry=5000)

# user_cache - For user status/profile data
user_cache = FeedCache(ttl_seconds=60, max_entries=500)

# categories_cache - For channel/category data
categories_cache = FeedCache(ttl_seconds=300, max_entries=100)