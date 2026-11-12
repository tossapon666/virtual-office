# ทำให้ Virtual Office ออนไลน์ถาวร (ปิดเครื่องนี้ก็ใช้ได้)

> **สถาปัตยกรรมที่แนะนำ:** Render (free) + **Turso** (ฐานข้อมูลถาวร) + **Google Drive** (ไฟล์อัปโหลดถาวร) + GitHub Actions keep-alive  
> โฟลเดอร์ `virtual-office/` พร้อม deploy (`render.yaml`, `Dockerfile`, `Procfile`, `requirements.txt`, `serve_online.py`)

## ทำไมต้อง Turso + Google Drive

Render free tier มี 2 ข้อจำกัด:
- **Sleep หลังไม่มีคนใช้ ~15 นาที** → เปิดครั้งแรกช้า 30–60 วินาที
- **Filesystem ชั่วคราว** → `office.db`, `uploads/`, settings (LINE/Sheets/Drive token) หายเมื่อ redeploy/รีสตาร์ท

แก้ด้วย:
| ส่วน | เก็บที่ | ผล |
|---|---|---|
| ฐานข้อมูล | **Turso** (libSQL cloud, free) | ข้อมูลงาน/แผนก/agent/settings อยู่ถาวร |
| ไฟล์อัปโหลด | **Google Drive** (OAuth ของบัญชีคุณเอง, 15GB ฟรี) | ไฟล์อยู่ถาวร ดาวน์โหลด/พรีวิวได้แม้เซิร์ฟเวอร์รีสตาร์ท |
| กัน sleep | **GitHub Actions cron** ping `/health` ทุก 5 นาที | ลด cold start (ไม่ใช่ always-on 100%) |

---

## 1) สร้างฐานข้อมูล Turso

1. สมัคร/ล็อกอิน https://turso.tech
2. ติดตั้ง Turso CLI (หรือใช้เว็บ dashboard):
   ```bash
   # macOS/Linux
   curl -sSfL https://get.tur.so/install.sh | bash
   # Windows (PowerShell) ใช้ WSL หรือดาวน์โหลดจาก GitHub releases
   ```
3. สร้าง DB:
   ```bash
   turso db create virtual-office
   turso db show virtual-office --url      # libsql://<db>-<org>.turso.io
   turso db tokens create virtual-office   # token
   ```
4. เก็บค่า 2 อย่างไว้: `TURSO_DATABASE_URL` และ `TURSO_AUTH_TOKEN`

> แอปรองรับชื่อ env สำรอง `LIBSQL_URL` / `LIBSQL_AUTH_TOKEN` ด้วย

## 2) ตั้ง env บน Render

Render Dashboard → service `virtual-office` → **Environment** → เพิ่ม:

| Key | Value |
|---|---|
| `TURSO_DATABASE_URL` | `libsql://<db>-<org>.turso.io` |
| `TURSO_AUTH_TOKEN` | token จากข้อ 1 |
| `OFFICE_SECRET` | ค่าสุ่มยาว (Render generate ให้ได้) |
| `OFFICE_SECURE_COOKIE` | `1` |
| `OFFICE_BEHIND_PROXY` | `1` |

หลังเพิ่ม env แล้วกด **Manual Deploy → Deploy latest commit**

## 3) ย้ายข้อมูลเดิมขึ้น Turso (ครั้งเดียว)

บนเครื่องนี้ (ต้องมี `pip install libsql`):
```powershell
cd "C:\Users\torij\Documents\Default Project\virtual-office"
$env:TURSO_DATABASE_URL = "libsql://<db>-<org>.turso.io"
$env:TURSO_AUTH_TOKEN   = "<token>"
python tools\migrate_to_turso.py --sqlite office.db --dry-run   # ดูจำนวนแถวก่อน
python tools\migrate_to_turso.py --sqlite office.db --wipe      # ย้ายจริง
```
สคริปต์จะสร้างตารางตาม schema, นำเข้าทุกตาราง และตรวจจำนวนแถวปลายทางให้

> ถ้าไม่ต้องการข้อมูลเดิม ปล่อยให้แอป seed ข้อมูลตัวอย่างอัตโนมัติเมื่อเปิดครั้งแรก

## 4) ตั้ง Google Drive สำหรับไฟล์อัปโหลด

> **สำคัญ:** ต้องใช้ **OAuth ของบัญชีผู้ใช้** (`"type": "authorized_user"`) ไม่ใช่ service account
> เพราะ service account ไม่มีโควตาที่เก็บไฟล์บน My Drive (จะได้ error `403 Service Accounts do not have storage quota`)
> แอปยังรองรับ service account แต่ใช้ได้เฉพาะกรณีมี Shared Drive ที่ให้สิทธิ์ไว้

### 4.1 เปิด API และสร้าง OAuth client

