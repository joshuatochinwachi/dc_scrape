# PATCH INSTRUCTIONS FOR app.py
# Apply these changes to optimize your API with caching

## 1. ADD IMPORT AT TOP (after existing imports, around line 27)

```python
from cache_utils import feed_cache, user_cache, categories_cache
```

## 2. UPDATE /v1/feed ENDPOINT (line ~1461)

REPLACE the entire @app.get("/v1/feed") function with:

```python
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
    force_refresh: bool = False  # NEW: Allow manual cache bypass
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
    
    # ======= EXISTING LOGIC STARTS HERE - KEEP AS IS =======
    if country and (not region or region == "ALL"): 
        region = country
    
    channels = await get_channels_data()
    
    channel_map = {}
    for c in channels:
        if c.get('enabled', True): 
            channel_map[c['id']] = {
                'category': c.get('category', 'USA Stores').strip(), 
                'name': c.get('name', 'Unknown').strip()
            }
    for c in DEFAULT_CHANNELS:
        if c['id'] not in channel_map: 
            channel_map[c['id']] = {
                'category': c.get('category', 'USA Stores').strip(), 
                'name': c.get('name', 'Unknown').strip()
            }
    
    target_ids = []
    if region and region.strip().upper() != "ALL":
        req_reg = region.strip().upper()
        if 'UK' in req_reg: 
            norm_reg = 'UK'
        elif 'CANADA' in req_reg or 'CA' in req_reg: 
            norm_reg = 'CANADA'
        else: 
            norm_reg = 'USA'
        for c in channels:
            c_cat = (c.get('category') or '').upper()
            c_name = (c.get('name') or '').upper()
            is_region_match = norm_reg in c_cat or (norm_reg == 'USA' and 'US' in c_cat)
            if category and category.strip().upper() != "ALL":
                if is_region_match and c_name == category.strip().upper(): 
                    target_ids.append(c['id'])
            elif is_region_match: 
                target_ids.append(c['id'])
    
    id_filter = ""
    if target_ids: 
        id_filter = f"&channel_id=in.({','.join(target_ids)})"
    
    premium_user = False
    try:
        premium_user = await verify_premium_status(user_id, background_tasks=background_tasks)
    except Exception as e: 
        print(f"[FEED] Quota check error: {e}")
    
    all_products = []
    seen_signatures = set()
    current_sql_offset = offset
    chunks_scanned = 0
    base_max = 50 if premium_user else 30
    search_multiplier = 20 if search else 1
    max_chunks = base_max * search_multiplier
    batch_limit = 1000 if search else 50
    
    db_end_reached = False
    while len(all_products) < limit and chunks_scanned < max_chunks:
        search_is_active = bool(search and search.strip())
        query = f"order=scraped_at.desc&offset={current_sql_offset}&limit={batch_limit}"
        
        if id_filter and not search_is_active:
             query += id_filter
             
        if search_is_active:
            keywords = [k.strip() for k in search.split() if len(k.strip()) >= 1]
            if keywords:
                or_parts = []
                for k in keywords:
                    or_parts.append(f"content.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->>title.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->>description.ilike.*{k}*")
                    or_parts.append(f"raw_data->embed->>title.ilike.*{k}*")
                    or_parts.append(f"raw_data->embed->>description.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->fields->0->>value.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->fields->1->>value.ilike.*{k}*")
                    or_parts.append(f"raw_data->embeds->0->author->>name.ilike.*{k}*")
                query += f"&or=({','.join(or_parts)})"
                
        try:
            response = await http_client.get(f"{URL}/rest/v1/discord_messages?{query}", headers=HEADERS)
            if response.status_code != 200: 
                print(f"[FEED] Error {response.status_code}: {response.text}")
                break
            messages = response.json()
            if not messages: 
                db_end_reached = True
                break
                
            for msg in messages:
                sig = _get_content_signature(msg)
                if sig in seen_signatures: 
                    continue
                prod = extract_product(msg, channel_map)
                if not prod: 
                    continue
                
                p_data = prod.get("product_data", {})
                price_val = p_data.get("price")
                resale_val = p_data.get("resell")
                was_val = p_data.get("was_price")
                has_image = p_data.get("image") and "placeholder" not in p_data.get("image")
                has_links = bool(p_data.get("buy_url") or (p_data.get("links") and any(p_data["links"].values())))
                
                try:
                    p_num = float(str(price_val or 0).replace(',', ''))
                    r_num = float(str(resale_val or 0).replace(',', ''))
                    w_num = float(str(was_val or 0).replace(',', ''))
                    has_any_price = p_num > 0 or r_num > 0 or w_num > 0
                except (ValueError, TypeError): 
                    has_any_price = bool(price_val or resale_val or was_val)
                
                if not (has_image or has_any_price or has_links): 
                    continue
                
                if search_is_active:
                    search_keywords = [k.lower().strip() for k in search.split() if k.strip()]
                    search_blob = f"{prod['product_data'].get('title','')}\n{prod['product_data'].get('description','')}\n{prod.get('category_name','')}"
                    for detail in prod["product_data"].get("details", []):
                        search_blob += f"\n{detail.get('label','')}: {detail.get('value','')}"
                    
                    search_blob = search_blob.lower()
                    match_found = False
                    for kw in search_keywords:
                        if kw in search_blob:
                            match_found = True
                            break
                    if not match_found: 
                        continue

                if not search_is_active:
                    if region and region.strip().upper() != "ALL":
                        if prod["region"].strip() != region.strip(): 
                            continue
                    if category and category.strip().upper() != "ALL":
                        if prod["category_name"].upper().strip() != category.upper().strip(): 
                            continue
                
                all_products.append(prod)
                seen_signatures.add(sig)
                if len(all_products) >= limit: 
                    break
            
            current_sql_offset += len(messages)
            chunks_scanned += 1
            if len(messages) < batch_limit: 
                db_end_reached = True
                break
        except Exception as e:
            print(f"[FEED] Error in batch fetch: {e}")
            break

    has_more = not db_end_reached
    
    if not premium_user:
        if len(all_products) > 4:
            all_products = all_products[:4]
            has_more = False
        for product in all_products: 
            product["is_locked"] = False
    
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
```

