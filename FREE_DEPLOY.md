# ทำให้ Virtual Office ออนไลน์ “ฟรี” (ปิดเครื่องนี้ก็ใช้ได้)

> สรุปสั้น: ใช้ **Render free** เป็นตัวรันแอป + **Turso** เก็บฐานข้อมูล + **Google Drive** เก็บไฟล์ + **GitHub Actions** ping กัน sleep  
> รายละเอียดทุกขั้นตอนอยู่ใน [`DEPLOY_OPTIONS.md`](DEPLOY_OPTIONS.md)

## ทำไมต้องทำแบบนี้
Render free tier:
- **หลับหลังไม่มีคนใช้ ~15 นาที** → เปิดครั้งแรกช้า (แก้ด้วย keep-alive ping)
- **ดิสก์ชั่วคราว** → ข้อมูล/ไฟล์หายเมื่อ redeploy (แก้ด้วย Turso + Drive)

## ขั้นตอนย่อ

### 1. ขึ้น GitHub
- อัปโหลดไฟล์ในโฟลเดอร์ `virtual-office/` ขึ้น repo (ยกเว้น `office.db`, `uploads/`, `.secret_key`, `.env`)
- repo ตัวอย่าง: `https://github.com/tossapon666/virtual-office`

### 2. Deploy บน Render
- https://render.com → **New + → Blueprint** → เลือก repo → Apply
- รอ build → ได้ URL เช่น `https://virtual-office-ncvu.onrender.com`

### 3. ตั้ง env
| Key | Value |
|---|---|
| `TURSO_DATABASE_URL` | จาก Turso |
| `TURSO_AUTH_TOKEN` | จาก Turso |
| `OFFICE_SECRET` | ค่าสุ่มยาว |
| `OFFICE_SECURE_COOKIE` | `1` |
| `OFFICE_BEHIND_PROXY` | `1` |

### 4. สร้าง Turso + ย้ายข้อมูล
```powershell
turso db create virtual-office
turso db show virtual-office --url
turso db tokens create virtual-office

cd "C:\Users\torij\Documents\Default Project\virtual-office"
$env:TURSO_DATABASE_URL = "libsql://<db>-<org>.turso.io"
$env:TURSO_AUTH_TOKEN   = "<token>"
python tools\migrate_to_turso.py --sqlite office.db --wipe
```

### 5. ตั้ง Google Drive
- Google Cloud → เปิด Drive API → Service account → JSON key
- แชร์โฟลเดอร์ Drive ให้ `client_email` เป็น Editor
- ในแอป → **🗄️ ที่เก็บข้อมูล** → วาง JSON + Folder ID → บันทึก → ทดสอบ → อัปโหลดไฟล์เดิม

### 6. กัน sleep
- `.github/workflows/keepalive.yml` ping `/health` ทุก 5 นาที
- ทางเลือก: UptimeRobot free ชี้ไปที่ `/health`

### 7. ตรวจสอบ
- `/health` → `{"ok": true}`
- **🗄️ ที่เก็บข้อมูล** → badge **✅ Turso (ถาวร)**
- สร้างงาน/อัปโหลดไฟล์ → รีสตาร์ท → ข้อมูลยังอยู่

## ความปลอดภัย
- เปลี่ยนรหัสผ่าน `admin123` ทันทีหลังออนไลน์
- อย่าเผย `OFFICE_SECRET`, `TURSO_AUTH_TOKEN`, service account JSON, API token
