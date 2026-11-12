"""สร้าง OAuth token สำหรับอัปโหลดไฟล์ขึ้น Google Drive (ทำครั้งเดียว).

ทำไมต้อง OAuth ไม่ใช่ service account:
    service account ไม่มีโควตาที่เก็บไฟล์บน My Drive → อัปโหลดจะได้
    403 "Service Accounts do not have storage quota"

ขั้นตอน:
  1. เปิด Google Drive API ใน Google Cloud project
  2. สร้าง OAuth client ชนิด "Desktop app" แล้วดาวน์โหลด JSON
  3. รันสคริปต์นี้ เปิด URL ที่พิมพ์ออกมา เลือกบัญชี แล้วกดอนุญาต
  4. ได้ไฟล์ token (type: authorized_user) → วางในเมนู "🗄️ ที่เก็บข้อมูล"

วิธีใช้ (Windows PowerShell):
  python tools\\drive_oauth.py --client .local\\secrets\\oauth-client.json --out .local\\secrets\\drive-oauth.json

ตัวเลือก:
  --client PATH   ไฟล์ OAuth client JSON จาก Google Cloud (ค่าเริ่มต้น: .local/secrets/oauth-client.json)
  --out PATH      ไฟล์ปลายทางสำหรับ token (ค่าเริ่มต้น: .local/secrets/drive-oauth.json)
  --port N        พอร์ต localhost ที่รอรับ callback (ค่าเริ่มต้น: 5131)
  --folder NAME   ชื่อโฟลเดอร์ใน Drive ที่จะใช้/สร้าง (ค่าเริ่มต้น: Virtual Office Uploads)
  --no-folder     ไม่ต้องสร้าง/ตรวจโฟลเดอร์ แค่บันทึก token

หมายเหตุ: ต้องติดตั้ง google-auth-oauthlib และ google-api-python-client
"""
import argparse
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCOPE = "https://www.googleapis.com/auth/drive.file"

code_holder = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            code_holder["code"] = params["code"][0]
            body = "<h2>เชื่อมต่อ Google Drive สำเร็จ</h2><p>ปิดแท็บนี้ได้เลย</p>".encode("utf-8")
            self.send_response(200)
        else:
            code_holder["error"] = params.get("error", ["unknown"])[0]
            body = f"<h2>เชื่อมต่อไม่สำเร็จ: {code_holder['error']}</h2>".encode("utf-8")
            self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="สร้าง Google Drive OAuth token (authorized_user)")
    parser.add_argument("--client", default=str(BASE_DIR / ".local" / "secrets" / "oauth-client.json"))
    parser.add_argument("--out", default=str(BASE_DIR / ".local" / "secrets" / "drive-oauth.json"))
    parser.add_argument("--port", type=int, default=5131)
    parser.add_argument("--folder", default="Virtual Office Uploads")
    parser.add_argument("--no-folder", action="store_true")
    args = parser.parse_args()

    client_file = Path(args.client)
    if not client_file.exists():
        print(f"ไม่พบไฟล์ OAuth client: {client_file}", file=sys.stderr)
        return 1

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        print("ต้องติดตั้งก่อน: pip install google-auth-oauthlib google-api-python-client", file=sys.stderr)
        return 1

    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    flow = Flow.from_client_secrets_file(str(client_file), scopes=[SCOPE])
    flow.redirect_uri = f"http://localhost:{args.port}/"
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    print("เปิด URL นี้ในเบราว์เซอร์แล้วอนุญาต:\n")
    print(auth_url, flush=True)

    server = HTTPServer(("127.0.0.1", args.port), _Handler)
    server.handle_request()
    server.server_close()

    if "code" not in code_holder:
        print(f"ไม่ได้รับ code: {code_holder.get('error', 'timeout')}", file=sys.stderr)
        return 1

    flow.fetch_token(code=code_holder["code"])
    creds = flow.credentials

    info = {
        "type": "authorized_user",
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri or "https://oauth2.googleapis.com/token",
        "scopes": list(creds.scopes or [SCOPE]),
    }

    out_file = Path(args.out)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if not args.no_folder:
        try:
            from googleapiclient.discovery import build

            svc = build("drive", "v3", credentials=creds, cache_discovery=False)
            q = (
                f"name = '{args.folder}' and mimeType = 'application/vnd.google-apps.folder' "
                "and trashed = false"
            )
            found = svc.files().list(q=q, fields="files(id,name)", pageSize=10).execute().get("files", [])
            if found:
                folder_id = found[0]["id"]
                print("ใช้โฟลเดอร์เดิม:", folder_id)
            else:
                folder = svc.files().create(
                    body={"name": args.folder, "mimeType": "application/vnd.google-apps.folder"},
                    fields="id",
                ).execute()
                folder_id = folder["id"]
                print("สร้างโฟลเดอร์ใหม่:", folder_id)
            info["folder_id"] = folder_id
            about = svc.about().get(fields="user(displayName,emailAddress)").execute()
            user = about.get("user", {})
            info["account"] = user.get("emailAddress", "")
            print("บัญชี:", user.get("displayName", ""), user.get("emailAddress", ""))
        except Exception as exc:  # ไม่ให้ token ที่ได้มาสูญเปล่า
            print("ตรวจโฟลเดอร์ไม่สำเร็จ (ยังบันทึก token ได้):", str(exc)[:200])

    out_file.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nบันทึก token ที่:", out_file)
    print("นำเนื้อหา JSON ไปวางในเมนู '🗄️ ที่เก็บข้อมูล' ของแอป")
    return 0


if __name__ == "__main__":
    sys.exit(main())
