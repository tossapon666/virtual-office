"""ฐานข้อมูลและข้อมูลตั้งต้นของ Virtual Office."""
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("OFFICE_DB") or (BASE_DIR / "office.db"))
UPLOAD_DIR = Path(os.environ.get("OFFICE_UPLOADS") or (BASE_DIR / "uploads"))

# --- Turso / libSQL (ฐานข้อมูลถาวรบนคลาวด์) -------------------------------
# ตั้ง TURSO_DATABASE_URL + TURSO_AUTH_TOKEN แล้วแอปจะเก็บข้อมูลบน Turso แทน
# ไฟล์ office.db ในเครื่อง (ถ้ามี) จะไม่ถูกใช้เป็นแหล่งข้อมูลหลัก
TURSO_URL = (os.environ.get("TURSO_DATABASE_URL") or os.environ.get("LIBSQL_URL") or "").strip()
TURSO_TOKEN = (os.environ.get("TURSO_AUTH_TOKEN") or os.environ.get("LIBSQL_AUTH_TOKEN") or "").strip()


def using_turso():
    return bool(TURSO_URL)


def db_mode():
    return "turso" if using_turso() else "local"


class Row(dict):
    """แถวข้อมูลที่รองรับทั้ง row["ชื่อคอลัมน์"] และ row[0] เหมือน sqlite3.Row."""

    __slots__ = ("_values",)

    def __init__(self, keys, values):
        super().__init__(zip(keys or (), values or ()))
        self._values = tuple(values or ())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def __repr__(self):
        return f"Row({dict(self)!r})"


def _col_names(cur):
    desc = getattr(cur, "description", None)
    if not desc:
        return []
    return [d[0] if not isinstance(d, (list, tuple)) else d[0] for d in desc]


class _LibsqlCursor:
    """ห่อ cursor ของ libsql ให้คืน Row และค่าสถานะคงที่เหมือน sqlite3.

    libsql อัปเดต lastrowid/rowcount ของ Cursor ตามคำสั่งล่าสุดทั้ง connection
    ต่างจาก sqlite3 ที่ผูกกับคำสั่งของ cursor นั้น จึงต้องจับค่าไว้ตอน execute
    """

    def __init__(self, cur):
        self._cur = cur
        self._keys = _col_names(cur)
        self._lastrowid = getattr(cur, "lastrowid", None)
        self._rowcount = getattr(cur, "rowcount", -1)
        self._description = getattr(cur, "description", None)

    def _snapshot(self):
        self._keys = _col_names(self._cur)
        self._lastrowid = getattr(self._cur, "lastrowid", None)
        self._rowcount = getattr(self._cur, "rowcount", -1)
        self._description = getattr(self._cur, "description", None)

    def execute(self, sql, params=()):
        self._cur.execute(sql, params)
        self._snapshot()
        return self

    def executemany(self, sql, seq):
        self._cur.executemany(sql, seq)
        self._snapshot()
        return self

    def _row(self, values):
        if values is None:
            return None
        return Row(self._keys, values)

    def fetchone(self):
        return self._row(self._cur.fetchone())

    def fetchmany(self, size=1):
        return [self._row(v) for v in self._cur.fetchmany(size)]

    def fetchall(self):
        return [self._row(v) for v in self._cur.fetchall()]

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._rowcount

    @property
    def description(self):
        return self._description

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class _LibsqlConnection:
    """ห่อ connection ของ libsql ให้ API ใกล้เคียง sqlite3."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        return _LibsqlCursor(self._conn.execute(sql, params))

    def executemany(self, sql, seq):
        return _LibsqlCursor(self._conn.executemany(sql, seq))

    def executescript(self, script):
        return self._conn.executescript(script)

    def cursor(self):
        return _LibsqlCursor(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_en TEXT DEFAULT '',
    icon TEXT DEFAULT '🏢',
    color TEXT DEFAULT '#0f766e',
    tagline TEXT DEFAULT '',
    description TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    emoji TEXT DEFAULT '🤖',
    color TEXT DEFAULT '#0f766e',
    status TEXT NOT NULL DEFAULT 'working',
    persona TEXT DEFAULT '',
    duties TEXT DEFAULT '',
    active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'todo'
        CHECK(status IN ('todo','doing','done','cancelled')),
    priority TEXT NOT NULL DEFAULT 'normal'
        CHECK(priority IN ('low','normal','high','urgent')),
    due_date TEXT,
    due_time TEXT,
    repeat_rule TEXT DEFAULT 'none',
    tags TEXT DEFAULT '',
    recurrence_generated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT DEFAULT 'ยังไม่จัดหมวด',
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime TEXT DEFAULT '',
    size INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    drive_file_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'reminder',
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    ref_type TEXT,
    ref_id INTEGER,
    dedupe TEXT UNIQUE,
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS widgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    widget_type TEXT NOT NULL,
    title TEXT NOT NULL,
    size TEXT DEFAULT 'half',
    position INTEGER DEFAULT 0,
    visible INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date, status);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(is_read, created_at);
CREATE INDEX IF NOT EXISTS idx_docs_dept ON documents(department_id);
"""

