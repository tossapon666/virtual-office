"""Virtual Office — เว็บแอปออฟฟิศเสมือนที่มีทีม AI ทำงานแทนคุณ."""
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask, g, jsonify, redirect, render_template, request, send_file,
    send_from_directory, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import agents as agent_engine
import db as database

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = database.UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv",
    ".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".zip", ".rar",
    ".7z", ".json",
}

WIDGET_TYPES = {
    "overview": "ภาพรวมวันนี้",
    "today": "งานที่ต้องทำวันนี้",
    "overdue": "งานเกินกำหนด",
    "upcoming": "งานกำลังจะถึง",
    "workload": "ภาระงานแต่ละแผนก",
    "team": "สถานะทีม AI",
    "docs": "เอกสารล่าสุด",
    "quickadd": "เพิ่มงานเร็ว",
    "calendar": "ปฏิทินย่อ",
    "activity": "กิจกรรมล่าสุด",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
# Set OFFICE_SECURE_COOKIE=1 when serving over HTTPS (e.g. Render/Railway/tunnel)
if os.environ.get("OFFICE_SECURE_COOKIE") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True
# Trust proxy headers when deployed behind a reverse proxy
if os.environ.get("OFFICE_BEHIND_PROXY") == "1":
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    except Exception:
        pass


def _secret_key():
    env = os.environ.get("OFFICE_SECRET")
    if env:
        return env
    path = BASE_DIR / ".secret_key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = uuid.uuid4().hex + uuid.uuid4().hex
    path.write_text(value, encoding="utf-8")
    return value


app.secret_key = _secret_key()
database.init_db()


def get_db():
    if "db" not in g:
        g.db = database.connect()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify(error="unauthorized"), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def current_user(conn):
    uid = session.get("uid")
    if not uid:
        return None
    return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def rows(rows_):
    return [dict(r) for r in rows_]


def log(conn, actor, action, detail=""):
    conn.execute(
        "INSERT INTO activity (actor, action, detail) VALUES (?,?,?)",
        (actor, action, detail),
    )


# ---------------------------------------------------------------------------
# UI Config (ให้ AI/ระบบภายนอกจัดการหน้าแอปได้อย่างปลอดภัย ผ่าน config)
# ---------------------------------------------------------------------------
import re as _re

_UI_AREAS = {"manager", "secretary", "accounting", "documents", "archive", "operations", "stock"}
_UI_COLOR_RE = _re.compile(r"^#[0-9a-fA-F]{3,8}$|^rgba?\([0-9., %]+\)$|^hsla?\([0-9., %deg]+\)$")


def _ui_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not row or row["value"] is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def _ui_set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def _ui_default_config(conn=None):
    # rooms keyed by department name (stable in seed); frontend also accepts dept id keys
    return {
        "version": 1,
        "floor": {
            "title": "🏢 ผังออฟฟิศ (ห้องแยกแผนก · พาร์ติชันกั้น)",
            "subtitle": "คลิกสมาชิกเพื่อคุย/ดูข้อมูล · คลิกห้องแผนกเพื่อดูรายละเอียด",
            "showStats": True,
        },
        "manager": {"label": "ห้องผู้จัดการ", "visible": True},
        "note": "💡 แต่ละห้องกั้นด้วยพาร์ติชัน/ผนังเรืองแสง · สมาชิกทุกคนมีโต๊ะทำงาน · คลิกสมาชิก = คุย/สั่งงาน AI, คลิกห้อง = รายละเอียดแผนก, คลิกห้องผู้จัดการ = แดชบอร์ด",
        "rooms": {},
    }


def _safe_text(val, maxlen=120):
    if val is None:
        return None
    s = str(val).strip()
    if len(s) > maxlen:
        s = s[:maxlen]
    return s


def _safe_color(val):
    s = _safe_text(val, 40)
    if not s:
        return None
    return s if _UI_COLOR_RE.match(s) else None


def _sanitize_ui_config(raw, conn=None):
    """Whitelist + validate config from API/AI. Never allows code."""
    base = _ui_default_config(conn)
    if not isinstance(raw, dict):
        return base
    out = {"version": 1}
    floor = raw.get("floor") if isinstance(raw.get("floor"), dict) else {}
    out["floor"] = {
        "title": _safe_text(floor.get("title"), 140) or base["floor"]["title"],
        "subtitle": _safe_text(floor.get("subtitle"), 200) or base["floor"]["subtitle"],
        "showStats": bool(floor.get("showStats", True)),
    }
    mgr = raw.get("manager") if isinstance(raw.get("manager"), dict) else {}
    out["manager"] = {
        "label": _safe_text(mgr.get("label"), 80) or base["manager"]["label"],
        "visible": bool(mgr.get("visible", True)),
    }
    out["note"] = _safe_text(raw.get("note"), 400) or base["note"]
    rooms = {}
    raw_rooms = raw.get("rooms") if isinstance(raw.get("rooms"), dict) else {}
    # map allowed areas by dept name for validation
    area_by_name = {
        "สำนักเลขา": "secretary", "ฝ่ายบัญชี": "accounting", "ฝ่ายเอกสาร": "documents",
        "คลังเอกสารและไฟล์": "archive", "ฝ่ายปฏิบัติการ": "operations", "แผนกสต็อก": "stock",
    }
    for key, rv in list(raw_rooms.items())[:30]:
        if not isinstance(rv, dict):
            continue
        k = _safe_text(key, 80)
        if not k:
            continue
        item = {}
        if "label" in rv:
            item["label"] = _safe_text(rv.get("label"), 80)
        if "sign" in rv:
            item["sign"] = _safe_text(rv.get("sign"), 120)
        if "subtitle" in rv:
            item["subtitle"] = _safe_text(rv.get("subtitle"), 140)
        color = _safe_color(rv.get("color"))
        if color:
            item["color"] = color
        if "visible" in rv:
            item["visible"] = bool(rv.get("visible"))
        for posk in ("x", "y", "w"):
            if posk in rv:
                try:
                    v = float(rv.get(posk))
                    if 0 <= v <= 100:
                        item[posk] = round(v, 2)
                except Exception:
                    pass
        area = _safe_text(rv.get("area"), 30)
        if area and area in _UI_AREAS:
            # only allow assigning an area that matches this room's identity (prevent breaking layout badly)
            default_area = area_by_name.get(k)
            if default_area is None or area == default_area:
                item["area"] = area
        rooms[k] = item
    out["rooms"] = rooms
    return out


def get_ui_config(conn):
    saved = _ui_setting(conn, "ui_config", None)
    if not saved:
        return _ui_default_config(conn)
    return _sanitize_ui_config(saved, conn)


def save_ui_config(conn, raw, actor="system"):
    cfg = _sanitize_ui_config(raw, conn)
    cfg["_meta"] = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "updated_by": actor}
    _ui_set_setting(conn, "ui_config", cfg)
    return cfg


