# Implementation Brief: Add Caching to Reduce Database Queries by 90%+

## Problem
The mobile app polls aggressively (every 3-5 seconds), causing:
- 6,000-20,000 database messages scanned per minute per active user
- Excessive database load and API costs
- Slow response times

## Solution Implemented
**Server-side caching with TTL** to serve repeated requests from memory instead of querying the database.

---

## Files to Review

### 1. `cache_utils.py` (NEW FILE - Must be added)
This is a new Python module that provides caching functionality. Place it in the same directory as `main_api.py`.

**What it does:**
- Provides `FeedCache` class for storing API responses
- Automatically expires cached data after TTL (Time To Live)
- Generates consistent cache keys for queries
- Tracks cache statistics

**Key features:**
- `feed_cache`: 30-second cache for feed queries
- `user_cache`: 60-second cache for user status
- `categories_cache`: 5-minute cache for category data

### 2. `PATCH_INSTRUCTIONS.md` (IMPLEMENTATION GUIDE)
Step-by-step instructions showing:
- Where to add caching code in `main_api.py`
- Exact code to add to each endpoint
- How to invalidate cache when data changes
- Testing and monitoring guidelines

**Key changes needed in `main_api.py`:**

1. Add import: `from cache_utils import feed_cache, user_cache, categories_cache`

2. Modify `/v1/feed` endpoint to:
   - Check cache before querying database
   - Store results in cache after fetching
   - Return cached data for repeated requests

3. Modify `/v1/user/status` endpoint to:
   - Cache user status for 60 seconds
   - Avoid repeated user credential checks

4. Add cache management endpoints:
   - `/v1/cache/invalidate` - Manually clear cache
   - `/v1/cache/stats` - Monitor cache performance

---

## Expected Behavior

### Before Caching
```
Request 1 (t=0s):  Query DB → Scan 1000 messages → Return 10 products
Request 2 (t=3s):  Query DB → Scan 1000 messages → Return 10 products (same data)
Request 3 (t=6s):  Query DB → Scan 1000 messages → Return 10 products (same data)
Request 4 (t=9s):  Query DB → Scan 1000 messages → Return 10 products (same data)
```
**Result:** 4 DB queries, 4,000 messages scanned in 9 seconds

### After Caching
```
Request 1 (t=0s):  CACHE MISS → Query DB → Scan 1000 messages → Return & cache
Request 2 (t=3s):  CACHE HIT → Return from memory (0ms, no DB query)
Request 3 (t=6s):  CACHE HIT → Return from memory (0ms, no DB query)
Request 4 (t=9s):  CACHE HIT → Return from memory (0ms, no DB query)
...
Request 11 (t=31s): CACHE EXPIRED → Query DB → Scan 1000 messages → Return & cache
```
**Result:** 2 DB queries, 2,000 messages scanned in 31 seconds (50% reduction for same period, 90%+ over time)

---

## What I've Already Done

✅ Fixed duplicate endpoint warning (removed duplicate `/v1/user/status` at line 1611)
✅ Copied the fixed code from `app.py` to `main_api.py`

## What Needs to Be Done

1. **Add `cache_utils.py`** to the project (same directory as `main_api.py`)

2. **Import the cache** at the top of `main_api.py`:
   ```python
   from cache_utils import feed_cache, user_cache, categories_cache
   ```

3. **Update `/v1/feed` endpoint** (around line 1461):
   - Add cache check at the beginning
   - Add cache storage at the end
   - See PATCH_INSTRUCTIONS.md section 2 for exact code

4. **Update `/v1/user/status` endpoint** (around line 715):
   - Add cache check at the beginning
   - Add cache storage before return
   - See PATCH_INSTRUCTIONS.md section 3 for exact code

5. **Optional but recommended**: Add cache management endpoints from section 5 of PATCH_INSTRUCTIONS.md

---

## Testing After Implementation

1. **Deploy the changes**

2. **Monitor logs** for these messages:
   ```
   [FEED CACHE] ✗ Miss - Fetching from DB for user abc...
   [FEED CACHE] ✓ Hit for user abc... (UK Stores/ALL)
   [USER CACHE] ✓ Hit for abc...
   ```

3. **Check cache stats** by calling: `GET /v1/cache/stats`
   Should show increasing hit rates over time

4. **Verify performance**:
   - Response times should drop from 200-500ms to <10ms for cached requests
   - Database query count in Supabase should decrease by 70-90%
   - Railway compute usage should decrease

---

## Important Notes

- **No client changes required** - The aggressive polling continues, but most requests are served from cache
- **Cache is in-memory** - Will reset if the server restarts (this is fine, it rebuilds quickly)
- **TTL is configurable** - Can adjust 30s/60s timings in `cache_utils.py` if needed
- **Cache invalidation** - Automatically happens on TTL expiry, or manually via `/v1/cache/invalidate` endpoint

---

## Rollback Plan

If caching causes issues:
1. Remove the cache checks from the endpoints (the DB query code is unchanged)
2. Or restart the Railway service (clears in-memory cache)
3. The code is designed to gracefully fall back to DB queries if cache fails

---

## Next Steps (Future Enhancement)

After confirming caching works, we can implement **Supabase Realtime** (see `realtime_optimization_guide.md`) to:
- Push database changes to the API automatically
- Implement long-polling so clients only refresh when new data exists
- Further reduce polling frequency from client side

But caching alone should provide 90%+ improvement immediately.
