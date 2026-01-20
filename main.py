import os
import shutil
import re
import random
import time
import easyocr
from instagrapi import Client

# ================= CONFIGURATION =================
IG_USER = "ryukul0032"
IG_PASS = "XsoEllsJ001" 

TARGET_PROFILES = [
    "meanband", "slapkiss.official", "pun___official", 
    "zentyarb", "urboytj", "guncharlieee", "diamond.mqt"
]

KEYWORDS = ["ตาราง", "schedule", "lineup", "งาน", "tour", "january", "february", "jan", "feb", "มีนา", "เมษา", "april", "march"] 
OUTPUT_FILE = "artist_schedule_mobile.txt"

print("กำลังโหลดโมเดล EasyOCR...")
reader = easyocr.Reader(['th', 'en'], gpu=False)

# ================= SYSTEM FUNCTIONS =================

def extract_text_from_image(image_path):
    """แกะตัวหนังสือจากภาพ"""
    try: results = reader.readtext(image_path)
    except: return "Error reading image"
    
    dates_found = []
    for (bbox, text, prob) in results:
        clean_text = re.sub(r'\D', '', text)
        if clean_text.isdigit() and 1 <= len(clean_text) <= 2 and prob > 0.4:
            (tl, tr, br, bl) = bbox
            dates_found.append({'num': int(clean_text), 'y': (tl[1]+bl[1])/2, 'x': tr[0], 'detail': []})

    if not dates_found: return "ไม่พบตัวเลขวันที่"

    for (bbox, text, prob) in results:
        if re.sub(r'\D', '', text).isdigit() and len(re.sub(r'\D', '', text)) <= 2: continue
        (tl, tr, br, bl) = bbox
        y, x = (tl[1]+bl[1])/2, tl[0]
        
        best_match = None; min_dist_x = 10000
        for d in dates_found:
            if abs(d['y'] - y) < 50:
                dist_x = x - d['x']
                if 0 < dist_x < min_dist_x: min_dist_x = dist_x; best_match = d
        if best_match: best_match['detail'].append(text)

    dates_found.sort(key=lambda k: k['num'])
    final_output = [f"วันที่ {d['num']} - {' '.join(d['detail'])}" for d in dates_found if d['detail']]
    return "\n".join(final_output)

def get_latest_posts_raw(cl, user_id, amount=3):
    """
    ดึงข้อมูลดิบโดยไม่ผ่าน Pydantic Validation (แก้บั๊ก Crash)
    """
    posts = []
    try:
        # ยิง Request ไปที่ API มือถือโดยตรง
        resp = cl.private_request(f"feed/user/{user_id}/")
        items = resp.get("items", [])
        
        for item in items[:amount]:
            # แกะข้อมูลเองด้วยมือ (ปลอดภัยกว่า)
            pk = item.get("pk")
            code = item.get("code")
            taken_at = item.get("taken_at")
            
            # หา Caption
            caption_text = ""
            if item.get("caption"):
                caption_text = item["caption"].get("text", "")
            
            # หา URL รูปภาพ (รองรับทั้งรูปเดี่ยวและอัลบั้ม)
            image_url = None
            if "image_versions2" in item:
                candidates = item["image_versions2"].get("candidates", [])
                if candidates:
                    image_url = candidates[0].get("url")
            elif "carousel_media" in item: # กรณีเป็นอัลบั้ม
                if item["carousel_media"]:
                     candidates = item["carousel_media"][0]["image_versions2"].get("candidates", [])
                     if candidates:
                        image_url = candidates[0].get("url")
            
            if pk and image_url:
                posts.append({
                    "pk": pk,
                    "code": code,
                    "taken_at": taken_at,
                    "caption_text": caption_text,
                    "image_url": image_url
                })
    except Exception as e:
        print(f"⚠️ Error fetching raw posts: {e}")
        
    return posts

def main():
    print("🚀 เริ่มทำงาน (Mode: Mobile API - Raw Fetch)...")
    cl = Client()
    cl.delay_range = [2, 5]
    
    # 1. Login
    print(f"🔑 กำลัง Login เข้าบัญชี {IG_USER}...")
    try:
        cl.login(IG_USER, IG_PASS)
        print("✅ Login สำเร็จ!")
    except Exception as e:
        print(f"❌ Login ไม่ผ่าน: {e}")
        return

    # 2. เริ่มวนลูปศิลปิน
    for artist in TARGET_PROFILES:
        print(f"\n--- {artist} ---")
        try:
            user_id = cl.user_id_from_username(artist)
            print(f"   > User ID: {user_id}")
            
            # ใช้ฟังก์ชันดึงดิบแทนฟังก์ชันมาตรฐาน
            medias = get_latest_posts_raw(cl, user_id, amount=3)
            
            for i, media in enumerate(medias):
                caption_text = media["caption_text"].lower()
                
                if any(k in caption_text for k in KEYWORDS):
                    print(f"     > 📅 เจอโพสต์ (ID: {media['pk']})")
                    
                    temp_path = f"temp_{artist}_{i}.jpg"
                    
                    # โหลดรูปจาก URL โดยตรง (ใช้ download helper ของ cl ก็ได้แต่นี่ชัวร์กว่า)
                    print("       📥 กำลังโหลดรูป...")
                    cl.photo_download(int(media['pk']), folder=".")
                    
                    # หาไฟล์ที่เพิ่งโหลดมา (instagrapi ชอบตั้งชื่อไฟล์ยาวๆ)
                    # เราจะ Rename ให้เป็นชื่อที่เราต้องการ
                    for f in os.listdir("."):
                        if f.endswith(".jpg") and str(media['pk']) in f:
                            # ลบไฟล์เก่าถ้ามี
                            if os.path.exists(temp_path): os.remove(temp_path)
                            os.rename(f, temp_path)
                            break
                    
                    if not os.path.exists(temp_path):
                        print("       ❌ หาไฟล์รูปไม่เจอ ข้าม...")
                        continue

                    # ส่งไปแกะ OCR
                    print("       📖 กำลังแกะข้อมูล...")
                    text = extract_text_from_image(temp_path)
                    
                    link = f"https://www.instagram.com/p/{media['code']}/"
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                        f.write(f"\n{'='*40}\nศิลปิน: {artist}\nลิงก์: {link}\nที่มา: Mobile API (Raw)\n{'-'*20}\n{text}\n{'='*40}\n")
                    
                    print("       ✅ บันทึกเสร็จเรียบร้อย!")
                    
                    if os.path.exists(temp_path): os.remove(temp_path)
                    break 
                
            s = random.randint(5, 10)
            print(f"   - 💤 พัก {s} วินาที...")
            time.sleep(s)

        except Exception as e:
            print(f"   ❌ ข้าม {artist}: {e}")

    print("\n🏁 จบการทำงาน")

if __name__ == "__main__":
    main()