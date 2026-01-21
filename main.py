import os
import shutil
import re
import random
import time
import requests
import easyocr
import cv2
import numpy as np
from instagrapi import Client

# ================= CONFIGURATION =================
DISCORD_BOT_TOKEN = "<DISCORD_BOT_TOKEN>"
DISCORD_CHANNEL_ID = "<DISCORD_CHANNEL_ID>"

IG_USER = "<IG_USERNAME>"
IG_PASS = "<IG_PASSWORD>"

TARGET_PROFILES = [
    "meanband", "slapkiss.official", "pun___official", 
    "zentyarb", "urboytj", "guncharlieee", "diamond.mqt"
]

VALIDATION_KEYWORDS = [
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "มกรา", "กุมภา", "มีนา", "เมษา", "พฤษภา", "มิถุนา", 
    "2026", "schedule", "lineup", "tour", "bar", "fest", "music", "live", "concert",
    "ticket", "door", "show"
]

# Keyword
KEYWORDS = ["ตาราง", "schedule", "lineup", "งาน", "tour", "update", "jan", "feb", "มีนา"]

print(" Initializing EasyOCR ...")
reader = easyocr.Reader(['en', 'th'], gpu=False)

# ================= SORTING LOGIC =================

def sort_boxes_multicolumn(boxes, image_width):
    mid_point = image_width / 2
    
    left_col = []
    right_col = []
    
    for box in boxes:
        # box format: ([[tl, tr, br, bl], text, prob])
        (tl, tr, br, bl) = box[0]
        x_center = (tl[0] + tr[0]) / 2
        if x_center < mid_point:
            left_col.append(box)
        else:
            right_col.append(box)
    left_col.sort(key=lambda r: r[0][0][1])  
    right_col.sort(key=lambda r: r[0][0][1]) 
    
    return left_col + right_col

def extract_schedule_final(image_path):
    # 1. Image Preprocessing
    try:
        img = cv2.imread(image_path)
        img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        h, w, _ = img.shape
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        proc_path = image_path.replace(".jpg", "_proc.jpg")
        cv2.imwrite(proc_path, enhanced)
        target_img = proc_path
    except:
        target_img = image_path
        h, w = 1000, 1000

    # 2. Run OCR
    try:
        raw_results = reader.readtext(target_img, detail=1)
    except Exception as e:
        print(f"       ❌ OCR Error: {e}")
        return None
    finally:
        if os.path.exists(proc_path): os.remove(proc_path)

    # 3. Validation Check
    all_text = " ".join([r[1].lower() for r in raw_results])
    valid_score = sum(1 for k in VALIDATION_KEYWORDS if k in all_text)
    date_count = len(re.findall(r'\b(0?[1-9]|[12][0-9]|3[01])\b', all_text))
    
    if valid_score < 1 and date_count < 3:
        print(f"       ⚠️ Junk Filter: รูปนี้ไม่มี keyword ตารางงาน (Score: {valid_score}, Dates: {date_count})")
        return None

    # 4. Left-Right Column Sorting
    sorted_results = sort_boxes_multicolumn(raw_results, w)

    # 5. Text Parsing
    schedule_list = []
    
    for (bbox, text, prob) in sorted_results:
        text = text.strip()
        if len(text) < 2: continue

        # Regex หา Date: ขึ้นต้นด้วยเลข 1-2 หลัก (01-31)
        # รองรับ format: "17 UrboyTJ", "24 | Music Fest", "31 jan"
        match = re.match(r'^(\d{1,2})\s*[:|\-]?\s*(.*)', text)
        
        if match:
            d_str = match.group(1)
            detail = match.group(2).strip()
            
            day = int(d_str)
            if 1 <= day <= 31:
                if not detail:
                    detail = "รายละเอียดตามภาพ" 
                if day == 20 and "26" in detail: continue 
                
                schedule_list.append({'num': day, 'detail': detail})

    return schedule_list

# ================= DISCORD =================

def send_discord_card(artist, source_type, link, schedule_data, image_path):
    if not DISCORD_BOT_TOKEN: return

    url = f"https://discord.com/api/v9/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    
    description = ""
    if schedule_data:
        for item in schedule_data:
            # Check Update status
            is_update = "update" in item['detail'].lower()
            icon = "🆕" if is_update else "🗓️"
            
            # Clean text
            clean_text = re.sub(r'(?i)update', '', item['detail']).strip()
            if len(clean_text) < 2: clean_text = "Check Image"
            
            # ตัดข้อความยาวเกินไป
            if len(clean_text) > 40: clean_text = clean_text[:37] + "..."
            
            description += f"`{item['num']:02d}` | {clean_text} {icon}\n"
    else:
        description = "⚠️ อ่านข้อมูลแบบ Text ไม่สำเร็จ โปรดดูภาพประกอบ"

    embed = {
        "title": f"🎤 {artist.upper()} - Schedule",
        "description": f"**Source:** {source_type}\n[Open Post]({link})\n\n{description}",
        "color": 15158332,
        "footer": {"text": f"Concert Reade • {time.strftime('%H:%M')}"}
    }

    try:
        import json
        payload = json.dumps({"embeds": [embed]})
        with open(image_path, 'rb') as f:
            files = {'file': (os.path.basename(image_path), f, 'image/jpeg')}
            requests.post(url, headers=headers, data={'payload_json': payload}, files=files)
            print("       🔔 Discord Sent!")
    except Exception as e:
        print(f"       ⚠️ Discord Error: {e}")

