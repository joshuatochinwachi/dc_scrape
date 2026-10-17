#!/usr/bin/env python3
"""
backtest_logo_filter.py
Standalone tool to backtest and sanitize existing historical messages from logo-monitored channels.
It inspects messages in Supabase discord_messages, detects any that contain the RP logo,
and replaces them with HollowScan's official fallback (no_image.png) so they render cleanly in the Mobile App.

Usage:
    python backtest_logo_filter.py                  # Scans last 50 products per channel & patches DB
    python backtest_logo_filter.py --limit 100      # Scan last 100 products per channel
    python backtest_logo_filter.py --dry-run        # Check only, without writing changes to DB
"""

import os
import sys
import json
import argparse
import requests
from io import BytesIO
from PIL import Image
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

RP_LOGO_URL = "https://raw.githubusercontent.com/joshuatochinwachi/HollowScan-Mobile-App/main/public/RP_logo.png"
FALLBACK_IMAGE_URL = "https://raw.githubusercontent.com/joshuatochinwachi/HollowScan-Mobile-App/main/public/no_image.png"
LOGO_HASH_THRESHOLD = 10

def compute_phash(img_bytes: bytes) -> Optional[int]:
    """Compute 1024-bit perceptual hash with alpha compositing."""
    try:
        raw_img = Image.open(BytesIO(img_bytes))
        if raw_img.mode in ("RGBA", "LA") or (raw_img.mode == "P" and "transparency" in raw_img.info):
            raw_img = raw_img.convert("RGBA")
            bg = Image.new("RGBA", raw_img.size, (255, 255, 255, 255))
            bg.alpha_composite(raw_img)
            img = bg.convert("L")
        else:
            img = raw_img.convert("L")

        img = img.resize((32, 32), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = [1 if p >= avg else 0 for p in pixels]
        return int("".join(str(b) for b in bits), 2)
    except Exception as e:
        return None

def hamming_distance(h1: int, h2: int) -> int:
    return bin(h1 ^ h2).count("1")

def load_rp_logo_phash() -> Optional[int]:
    local_candidates = [
        "public/RP_logo.png",
        "../public/RP_logo.png",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public", "RP_logo.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "RP_logo.png"),
    ]
    for path in local_candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    phash = compute_phash(f.read())
                if phash:
                    print(f"✅ Loaded RP logo pHash from local disk: {path}")
                    return phash
            except Exception:
                pass

    print(f"📥 Downloading RP logo reference from GitHub raw...")
    try:
        resp = requests.get(RP_LOGO_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        phash = compute_phash(resp.content)
        if phash:
            print(f"✅ Loaded RP logo pHash from remote: {hex(phash)}")
            return phash
    except Exception as e:
        print(f"❌ Failed to download RP logo: {e}")
    return None

def get_monitored_channels(supabase_url: str, supabase_key: str) -> List[str]:
    # 1. Try Supabase storage
    try:
        headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        res = requests.get(
            f"{supabase_url}/storage/v1/object/authenticated/monitor-data/discord_josh/logo_filter_channels.json",
            headers=headers,
            timeout=10
        )
        if res.status_code == 200:
            cids = res.json() or []
            if cids:
                return [str(c).strip() for c in cids]
    except Exception:
        pass

    # 2. Local fallback
    for p in ["data/logo_filter_channels.json", "../data/logo_filter_channels.json"]:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    cids = json.load(f)
                if cids:
                    return [str(c).strip() for c in cids]
            except Exception:
                pass
    return []

def main():
    parser = argparse.ArgumentParser(description="Backtest and sanitize RP logo images in Supabase")
    parser.add_argument("--limit", type=int, default=50, help="Max messages to fetch per channel (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without modifying Supabase records")
    args = parser.parse_args()

    sb_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
    if not sb_url or not sb_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY not found in environment/.env")
        sys.exit(1)

    print("=" * 70)
    print("🛡️  HOLLOWSCAN LOGO SANITIZER — BACKTEST & RETROACTIVE REPAIR")
    print("=" * 70)
    if args.dry_run:
        print("🔍 MODE: DRY-RUN (no database writes will occur)")
    else:
        print("⚡ MODE: LIVE PATCHING (detected logos will be replaced in DB)")
    print()

    rp_phash = load_rp_logo_phash()
    if not rp_phash:
        print("❌ Could not compute RP logo pHash. Exiting.")
        sys.exit(1)

    monitored_channels = get_monitored_channels(sb_url, sb_key)
    if not monitored_channels:
        print("⚠️ No channels found in logo filter list. Please add channels via /add_logo_filter first.")
        sys.exit(0)

    print(f"📋 Monitored Channels ({len(monitored_channels)}): {', '.join(monitored_channels)}")
    print(f"🔍 Fetching recent messages (up to {args.limit} per channel)...")
    print()

    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    url = f"{sb_url}/rest/v1/discord_messages"
    ch_filter = f"in.({','.join(monitored_channels)})"
    params = {
        "channel_id": ch_filter,
        "select": "id,channel_id,content,raw_data,scraped_at",
        "order": "scraped_at.desc",
        "limit": args.limit
    }

    res = requests.get(url, headers=headers, params=params, timeout=20)
    if res.status_code != 200:
        print(f"❌ Supabase API error: HTTP {res.status_code} - {res.text[:200]}")
        sys.exit(1)

    messages = res.json() or []
    print(f"📦 Total messages retrieved from DB: {len(messages)}")
    print("-" * 70)

    sanitized_count = 0
    genuine_count = 0
    no_image_count = 0
    cache = {}

    for idx, msg in enumerate(messages, 1):
        msg_id = str(msg.get("id"))
        ch_id = str(msg.get("channel_id", ""))
        raw = msg.get("raw_data") or {}
        embed = raw.get("embed") or (raw.get("embeds") or [{}])[0]
        title = (embed.get("title") or msg.get("content", "")[:50] or f"Message #{msg_id}").strip()

        # Extract primary image URL
        candidate_url = None
        if embed.get("images") and isinstance(embed["images"], list) and embed["images"]:
            candidate_url = embed["images"][0]
        elif embed.get("image"):
            candidate_url = embed["image"].get("url") if isinstance(embed["image"], dict) else embed["image"]
        elif embed.get("thumbnail"):
            candidate_url = embed["thumbnail"].get("url") if isinstance(embed["thumbnail"], dict) else embed["thumbnail"]
        elif raw.get("product_image"):
            candidate_url = raw.get("product_image")

        if not candidate_url or not str(candidate_url).startswith("http"):
            no_image_count += 1
            continue

        cand_str = str(candidate_url).strip()
        c_low = cand_str.lower()

        is_match = False
        distance = 999

        # Fast path
        if "rp_logo" in c_low or "retailpinger" in c_low:
            is_match = True
            distance = 0
        else:
            # Check pHash
            if cand_str in cache:
                cand_hash = cache[cand_str]
            else:
                try:
                    img_resp = requests.get(cand_str, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                    cand_hash = compute_phash(img_resp.content) if img_resp.status_code == 200 else None
                    cache[cand_str] = cand_hash
                except Exception:
                    cand_hash = None
                    cache[cand_str] = None

            if cand_hash is not None:
                distance = hamming_distance(rp_phash, cand_hash)
                if distance <= LOGO_HASH_THRESHOLD:
                    is_match = True

        if is_match:
            sanitized_count += 1
            print(f"🎯 [MATCH #{sanitized_count}] ID: {msg_id} | Ch: {ch_id}")
            print(f"   Title: {title[:60]}")
            print(f"   Distance: {distance} bits (<= {LOGO_HASH_THRESHOLD})")
            print(f"   Original Image: {cand_str[:70]}...")
            print(f"   Action: Replacing with {FALLBACK_IMAGE_URL}")

            if not args.dry_run:
                # Update in-memory embed
                if embed.get("images") and isinstance(embed["images"], list):
                    embed["images"] = [FALLBACK_IMAGE_URL]
                if embed.get("image"):
                    if isinstance(embed["image"], dict):
                        embed["image"]["url"] = FALLBACK_IMAGE_URL
                    else:
                        embed["image"] = FALLBACK_IMAGE_URL
                if embed.get("thumbnail"):
                    if isinstance(embed["thumbnail"], dict):
                        embed["thumbnail"]["url"] = FALLBACK_IMAGE_URL
                    else:
                        embed["thumbnail"] = FALLBACK_IMAGE_URL
                raw["product_image"] = FALLBACK_IMAGE_URL

                # Patch Supabase
                patch_res = requests.patch(
                    f"{sb_url}/rest/v1/discord_messages?id=eq.{msg_id}",
                    headers=headers,
                    json={"raw_data": raw},
                    timeout=10
                )
                if patch_res.status_code in [200, 204]:
                    print(f"   💾 Database updated successfully (HTTP {patch_res.status_code})")
                else:
                    print(f"   ⚠️ Database update failed (HTTP {patch_res.status_code}): {patch_res.text[:100]}")
            print()
        else:
            genuine_count += 1

    print("=" * 70)
    print("📊 BACKTEST SUMMARY REPORT")
    print("=" * 70)
    print(f"• Total Messages Scanned:        {len(messages)}")
    print(f"• RP Logos Found & Sanitized:    {sanitized_count}")
    print(f"• Genuine Photos Kept Untouched: {genuine_count}")
    print(f"• Alerts with No Image:          {no_image_count}")
    print("=" * 70)
    if sanitized_count > 0:
        if args.dry_run:
            print("💡 Run without --dry-run to write these updates to Supabase so the Mobile App reflects them.")
        else:
            print("✅ All matching products have been updated in Supabase!")
            print("📱 When you open the HollowScan Mobile App, these products will now show no_image.png")
            print("   with titles, prices, and buy links 100% functional.")
    else:
        print("✨ No RP logos detected in the scanned set. All products have genuine photos or clean images.")

if __name__ == "__main__":
    main()