DEPARTMENTS = [
    ("สำนักเลขา", "Secretariat / Executive Office", "🗂️", "#d97706", "ผู้ช่วยส่วนตัวและภาพรวมงานทั้งออฟฟิศ",
     "ดูแลตารางงาน สรุปภาพรวม แจ้งเตือนกำหนดส่ง และจัดลำดับความสำคัญให้ผู้บริหาร"),
    ("ฝ่ายบัญชี", "Accounting", "🧾", "#059669", "รายรับ–รายจ่าย เอกสารการเงิน และภาษี",
     "ตรวจสอบใบกำกับ ปิดบัญชีประจำเดือน สรุปรายจ่าย และเตือนกำหนดยื่นภาษี"),
    ("ฝ่ายเอกสาร", "Documents / Contracts", "📄", "#2563eb", "สัญญา หนังสือราชการ และเอกสารลูกค้า",
     "จัดทำและตรวจสอบสัญญา ติดตามเอกสารที่ครบกำหนด และดูแลความถูกต้องของหนังสือ"),
    ("คลังเอกสารและไฟล์", "Archive & File Storage", "🗄️", "#7c3aed", "จัดเก็บ ค้นคืน และสำรองข้อมูล",
     "จัดหมวดไฟล์ให้ค้นหาง่าย ตรวจไฟล์ที่ยังไม่จัดหมวด และสำรองข้อมูลสำคัญเป็นประจำ"),
    ("ฝ่ายปฏิบัติการ", "Operations", "⚙️", "#dc2626", "งานธุรการ ประสานงาน และการประชุม",
     "ประสานงานระหว่างแผนก ติดตามงานค้าง จัดประชุม และอัปเดตรายชื่อผู้ติดต่อ"),
    ("แผนกสต็อก", "Stock / Inventory", "📦", "#0891b2", "สินค้าคงคลัง รับเข้า–เบิกออก และตรวจนับสต็อก",
     "ติดตามระดับสต็อก รับเข้า/เบิกจ่ายสินค้า แจ้งเตือนของใกล้หมด และจัดทำรายงานสต็อก/Excel"),
]

AGENTS = [
    (0, "น้องลิน", "เลขาธิการส่วนตัว", "👩‍💼", "#d97706", "working",
     "ละเอียด รอบคอบ พูดจาสุภาพ ตรงต่อเวลา และชอบสรุปเป็นข้อ ๆ",
     "สรุปงานประจำวัน • แจ้งเตือนกำหนดส่ง • จัดลำดับความสำคัญ • นัดหมายและจดบันทึก"),
    (1, "พี่บี", "นักบัญชี", "🧑‍💻", "#059669", "working",
     "ละเอียดกับตัวเลข ระวังข้อผิดพลาด และอธิบายเรื่องการเงินให้เข้าใจง่าย",
     "ตรวจเอกสารการเงิน • เตือนปิดบัญชี • สรุปรายจ่าย • ดูแลกำหนดยื่นภาษี"),
    (2, "น้องเอก", "เจ้าหน้าที่เอกสาร", "🧑‍🏫", "#2563eb", "working",
     "เป็นระเบียบ ช่างตรวจทาน และจำวันครบกำหนดของเอกสารได้แม่น",
     "ตรวจสัญญา • ติดตามเอกสารครบกำหนด • จัดทำหนังสือ • ดูแลความถูกต้องของแบบฟอร์ม"),
    (3, "พี่คลัง", "ผู้ดูแลคลังเอกสาร", "🧑‍💼", "#7c3aed", "idle",
     "ใจเย็น เป็นระบบ และเชื่อว่าทุกไฟล์ต้องมีที่อยู่ของมัน",
     "จัดหมวดไฟล์ • ตรวจไฟล์ที่ยังไม่จัดหมวด • สำรองข้อมูล • ค้นคืนเอกสารย้อนหลัง"),
    (4, "น้องมิ้น", "ธุรการปฏิบัติการ", "👩‍🔧", "#dc2626", "working",
     "กระตือรือร้น ชอบประสานงาน และตามงานให้จบตรงเวลา",
     "ประสานงานระหว่างแผนก • ติดตามงานค้าง • จัดประชุม • อัปเดตรายชื่อผู้ติดต่อ"),
    (5, "พี่สต็อก", "เจ้าหน้าที่สต็อก", "📦", "#0891b2", "working",
     "รอบคอบเรื่องตัวเลขและรายการสินค้า ชอบความถูกต้องของยอดคงคลัง",
     "ตรวจระดับสต็อก • บันทึกรับเข้า/เบิกออก • แจ้งเตือนของใกล้หมด • จัดทำรายงานสต็อกและไฟล์ Excel"),
]

