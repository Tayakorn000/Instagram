import instaloader
import easyocr
import schedule
import time
import os
import shutil
import re
from datetime import datetime

# ================= CONFIGURATION =================
# ⚠️ ใส่ User/Pass IG ของคุณที่นี่
IG_USER = "ryukul0032"
IG_PASS = "XsoEllsJ001" 

TARGET_PROFILES = [
    "meanband", 
    "slapkiss.official", 
    "pun___official", 
    "zentyarb", 
    "urboytj", 
    "guncharlieee",
    "diamond.mqt"
]

# คำค้นหา (Keywords)
KEYWORDS = ["ตาราง", "schedule", "lineup", "งาน", "tour", "january", "february", "jan", "feb", "มีนา", "เมษา", "april", "march"] 
OUTPUT_FILE = "artist_schedule.txt"

print("กำลังโหลดโมเดล EasyOCR...")
reader = easyocr.Reader(['th', 'en'], gpu=False) 
# =================================================

def login_instaloader():
    """ระบบ Login แบบปลอดภัย + ลบ Session เสียอัตโนมัติ"""
    L = instaloader.Instaloader()
    
    # พยายามโหลด Session เก่าก่อน
    session_file = f"session-{IG_USER}"
    
    # ถ้ามีไฟล์ Session เก่า ให้ลองลบทิ้งก่อน เพื่อเริ่มใหม่แบบคลีนๆ (แก้ 401)
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
            print(" > (Auto-Fix) ลบ Session เก่าทิ้งเพื่อป้องกัน Error ค้าง")
        except:
            pass

    try:
        print(f" > กำลัง Login เข้าบัญชี {IG_USER}...")
        L.login(IG_USER, IG_PASS)
        print(" > Login สำเร็จ!")
    except Exception as e:
        print(f" ! Login ไม่ผ่าน: {e}")
        print("   (คำแนะนำ: หยุดรัน, เข้าแอป IG ไปกดยืนยันตัวตน, รอ 1 ชม. แล้วลองใหม่)")
        return None
        
    return L

def extract_schedule_columns(image_path):
    """ฟังก์ชันอ่านตารางงานแบบหลายคอลัมน์ (Smart Coordinate System)"""
    try:
        results = reader.readtext(image_path)
    except: return "Error reading image"

    dates_found = []
    
    # 1. หาตัวเลขวันที่ (Anchor)
    for (bbox, text, prob) in results:
        clean_text = re.sub(r'\D', '', text)
        # กรองเอาเฉพาะตัวเลข 1-2 หลัก ที่มั่นใจเกิน 40%
        if clean_text.isdigit() and 1 <= len(clean_text) <= 2 and prob > 0.4:
            (tl, tr, br, bl) = bbox
            y_center = (tl[1] + bl[1]) / 2
            x_right = tr[0]
            dates_found.append({'num': int(clean_text), 'y': y_center, 'x': x_right, 'detail': []})

    if not dates_found: return "ไม่พบตัวเลขวันที่ในภาพ (อาจเป็นเพราะฟอนต์อ่านยาก)"

    # 2. จับคู่ข้อความกับวันที่ (Nearest Neighbor Logic)
    for (bbox, text, prob) in results:
        # ข้ามตัวที่เป็นตัวเลขวันที่ไป
        if re.sub(r'\D', '', text).isdigit() and len(re.sub(r'\D', '', text)) <= 2: continue
        
        (tl, tr, br, bl) = bbox
        y = (tl[1] + bl[1]) / 2
        x = tl[0]

        best_match = None
        min_dist_x = 10000

        for d in dates_found:
            # กฏ 1: ต้องอยู่บรรทัดเดียวกัน (แกน Y ห่างกันไม่เกิน 50px)
            if abs(d['y'] - y) < 50:
                # กฏ 2: ข้อความต้องอยู่ทางขวาของวันที่ (ค่า X มากกว่า)
                dist_x = x - d['x']
                if dist_x > 0 and dist_x < min_dist_x:
                    min_dist_x = dist_x
                    best_match = d
        
        if best_match: best_match['detail'].append(text)

    # 3. เรียงตามวันที่ 1-31
    dates_found.sort(key=lambda k: k['num'])
    
    # จัดรูปแบบข้อความ Output
    final_output = []
    for d in dates_found:
        if d['detail']:
            row_text = f"วันที่ {d['num']} - {' '.join(d['detail'])}"
            final_output.append(row_text)
            
    if not final_output:
        return "อ่านข้อมูลดิบ (จับคู่ไม่ได้):\n" + " ".join([r[1] for r in results])
        
    return "\n".join(final_output)

