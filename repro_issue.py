
import asyncio
import os
import re
import json
from playwright.async_api import async_playwright

# Mocking app.py functions
def log(message):
    print(message)

def clean_text(text):
    if not text: return ""
    text = str(text).replace('\x00', '')
    return ' '.join(text.split()).encode('ascii', 'ignore').decode('ascii')

async def extract_message_author(message_element):
    """Extract author info with robust fallbacks"""
    try:
        # Priority 1: ID-based
        author_elem = message_element.locator('[id^="message-username-"]').first
        
        # Priority 2: Standard Class-based
        if await author_elem.count() == 0:
            author_elem = message_element.locator('span[class*="username"]').first
            
        # Priority 3: Header-based
        if await author_elem.count() == 0:
            author_elem = message_element.locator('h3 span').first

        if await author_elem.count() > 0:
            author_name = await author_elem.inner_text()
            
            is_bot = await message_element.locator('[class*="botTag"]').count() > 0
            
            avatar_elem = message_element.locator('img[class*="avatar"]').first
            avatar_url = None
            if await avatar_elem.count() > 0:
                avatar_url = await avatar_elem.get_attribute('src')
                
            return {"name": clean_text(author_name), "is_bot": is_bot, "avatar": avatar_url}
    except Exception as e:
        pass
    return {"name": "Unknown", "is_bot": False, "avatar": None}

