"""
cache_utils.py - Caching utilities for hollowScan API
Provides in-memory caching with TTL to reduce database queries
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import hashlib


class FeedCache:
    """In-memory cache for feed data with automatic expiration"""
    
    def __init__(self, ttl_seconds: int = 30):
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self.ttl_seconds = ttl_seconds
        self.last_db_update = datetime.now(timezone.utc)
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            age = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if age < self.ttl_seconds:
                return data
            else:
                # Expired, remove it
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Store value with current timestamp"""
        self.cache[key] = (value, datetime.now(timezone.utc))
    
    def invalidate(self, pattern: Optional[str] = None):
        """Invalidate cache entries matching pattern, or all if None"""
        if pattern is None:
            self.cache.clear()
            self.last_db_update = datetime.now(timezone.utc)
        else:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for k in keys_to_delete:
                del self.cache[k]
    
    def get_cache_key(self, user_id: str, region: str, category: str, search: str, offset: int) -> str:
        """Generate consistent cache key for feed queries"""
        # Normalize inputs
        region = (region or "ALL").strip().upper()
        category = (category or "ALL").strip().upper()
        search = (search or "").strip().lower()
        
        # Create hash for long search terms to keep keys manageable
        if len(search) > 50:
            search_hash = hashlib.md5(search.encode()).hexdigest()[:8]
        else:
            search_hash = search
        
        return f"feed:{user_id}:{region}:{category}:{search_hash}:{offset}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = datetime.now(timezone.utc)
        valid_entries = 0
        expired_entries = 0
        
        for key, (data, timestamp) in self.cache.items():
            age = (now - timestamp).total_seconds()
            if age < self.ttl_seconds:
                valid_entries += 1
            else:
                expired_entries += 1
        
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "ttl_seconds": self.ttl_seconds,
            "last_db_update": self.last_db_update.isoformat()
        }


# Initialize global cache instances
# These will be imported and used by the main API
feed_cache = FeedCache(ttl_seconds=30)  # 30 second cache for feeds
user_cache = FeedCache(ttl_seconds=60)  # 60 second cache for user status
categories_cache = FeedCache(ttl_seconds=300)  # 5 minute cache for categories