WIDGETS = [
    ("overview", "ภาพรวมวันนี้", "full"),
    ("today", "งานที่ต้องทำวันนี้", "half"),
    ("overdue", "งานเกินกำหนด", "half"),
    ("upcoming", "งานกำลังจะถึง", "half"),
    ("workload", "ภาระงานแต่ละแผนก", "half"),
    ("team", "สถานะทีม AI", "third"),
    ("docs", "เอกสารล่าสุด", "third"),
    ("quickadd", "เพิ่มงานเร็ว", "third"),
    ("calendar", "ปฏิทินย่อ", "half"),
    ("activity", "กิจกรรมล่าสุด", "half"),
]


def connect():
    if using_turso():
        try:
            import libsql
        except Exception as exc:  # pragma: no cover - depends on deploy env
            raise RuntimeError(
                "ตั้ง TURSO_DATABASE_URL ไว้แต่ยังไม่ได้ติดตั้งไลบรารี libsql "
                "(pip install libsql) — หรือเอา env ออกเพื่อใช้ SQLite ในเครื่อง"
            ) from exc
        conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
        wrapped = _LibsqlConnection(conn)
        try:
            wrapped.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        return wrapped
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _day(offset):
    return (datetime.now().date() + timedelta(days=offset)).isoformat()


def _table_columns(conn, table):
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        try:
            return [r[1] for r in conn.execute(
                "SELECT * FROM pragma_table_info(?)", (table,)
            ).fetchall()]
        except Exception:
            return []


def init_db():
    if not using_turso():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    empty = conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0
    if empty:
        seed(conn)
    else:
        migrate(conn)
    conn.commit()
    conn.close()