# ================= MAIN LOOP =================

def get_latest_posts_raw(cl, user_id, amount=3):
    posts = []
    try:
        data = cl.private_request(f"feed/user/{user_id}/")
        items = data.get("items", [])
        for item in items[:amount]:
            pk = item.get("pk")
            code = item.get("code")
            caption = item.get("caption", {}).get("text", "") if item.get("caption") else ""
            
            img_url = None
            # Logic 
            if "image_versions2" in item:
                img_url = item["image_versions2"]["candidates"][0]["url"]
            elif "carousel_media" in item:
                img_url = item["carousel_media"][0]["image_versions2"]["candidates"][0]["url"]
            
            if pk and img_url:
                posts.append({"pk": pk, "code": code, "caption": caption, "url": img_url})
    except: pass
    return posts

def get_highlight_stories_raw(cl, highlight_id):
    stories = []
    try:
        data = cl.private_request(f"feed/reels_media/?reel_ids=highlight:{highlight_id}")
        reels = data.get("reels", {})
        hl_data = reels.get(f"highlight:{highlight_id}", {})
        items = hl_data.get("items", [])
        if items:
            last_item = items[-1]
            if "image_versions2" in last_item:
                url = last_item["image_versions2"]["candidates"][0]["url"]
                stories.append({"pk": last_item["pk"], "code": last_item.get("code", ""), "url": url})
    except: pass
    return stories

def process_and_send(cl, item, artist, source_type):
    print(f" Downloading {source_type}...")
    try:
        r = requests.get(item['url'], stream=True)
        if r.status_code == 200:
            temp_path = f"temp_{artist}_{item['pk']}.jpg"
            with open(temp_path, 'wb') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)
            
            print(" Analyzing ...")
            schedule_list = extract_schedule_final(temp_path)
            
            if schedule_list is not None: 
                print(f" Valid Schedule Found ({len(schedule_list)} dates)")
                link = f"https://www.instagram.com/p/{item['code']}/" if source_type == "Post" else f"https://www.instagram.com/stories/{artist}/{item['pk']}/"
                send_discord_card(artist, source_type, link, schedule_list, temp_path)
            else:
                print(" Ignored")
            
            if os.path.exists(temp_path): os.remove(temp_path)
            return True
    except Exception as e:
        print(f" Error: {e}")
    return False

def main():
    print("System Start")
    cl = Client()
    cl.delay_range = [3, 7]
    
    try:
        cl.login(IG_USER, IG_PASS)
        print("Login Successful")
    except Exception as e:
        print(f"Login Failed: {e}")
        return

    for artist in TARGET_PROFILES:
        print(f"\nTarget: {artist}")
        found = False
        
        try:
            user_info = cl.user_info_by_username_v1(artist)
            user_id = user_info.pk
            
            # 1. Feed
            print("   🔎 Checking Feed...")
            posts = get_latest_posts_raw(cl, user_id, amount=5)
            for post in posts:
                if any(k in post['caption'].lower() for k in KEYWORDS):
                    print(f"     > 📸 Inspecting Post ID: {post['pk']}")
                    process_and_send(cl, post, artist, "Post")
                    found = True
                    break
            
            # 2. Highlights
            if not found:
                print(" Feed empty. Checking Highlights...")
                highlights = cl.user_highlights_v1(user_id)
                target_hl = None
                for hl in highlights:
                    if any(k in hl.title.lower() for k in KEYWORDS):
                        target_hl = hl
                        break
                
                if target_hl:
                    print(f" Inspecting Highlight: '{target_hl.title}'")
                    stories = get_highlight_stories_raw(cl, target_hl.pk)
                    if stories:
                        process_and_send(cl, stories[0], artist, f"Highlight: {target_hl.title}")
                        found = True
                else:
                    print(" No relevant highlights.")

            if not found: print(" No schedule found.")
            
            time.sleep(random.randint(5, 10))

        except Exception as e:
            print(f" Skip {artist}: {e}")

    print("\n Mission Complete.")

if __name__ == "__main__":
    main()