def ensure_ui_api_token(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='ui_api_token'").fetchone()
    if row and row["value"]:
        return row["value"]
    token = "vo_" + uuid.uuid4().hex + uuid.uuid4().hex
    _ui_set_setting(conn, "ui_api_token", token)
    conn.commit()
    return token


def check_ui_token(req):
    token = ensure_ui_api_token(get_db()) if False else None  # placeholder
    # read without creating side effects in wrong context
    conn = database.connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key='ui_api_token'").fetchone()
        token = row["value"] if row else None
    finally:
        conn.close()
    if not token:
        return False
    auth = req.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        got = auth.split(None, 1)[1].strip()
    else:
        got = (req.headers.get("X-Office-Token") or req.args.get("token") or "").strip()
    return bool(got) and got == token


def ui_auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("uid"):
            g.ui_auth = "session"
            return fn(*args, **kwargs)
        if check_ui_token(request):
            g.ui_auth = "token"
            # ensure a user context exists for code paths that expect it
            conn = get_db()
            if not getattr(g, "_ui_user", None):
                g._ui_user = conn.execute("SELECT * FROM users WHERE role='owner' ORDER BY id LIMIT 1").fetchone()
            return fn(*args, **kwargs)
        return jsonify(error="unauthorized"), 401
    return wrapper


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------
def q_departments(conn):
    return rows(conn.execute(
        """SELECT d.*,
             (SELECT COUNT(*) FROM tasks t WHERE t.department_id=d.id
                AND t.status IN ('todo','doing')) AS open_tasks,
             (SELECT COUNT(*) FROM documents doc WHERE doc.department_id=d.id) AS docs,
             (SELECT COUNT(*) FROM agents a WHERE a.department_id=d.id AND a.active=1) AS agent_count
           FROM departments d ORDER BY d.sort_order, d.id"""
    ).fetchall())


def q_agents(conn):
    return rows(conn.execute(
        """SELECT a.*, d.name AS dept_name, d.color AS dept_color, d.icon AS dept_icon,
             (SELECT COUNT(*) FROM tasks t WHERE t.agent_id=a.id
                AND t.status IN ('todo','doing')) AS open_tasks,
             (SELECT COUNT(*) FROM tasks t WHERE t.agent_id=a.id AND t.status='done') AS done_tasks,
             (SELECT COUNT(*) FROM documents doc WHERE doc.agent_id=a.id) AS docs
           FROM agents a LEFT JOIN departments d ON d.id=a.department_id
           WHERE a.active=1 ORDER BY a.sort_order, a.id"""
    ).fetchall())


def q_tasks(conn):
    return rows(conn.execute(
        """SELECT t.*, d.name AS dept_name, d.color AS dept_color, d.icon AS dept_icon,
             a.name AS agent_name, a.emoji AS agent_emoji, a.color AS agent_color
           FROM tasks t
           LEFT JOIN departments d ON d.id=t.department_id
           LEFT JOIN agents a ON a.id=t.agent_id
           ORDER BY CASE t.status WHEN 'todo' THEN 0 WHEN 'doing' THEN 1
                    WHEN 'done' THEN 2 ELSE 3 END,
                    (t.due_date IS NULL), t.due_date, (t.due_time IS NULL), t.due_time, t.id"""
    ).fetchall())


def q_documents(conn):
    return rows(conn.execute(
        """SELECT doc.*, d.name AS dept_name, d.color AS dept_color, d.icon AS dept_icon,
             a.name AS agent_name, a.emoji AS agent_emoji
           FROM documents doc
           LEFT JOIN departments d ON d.id=doc.department_id
           LEFT JOIN agents a ON a.id=doc.agent_id
           ORDER BY doc.created_at DESC, doc.id DESC"""
    ).fetchall())


def q_notifications(conn, limit=60):
    return rows(conn.execute(
        "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall())


def q_activity(conn, limit=80):
    return rows(conn.execute(
        "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall())


def q_widgets(conn, uid):
    return rows(conn.execute(
        "SELECT * FROM widgets WHERE user_id=? ORDER BY position, id", (uid,)
    ).fetchall())


def q_stats(conn):
    today = date.today().isoformat()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    one = lambda sql, args=(): conn.execute(sql, args).fetchone()[0]
    return {
        "open": one("SELECT COUNT(*) FROM tasks WHERE status IN ('todo','doing')"),
        "today": one("SELECT COUNT(*) FROM tasks WHERE status IN ('todo','doing') AND due_date=?", (today,)),
        "overdue": one("SELECT COUNT(*) FROM tasks WHERE status IN ('todo','doing') AND due_date IS NOT NULL AND due_date<?", (today,)),
        "doing": one("SELECT COUNT(*) FROM tasks WHERE status='doing'"),
        "done_week": one("SELECT COUNT(*) FROM tasks WHERE status='done' AND completed_at>=?", (week_ago,)),
        "docs": one("SELECT COUNT(*) FROM documents"),
        "unread": one("SELECT COUNT(*) FROM notifications WHERE is_read=0"),
        "agents": one("SELECT COUNT(*) FROM agents WHERE active=1"),
    }


def bootstrap_data(conn, user):
    agent_engine.run_agents(conn)
    return {
        "me": {
            "id": user["id"], "username": user["username"],
            "display_name": user["display_name"], "role": user["role"],
        },
        "departments": q_departments(conn),
        "agents": q_agents(conn),
        "tasks": q_tasks(conn),
        "documents": q_documents(conn),
        "notifications": q_notifications(conn),
        "activity": q_activity(conn),
        "widgets": q_widgets(conn, user["id"]),
        "stats": q_stats(conn),
        "ai": agent_engine.ai_status(),
        "ui_config": get_ui_config(conn),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Pages / auth
# ---------------------------------------------------------------------------
@app.get("/login")
def login():
    if session.get("uid"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.get("/")
@login_required
def index():
    conn = get_db()
    user = current_user(conn)
    if not user:
        session.clear()
        return redirect(url_for("login"))
    return render_template("index.html", user=user)


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify(error="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"), 401
    session.clear()
    session["uid"] = user["id"]
    session.permanent = True
    app.permanent_session_lifetime = timedelta(days=30)
    log(conn, user["display_name"], "เข้าสู่ระบบ", "เข้าสู่ออฟฟิศเสมือน")
    conn.commit()
    return jsonify(ok=True)


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/bootstrap")
@login_required
def api_bootstrap():
    conn = get_db()
    user = current_user(conn)
    return jsonify(bootstrap_data(conn, user))


@app.get("/api/notifications")
@login_required
def api_notifications():
    conn = get_db()
    agent_engine.run_agents(conn)
    return jsonify({
        "notifications": q_notifications(conn),
        "stats": q_stats(conn),
    })


@app.post("/api/notifications/<int:nid>/read")
@login_required
def api_notification_read(nid):
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE id=?", (nid,))
    conn.commit()
    return jsonify(ok=True)


@app.post("/api/notifications/read-all")
@login_required
def api_notifications_read_all():
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE is_read=0")
    conn.commit()
    return jsonify(ok=True)


@app.post("/api/password")
@login_required
def api_password():
    conn = get_db()
    user = current_user(conn)
    data = request.get_json(silent=True) or {}
    if not check_password_hash(user["password_hash"], data.get("current") or ""):
        return jsonify(error="รหัสผ่านปัจจุบันไม่ถูกต้อง"), 400
    new = (data.get("new") or "").strip()
    if len(new) < 6:
        return jsonify(error="รหัสผ่านใหม่ต้องมีอย่างน้อย 6 ตัวอักษร"), 400
    conn.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (generate_password_hash(new), user["id"]),
    )
    log(conn, user["display_name"], "เปลี่ยนรหัสผ่าน", "อัปเดตรหัสผ่านเรียบร้อย")
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
TASK_FIELDS = {"title", "detail", "department_id", "agent_id", "status",
               "priority", "due_date", "due_time", "repeat_rule", "tags"}


def _clean_task_payload(data):
    payload = {}
    for key in TASK_FIELDS:
        if key in data:
            value = data[key]
            if isinstance(value, str):
                value = value.strip()
            if key in ("department_id", "agent_id") and value in ("", None):
                value = None
            payload[key] = value
    return payload


def _next_due(due_date, rule):
    try:
        base = date.fromisoformat(due_date) if due_date else date.today()
    except ValueError:
        base = date.today()
    if rule == "daily":
        return base + timedelta(days=1)
    if rule == "weekly":
        return base + timedelta(days=7)
    if rule == "monthly":
        month = base.month + 1
        year = base.year + (1 if month > 12 else 0)
        month = 1 if month > 12 else month
        day = min(base.day, 28)
        return date(year, month, day)
    if rule == "yearly":
        return date(base.year + 1, base.month, min(base.day, 28))
    return base


@app.post("/api/tasks")
@login_required
def api_task_create():
    conn = get_db()
    user = current_user(conn)
    data = request.get_json(silent=True) or {}
    payload = _clean_task_payload(data)
    if not payload.get("title"):
        return jsonify(error="กรุณาระบุชื่องาน"), 400
    if payload.get("agent_id") and not payload.get("department_id"):
        row = conn.execute("SELECT department_id FROM agents WHERE id=?",
                           (payload["agent_id"],)).fetchone()
        if row:
            payload["department_id"] = row["department_id"]
    cols = list(payload.keys())
    cur = conn.execute(
        f"INSERT INTO tasks ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [payload[c] for c in cols],
    )
    tid = cur.lastrowid
    log(conn, user["display_name"], "เพิ่มงาน", payload["title"])
    conn.commit()
    agent_engine.run_agents(conn, force=True)
    task = conn.execute(
        """SELECT t.*, d.name dept_name, a.name agent_name, a.emoji agent_emoji
           FROM tasks t LEFT JOIN departments d ON d.id=t.department_id
           LEFT JOIN agents a ON a.id=t.agent_id WHERE t.id=?""", (tid,)
    ).fetchone()
    if task and task["department_id"]:
        try: dispatch_dept_event(conn, task["department_id"], "task.created", f"สร้างงานใหม่: {task['title']}", {"task_id": tid, "title": task["title"]})
        except Exception: pass
    return jsonify(ok=True, task=dict(task))


@app.patch("/api/tasks/<int:tid>")
@login_required
def api_task_update(tid):
    conn = get_db()
    user = current_user(conn)
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return jsonify(error="ไม่พบงาน"), 404
    data = request.get_json(silent=True) or {}
    payload = _clean_task_payload(data)
    if not payload:
        return jsonify(error="ไม่มีข้อมูลที่จะอัปเดต"), 400

    old_status = task["status"]
    new_status = payload.get("status", old_status)
    if new_status == "done" and old_status != "done":
        payload["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if task["repeat_rule"] and task["repeat_rule"] != "none" and not task["recurrence_generated"]:
            next_date = _next_due(task["due_date"], task["repeat_rule"]).isoformat()
            conn.execute(
                """INSERT INTO tasks
                   (title, detail, department_id, agent_id, status, priority, due_date,
                    due_time, repeat_rule, tags)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (task["title"], task["detail"], task["department_id"], task["agent_id"],
                 "todo", task["priority"], next_date, task["due_time"],
                 task["repeat_rule"], task["tags"]),
            )
            payload["recurrence_generated"] = 1
            log(conn, "ทีม AI", "สร้างงานซ้ำ", f"{task['title']} · กำหนด {next_date}")
    elif new_status != "done" and old_status == "done":
        payload["completed_at"] = None

    cols = list(payload.keys())
    conn.execute(
        f"UPDATE tasks SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
        [payload[c] for c in cols] + [tid],
    )
    if new_status != old_status:
        action = {"done": "ทำงานเสร็จ", "doing": "เริ่มทำงาน",
                  "todo": "เปิดงานอีกครั้ง", "cancelled": "ยกเลิกงาน"}.get(new_status, "อัปเดตงาน")
        log(conn, user["display_name"], action, task["title"])
        if new_status == "done":
            agent_engine.notify(
                conn, "done", f"งานเสร็จแล้ว: {task['title']}",
                f"ปิดงานเรียบร้อยเมื่อ {datetime.now().strftime('%H:%M')} น.",
                "task", tid, f"done:{tid}",
            )
    conn.commit()
    try:
        updated = conn.execute("SELECT id,title,status,department_id FROM tasks WHERE id=?", (tid,)).fetchone()
        if updated and updated["department_id"]:
            dispatch_dept_event(conn, updated["department_id"], "task.updated", f"อัปเดตงาน: {updated["title"]} ({updated["status"]})", {"task_id": tid, "status": updated["status"]})
    except Exception:
        pass
    return jsonify(ok=True)


@app.delete("/api/tasks/<int:tid>")
@login_required
def api_task_delete(tid):
    conn = get_db()
    user = current_user(conn)
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return jsonify(error="ไม่พบงาน"), 404
    conn.execute("DELETE FROM notifications WHERE ref_type='task' AND ref_id=?", (tid,))
    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    log(conn, user["display_name"], "ลบงาน", task["title"])
    if task["department_id"]:
        try:
            dispatch_dept_event(conn, task["department_id"], "task.deleted", f"ลบงาน: {task["title"]}", {"task_id": tid})
        except Exception:
            pass
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Natural-language command execution (ใช้ร่วมกับแชทและช่องสั่งงาน)
# ---------------------------------------------------------------------------
def _fetch_task(conn, tid):
    row = conn.execute(
        """SELECT t.*, d.name AS dept_name, d.color AS dept_color,
                  a.name AS agent_name, a.emoji AS agent_emoji
           FROM tasks t
           LEFT JOIN departments d ON d.id=t.department_id
           LEFT JOIN agents a ON a.id=t.agent_id
           WHERE t.id=?""", (tid,)
    ).fetchone()
    return dict(row) if row else None


def _default_agent(conn, agent=None):
    if agent is not None:
        return agent
    return conn.execute(
        "SELECT * FROM agents WHERE active=1 ORDER BY sort_order, id LIMIT 1"
    ).fetchone()


def _valid_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _valid_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:5], "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def _do_create_task(conn, actor, agent, payload):
    title = (payload.get("title") or "").strip()[:180]
    if not title:
        return {"ok": False, "error": "ไม่พบชื่องาน กรุณาระบุชื่องานที่ต้องการ"}
    agent_id = payload.get("agent_id") or (agent["id"] if agent else None)
    department_id = payload.get("department_id")
    if agent_id and not department_id:
        row = conn.execute("SELECT department_id FROM agents WHERE id=?", (agent_id,)).fetchone()
        if row:
            department_id = row["department_id"]
    priority = payload.get("priority")
    if priority not in ("low", "normal", "high", "urgent"):
        priority = "normal"
    repeat_rule = payload.get("repeat_rule")
    if repeat_rule not in ("none", "daily", "weekly", "monthly", "yearly"):
        repeat_rule = "none"
    due_date = _valid_date(payload.get("due_date"))
    due_time = _valid_time(payload.get("due_time"))
    cur = conn.execute(
        """INSERT INTO tasks
           (title, department_id, agent_id, status, priority, due_date, due_time, repeat_rule)
           VALUES (?,?,?,?,?,?,?,?)""",
        (title, department_id, agent_id, "todo", priority, due_date, due_time, repeat_rule),
    )
    tid = cur.lastrowid
    log(conn, actor, "เพิ่มงาน", title)
    conn.commit()
    agent_engine.run_agents(conn, force=True)
    task = _fetch_task(conn, tid)
    who = task.get("agent_name") if task else None
    detail = agent_engine._fmt_due(due_date, due_time)
    reply = f"✅ สร้างงาน “{title}” เรียบร้อย"
    if who:
        reply += f" มอบหมายให้ {who}"
    reply += f" · กำหนด {detail}"
    if priority in ("high", "urgent"):
        reply += f" · ความสำคัญ {PRIORITY_THAI[priority]}"
    if repeat_rule != "none":
        reply += f" · ทำซ้ำ{REPEAT_THAI[repeat_rule]}"
    return {"ok": True, "task": task, "task_id": tid, "message": reply, "reply": reply}


def _do_complete_task(conn, actor, tid):
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return {"ok": False, "error": "ไม่พบงานนี้"}
    if task["status"] == "done":
        return {"ok": True, "task": _fetch_task(conn, tid),
                "reply": f"งาน “{task['title']}” ปิดไปแล้วก่อนหน้านี้"}
    payload = {"status": "done",
               "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if task["repeat_rule"] and task["repeat_rule"] != "none" and not task["recurrence_generated"]:
        next_date = _next_due(task["due_date"], task["repeat_rule"]).isoformat()
        conn.execute(
            """INSERT INTO tasks
               (title, detail, department_id, agent_id, status, priority, due_date,
                due_time, repeat_rule, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (task["title"], task["detail"], task["department_id"], task["agent_id"],
             "todo", task["priority"], next_date, task["due_time"],
             task["repeat_rule"], task["tags"]),
        )
        payload["recurrence_generated"] = 1
        log(conn, "ทีม AI", "สร้างงานซ้ำ", f"{task['title']} · กำหนด {next_date}")
    conn.execute(
        "UPDATE tasks SET status=?, completed_at=?, recurrence_generated=? WHERE id=?",
        ("done", payload["completed_at"], payload.get("recurrence_generated", task["recurrence_generated"]), tid),
    )
    log(conn, actor, "ทำงานเสร็จ", task["title"])
    agent_engine.notify(
        conn, "done", f"งานเสร็จแล้ว: {task['title']}",
        f"ปิดงานเรียบร้อยเมื่อ {datetime.now().strftime('%H:%M')} น.",
        "task", tid, f"done:{tid}",
    )
    conn.commit()
    return {"ok": True, "task": _fetch_task(conn, tid), "task_id": tid,
            "reply": f"✅ ปิดงาน “{task['title']}” เรียบร้อยแล้ว"}


def _do_reschedule_task(conn, actor, tid, due_date, due_time=None):
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        return {"ok": False, "error": "ไม่พบงานนี้"}
    new_date = _valid_date(due_date)
    if not new_date:
        return {"ok": False, "error": "ไม่พบวันที่ใหม่ที่เข้าใจได้"}
    new_time = _valid_time(due_time) if due_time else task["due_time"]
    conn.execute("UPDATE tasks SET due_date=?, due_time=? WHERE id=?",
                 (new_date, new_time, tid))
    log(conn, actor, "เลื่อนกำหนดงาน",
        f"{task['title']} → {agent_engine._fmt_due(new_date, new_time)}")
    conn.commit()
    return {"ok": True, "task": _fetch_task(conn, tid), "task_id": tid,
            "reply": f"📅 เลื่อนงาน “{task['title']}” ไปเป็น "
                     f"{agent_engine._fmt_due(new_date, new_time)} แล้ว"}


def _do_search_docs(conn, query):
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "ต้องการคำค้นเอกสาร"}
    like = f"%{query}%"
    found = rows(conn.execute(
        """SELECT id, title, category, filename FROM documents
           WHERE title LIKE ? OR category LIKE ? OR notes LIKE ? OR filename LIKE ?
           ORDER BY id DESC LIMIT 8""",
        (like, like, like, like),
    ).fetchall())
    if not found:
        return {"ok": False, "error": f"ไม่พบเอกสารที่ตรงกับ “{query}”",
                "reply": f"🔍 ไม่พบเอกสารที่ตรงกับ “{query}” ลองใช้คำสั้นลงหรือค้นในหน้าศูนย์เอกสาร"}
    lines = [f"🔍 พบเอกสาร {len(found)} รายการสำหรับ “{query}”"]
    lines += [f"• {d['title']} ({d['category'] or 'ไม่ระบุหมวด'})" for d in found]
    return {"ok": True, "documents": found, "reply": "\n".join(lines)}


def _candidate_reply(cmd, verb):
    cands = cmd.get("candidates") or []
    query = cmd.get("query") or "-"
    if not cands:
        return {
            "ok": False,
            "error": "ไม่พบงานที่ตรงกัน",
            "verb": verb,
            "candidates": [],
            "reply": f"❓ ไม่พบงานที่เปิดอยู่ที่ตรงกับ “{query}”\n"
                     f"ลองพิมพ์ชื่อให้ชัดเจนขึ้น เช่น “{verb} ชื่องานเต็ม” "
                     f"หรือดูรายการงานทั้งหมดในเมนู “งานและแจ้งเตือน”",
        }
    names = " · ".join(f"“{c['title']}”" for c in cands)
    sample = cands[0]["title"]
    return {
        "ok": False,
        "error": "ต้องระบุงานให้ชัดเจนขึ้น",
        "verb": verb,
        "candidates": cands,
        "reply": f"พบงานที่ใกล้เคียง {len(cands)} รายการ กดเลือกได้เลย:\n{names}\n"
                 f"หรือพิมพ์ต่อ เช่น “{verb} {sample}”",
    }


PRIORITY_THAI = {"low": "ต่ำ", "normal": "ปกติ", "high": "สูง", "urgent": "ด่วนมาก"}
REPEAT_THAI = {"daily": "ทุกวัน", "weekly": "ทุกสัปดาห์",
               "monthly": "ทุกเดือน", "yearly": "ทุกปี"}
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def _rank_open(tasks):
    today = date.today().isoformat()
    return sorted(
        tasks,
        key=lambda t: (
            0 if t["due_date"] and t["due_date"] < today else 1,
            PRIORITY_RANK.get(t["priority"], 2),
            t["due_date"] or "9999-12-31",
            t["due_time"] or "23:59",
        ),
    )


def _task_brief(t):
    today = date.today().isoformat()
    flag = "⚠️ " if t["due_date"] and t["due_date"] < today else "• "
    who = t["agent_name"] or t["dept_name"] or "ยังไม่มอบหมาย"
    return (f"{flag}{t['title']} — กำหนด {agent_engine._fmt_due(t['due_date'], t['due_time'])}"
            f" · {who}")


def _office_briefing(conn, intent="summary", agent_id=None):
    today = date.today()
    today_s = today.isoformat()
    open_tasks = agent_engine._open_tasks(conn, agent_id)
    overdue = [t for t in open_tasks if t["due_date"] and t["due_date"] < today_s]
    due_today = [t for t in open_tasks if t["due_date"] == today_s]
    if agent_id:
        docs = conn.execute("SELECT COUNT(*) c FROM documents WHERE agent_id=?",
                            (agent_id,)).fetchone()["c"]
    else:
        docs = conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"]

    scope = ""
    if agent_id:
        row = conn.execute("SELECT name FROM agents WHERE id=?", (agent_id,)).fetchone()
        scope = f"ของ {row['name']}" if row else ""

    if intent == "urgent":
        ranked = _rank_open(open_tasks)
        if not ranked:
            return {"reply": f"🎉 ตอนนี้ไม่มีงาน{scope}ค้างเหลืออยู่เลย ทีม AI พร้อมรับงานใหม่ทันที",
                    "tasks": []}
        lines = [f"⚡ งาน{scope}ที่ควรทำก่อน {min(5, len(ranked))} อันดับแรก "
                 f"(จากงานค้าง {len(ranked)} งาน):"]
        lines += [_task_brief(t) for t in ranked[:5]]
        return {"reply": "\n".join(lines),
                "tasks": [{"id": t["id"], "title": t["title"]} for t in ranked[:5]]}

    if agent_id:
        done_week = conn.execute(
            """SELECT COUNT(*) c FROM tasks WHERE status='done' AND agent_id=?
               AND date(completed_at) >= date('now','-7 day')""", (agent_id,)
        ).fetchone()["c"]
    else:
        done_week = conn.execute(
            "SELECT COUNT(*) c FROM tasks WHERE status='done' AND date(completed_at) >= date('now','-7 day')"
        ).fetchone()["c"]
    month_text = agent_engine.THAI_MONTHS[today.month - 1]
    lines = [
        f"📊 ภาพรวมวันนี้{scope} ({today.day} {month_text} {today.year + 543})",
        f"• งานค้างทั้งหมด {len(open_tasks)} งาน · ครบกำหนดวันนี้ {len(due_today)} งาน",
        f"• เกินกำหนด {len(overdue)} งาน · เสร็จใน 7 วันล่าสุด {done_week} งาน",
        f"• เอกสารในคลัง {docs} รายการ",
    ]
    ranked = _rank_open(open_tasks)[:3]
    if ranked:
        lines.append("\nงานที่ควรทำก่อน:")
        lines += [_task_brief(t) for t in ranked]
    else:
        lines.append("\nไม่มีงานค้างเหลืออยู่เลย ทีม AI พร้อมรับงานใหม่")
    return {"reply": "\n".join(lines),
            "tasks": [{"id": t["id"], "title": t["title"]} for t in ranked]}


def execute_agent_command(conn, agent, cmd, actor, scoped=False):
    """เรียกใช้คำสั่งที่ parse แล้ว แล้วคืน reply/actions ให้ frontend."""
    intent = cmd.get("intent")
    if intent == "help":
        return {"reply": agent_engine.COMMAND_HELP, "source": "command", "actions": []}

    if intent in ("summary", "urgent"):
        result = _office_briefing(conn, intent, agent["id"] if scoped and agent else None)
        return {"reply": result["reply"], "source": "command", "actions": [],
                "tasks": result.get("tasks", [])}

    if intent == "create":
        result = _do_create_task(conn, actor, agent, cmd)
        action = {"tool": "create_task", "ok": result["ok"]}
        if result["ok"]:
            action.update(task_id=result.get("task_id"), title=result["task"]["title"])
        else:
            action["error"] = result.get("error")
        return {"reply": result.get("reply") or result.get("error", ""),
                "source": "command", "actions": [action], "task": result.get("task")}

    if intent == "complete":
        tid = cmd.get("task_id")
        if not tid:
            return {"source": "command", **_candidate_reply(cmd, "ปิดงาน")}
        result = _do_complete_task(conn, actor, tid)
        return {"reply": result.get("reply") or result.get("error", ""),
                "source": "command",
                "actions": [{"tool": "complete_task", "ok": result["ok"],
                             "task_id": tid, "title": (result.get("task") or {}).get("title")}],
                "task": result.get("task")}

    if intent == "reschedule":
        tid = cmd.get("task_id")
        if not tid:
            return {"source": "command", **_candidate_reply(cmd, "เลื่อนงาน")}
        if not cmd.get("due_date"):
            return {"reply": "📅 บอกวันที่ใหม่ด้วยได้ไหม เช่น “เลื่อนงาน … ไปวันที่ 20”",
                    "source": "command", "actions": []}
        result = _do_reschedule_task(conn, actor, tid, cmd["due_date"], cmd.get("due_time"))
        return {"reply": result.get("reply") or result.get("error", ""),
                "source": "command",
                "actions": [{"tool": "reschedule_task", "ok": result["ok"],
                             "task_id": tid, "title": (result.get("task") or {}).get("title")}],
                "task": result.get("task")}

    if intent == "search_docs":
        result = _do_search_docs(conn, cmd.get("query"))
        return {"reply": result["reply"], "source": "command",
                "actions": [{"tool": "search_documents", "ok": result["ok"]}],
                "documents": result.get("documents", [])}

    return {"reply": "ยังไม่เข้าใจคำสั่งนี้ ลองพิมพ์ “ช่วยอะไรได้บ้าง”",
            "source": "command", "actions": []}


def execute_agent_tool(conn, agent, name, args, actor):
    """ตัวแปลง tool call ของ AI ให้ทำงานกับฐานข้อมูลจริง."""
    if name == "create_task":
        payload = dict(args)
        agent_name = payload.pop("agent_name", None)
        if agent_name:
            found = agent_engine.find_agent(conn, agent_name)
            if found:
                payload["agent_id"] = found["id"]
        return _do_create_task(conn, actor, agent, payload)

    if name == "complete_task":
        query = (args.get("title") or "").strip()
        task, candidates = agent_engine.pick_task(conn, query, agent["id"])
        if not task:
            return {"ok": False, "error": "ไม่พบงานที่ตรงกัน",
                    "candidates": [{"id": t["id"], "title": t["title"]} for t in candidates]}
        return _do_complete_task(conn, actor, task["id"])

    if name == "reschedule_task":
        query = (args.get("title") or "").strip()
        task, candidates = agent_engine.pick_task(conn, query, agent["id"])
        if not task:
            return {"ok": False, "error": "ไม่พบงานที่ตรงกัน",
                    "candidates": [{"id": t["id"], "title": t["title"]} for t in candidates]}
        return _do_reschedule_task(conn, actor, task["id"],
                                   args.get("due_date"), args.get("due_time"))

    if name == "list_tasks":
        mode = args.get("filter") or "open"
        agent_id = None
        if args.get("agent_name"):
            found = agent_engine.find_agent(conn, args["agent_name"])
            if found:
                agent_id = found["id"]
        sql = """SELECT t.id, t.title, t.status, t.priority, t.due_date, t.due_time,
                        a.name AS agent_name
                 FROM tasks t LEFT JOIN agents a ON a.id=t.agent_id WHERE 1=1"""
        params = []
        today = date.today().isoformat()
        if mode == "open":
            sql += " AND t.status IN ('todo','doing')"
        elif mode == "today":
            sql += " AND t.status IN ('todo','doing') AND t.due_date=?"
            params.append(today)
        elif mode == "overdue":
            sql += " AND t.status IN ('todo','doing') AND t.due_date<?"
            params.append(today)
        elif mode == "done":
            sql += " AND t.status='done'"
        if agent_id:
            sql += " AND t.agent_id=?"
            params.append(agent_id)
        sql += " ORDER BY (t.due_date IS NULL), t.due_date, t.due_time LIMIT 20"
        found = rows(conn.execute(sql, params).fetchall())
        return {"ok": True, "tasks": found, "count": len(found)}

    if name == "search_documents":
        return _do_search_docs(conn, args.get("query"))

    return {"ok": False, "error": f"ไม่รู้จักเครื่องมือ {name}"}


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
@app.post("/api/agents/run")
@login_required
def api_agents_run():
    conn = get_db()
    result = agent_engine.run_agents(conn, force=True)
    return jsonify(ok=True, **result)


@app.patch("/api/agents/<int:aid>")
@login_required
def api_agent_update(aid):
    conn = get_db()
    user = current_user(conn)
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (aid,)).fetchone()
    if not agent:
        return jsonify(error="ไม่พบผู้ช่วย"), 404
    data = request.get_json(silent=True) or {}
    allowed = {}
    if data.get("status") in ("working", "idle", "meeting", "offline"):
        allowed["status"] = data["status"]
    for key in ("duties", "persona", "role"):
        if isinstance(data.get(key), str):
            allowed[key] = data[key].strip()
    if not allowed:
        return jsonify(error="ไม่มีข้อมูลที่จะอัปเดต"), 400
    conn.execute(
        f"UPDATE agents SET {', '.join(k + '=?' for k in allowed)} WHERE id=?",
        list(allowed.values()) + [aid],
    )
    log(conn, user["display_name"], "อัปเดตทีม AI", f"{agent['name']} · {', '.join(allowed.keys())}")
    conn.commit()
    return jsonify(ok=True)


@app.post("/api/agents/<int:aid>/chat")
@login_required
def api_agent_chat(aid):
    conn = get_db()
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (aid,)).fetchone()
    if not agent:
        return jsonify(error="ไม่พบผู้ช่วย"), 404
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify(error="กรุณาพิมพ์ข้อความ"), 400
    user = current_user(conn)
    actor = user["display_name"] if user else agent["name"]

    cmd = agent_engine.parse_command(conn, agent, message)
    if cmd:
        result = dict(execute_agent_command(conn, agent, cmd, actor, scoped=True))
        conn.commit()
        result.setdefault("ok", True)
        return jsonify(result)

    result = agent_engine.agent_reply(
        conn, agent, message, data.get("history") or [],
        tool_executor=lambda name, args: execute_agent_tool(conn, agent, name, args, actor),
    )
    conn.commit()
    return jsonify(ok=True, **result)


@app.post("/api/commands")
@login_required
def api_command():
    """ช่องสั่งงานด่วน: รับภาษาธรรมชาติแล้วเลือกผู้ช่วยที่เหมาะสมให้เอง."""
    conn = get_db()
    user = current_user(conn)
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify(error="กรุณาพิมพ์คำสั่ง"), 400
    actor = user["display_name"] if user else "เจ้าของ"
    matched = agent_engine.find_agent(conn, message)
    agent = matched or _default_agent(conn)
    if not agent:
        return jsonify(error="ยังไม่มีผู้ช่วย AI ในระบบ"), 400

    cmd = agent_engine.parse_command(conn, agent, message)
    if cmd:
        result = dict(execute_agent_command(conn, agent, cmd, actor, scoped=bool(matched)))
        conn.commit()
        result.setdefault("ok", True)
        if matched or cmd.get("intent") in ("create", "complete", "reschedule"):
            result["agent"] = {"id": agent["id"], "name": agent["name"]}
        return jsonify(result)

    result = agent_engine.agent_reply(
        conn, agent, message, [],
        tool_executor=lambda name, args: execute_agent_tool(conn, agent, name, args, actor),
    )
    conn.commit()
    return jsonify(ok=True, agent={"id": agent["id"], "name": agent["name"]}, **result)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
@app.post("/api/documents")
@login_required
def api_document_upload():
    conn = get_db()
    user = current_user(conn)
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="กรุณาเลือกไฟล์"), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify(error=f"ไม่รองรับไฟล์ประเภท {ext or 'นี้'}"), 400
    stored = uuid.uuid4().hex + ext
    path = UPLOAD_DIR / stored
    data = file.read()
    path.write_bytes(data)
    size = len(data)
    title = (request.form.get("title") or "").strip() or os.path.splitext(file.filename)[0]
    category = (request.form.get("category") or "ยังไม่จัดหมวด").strip()
    department_id = request.form.get("department_id") or None
    agent_id = request.form.get("agent_id") or None
    notes = (request.form.get("notes") or "").strip()
    if agent_id and not department_id:
        row = conn.execute("SELECT department_id FROM agents WHERE id=?", (agent_id,)).fetchone()
        if row:
            department_id = row["department_id"]
    drive_file_id = ""
    drive_warning = ""
    storage_cfg = get_storage(conn)
    if storage_ready(storage_cfg):
        try:
            drive_file_id = drive_upload_bytes(storage_cfg, stored, data, file.mimetype or "") or ""
        except Exception as exc:
            drive_warning = f"อัปโหลดขึ้น Google Drive ไม่สำเร็จ เก็บไว้ในเครื่องแทน: {str(exc)[:240]}"
    cur = conn.execute(
        """INSERT INTO documents
           (title, category, department_id, agent_id, filename, stored_name, mime, size, notes, drive_file_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (title, category, department_id, agent_id, file.filename, stored,
         file.mimetype or "", size, notes, drive_file_id),
    )
    log(conn, user["display_name"], "อัปโหลดเอกสาร", f"{title} ({file.filename})")
    conn.commit()
    agent_engine.run_agents(conn, force=True)
    return jsonify(ok=True, id=cur.lastrowid, drive=bool(drive_file_id), warning=drive_warning)


@app.get("/api/documents/<int:did>/download")
@login_required
def api_document_download(did):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    if not doc:
        return jsonify(error="ไม่พบเอกสาร"), 404
    path = _doc_local_path(doc)
    if str(path).startswith(str(UPLOAD_DIR.resolve())) and path.exists():
        return send_file(path, as_attachment=True, download_name=doc["filename"])
    try:
        data = _doc_bytes(conn, doc)
    except Exception as exc:
        return jsonify(error=f"ดึงไฟล์จาก Google Drive ไม่สำเร็จ: {str(exc)[:240]}"), 502
    if not data:
        return jsonify(error="ไม่พบไฟล์ในระบบ"), 404
    return send_file(io.BytesIO(data), as_attachment=True, download_name=doc["filename"],
                     mimetype=doc["mime"] or "application/octet-stream")


def _read_spreadsheet_preview(source, ext, max_rows=200, max_cols=30):
    """อ่านตัวอย่างข้อมูลจาก Excel/CSV (รองรับ path หรือ bytes)."""
    rows = []
    columns = []
    sheet_name = None
    total_rows = 0
    truncated = False

    raw = source if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()

    if ext == ".csv":
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp874", "tis-620", "latin1"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            text = raw.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        for i, row in enumerate(reader):
            if i == 0:
                columns = [(c or f"คอลัมน์ {j+1}") for j, c in enumerate(row[:max_cols])]
            else:
                if len(rows) < max_rows:
                    rows.append([("" if v is None else str(v)) for v in row[:max_cols]])
                total_rows += 1
        if total_rows > max_rows:
            truncated = True
        return {"ok": True, "kind": "csv", "sheet": None, "columns": columns, "rows": rows,
                "total_rows": total_rows, "truncated": truncated}

    if ext == ".xlsx":
        try:
            import openpyxl
        except Exception:
            return {"ok": False, "error": "ระบบยังไม่รองรับการอ่าน .xlsx (ยังไม่ได้ติดตั้ง openpyxl) — กรุณาดาวน์โหลดไฟล์ หรือบันทึกเป็น .csv"}
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            sheet_name = getattr(ws, "title", None)
            it = ws.iter_rows(values_only=True)
            first = next(it, None)
            if first is not None:
                columns = [(str(c) if c not in (None, "") else f"คอลัมน์ {j+1}") for j, c in enumerate(first[:max_cols])]
            for row in it:
                if len(rows) < max_rows:
                    rows.append([("" if v is None else str(v)) for v in row[:max_cols]])
                total_rows += 1
            wb.close()
        except Exception as e:
            return {"ok": False, "error": f"อ่านไฟล์ Excel ไม่สำเร็จ: {e}"}
        if total_rows > max_rows:
            truncated = True
        return {"ok": True, "kind": "xlsx", "sheet": sheet_name, "columns": columns, "rows": rows,
                "total_rows": total_rows, "truncated": truncated}

    if ext == ".xls":
        return {"ok": False, "error": "ไฟล์ .xls (รูปแบบเก่า) ยังไม่รองรับการพรีวิวโดยตรง — แนะนำเปิดแล้วบันทึกเป็น .xlsx หรือ .csv แล้วอัปโหลดใหม่ (หรือกดดาวน์โหลดไฟล์)"}

    return {"ok": False, "error": "ไฟล์ประเภทนี้ไม่รองรับการพรีวิวตาราง"}


@app.get("/api/documents/<int:did>/preview")
@login_required
def api_document_preview(did):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    if not doc:
        return jsonify(error="ไม่พบเอกสาร"), 404
    try:
        data = _doc_bytes(conn, doc)
    except Exception as exc:
        return jsonify(error=f"ดึงไฟล์จาก Google Drive ไม่สำเร็จ: {str(exc)[:240]}"), 502
    if not data:
        return jsonify(error="ไม่พบไฟล์ในระบบ"), 404
    ext = os.path.splitext(doc["filename"] or "")[1].lower()
    result = _read_spreadsheet_preview(data, ext)
    result["filename"] = doc["filename"]
    result["title"] = doc["title"]
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@app.delete("/api/documents/<int:did>")
@login_required
def api_document_delete(did):
    conn = get_db()
    user = current_user(conn)
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    if not doc:
        return jsonify(error="ไม่พบเอกสาร"), 404
    fid = ""
    try:
        fid = (doc["drive_file_id"] or "").strip()
    except Exception:
        fid = ""
    if fid:
        cfg = get_storage(conn)
        if storage_ready(cfg):
            try:
                drive_delete_file(cfg, fid)
            except Exception:
                pass
    path = UPLOAD_DIR / os.path.basename(doc["stored_name"])
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    conn.execute("DELETE FROM notifications WHERE ref_type='document' AND ref_id=?", (did,))
    conn.execute("DELETE FROM documents WHERE id=?", (did,))
    log(conn, user["display_name"], "ลบเอกสาร", doc["title"])
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Dashboard widgets
# ---------------------------------------------------------------------------
@app.post("/api/widgets")
@login_required
def api_widget_add():
    conn = get_db()
    user = current_user(conn)
    data = request.get_json(silent=True) or {}
    wtype = data.get("widget_type")
    if wtype not in WIDGET_TYPES:
        return jsonify(error="ไม่รู้จัก widget นี้"), 400
    maxpos = conn.execute(
        "SELECT COALESCE(MAX(position),-1) m FROM widgets WHERE user_id=?", (user["id"],)
    ).fetchone()["m"]
    cur = conn.execute(
        "INSERT INTO widgets (user_id, widget_type, title, size, position) VALUES (?,?,?,?,?)",
        (user["id"], wtype, WIDGET_TYPES[wtype], "half", maxpos + 1),
    )
    conn.commit()
    return jsonify(ok=True, widget={
        "id": cur.lastrowid, "widget_type": wtype, "title": WIDGET_TYPES[wtype],
        "size": "half", "position": maxpos + 1, "visible": 1,
    })


@app.patch("/api/widgets/<int:wid>")
@login_required
def api_widget_update(wid):
    conn = get_db()
    user = current_user(conn)
    widget = conn.execute(
        "SELECT * FROM widgets WHERE id=? AND user_id=?", (wid, user["id"])
    ).fetchone()
    if not widget:
        return jsonify(error="ไม่พบ widget"), 404
    data = request.get_json(silent=True) or {}
    fields = {}
    if data.get("size") in ("third", "half", "full"):
        fields["size"] = data["size"]
    if "visible" in data:
        fields["visible"] = 1 if data["visible"] else 0
    if isinstance(data.get("title"), str) and data["title"].strip():
        fields["title"] = data["title"].strip()[:60]
    if not fields:
        return jsonify(error="ไม่มีข้อมูลที่จะอัปเดต"), 400
    conn.execute(
        f"UPDATE widgets SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
        list(fields.values()) + [wid],
    )
    conn.commit()
    return jsonify(ok=True)


@app.delete("/api/widgets/<int:wid>")
@login_required
def api_widget_delete(wid):
    conn = get_db()
    user = current_user(conn)
    conn.execute("DELETE FROM widgets WHERE id=? AND user_id=?", (wid, user["id"]))
    conn.commit()
    return jsonify(ok=True)


@app.post("/api/widgets/reorder")
@login_required
def api_widget_reorder():
    conn = get_db()
    user = current_user(conn)
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    for pos, wid in enumerate(ids):
        conn.execute(
            "UPDATE widgets SET position=? WHERE id=? AND user_id=?",
            (pos, wid, user["id"]),
        )
    conn.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# UI Config API (??????/???????????????? config ???????????????)
# - ??? session (owner) ???? API token: Authorization: Bearer <token> / X-Office-Token
# - token ??/???????????????? session ????????
# ---------------------------------------------------------------------------
@app.get("/api/ui-config")
@ui_auth_required
def api_ui_config_get():
    conn = get_db()
    return jsonify(ok=True, config=get_ui_config(conn))


@app.put("/api/ui-config")
@ui_auth_required
def api_ui_config_put():
    conn = get_db()
    user = current_user(conn) or getattr(g, "_ui_user", None)
    actor = (user["display_name"] if user else "API")
    raw = request.get_json(silent=True) or {}
    # allow either {config:{...}} or direct config
    cfg_in = raw.get("config") if isinstance(raw.get("config"), dict) else raw
    cfg = save_ui_config(conn, cfg_in, actor)
    log(conn, actor, "???????????????????????", "???? UI config")
    conn.commit()
    return jsonify(ok=True, config=get_ui_config(conn))


@app.post("/api/ui-config/reset")
@ui_auth_required
def api_ui_config_reset():
    conn = get_db()
    user = current_user(conn) or getattr(g, "_ui_user", None)
    actor = (user["display_name"] if user else "API")
    _ui_set_setting(conn, "ui_config", _ui_default_config(conn))
    log(conn, actor, "???????????????????????", "???????????????")
    conn.commit()
    return jsonify(ok=True, config=get_ui_config(conn))


@app.get("/api/ui-config/token")
@login_required
def api_ui_config_token_get():
    conn = get_db()
    token = ensure_ui_api_token(conn)
    return jsonify(ok=True, token=token,
                   hint="??? header Authorization: Bearer <token> ???? X-Office-Token ???????? AI/??????????????? GET/PUT /api/ui-config ???")


@app.post("/api/ui-config/token/regenerate")
@login_required
def api_ui_config_token_regen():
    conn = get_db()
    user = current_user(conn)
    token = "vo_" + uuid.uuid4().hex + uuid.uuid4().hex
    _ui_set_setting(conn, "ui_api_token", token)
    log(conn, user["display_name"], "????? API token ????", "UI config token")
    conn.commit()
    return jsonify(ok=True, token=token)


# ---------------------------------------------------------------------------
# Backup / PWA / errors
# ---------------------------------------------------------------------------
@app.get("/api/backup")
@login_required
def api_backup():
    conn = get_db()
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "app": "virtual-office",
        "departments": q_departments(conn),
        "agents": q_agents(conn),
        "tasks": q_tasks(conn),
        "documents": q_documents(conn),
        "activity": q_activity(conn, 1000),
        "settings": rows(conn.execute("SELECT * FROM settings").fetchall()),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return app.response_class(
        body, mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=virtual-office-backup.json"},
    )


@app.get("/sw.js")
def service_worker():
    return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")


@app.get("/health")
def health():
    return jsonify(ok=True, time=datetime.now().isoformat(timespec="seconds"))


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="ไฟล์ใหญ่เกิน 25 MB"), 413


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify(error="ไม่พบข้อมูล"), 404
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Integrations (per department) - LINE / Google Sheets / Webhook (ใช้งานจริง)
# ---------------------------------------------------------------------------
_INTEG_SECRET_KEYS = {
    "line": {"channel_access_token", "channel_secret"},
    "google_sheets": {"service_account_json"},
    "webhook": {"secret"},
}

def _integ_key(dept_id):
    return f"integrations:dept:{int(dept_id)}"

def _default_integrations():
    return {
        "line": {"enabled": False, "channel_access_token": "", "channel_secret": "", "to": "", "notify_events": True, "note": ""},
        "google_sheets": {"enabled": False, "spreadsheet_id": "", "sheet_name": "Tasks", "service_account_json": "", "note": ""},
        "webhook": {"enabled": False, "url": "", "secret": "", "events": "all", "note": ""},
    }

def get_integrations(conn, dept_id):
    raw = agent_engine.get_setting(conn, _integ_key(dept_id))
    base = _default_integrations()
    if not raw:
        return base
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return base
    if not isinstance(data, dict):
        return base
    for k, v in base.items():
        if isinstance(data.get(k), dict):
            vv = dict(v)
            for kk in v.keys():
                if kk in data[k] and data[k][kk] is not None:
                    val = data[k][kk]
                    vv[kk] = (val if isinstance(val, bool) else str(val))[:8000]
            base[k] = vv
    return base

def mask_integrations(cfg):
    out = json.loads(json.dumps(cfg))
    for prov, keys in _INTEG_SECRET_KEYS.items():
        if prov in out and isinstance(out[prov], dict):
            for k in keys:
                if out[prov].get(k):
                    out[prov][f"{k}_set"] = bool(cfg.get(prov, {}).get(k))
                    out[prov][k] = "********"
                else:
                    out[prov][f"{k}_set"] = False
    return out

def save_integrations(conn, dept_id, incoming):
    current = get_integrations(conn, dept_id)
    inc = incoming if isinstance(incoming, dict) else {}
    for prov, base in _default_integrations().items():
        if prov in inc and isinstance(inc[prov], dict):
            for kk in base.keys():
                if kk not in inc[prov]:
                    continue
                val = inc[prov][kk]
                if kk in _INTEG_SECRET_KEYS.get(prov, set()) and val == "********":
                    continue
                if isinstance(base[kk], bool):
                    current[prov][kk] = bool(val)
                else:
                    current[prov][kk] = str(val or "")[:8000]
    agent_engine.set_setting(conn, _integ_key(dept_id), json.dumps(current, ensure_ascii=False))
    return current


# ---------------------------------------------------------------------------
# ที่เก็บไฟล์กลาง (Google Drive) — สำหรับ uploads/ ให้อยู่ถาวรนอกเซิร์ฟเวอร์
# ---------------------------------------------------------------------------
_STORAGE_KEY = "storage:google_drive"
_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _default_storage():
    return {"enabled": False, "folder_id": "", "service_account_json": "", "note": ""}


def get_storage(conn):
    base = _default_storage()
    raw = agent_engine.get_setting(conn, _STORAGE_KEY)
    if not raw:
        return base
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return base
    if not isinstance(data, dict):
        return base
    for k in base:
        if k in data and data[k] is not None:
            base[k] = data[k] if isinstance(base[k], bool) else str(data[k])[:20000]
    return base


def mask_storage(cfg):
    out = json.loads(json.dumps(cfg))
    sa = (cfg.get("service_account_json") or "").strip()
    out["service_account_json"] = "********" if sa else ""
    out["service_account_set"] = bool(sa)
    out["sa_email"] = ""
    if sa:
        try:
            out["sa_email"] = (json.loads(sa) or {}).get("client_email") or ""
        except Exception:
            out["sa_email"] = ""
    return out


def save_storage(conn, incoming):
    current = get_storage(conn)
    inc = incoming if isinstance(incoming, dict) else {}
    for k, default in _default_storage().items():
        if k not in inc:
            continue
        val = inc[k]
        if k == "service_account_json" and val == "********":
            continue
        if isinstance(default, bool):
            current[k] = bool(val)
        else:
            current[k] = str(val or "")[:20000]
    agent_engine.set_setting(conn, _STORAGE_KEY, json.dumps(current, ensure_ascii=False))
    return current


def storage_ready(cfg):
    return bool(cfg.get("enabled") and (cfg.get("service_account_json") or "").strip())


def _drive_service(cfg):
    sa = (cfg.get("service_account_json") or "").strip()
    if not sa:
        raise RuntimeError("ยังไม่ได้ตั้ง Service account JSON")
    try:
        info = json.loads(sa)
    except Exception as exc:
        raise RuntimeError(f"Service account JSON ไม่ถูกต้อง: {exc}") from exc
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError(
            "เซิร์ฟเวอร์ยังไม่ติดตั้ง google-api-python-client/google-auth — deploy ใหม่ให้ติดตั้ง requirements"
        ) from exc
    creds = Credentials.from_service_account_info(info, scopes=_DRIVE_SCOPES)
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    return svc, info


def drive_upload_bytes(cfg, filename, data, mimetype=""):
    svc, _ = _drive_service(cfg)
    try:
        from googleapiclient.http import MediaIoBaseUpload
    except Exception as exc:
        raise RuntimeError("ยังไม่ติดตั้ง google-api-python-client") from exc
    meta = {"name": filename}
    folder = (cfg.get("folder_id") or "").strip()
    if folder:
        meta["parents"] = [folder]
    media = MediaIoBaseUpload(
        io.BytesIO(data), mimetype=mimetype or "application/octet-stream", resumable=False
    )
    created = svc.files().create(
        body=meta, media_body=media, fields="id,name,size", supportsAllDrives=True
    ).execute()
    return created.get("id")


def drive_download_bytes(cfg, file_id):
    svc, _ = _drive_service(cfg)
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except Exception as exc:
        raise RuntimeError("ยังไม่ติดตั้ง google-api-python-client") from exc
    req = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def drive_delete_file(cfg, file_id):
    svc, _ = _drive_service(cfg)
    svc.files().delete(fileId=file_id, supportsAllDrives=True).execute()


def drive_test(cfg):
    svc, info = _drive_service(cfg)
    result = {"ok": True, "sa_email": info.get("client_email") or ""}
    folder = (cfg.get("folder_id") or "").strip()
    if folder:
        meta = svc.files().get(
            fileId=folder, fields="id,name,mimeType", supportsAllDrives=True
        ).execute()
        result["folder"] = {"id": meta.get("id"), "name": meta.get("name")}
    else:
        about = svc.about().get(fields="user(displayName,emailAddress)").execute()
        result["user"] = about.get("user", {})
    return result


def _doc_local_path(doc):
    return (UPLOAD_DIR / os.path.basename(doc["stored_name"])).resolve()


def _doc_bytes(conn, doc):
    """คืน bytes ของเอกสาร: ใช้ไฟล์ในเครื่องก่อน ถ้าไม่มีค่อยดึงจาก Google Drive."""
    path = _doc_local_path(doc)
    if str(path).startswith(str(UPLOAD_DIR.resolve())) and path.exists():
        return path.read_bytes()
    fid = ""
    try:
        fid = (doc["drive_file_id"] or "").strip()
    except Exception:
        fid = ""
    if fid:
        cfg = get_storage(conn)
        if storage_ready(cfg):
            return drive_download_bytes(cfg, fid)
    return None


def send_line_push(token, to, text):
    payload = {"to": to, "messages": [{"type": "text", "text": str(text)[:5000]}]}
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": 200 <= resp.status < 300, "status": resp.status}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        return {"ok": False, "status": e.code, "error": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send_line_reply(token, reply_token, text):
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": str(text)[:5000]}]}
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/reply",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": 200 <= resp.status < 300, "status": resp.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send_webhook(url, payload, secret=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Office-Secret"] = secret
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return {"ok": 200 <= resp.status < 300, "status": resp.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def dispatch_dept_event(conn, dept_id, event, message, payload=None):
    """ส่งแจ้งเตือนอัตโนมัติไป LINE/Webhook ของแผนก (best-effort)."""
    if not dept_id:
        return
    try:
        cfg = get_integrations(conn, int(dept_id))
    except Exception:
        return
    body = {"event": event, "department_id": dept_id, "message": message, "data": payload or {}}
    try:
        if cfg.get("webhook", {}).get("enabled") and cfg["webhook"].get("url"):
            send_webhook(cfg["webhook"]["url"], body, cfg["webhook"].get("secret"))
    except Exception:
        pass
    try:
        line = cfg.get("line", {})
        if line.get("enabled") and line.get("notify_events") and line.get("channel_access_token") and line.get("to"):
            send_line_push(line["channel_access_token"], line["to"], f"[Virtual Office] {message}")
    except Exception:
        pass

def sync_google_sheets(cfg, rows, headers):
    sa = (cfg.get("service_account_json") or "").strip()
    sid = (cfg.get("spreadsheet_id") or "").strip()
    sname = (cfg.get("sheet_name") or "Tasks").strip() or "Tasks"
    if not sa or not sid:
        return {"ok": False, "error": "ต้องใส่ Spreadsheet ID และ Service account JSON"}
    try:
        info = json.loads(sa)
    except Exception as e:
        return {"ok": False, "error": f"Service account JSON ไม่ถูกต้อง: {e}"}
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception:
        return {"ok": False, "error": "ยังไม่ติดตั้งไลบรารี Google Sheets (gspread/google-auth) บนเซิร์ฟเวอร์นี้ — ใช้ปุ่มส่งออก CSV แทนได้ หรือ deploy ใหม่ให้ติดตั้ง dependencies"}
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sid)
        try:
            ws = sh.worksheet(sname)
        except Exception:
            ws = sh.add_worksheet(title=sname[:100], rows=max(100, len(rows)+10), cols=max(10, len(headers)))
        ws.clear()
        ws.update([headers] + rows, value_input_option="USER_ENTERED")
        return {"ok": True, "sheet": sname, "rows": len(rows)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/departments/<int:dept_id>/integrations")
@login_required
def api_dept_integrations_get(dept_id):
    conn = get_db()
    dept = conn.execute("SELECT id, name, name_en FROM departments WHERE id=?", (dept_id,)).fetchone()
    if not dept:
        return jsonify(error="ไม่พบแผนก"), 404
    cfg = get_integrations(conn, dept_id)
    callback_url = request.url_root.rstrip("/") + f"/api/integrations/line/webhook/{dept_id}"
    return jsonify(ok=True, integrations=mask_integrations(cfg), department={"id": dept["id"], "name": dept["name"], "name_en": dept["name_en"]}, line_callback_url=callback_url)

@app.put("/api/departments/<int:dept_id>/integrations")
@login_required
def api_dept_integrations_put(dept_id):
    conn = get_db()
    user = current_user(conn)
    dept = conn.execute("SELECT id, name FROM departments WHERE id=?", (dept_id,)).fetchone()
    if not dept:
        return jsonify(error="ไม่พบแผนก"), 404
    data = request.get_json(silent=True) or {}
    cfg = save_integrations(conn, dept_id, data)
    log(conn, user["display_name"], "อัปเดตการเชื่อมต่อ", f"{dept['name']}")
    conn.commit()
    return jsonify(ok=True, integrations=mask_integrations(cfg))

@app.post("/api/departments/<int:dept_id>/integrations/test")
@login_required
def api_dept_integrations_test(dept_id):
    conn = get_db()
    dept = conn.execute("SELECT id, name FROM departments WHERE id=?", (dept_id,)).fetchone()
    if not dept:
        return jsonify(error="ไม่พบแผนก"), 404
    cfg = get_integrations(conn, dept_id)
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip()
    results = {}
    if provider in ("line", "all") and cfg["line"].get("enabled") and cfg["line"].get("channel_access_token") and cfg["line"].get("to"):
        results["line"] = send_line_push(cfg["line"]["channel_access_token"], cfg["line"]["to"], f"[Virtual Office] ทดสอบการเชื่อมต่อจากแผนก {dept['name']} สำเร็จ ✅")
    if provider in ("webhook", "all") and cfg["webhook"].get("enabled") and cfg["webhook"].get("url"):
        results["webhook"] = send_webhook(cfg["webhook"]["url"], {"event": "test", "department": dept["name"], "message": "Virtual Office integration test"}, cfg["webhook"].get("secret"))
    if provider == "sheets":
        rows = [[r["id"], r["title"], r["status"], r["priority"], r["due_date"] or "", r["agent"] or ""] for r in conn.execute("SELECT t.id,t.title,t.status,t.priority,t.due_date,a.name agent FROM tasks t LEFT JOIN agents a ON a.id=t.agent_id WHERE t.department_id=? ORDER BY t.id DESC LIMIT 200", (dept_id,)).fetchall()]
        results["sheets"] = sync_google_sheets(cfg.get("google_sheets", {}), rows, ["id","title","status","priority","due_date","agent"])
    if not results:
        results["info"] = {"ok": False, "error": "ยังไม่ได้ตั้งค่าหรือเปิดใช้งานผู้ให้บริการที่เลือก (LINE ต้องมี token+to, Webhook ต้องมี URL, Sheets ต้องมี ID+Service account JSON)"}
    return jsonify(ok=any(v.get("ok") for v in results.values() if isinstance(v, dict)), results=results)

@app.post("/api/departments/<int:dept_id>/integrations/sheets/sync")
@login_required
def api_dept_sheets_sync(dept_id):
    conn = get_db()
    user = current_user(conn)
    dept = conn.execute("SELECT id, name FROM departments WHERE id=?", (dept_id,)).fetchone()
    if not dept:
        return jsonify(error="ไม่พบแผนก"), 404
    cfg = get_integrations(conn, dept_id)
    rows = [[r["id"], r["title"], r["status"], r["priority"], r["due_date"] or "", r["due_time"] or "", r["agent"] or "", (r["detail"] or "").replace("\n"," ")] for r in conn.execute("SELECT t.id,t.title,t.status,t.priority,t.due_date,t.due_time,a.name agent,t.detail FROM tasks t LEFT JOIN agents a ON a.id=t.agent_id WHERE t.department_id=? ORDER BY t.id DESC", (dept_id,)).fetchall()]
    res = sync_google_sheets(cfg.get("google_sheets", {}), rows, ["id","title","status","priority","due_date","due_time","agent","detail"])
    if res.get("ok"):
        log(conn, user["display_name"], "ซิงก์ Google Sheets", f"{dept['name']} ({res.get('rows',0)} แถว)")
        conn.commit()
    return jsonify(res), (200 if res.get("ok") else 400)

@app.get("/api/storage")
@login_required
def api_storage_get():
    conn = get_db()
    cfg = get_storage(conn)
    return jsonify(
        ok=True,
        storage=mask_storage(cfg),
        db={"mode": database.db_mode(), "persistent": database.using_turso()},
    )


@app.put("/api/storage")
@login_required
def api_storage_put():
    conn = get_db()
    user = current_user(conn)
    data = request.get_json(silent=True) or {}
    cfg = save_storage(conn, data)
    log(conn, user["display_name"], "อัปเดตที่เก็บไฟล์", "Google Drive" if cfg.get("enabled") else "ปิดใช้งาน")
    conn.commit()
    return jsonify(ok=True, storage=mask_storage(cfg))


@app.post("/api/storage/test")
@login_required
def api_storage_test():
    conn = get_db()
    cfg = get_storage(conn)
    if not storage_ready(cfg):
        return jsonify(ok=False, error="ยังไม่ได้เปิดใช้งานหรือใส่ Service account JSON"), 400
    try:
        res = drive_test(cfg)
        return jsonify(res)
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)[:500]), 400


@app.post("/api/storage/migrate-uploads")
@login_required
def api_storage_migrate_uploads():
    conn = get_db()
    user = current_user(conn)
    cfg = get_storage(conn)
    if not storage_ready(cfg):
        return jsonify(ok=False, error="ยังไม่ได้เปิดใช้งานหรือใส่ Service account JSON"), 400
    limit = 100
    docs = conn.execute(
        "SELECT * FROM documents WHERE COALESCE(drive_file_id,'')='' ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    uploaded = 0
    failed = 0
    errors = []
    for doc in docs:
        path = _doc_local_path(doc)
        if not (str(path).startswith(str(UPLOAD_DIR.resolve())) and path.exists()):
            failed += 1
            errors.append(f"{doc['title']}: ไม่พบไฟล์ในเครื่อง (ข้าม)")
            continue
        try:
            fid = drive_upload_bytes(cfg, doc["stored_name"] or doc["filename"], path.read_bytes(), doc["mime"])
            conn.execute("UPDATE documents SET drive_file_id=? WHERE id=?", (fid, doc["id"]))
            uploaded += 1
        except Exception as exc:
            failed += 1
            errors.append(f"{doc['title']}: {str(exc)[:160]}")
    remaining = conn.execute(
        "SELECT COUNT(*) c FROM documents WHERE COALESCE(drive_file_id,'')=''"
    ).fetchone()["c"]
    log(conn, user["display_name"], "อัปโหลดไฟล์ขึ้น Google Drive", f"สำเร็จ {uploaded} / ล้มเหลว {failed}")
    conn.commit()
    return jsonify(ok=True, uploaded=uploaded, failed=failed, remaining=remaining, errors=errors[:10])


@app.get("/api/system/status")
@login_required
def api_system_status():
    conn = get_db()
    cfg = get_storage(conn)
    return jsonify(
        ok=True,
        db={
            "mode": database.db_mode(),
            "persistent": database.using_turso(),
            "label": "Turso (ถาวร)" if database.using_turso() else "SQLite ในเครื่อง/ดิสก์ชั่วคราว",
        },
        storage={
            "enabled": bool(cfg.get("enabled")),
            "ready": storage_ready(cfg),
            "folder_id": cfg.get("folder_id") or "",
        },
    )


@app.post("/api/integrations/line/webhook/<int:dept_id>")
def api_line_webhook(dept_id):
    """LINE Messaging API inbound webhook (ตั้ง URL นี้ใน LINE Developers)."""
    conn = get_db()
    dept = conn.execute("SELECT id, name FROM departments WHERE id=?", (dept_id,)).fetchone()
    if not dept:
        return jsonify(ok=False), 404
    cfg = get_integrations(conn, dept_id)
    secret = (cfg.get("line", {}).get("channel_secret") or "").strip()
    body = request.get_data() or b""
    # verify signature when secret is configured
    if secret:
        sig = request.headers.get("X-Line-Signature", "")
        mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("utf-8")
        if not hmac.compare_digest(sig, expected):
            return jsonify(ok=False, error="invalid signature"), 403
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except Exception:
        data = {}
    events = data.get("events") or []
    token = (cfg.get("line", {}).get("channel_access_token") or "").strip()
    replies = 0
    for ev in events:
        if ev.get("type") != "message":
            continue
        msg = ev.get("message") or {}
        if msg.get("type") != "text":
            continue
        text = (msg.get("text") or "").strip()
        reply_token = ev.get("replyToken")
        if not text:
            continue
        # route to department's agent/command
        agent = conn.execute("SELECT * FROM agents WHERE department_id=? AND active=1 ORDER BY sort_order, id LIMIT 1", (dept_id,)).fetchone()
        if not agent:
            agent = _default_agent(conn)
        user = conn.execute("SELECT display_name FROM users WHERE role='owner' LIMIT 1").fetchone()
        actor = f"LINE:{dept['name']}"
        result = None
        try:
            cmd = agent_engine.parse_command(conn, agent, text)
            if cmd:
                result = execute_agent_command(conn, agent, cmd, actor, scoped=True)
            else:
                result = agent_engine.agent_reply(conn, agent, text, [], tool_executor=lambda name, args: execute_agent_tool(conn, agent, name, args, actor))
            conn.commit()
        except Exception as e:
            result = {"reply": f"รับข้อความแล้ว แต่ประมวลผลไม่สำเร็จ: {e}"}
        reply_text = (result or {}).get("reply") or "รับข้อความแล้ว"
        if token and reply_token:
            send_line_reply(token, reply_token, reply_text)
            replies += 1
    return jsonify(ok=True, handled=len(events), replies=replies)

@app.get("/api/departments/<int:dept_id>/export/tasks.csv")
@login_required
def api_dept_export_tasks(dept_id):
    conn = get_db()
    dept = conn.execute("SELECT id, name FROM departments WHERE id=?", (dept_id,)).fetchone()
    if not dept:
        return jsonify(error="ไม่พบแผนก"), 404
    rows = conn.execute(
        """SELECT t.id, t.title, t.status, t.priority, t.due_date, t.due_time, a.name as agent, t.detail
           FROM tasks t LEFT JOIN agents a ON a.id=t.agent_id WHERE t.department_id=? ORDER BY t.id DESC""",
        (dept_id,),
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "status", "priority", "due_date", "due_time", "agent", "detail", "department"])
    for r in rows:
        w.writerow([r["id"], r["title"], r["status"], r["priority"], r["due_date"] or "", r["due_time"] or "", r["agent"] or "", (r["detail"] or "").replace("\n", " "), dept["name"]])
    data = ("\ufeff" + buf.getvalue()).encode("utf-8")
    from flask import Response
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=tasks-dept-{dept_id}.csv"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5100"))
    debug = os.environ.get("OFFICE_DEBUG") == "1"
    print(f"\n  Virtual Office  -  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