def process_image_and_save(target_dir, artist, date_ref, source_type):
    image_path = find_image_in_folder(target_dir)
    if image_path:
        print(f"   - พบรูปจาก {source_type}! กำลังแกะข้อมูล...")
        text = extract_schedule_columns(image_path)
        save_schedule_to_file(artist, date_ref, text, f"Source: {source_type}")
        print("   - บันทึกสำเร็จ!")
        cleanup(target_dir)
        return True
    return False

def check_highlights(L, artist):
    """เช็คไฮไลท์แบบปลอดภัย (กัน Error เวอร์ชันเก่า)"""
    print(f"   - กำลังเช็ค Highlights ของ {artist}...")
    try:
        profile = instaloader.Profile.from_username(L.context, artist)
        
        # เช็คว่าเวอร์ชันนี้รองรับ highlights ไหม
        if not hasattr(profile, 'get_highlights'):
            print("     ! Instaloader เวอร์ชันนี้ไม่รองรับ Highlights (กรุณาอัปเดต: pip install -U instaloader)")
            return False

        for highlight in profile.get_highlights():
            if any(k in highlight.title.lower() for k in KEYWORDS):
                print(f"     > เจอไฮไลท์ชื่อ: {highlight.title}")
                items = list(highlight.get_items())
                if items:
                    # เอา item ล่าสุดในไฮไลท์นั้น
                    target_item = items[-1] 
                    print(f"     > โหลดรูปไฮไลท์ ({target_item.date_local})...")
                    
                    if is_already_saved(target_item.date_local, artist):
                        print("       - ข้อมูลนี้มีแล้ว ข้าม...")
                        continue

                    temp_dir = f"temp_hl_{artist}"
                    L.download_storyitem(target_item, target=temp_dir)
                    
                    if process_image_and_save(temp_dir, artist, target_item.date_local, f"Highlight: {highlight.title}"):
                        return True 
    except Exception as e:
        print(f"     ! ข้าม Highlight ({e})")
    return False

def job():
    print(f"\n[{datetime.now()}] เริ่มงาน...")
    L = login_instaloader()
    
    if not L: 
        print(" ! จบการทำงานรอบนี้เพราะ Login ไม่ได้")
        return

    for artist in TARGET_PROFILES:
        print(f"\n--- {artist} ---")
        
        # 1. ลองเช็ค Highlight ก่อน
        if check_highlights(L, artist):
            continue 

        # 2. ถ้าไม่เจอ ค่อยเช็ค Post
        print(f"   - เช็ค Post ล่าสุด...")
        try:
            profile = instaloader.Profile.from_username(L.context, artist)
            count = 0
            for post in profile.get_posts():
                if count >= 3: break
                
                caption = post.caption if post.caption else ""
                if any(w in caption.lower() for w in KEYWORDS):
                    print(f"     > เจอ Post วันที่ {post.date_local}")
                    
                    if is_already_saved(post.date_local, artist):
                        count += 1; continue
                    
                    temp_dir = f"temp_post_{artist}"
                    L.download_post(post, target=temp_dir)
                    
                    if process_image_and_save(temp_dir, artist, post.date_local, "Post"):
                        break
                count += 1
        except Exception as e:
            print(f"     ! Error เช็ค Post: {e}")
            if "401" in str(e):
                print("     !!! เจอ 401 Unauthorized - พักระบบ 2 นาที...")
                time.sleep(120)
        
        # พัก 10 วินาทีระหว่างเปลี่ยนศิลปิน เพื่อลดความเสี่ยงโดนแบน
        time.sleep(10) 

def cleanup(d): 
    try: shutil.rmtree(d) 
    except: pass

def find_image_in_folder(d):
    if not os.path.exists(d): return None
    for r, _, f in os.walk(d):
        for file in f:
            if file.endswith(".jpg"): return os.path.join(r, file)
    return None

def is_already_saved(d, a):
    if not os.path.exists(OUTPUT_FILE): return False
    with open(OUTPUT_FILE,"r",encoding="utf-8") as f: 
        content = f.read()
        return (str(d) in content and a.upper() in content)

def save_schedule_to_file(artist, date, text, src):
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*50}\nศิลปิน: {artist.upper()}\nวันที่: {date}\nที่มา: {src}\n{'-'*20}\n{text}\n{'='*50}\n")

if __name__ == "__main__":
    job()
    # ตั้งเวลาเช็คทุกๆ 6 ชั่วโมง
    schedule.every(6).hours.do(job) 
    while True: 
        schedule.run_pending()
        time.sleep(60)