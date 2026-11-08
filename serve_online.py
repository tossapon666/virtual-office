"""รัน Virtual Office แบบพร้อมใช้งาน/ออนไลน์ (รองรับ Windows)
- ใช้ waitress ถ้ามี, ไม่งั้น fallback เป็น Flask dev server (bind 0.0.0.0)
- ตั้ง PORT/OFFICE_HOST ได้ผ่าน env
"""
import os
from app import app

host = os.environ.get("OFFICE_HOST", "0.0.0.0")
port = int(os.environ.get("PORT", "5100"))

if __name__ == "__main__":
    try:
        from waitress import serve
        print(f"\n  Virtual Office (waitress) - http://localhost:{port}  (LAN: http://{host}:{port})\n")
        serve(app, host=host, port=port)
    except Exception:
        print(f"\n  Virtual Office (flask dev) - http://localhost:{port}\n")
        app.run(host=host, port=port, debug=False)
