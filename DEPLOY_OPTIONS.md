# ตัวเลือกทำให้ Virtual Office ออนไลน์ถาวร (ปิดเครื่องนี้ก็ใช้ได้)

> ทุกตัวเลือกต้อง deploy โฟลเดอร์ `virtual-office/` ขึ้นโฮสต์ (ไฟล์พร้อมแล้ว: `render.yaml`, `Dockerfile`, `Procfile`, `requirements.txt`, `serve_online.py`).  
> **สำคัญ (SQLite):** แอปเก็บข้อมูลใน `office.db` + `uploads/` บน filesystem — โฮสต์ที่ filesystem ไม่ถาวรจะรีเซ็ตข้อมูลเมื่อรีสตาร์ท/รีดีพลอย. เลือกแบบที่มี **persistent disk/volume** ถ้าต้องการเก็บข้อมูลจริง.

| ตัวเลือก | เหมาะกับ | ข้อมูลถาวร | ความยาก | ค่าใช้จ่ายโดยประมาณ |
|---|---|---|---|---|
| **Render** (แนะนำ เริ่มง่ายสุด) | อยากขึ้นไว มี URL ทันที | ฟรี = ไม่ถาวร (ephemeral) / เพิ่ม Disk = ถาวร (paid) | ง่ายมาก (Blueprint `render.yaml`) | มี free tier (อาจ spin down) |
| **Railway** | ใช้งานง่าย คล้าย Render | มี Volume (ดูแพลน) | ง่าย | มีแผนเริ่มต้น/เครดิตตามเงื่อนไข |
| **Fly.io** | อยากคุม infra/region + volume | มี Volume (ทำได้) | กลาง (CLI + `fly.toml`) | มี allowance เล็กน้อย/ตามการใช้ |
| **VPS** (DigitalOcean/Hetzner/Vultr ฯลฯ) | ต้องการเซิร์ฟเวอร์ของตัวเอง 24/7 คุมเต็มที่ | ถาวร (ดิสก์ VPS) | กลาง-ยาก (ตั้งเครื่อง/โดเมน/HTTPS) | ~ $4–6+/เดือน |
| **Docker host ใด ๆ** | มีโฮสต์ Docker อยู่แล้ว | ถาวรถ้า mount volume | กลาง | ตามโฮสต์ |

## แนะนำ (ผมเลือกให้): Render — ง่ายสุด
1. เอาโฟลเดอร์ `virtual-office/` ขึ้น GitHub (ไฟล์ zip พร้อม: `C:\Users\torij\Downloads\virtual-office-deploy-ready.zip`) — อย่าใส่ `office.db`, `uploads/`, `.secret_key`
2. [render.com](https://render.com) → New + → **Blueprint** → เลือก repo → Deploy (ใช้ `render.yaml`)
3. ตั้ง env: `OFFICE_SECURE_COOKIE=1`, `OFFICE_BEHIND_PROXY=1` (HTTPS). เปลี่ยนรหัสผ่าน `admin` ทันที
4. ต้องการข้อมูลไม่หาย: ใช้ Render **Persistent Disk** แล้วตั้ง `OFFICE_DB=/data/office.db`, `OFFICE_UPLOADS=/data/uploads` (แผนที่รองรับ disk)

## Render vs ทางอื่น (สรุปสั้น)
- **เร็ว/ง่ายสุด:** Render (Blueprint)
- **อยาก volume/cum control บน container:** Fly.io (`fly.toml` + Dockerfile พร้อม)
- **อยากเป็น “เซิร์ฟเวอร์ของเรา” จริง ๆ 24/7:** VPS + Docker/`serve_online.py`

## env ที่ควรตั้งบนโฮสต์
- `OFFICE_SECRET` (สุ่ม/ยาว), `PORT` (โฮสต์กำหนด), `OFFICE_SECURE_COOKIE=1`, `OFFICE_BEHIND_PROXY=1` (เมื่ออยู่หลัง HTTPS)
- ถาวรข้อมูล: `OFFICE_DB`, `OFFICE_UPLOADS` ชี้ไป volume/disk
- เปลี่ยนรหัสผ่าน admin หลัง deploy ทันที และเก็บ API token (`เมนู UI/API`) เป็นความลับ