def migrate(conn):
    """อัปเดต DB เดิมให้มีแผนก/agent คอลัมน์/ตารางที่เพิ่มใหม่ (idempotent)."""
    # add name_en column
    cols = _table_columns(conn, "departments")
    if "name_en" not in cols:
        conn.execute("ALTER TABLE departments ADD COLUMN name_en TEXT DEFAULT ''")
    # add drive_file_id column (Google Drive storage)
    doc_cols = _table_columns(conn, "documents")
    if doc_cols and "drive_file_id" not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN drive_file_id TEXT DEFAULT ''")
    en_map = {
        "สำนักเลขา": "Secretariat / Executive Office",
        "ฝ่ายบัญชี": "Accounting",
        "ฝ่ายเอกสาร": "Documents / Contracts",
        "คลังเอกสารและไฟล์": "Archive & File Storage",
        "ฝ่ายปฏิบัติการ": "Operations",
        "แผนกสต็อก": "Stock / Inventory",
    }
    for th, en in en_map.items():
        conn.execute("UPDATE departments SET name_en=? WHERE name=? AND (name_en IS NULL OR name_en='')", (en, th))
    # แผนกสต็อก
    row = conn.execute("SELECT id FROM departments WHERE name=?", ("แผนกสต็อก",)).fetchone()
    if not row:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) m FROM departments").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO departments (name, name_en, icon, color, tagline, description, sort_order) VALUES (?,?,?,?,?,?,?)",
            ("แผนกสต็อก", "Stock / Inventory", "📦", "#0891b2", "สินค้าคงคลัง รับเข้า–เบิกออก และตรวจนับสต็อก",
             "ติดตามระดับสต็อก รับเข้า/เบิกจ่ายสินค้า แจ้งเตือนของใกล้หมด และจัดทำรายงานสต็อก/Excel",
             max_order + 1),
        )
        dept_id = cur.lastrowid
    else:
        dept_id = row["id"]
    if not conn.execute("SELECT 1 FROM agents WHERE name=? AND department_id=?", ("พี่สต็อก", dept_id)).fetchone():
        max_a = conn.execute("SELECT COALESCE(MAX(sort_order), -1) m FROM agents").fetchone()["m"]
        conn.execute(
            """INSERT INTO agents
               (department_id, name, role, emoji, color, status, persona, duties, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (dept_id, "พี่สต็อก", "เจ้าหน้าที่สต็อก", "📦", "#0891b2", "working",
             "รอบคอบเรื่องตัวเลขและรายการสินค้า ชอบความถูกต้องของยอดคงคลัง",
             "ตรวจระดับสต็อก • บันทึกรับเข้า/เบิกออก • แจ้งเตือนของใกล้หมด • จัดทำรายงานสต็อกและไฟล์ Excel",
             max_a + 1),
        )
        conn.execute(
            "INSERT INTO activity (actor, action, detail) VALUES (?,?,?)",
            ("ระบบ", "เพิ่มแผนก", "เพิ่มแผนกสต็อกและผู้ช่วยพี่สต็อก"),
        )


def seed(conn):
    now = datetime.now()
    password = os.environ.get("OFFICE_PASSWORD", "admin123")
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, display_name, role) VALUES (?,?,?,?)",
        ("admin", generate_password_hash(password), "ผู้จัดการออฟฟิศ", "owner"),
    )
    user_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]

    dept_ids = []
    for order, (name, name_en, icon, color, tagline, desc) in enumerate(DEPARTMENTS):
        cur = conn.execute(
            "INSERT INTO departments (name, name_en, icon, color, tagline, description, sort_order) VALUES (?,?,?,?,?,?,?)",
            (name, name_en, icon, color, tagline, desc, order),
        )
        dept_ids.append(cur.lastrowid)

    agent_ids = []
    for order, (di, name, role, emoji, color, status, persona, duties) in enumerate(AGENTS):
        cur = conn.execute(
            """INSERT INTO agents
               (department_id, name, role, emoji, color, status, persona, duties, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (dept_ids[di], name, role, emoji, color, status, persona, duties, order),
        )
        agent_ids.append(cur.lastrowid)

    tasks = [
        ("สรุปงานประจำวันเสนอผู้บริหาร", "รวมงานค้าง งานด่วน และนัดหมายของวันนี้ไว้ในกระดาษแผ่นเดียว",
         0, 0, "todo", "high", _day(0), "09:00", "daily"),
        ("ตรวจใบกำกับภาษีเดือนนี้", "ตรวจความถูกต้องของเลขใบกำกับและยอดรวมก่อนส่งฝ่ายบัญชี",
         1, 1, "doing", "high", _day(1), "10:00", "none"),
        ("ปิดบัญชีประจำเดือน", "กระทบยอดธนาคารและปิดงบเดือนก่อนส่งผู้บริหาร",
         1, 1, "todo", "urgent", _day(3), "16:00", "monthly"),
        ("ต่ออายุสัญญาบริการลูกค้า A", "สัญญาหมดอายุแล้ว ต้องติดต่อลูกค้าและออกฉบับใหม่",
         2, 2, "todo", "urgent", _day(-1), "12:00", "none"),
        ("จัดทำหนังสือแจ้งลูกค้า", "ร่างหนังสือแจ้งปรับรอบบริการและส่งให้หัวหน้าตรวจ",
         2, 2, "todo", "normal", _day(2), "15:00", "none"),
        ("จัดหมวดไฟล์สัญญาปี 2026", "แยกโฟลเดอร์ตามลูกค้าและปีให้ค้นหาได้ภายใน 1 นาที",
         3, 3, "todo", "normal", _day(4), "11:00", "none"),
        ("สำรองข้อมูลเอกสารสำคัญ", "สำรองไฟล์ขึ้นคลาวด์และตรวจว่ากู้คืนได้",
         3, 3, "todo", "low", _day(6), "17:00", "weekly"),
        ("ประชุมทีมประจำสัปดาห์", "สรุปความคืบหน้าแต่ละแผนกและกำหนดงานสัปดาห์หน้า",
         4, 4, "todo", "normal", _day(0), "14:00", "weekly"),
        ("ติดตามใบเสนอราคาลูกค้า B", "ลูกค้ายังไม่ตอบกลับเกินกำหนด 2 วัน ต้องโทรติดตาม",
         4, 4, "todo", "high", _day(-2), "10:30", "none"),
        ("ตรวจรายจ่ายพนักงาน", "ตรวจใบเสร็จและสรุปยอดเบิกจ่ายรอบสัปดาห์",
         1, 1, "todo", "normal", _day(2), "13:00", "weekly"),
        ("อัปเดตรายชื่อผู้ติดต่อ", "เพิ่มเบอร์และอีเมลของลูกค้าใหม่เข้าระบบ",
         4, 4, "done", "low", _day(-1), "16:00", "none"),
        ("ส่งรายงานภาษี", "ยื่นแบบและเก็บหลักฐานการยื่นเข้าระบบ",
         1, 1, "done", "high", _day(-3), "09:00", "monthly"),
        ("ทบทวนคู่มือการจัดเก็บเอกสาร", "ปรับขั้นตอนให้ตรงกับโครงสร้างโฟลเดอร์ใหม่",
         3, 3, "doing", "normal", _day(5), "14:00", "none"),
    ]
    for title, detail, di, ai, status, priority, due, due_time, repeat in tasks:
        completed = now.strftime("%Y-%m-%d %H:%M:%S") if status == "done" else None
        conn.execute(
            """INSERT INTO tasks
               (title, detail, department_id, agent_id, status, priority, due_date, due_time,
                repeat_rule, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (title, detail, dept_ids[di], agent_ids[ai], status, priority, due, due_time,
             repeat, completed),
        )

    docs = [
        ("สัญญาบริการลูกค้า A", "สัญญา", 2, 2,
         "สัญญาบริการฉบับลงนามแล้ว ระยะเวลา 1 ปี เริ่ม 1 ม.ค. 2025\nคู่สัญญา: บริษัท เอบีซี จำกัด\nผู้รับผิดชอบ: น้องเอก\nหมายเหตุ: ใกล้ครบกำหนดต่ออายุ"),
        ("สรุปค่าใช้จ่ายเดือนตุลาคม", "การเงิน", 1, 1,
         "ค่าบริการ 42,000 บาท\nค่าวัสดุสำนักงาน 8,500 บาท\nค่าเดินทาง 3,200 บาท\nรวมทั้งสิ้น 53,700 บาท\nผู้จัดทำ: พี่บี"),
        ("คู่มือจัดเก็บเอกสารและไฟล์", "คู่มือ", 3, 3,
         "1. ตั้งชื่อไฟล์เป็น YYYY-MM-DD_ชื่อเอกสาร\n2. แยกโฟลเดอร์ตามลูกค้าและปี\n3. ไฟล์ที่ยังไม่จัดหมวดให้ใส่ใน _inbox\n4. สำรองข้อมูลทุกวันศุกร์"),
        ("รายงานประชุมทีมประจำสัปดาห์", "รายงาน", 4, 4,
         "วาระ: ความคืบหน้าแต่ละแผนก\nมติ: เร่งปิดบัญชีภายในวันที่ 5\nผู้จดบันทึก: น้องมิ้น"),
    ]
    for title, category, di, ai, content in docs:
        stored = uuid.uuid4().hex + ".txt"
        path = UPLOAD_DIR / stored
        path.write_text(content, encoding="utf-8")
        conn.execute(
            """INSERT INTO documents
               (title, category, department_id, agent_id, filename, stored_name, mime, size, notes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (title, category, dept_ids[di], agent_ids[ai], title + ".txt", stored,
             "text/plain", path.stat().st_size, "ไฟล์ตัวอย่างสำหรับสาธิตระบบ"),
        )

    for pos, (wtype, title, size) in enumerate(WIDGETS):
        conn.execute(
            "INSERT INTO widgets (user_id, widget_type, title, size, position) VALUES (?,?,?,?,?)",
            (user_id, wtype, title, size, pos),
        )

    conn.execute(
        "INSERT INTO activity (actor, action, detail) VALUES (?,?,?)",
        ("ระบบ", "เปิดออฟฟิศ", "สร้างแผนก ทีม AI และข้อมูลตัวอย่างเรียบร้อยแล้ว"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('last_agent_run', '')"
    )
