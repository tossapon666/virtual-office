# ทำให้ Virtual Office ออนไลน์

แอปนี้เป็น Flask + SQLite (ไฟล์ `office.db`) มีล็อกอิน (`admin`/`admin123` ค่าเริ่มต้น) — **ควรเปลี่ยนรหัสผ่าน** ก่อนเปิดออนไลน์

## 1) ใช้งานในวง LAN (ออนไลน์ในเครือข่ายเดียวกัน) — ทำได้ทันที
เซิร์ฟเวอร์รันที่ `0.0.0.0:5100` แล้ว เข้าได้ที่:
- เครื่องนี้: `http://localhost:5100`
- เครื่องอื่นใน LAN: `http://<IP-เครื่องนี้>:5100` (เช่น `http://192.168.1.37:5100`)

ถ้าเข้าไม่ได้ ให้เปิดไฟร์วอลล์พอร์ต 5100 (รัน PowerShell แบบ Administrator):
```powershell
netsh advfirewall firewall add rule name="Virtual Office 5100" dir=in action=allow protocol=TCP localport=5100
```

## 2) ออนไลน์บนอินเทอร์เน็ตชั่วคราว (Quick Tunnel)
ต้องมีเครื่องมือนอก (เลือกอย่างใดอย่างหนึ่ง) แล้วชี้ไปที่พอร์ต 5100:
- Cloudflare Tunnel: ติดตั้ง `cloudflared` แล้วรัน `cloudflared tunnel --url http://localhost:5100`
- localtunnel (มี Node): `npx --yes localtunnel --port 5100`
- ngrok: `ngrok http 5100`

> หมายเหตุ: URL ชั่วคราว และการเปิด tunnel ทำให้เข้าถึงได้จากอินเทอร์เน็ต — **เปลี่ยนรหัสผ่าน** และรักษา `API token` (เมนู UI/API) เป็นความลับ

## 3) Deploy ขึ้นโฮสต์ (ออนไลน์ถาวร)
- ติดตั้ง: `pip install -r requirements.txt`
- รัน production: `python serve_online.py` (หรือ `waitress-serve --host=0.0.0.0 --port=$PORT app:app`)
- ตัวแปรแวดล้อมที่ควรตั้ง: `OFFICE_SECRET` (secret key), `OFFICE_PASSWORD` (รหัสผ่านเริ่มต้น/seed), `PORT`
- **ข้อมูลถาวร (แนะนำ):** ตั้ง `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` เพื่อเก็บ DB บน Turso และตั้ง Google Drive ในเมนู **🗄️ ที่เก็บข้อมูล** สำหรับไฟล์อัปโหลด — ดู [`DEPLOY_OPTIONS.md`](DEPLOY_OPTIONS.md)
- แพลตฟอร์มที่รองรับ Python (Render/Railway/Fly.io/VPS) ใช้ start command: `python serve_online.py`
- ข้อควรระวัง: ถ้าไม่ตั้ง Turso/Drive ข้อมูล `office.db` และ `uploads/` จะอยู่ใน filesystem ของโฮสต์ — บนโฮสต์ที่ filesystem ไม่ถาวร ข้อมูลอาจหายเมื่อรีสตาร์ท

## 4) ให้ AI ตัวอื่นจัดการหน้าแอปได้ (ข้ามอินเทอร์เน็ต)
เมื่อออนไลน์แล้ว ให้ AI เรียก `https://<โดเมนของคุณ>/api/ui-config` พร้อม header `X-Office-Token: <token>` (ดู token ในเมนู `🛠️ UI/API`)