1. ไปที่ https://console.cloud.google.com → สร้าง project (เช่น `virtual-office-drive`)
2. **APIs & Services → Library** → เปิด **Google Drive API**
3. **Google Auth Platform** → ตั้ง Branding (ชื่อแอป, อีเมล, โดเมนที่อนุญาต, privacy/terms URL)
4. **Clients → Create client → Desktop app** → ดาวน์โหลด JSON (เก็บเป็นความลับ)
5. **Audience → Publish app** (ถ้าปล่อยเป็น Testing refresh token จะหมดอายุใน 7 วัน)

### 4.2 แลก refresh token (ครั้งเดียว)

รันสคริปต์ OAuth บนเครื่องนี้ (ติดตั้ง `pip install google-auth-oauthlib google-api-python-client`):

```powershell
pip install google-auth-oauthlib google-api-python-client
python tools\drive_oauth.py --client .local\secrets\oauth-client.json --out .local\secrets\drive-oauth.json
```

สคริปต์จะพิมพ์ URL ให้เปิดในเบราว์เซอร์ → เลือกบัญชี → อนุญาต
จากนั้นจะบันทึกไฟล์ token และสร้าง/ตรวจโฟลเดอร์ `Virtual Office Uploads` ให้อัตโนมัติ

```json
{
  "type": "authorized_user",
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "scopes": ["https://www.googleapis.com/auth/drive.file"],
  "account": "you@gmail.com"
}
```

> scope `drive.file` อนุญาตเฉพาะไฟล์ที่แอปสร้าง — แอปจะไม่เห็นไฟล์อื่นใน Drive ของคุณ

### 4.3 ตั้งค่าในแอป

1. ล็อกอิน → เมนู **🗄️ ที่เก็บข้อมูล**
2. ติ๊ก **เปิดใช้งาน Google Drive**
3. วาง **Folder ID** (ถ้ามี) — ถ้าเว้นว่าง แอปจะใช้/สร้างโฟลเดอร์ `Virtual Office Uploads` ใน My Drive
4. วาง **credentials JSON** (`type: authorized_user`) → **บันทึก**
5. กด **🔍 ทดสอบการเชื่อมต่อ Drive** → ต้องเห็น `OAuth (อีเมล)` และชื่อโฟลเดอร์
6. กด **⬆️ อัปโหลดไฟล์เดิมขึ้น Drive** เพื่อย้ายไฟล์เก่า (ทำซ้ำได้ ครั้งละ ≤100 ไฟล์)

> ค่า JSON ถูก mask เป็น `********` ใน UI/API — เก็บเป็นความลับ

## 5) กัน sleep ด้วย GitHub Actions

ไฟล์ `.github/workflows/keepalive.yml` ถูกเพิ่มแล้ว (ping `https://virtual-office-ncvu.onrender.com/health` ทุก 5 นาที)

- ตรวจสอบ: GitHub repo → **Actions** → `Keep Virtual Office awake` → **Run workflow**
- ทางเลือก: ใช้ [UptimeRobot](https://uptimerobot.com) free (monitor ทุก 5 นาที) ชี้ไปที่ `/health`
- ข้อจำกัด: GitHub cron อาจหน่วง และ scheduled workflow หยุดถ้า repo ไม่มี activity เกิน 60 วัน

## 6) ตรวจสอบหลัง deploy

- เปิด `https://<service>.onrender.com/health` → ต้องได้ `{"ok": true, ...}`
- ล็อกอิน → **🗄️ ที่เก็บข้อมูล** → ต้องเห็น badge **✅ Turso (ถาวร)**
- ทดสอบ: สร้างงาน → รอ/spin down → เปิดใหม่ งานยังอยู่
- อัปโหลดไฟล์ → ตรวจว่า `drive=true` และดาวน์โหลดได้

---

## ตัวเลือกโฮสต์อื่น

| ตัวเลือก | เหมาะกับ | ข้อมูลถาวร | ความยาก | ค่าใช้จ่าย |
|---|---|---|---|---|
| **Render** (แนะนำ) | ขึ้นไว มี URL ทันที | Turso + Drive = ถาวร | ง่ายมาก | ฟรี (sleep) |
| **Railway** | คล้าย Render | Volume/ภายนอก | ง่าย | เครดิตตามเงื่อนไข |
| **Fly.io** | คุม region + volume | Volume | กลาง | allowance เล็กน้อย |
| **VPS** | 24/7 คุมเต็มที่ | ดิสก์ถาวร | กลาง-ยาก | ~$4–6+/เดือน |
| **Oracle Cloud Always Free** | always-on จริง | ดิสก์ถาวร | กลาง | ฟรีถาวร (ต้องยืนยันบัตร) |

## ความปลอดภัย
- เปลี่ยนรหัสผ่าน `admin` จาก `admin123` ทันทีหลังออนไลน์
- เก็บ `OFFICE_SECRET`, `TURSO_AUTH_TOKEN`, OAuth client/token JSON และ API token (`🛠️ UI/API`) เป็นความลับ
- อย่า commit `office.db`, `uploads/`, `.secret_key`, `.env`