## 3. UPDATE /v1/user/status ENDPOINT (line ~715)

REPLACE the function body with:

```python
@app.get("/v1/user/status")
async def get_user_status(background_tasks: BackgroundTasks, user_id: str = Query(...)):
    """Get user's current subscription and verification status (cached)"""
    
    # Check cache first
    cache_key = f"user_status:{user_id}"
    cached_status = user_cache.get(cache_key)
    if cached_status is not None:
        print(f"[USER CACHE] ✓ Hit for {user_id[:8]}...")
        return cached_status
    
    print(f"[USER CACHE] ✗ Miss - Fetching from DB for {user_id[:8]}...")
    
    # ======= EXISTING LOGIC - KEEP AS IS =======
    try:
        user_data = await get_user_by_id(user_id)
        if not user_data:
            return {"success": False, "message": "User not found"}

        is_premium = await verify_premium_status(user_id, user_data, background_tasks)
        subscription_end = user_data.get("subscription_end")
        
        if not is_premium:
            try:
                links_resp = await http_client.get(
                    f"{URL}/rest/v1/user_telegram_links?user_id=eq.{user_id}&select=telegram_id",
                    headers=HEADERS
                )
                if links_resp.status_code == 200 and links_resp.json():
                    telegram_id = links_resp.json()[0].get("telegram_id")
                    if telegram_id:
                        bot_users = await get_bot_users_data()
                        tg_user_data = bot_users.get(str(telegram_id), {})
                        expiry_str = tg_user_data.get("expiry")
                        if expiry_str:
                            try:
                                exp_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                                if exp_dt.tzinfo is None: 
                                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                                if exp_dt > datetime.now(timezone.utc):
                                    is_premium = True
                                    subscription_end = expiry_str
                                    background_tasks.add_task(update_user, user_id, {
                                        "subscription_status": "active",
                                        "subscription_end": expiry_str,
                                        "subscription_source": "telegram"
                                    })
                            except: 
                                pass
            except Exception as e:
                print(f"[STATUS] TG check failed: {e}")

        result = {
            "success": True,
            "is_premium": is_premium,
            "subscription_end": subscription_end,
            "status": "active" if is_premium else "free",
            "subscription_status": "active" if is_premium else "free",
            "email_verified": user_data.get("email_verified", False),
            "is_verified": user_data.get("email_verified", False),
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "bio": user_data.get("bio"),
            "location": user_data.get("location"),
            "avatar_url": user_data.get("avatar_url"),
            "region": user_data.get("region", "USA Stores")
        }
        
        # CACHE THE RESULT
        user_cache.set(cache_key, result)
        return result
        
    except Exception as e:
        print(f"[STATUS] Error: {e}")
        return {"success": False, "message": str(e)}
```