async def extract_embed_data(message_element):
    """Extract embed data from Discord message"""
    embed_data = {
        "title": None,
        "description": None,
        "fields": [],
        "images": [],
        "thumbnail": None,
        "color": None,
        "author": None,
        "footer": None,
        "timestamp": None,
        "links": []
    }
    
    try:
        embed = message_element.locator('article[class*="embedFull"]').first
        if await embed.count() == 0:
            embed = message_element.locator('article[class*="embed"]').first
        if await embed.count() == 0:
            return None
        
        try:
            color_style = await embed.get_attribute('style')
            if color_style and 'border-left-color' in color_style:
                embed_data["color"] = color_style
        except: pass
        
        try:
            author_elem = embed.locator('[class*="embedAuthor"] a, [class*="embedAuthor"] span, [class*="embedAuthorName"]').first
            if await author_elem.count() > 0:
                author_name = await author_elem.inner_text()
                author_url = await author_elem.get_attribute('href')
                embed_data["author"] = {"name": clean_text(author_name), "url": author_url}
                if author_url and author_url not in [l.get("url") for l in embed_data["links"]]:
                    embed_data["links"].append({"type": "author", "text": clean_text(author_name), "url": author_url})
        except: pass
        
        try:
            title_elem = embed.locator('[class*="embedTitle"] a, [class*="embedTitle"]').first
            if await title_elem.count() > 0:
                title_text = await title_elem.inner_text()
                title_url = await title_elem.get_attribute('href')
                embed_data["title"] = clean_text(title_text)
                if title_url and title_url not in [l.get("url") for l in embed_data["links"]]:
                    embed_data["links"].append({"type": "title", "text": embed_data["title"], "url": title_url})
        except: pass
        
        try:
            field_containers = embed.locator('[class*="embedField"]')
            field_count = await field_containers.count()
            
            for i in range(field_count):
                field = field_containers.nth(i)
                field_name_elem = field.locator('[class*="embedFieldName"]').first
                field_name = ""
                if await field_name_elem.count() > 0:
                    field_name = clean_text(await field_name_elem.inner_text())
                
                field_value = ""
                field_value_elem = field.locator('[class*="embedFieldValue"]').first
                if await field_value_elem.count() > 0:
                    try:
                        field_value = await field_value_elem.evaluate("""element => {
                            let clone = element.cloneNode(true);
                            clone.querySelectorAll('s, strike').forEach(s => {
                                s.textContent = `~~${s.textContent}~~`;
                            });
                            clone.querySelectorAll('*').forEach(el => {
                                let style = window.getComputedStyle(el);
                                if (style.textDecoration && style.textDecoration.includes('line-through') && !el.textContent.includes('~~')) {
                                    el.textContent = `~~${el.textContent}~~`;
                                }
                            });
                            clone.querySelectorAll('a').forEach(a => {
                                if (a.href) {
                                    a.textContent = `[${a.textContent}](${a.href})`;
                                }
                            });
                            return clone.innerText;
                        }""")
                    except:
                        field_value = await field_value_elem.inner_text()
                    
                    field_value = clean_text(field_value)
                
                if field_name or field_value:
                    embed_data["fields"].append({"name": field_name, "value": field_value})
                    
                    try:
                        value_links = field_value_elem.locator('a[href]')
                        link_count = await value_links.count()
                        for j in range(link_count):
                            link_elem = value_links.nth(j)
                            href = await link_elem.get_attribute('href')
                            text = await link_elem.inner_text()
                            if href and href not in [l.get("url") for l in embed_data["links"]]:
                                embed_data["links"].append({
                                    "field": field_name,
                                    "text": clean_text(text),
                                    "url": href
                                })
                    except: pass
        except: pass
        
        try:
            thumb_elem = embed.locator('img[class*="embedThumbnail"]').first
            if await thumb_elem.count() == 0:
                thumb_elem = embed.locator('[class*="embedThumbnail"] img').first
            
            if await thumb_elem.count() > 0:
                thumb_src = await thumb_elem.get_attribute('src')
                if thumb_src:
                    embed_data["images"].append(thumb_src)
        except: pass
        
        try:
            footer_elem = embed.locator('[class*="embedFooter"]').first
            if await footer_elem.count() > 0:
                embed_data["footer"] = clean_text(await footer_elem.inner_text())
        except: pass
        
        return embed_data if any([embed_data["title"], embed_data["fields"], embed_data["links"]]) else None
    except Exception as e:
        log(f"   ⚠️ Embed error: {e}")
        return None

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        data_dir = "data"
        files = [f for f in os.listdir(data_dir) if f.endswith(".html")]
        
        print(f"Found {len(files)} files to inspect.")
        
        for filename in files:
            filepath = os.path.join(data_dir, filename)
            # print(f"Checking {filename}...")
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            await page.set_content(content)
            
            # The HTML file contains the message div directly? Or wrapped?
            # Based on inspection, it starts with <div class="... message ...">
            # So it is the body's first child.
            
            msg = page.locator('div[role="article"]').first
            if await msg.count() == 0:
                # print(f"Skipping {filename}: No message div found")
                continue
                
            try:
                # Mimic app.py logic loop
                raw_id = await msg.get_attribute('id') or await msg.get_attribute('data-list-item-id') or ""
                match = re.search(r'(\d{17,19})$', raw_id)
                msg_id = match.group(1) if match else raw_id.replace('chat-messages-', '').replace('message-', '')
                
                author_data = await extract_message_author(msg)
                embed_data = await extract_embed_data(msg)
                
                # Check for NoneType error usage
                # In app.py:
                # "embed_title": embed_data.get("title") if embed_data else None,
                
                # simulate what happens in app.py
                channel_url = "http://fake/123"
                plain_content = "" # Mock content extraction
                
                message_data = {
                    "id": int(msg_id) if msg_id.isdigit() else 0,
                    "channel_id": channel_url.split('/')[-1],
                    "content": clean_text(plain_content),
                    "raw_data": {
                        "author": author_data,
                        "channel_url": channel_url,
                        "embed": embed_data,
                        "has_embed": embed_data is not None
                    }
                }
                
                hash_content = {
                    "content": plain_content,
                    "embed_title": embed_data.get("title") if embed_data else None,
                    "embed_desc": embed_data.get("description") if embed_data else None
                }
                
                print(f"Processed {filename}", flush=True)
                
            except TypeError as Te:
                if str(Te) == "'NoneType' object is not subscriptable":
                    print(f"\nCRITICAL: Reproduced 'NoneType' object is not subscriptable in file: {filename}")
                    import traceback
                    traceback.print_exc()
                    return # Stop on first find
                else:
                     print(f"Other TypeError in {filename}: {Te}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                
        await browser.close()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(run())
