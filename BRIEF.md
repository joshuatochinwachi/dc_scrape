"""
========================================
EXACT CODE CHANGES FOR main_api.py
========================================

This file shows the EXACT changes to make in your main_api.py file.
Search for the OLD code and replace with NEW code.

========================================
CHANGE 1: Update imports (Line ~29)
========================================

FIND THIS (around line 29):
----------------------------
from cache_utils import feed_cache, user_cache, categories_cache


REPLACE WITH:
----------------------------
from cache_utils import feed_cache, product_list_cache, user_cache, categories_cache


========================================
CHANGE 2: Modify /v1/feed endpoint
========================================

FIND THIS (around line 1520-1695):
----------------------------
@app.get("/v1/feed")
async def get_feed(
    user_id: str, 
    background_tasks: BackgroundTasks, 
    region: Optional[str] = "ALL", 
    category: Optional[str] = "ALL", 
    offset: int = 0, 
    limit: int = 20, 
    country: Optional[str] = None, 
    search: Optional[str] = None,
    force_refresh: bool = False
):
    # Generate cache key
    cache_key = feed_cache.get_cache_key(user_id, region, category, search or "", offset)
    
    # Check cache first (unless force_refresh requested)
    if not force_refresh:
        cached_result = feed_cache.get(cache_key)
        if cached_result is not None:
            print(f"[FEED CACHE] ✓ Hit for user {user_id[:8]}... ({region}/{category})")
            return cached_result
    
    print(f"[FEED CACHE] ✗ Miss - Fetching from DB for user {user_id[:8]}...")
    
    # ... rest of the function until the end ...


REPLACE WITH:
----------------------------
@app.get("/v1/feed")
async def get_feed(
    user_id: str, 
    background_tasks: BackgroundTasks, 
    region: Optional[str] = "ALL", 
    category: Optional[str] = "ALL", 
    offset: int = 0, 
    limit: int = 20, 
    country: Optional[str] = None, 
    search: Optional[str] = None,
    force_refresh: bool = False
):
    import time
    start_time = time.time()
    
    # Normalize inputs
    if country and (not region or region == "ALL"):
        region = country
    
    # Generate base cache key (WITHOUT offset - caches all products for this filter)
    base_cache_key = product_list_cache.get_base_cache_key(user_id, region, category, search or "")
    
    # Check if we have cached ALL products for this filter
    cached_data = None
    if not force_refresh:
        cached_data = product_list_cache.get(base_cache_key)
    
    # If cache hit, serve from memory
    if cached_data is not None:
        all_products, total_scanned = cached_data
        print(f"[FEED CACHE] ✓ HIT - Serving page from {len(all_products)} cached products")
        
        # Check premium status (cached separately)
        premium_user = await verify_premium_status(user_id, background_tasks=background_tasks)
        
        # Slice for requested page
        page_products = all_products[offset:offset+limit]
        has_more = (offset + limit) < len(all_products)
        
        # Apply free user limits
        if not premium_user:
            if len(page_products) > 4:
                page_products = page_products[:4]
                has_more = False
            for product in page_products:
                product["is_locked"] = False
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[FEED] Cache hit in {elapsed:.0f}ms - Returned {len(page_products)}/{len(all_products)} products")
        
        return {
            "products": page_products,
            "next_offset": offset + limit if has_more else offset,
            "has_more": has_more,
            "is_premium": premium_user,
            "total_count": len(all_products)
        }
    
    # Cache miss - fetch from database
    print(f"[FEED CACHE] ✗ MISS - Fetching from DB for user {user_id[:8]}...")
    
    # ... KEEP ALL THE EXISTING LOGIC FROM HERE ...
    # (The rest of the function stays exactly the same until line ~1690)


========================================
CHANGE 3: Update the end of /v1/feed 
========================================

FIND THIS (around line 1682-1695):
----------------------------
    has_more = not db_end_reached
    
    if not premium_user:
        if len(all_products) > 4:
            all_products = all_products[:4]
            has_more = False
        for product in all_products: product["is_locked"] = False
    
    # ======= EXISTING LOGIC ENDS HERE =======
    
    # Build result
    result = {
        "products": all_products, 
        "next_offset": current_sql_offset, 
        "has_more": has_more, 
        "is_premium": premium_user, 
        "total_count": 100
    }
    
    # CACHE THE RESULT
    feed_cache.set(cache_key, result)
    
    print(f"[FEED] Complete. Found {len(all_products)} products scanning {current_sql_offset - offset} messages. (Cached)")
    return result


REPLACE WITH:
----------------------------
    has_more = not db_end_reached
    
    # CACHE THE COMPLETE PRODUCT LIST (before applying free user limits)
    # This caches ALL products so pagination requests can be served from memory
    product_list_cache.set(base_cache_key, all_products, current_sql_offset - offset)
    
    # Now slice for the requested page
    total_products = len(all_products)
    page_products = all_products[offset:offset+limit]
    has_more_pages = (offset + limit) < total_products
    
    # Apply free user limits to the page
    if not premium_user:
        if len(page_products) > 4:
            page_products = page_products[:4]
            has_more_pages = False
        for product in page_products:
            product["is_locked"] = False
    
    # Build result
    result = {
        "products": page_products, 
        "next_offset": offset + limit if has_more_pages else offset, 
        "has_more": has_more_pages, 
        "is_premium": premium_user, 
        "total_count": total_products
    }
    
    elapsed = (time.time() - start_time) * 1000
    print(f"[FEED] Complete in {elapsed:.0f}ms. Found {total_products} products (scanned {current_sql_offset - offset} messages). Cached for future requests.")
    return result


========================================
CHANGE 4: Update cache stats endpoint (Optional)
========================================

FIND THIS (around line 2077):
----------------------------
@app.get("/v1/cache/stats")
async def get_cache_stats():
    """Get cache statistics for monitoring"""
    return {
        "feed_cache": feed_cache.get_stats(),
        "user_cache": user_cache.get_stats(),
        "categories_cache": categories_cache.get_stats()
    }


REPLACE WITH:
----------------------------
@app.get("/v1/cache/stats")
async def get_cache_stats():
    """Get cache statistics for monitoring"""
    return {
        "feed_cache": feed_cache.get_stats(),
        "product_list_cache": product_list_cache.get_stats(),  # NEW
        "user_cache": user_cache.get_stats(),
        "categories_cache": categories_cache.get_stats()
    }


========================================
CHANGE 5: Update cache invalidation (Optional)
========================================

FIND THIS (around line 2048):
----------------------------
        if cache_type == "all" or cache_type == "feed":
            if user_id:
                feed_cache.invalidate(f"feed:{user_id}")
                print(f"[CACHE] Invalidated feed cache for user {user_id}")
            else:
                feed_cache.invalidate()
                print("[CACHE] Invalidated all feed caches")


REPLACE WITH:
----------------------------
        if cache_type == "all" or cache_type == "feed":
            if user_id:
                feed_cache.invalidate(f"feed:{user_id}")
                product_list_cache.invalidate(f"feed_all:{user_id}")  # NEW
                print(f"[CACHE] Invalidated feed cache for user {user_id}")
            else:
                feed_cache.invalidate()
                product_list_cache.invalidate()  # NEW
                print("[CACHE] Invalidated all feed caches")


========================================
SUMMARY OF CHANGES
========================================

1. Add product_list_cache to imports
2. Use product_list_cache.get_base_cache_key() instead of feed_cache.get_cache_key()
3. Check product_list_cache first for cached ALL products
4. If cache hit, slice the cached list and return
5. If cache miss, fetch from DB as before
6. Cache the COMPLETE product list (not just one page)
7. Slice the complete list for the requested page
8. Update stats and invalidation endpoints

That's it! These changes will dramatically improve pagination performance.
"""