## 4. UPDATE /v1/categories ENDPOINT (line ~1403)

ADD caching to categories:

```python
@app.get("/v1/categories")
async def get_categories():
    # Check cache first
    cache_key = "categories"
    cached_result = categories_cache.get(cache_key)
    if cached_result is not None:
        print("[CATEGORIES CACHE] ✓ Hit")
        return cached_result
    
    print("[CATEGORIES CACHE] ✗ Miss - Fetching from storage")
    
    # ... rest of existing logic ...
    # At the end, before return:
    
    result_data = {
        "categories": result, 
        "source": source, 
        "channel_count": len(channels)
    }
    
    # Cache it
    categories_cache.set(cache_key, result_data)
    return result_data
```

## 5. ADD CACHE MANAGEMENT ENDPOINTS (at the end, before health check)

```python
@app.post("/v1/cache/invalidate")
async def invalidate_cache(
    user_id: Optional[str] = None,
    cache_type: str = "all"  # "all", "feed", "user", "categories"
):
    """
    Admin endpoint to manually invalidate cache
    Use this when you know data has changed and want immediate refresh
    """
    try:
        if cache_type == "all" or cache_type == "feed":
            if user_id:
                feed_cache.invalidate(f"feed:{user_id}")
                print(f"[CACHE] Invalidated feed cache for user {user_id}")
            else:
                feed_cache.invalidate()
                print("[CACHE] Invalidated all feed caches")
        
        if cache_type == "all" or cache_type == "user":
            if user_id:
                user_cache.invalidate(f"user_status:{user_id}")
                print(f"[CACHE] Invalidated user cache for {user_id}")
            else:
                user_cache.invalidate()
                print("[CACHE] Invalidated all user caches")
        
        if cache_type == "all" or cache_type == "categories":
            categories_cache.invalidate()
            print("[CACHE] Invalidated categories cache")
        
        return {
            "success": True, 
            "message": f"Cache invalidated for {cache_type}",
            "user_id": user_id
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/v1/cache/stats")
async def get_cache_stats():
    """Get cache statistics for monitoring"""
    return {
        "feed_cache": feed_cache.get_stats(),
        "user_cache": user_cache.get_stats(),
        "categories_cache": categories_cache.get_stats()
    }
```

## 6. INVALIDATE CACHE ON DATA CHANGES

When user data changes (subscription updates, profile updates), invalidate their cache:

ADD to any endpoint that updates user data:

```python
# After successful user update
user_cache.invalidate(f"user_status:{user_id}")
```

For example, in update_user_profile:

```python
@app.patch("/v1/user/profile")
async def update_user_profile(profile: UserProfileUpdate):
    try:
        # ... existing logic ...
        
        success, msg = await update_user(profile.user_id, data, return_details=True)
        if success:
            # INVALIDATE CACHE
            user_cache.invalidate(f"user_status:{profile.user_id}")
            
            return {"success": True, "message": "Profile updated", "data": data}
        # ...
```

## DEPLOYMENT STEPS

1. Copy `cache_utils.py` to the same directory as `app.py`
2. Apply all the patches above to `app.py`
3. Test locally
4. Deploy to Railway
5. Monitor logs for "[CACHE]" messages
6. Check `/v1/cache/stats` endpoint to verify caching is working

## EXPECTED LOG OUTPUT

After deployment, you should see:
```
[FEED CACHE] ✗ Miss - Fetching from DB for user abc123...
[FEED] Complete. Found 10 products scanning 150 messages. (Cached)
[FEED CACHE] ✓ Hit for user abc123... (UK Stores/ALL)
[FEED CACHE] ✓ Hit for user abc123... (UK Stores/ALL)
[USER CACHE] ✗ Miss - Fetching from DB for abc123...
[USER CACHE] ✓ Hit for abc123...
```

## MONITORING

Watch for:
- High cache hit rates (>70% after warmup)
- Reduced "[FEED] Complete" messages (only on cache misses)
- Faster response times in Railway logs
- Reduced database query count in Supabase dashboard
