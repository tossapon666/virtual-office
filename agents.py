"""สมองของทีม AI: ตรวจงาน แจ้งเตือน ตอบแชท และสั่งงานด้วยภาษาธรรมชาติ."""
import calendar
import difflib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def notify(conn, kind, title, body="", ref_type=None, ref_id=None, dedupe=None):
    cur = conn.execute(
        """INSERT OR IGNORE INTO notifications
           (kind, title, body, ref_type, ref_id, dedupe, created_at)
           VALUES (?,?,?,?,?,?,datetime('now','localtime'))""",
        (kind, title, body, ref_type, ref_id, dedupe),
    )
    return cur.rowcount > 0


def _due_dt(due_date, due_time):
    if not due_date:
        return None
    try:
        d = date.fromisoformat(due_date)
    except ValueError:
        return None
    t = None
    if due_time:
        try:
            t = datetime.strptime(due_time, "%H:%M").time()
        except ValueError:
            t = None
    if t is None:
        t = datetime.strptime("23:59", "%H:%M").time()
    return datetime.combine(d, t)


def _fmt_due(due_date, due_time):
    if not due_date:
        return "ไม่มีกำหนด"
    try:
        d = date.fromisoformat(due_date)
    except ValueError:
        return due_date
    text = f"{d.day} {THAI_MONTHS[d.month - 1]}"
    if due_time:
        text += f" เวลา {due_time}"
    return text


# ---------------------------------------------------------------------------
# Natural-language commands (ทำงานได้ทันทีโดยไม่ต้องใช้ AI ภายนอก)
# ---------------------------------------------------------------------------

THAI_MONTH_INDEX = {
    "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
    "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
    "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
    "พฤศจิกายน": 11, "ธันวาคม": 12,
}
_MONTH_ALT = "|".join(
    re.escape(k) for k in sorted(THAI_MONTH_INDEX, key=len, reverse=True)
)
_WEEKDAY_INDEX = {
    "จันทร์": 0, "อังคาร": 1, "พุธ": 2, "พฤหัสบดี": 3, "พฤหัส": 3,
    "ศุกร์": 4, "เสาร์": 5, "อาทิตย์": 6, "อาทิต": 6,
}

COMMAND_HELP = (
    "พิมพ์สั่งงานได้เลยครับ/ค่ะ เช่น\n"
    "• เพิ่มงาน ตรวจสต็อกพรุ่งนี้ 10:00 ให้พี่บี\n"
    "• เพิ่มงาน ประชุมทีมวันจันทร์ บ่าย 2 ด่วน\n"
    "• ปิดงาน ตรวจรายจ่ายพนักงาน\n"
    "• เลื่อนงาน ปิดบัญชีประจำเดือน ไปวันที่ 20\n"
    "• หาเอกสาร สัญญาลูกค้า A\n"
    "• สรุปงานวันนี้ · งานไหนด่วนที่สุด"
)


def _parse_date(text, today=None):
    """อ่านวันที่จากข้อความภาษาไทยแบบง่าย."""
    today = today or date.today()
    text = text or ""

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})\s*(" + _MONTH_ALT + r")", text)
    if m:
        day = int(m.group(1))
        month = THAI_MONTH_INDEX[m.group(2)]
        year = today.year
        last = calendar.monthrange(year, month)[1]
        if day > last:
            day = last
        found = date(year, month, day)
        if found < today - timedelta(days=30):
            found = date(year + 1, month, day)
        return found

    m = re.search(r"วันที่\s*(\d{1,2})", text)
    if m:
        day = int(m.group(1))
        year, month = today.year, today.month
        if day < today.day:
            month += 1
            if month > 12:
                month = 1
                year += 1
        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(day, last))

    m = re.search(r"อีก\s*(\d{1,2})\s*วัน", text)
    if m:
        return today + timedelta(days=int(m.group(1)))

    if "มะรืน" in text:
        return today + timedelta(days=2)
    if "พรุ่งนี้" in text:
        return today + timedelta(days=1)
    if "วันนี้" in text:
        return today
    if "สัปดาห์หน้า" in text:
        return today + timedelta(days=7)
    if "สิ้นเดือน" in text:
        return date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    if "เดือนหน้า" in text:
        month = today.month + 1
        year = today.year + (1 if month > 12 else 0)
        month = 1 if month > 12 else month
        day = min(today.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    m = re.search(
        r"วัน(จันทร์|อังคาร|พุธ|พฤหัสบดี|พฤหัส|ศุกร์|เสาร์|อาทิตย์|อาทิต)", text
    )
    if m:
        target = _WEEKDAY_INDEX[m.group(1)]
        delta = (target - today.weekday()) % 7
        if delta == 0:
            delta = 7
        return today + timedelta(days=delta)
    return None


def _parse_time(text):
    text = text or ""
    m = re.search(r"(\d{1,2})\s*[:.]\s*(\d{2})", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    if "เที่ยงคืน" in text:
        return "00:00"
    if "เที่ยง" in text:
        return "12:00"
    m = re.search(r"บ่าย\s*(\d{1,2})", text)
    if m:
        return f"{(int(m.group(1)) % 12) + 12:02d}:00"
    m = re.search(r"(\d{1,2})\s*ทุ่ม", text)
    if m:
        return f"{(int(m.group(1)) + 18) % 24:02d}:00"
    m = re.search(r"(\d{1,2})\s*โมง\s*(เช้า|เย็น)?", text)
    if m:
        hour = int(m.group(1))
        if m.group(2) == "เย็น" and hour < 12:
            hour += 12
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
    m = re.search(r"(\d{1,2})\s*น\.", text)
    if m:
        hour = int(m.group(1))
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
    return None


def _parse_priority(text):
    if re.search(r"ด่วนมาก|ด่วนที่สุด|ฉุกเฉิน|urgent", text, re.I):
        return "urgent"
    if re.search(r"ด่วน|สำคัญ|high", text, re.I):
        return "high"
    if re.search(r"ไม่เร่ง|ค่อย\s*ๆ|low", text, re.I):
        return "low"
    return "normal"


def _parse_repeat(text):
    if re.search(r"ทุกวัน|ประจำวัน|daily", text, re.I):
        return "daily"
    if re.search(r"ทุกสัปดาห์|ทุกอาทิตย์|ประจำสัปดาห์|weekly", text, re.I):
        return "weekly"
    if re.search(r"ทุกเดือน|ประจำเดือน|monthly", text, re.I):
        return "monthly"
    if re.search(r"ทุกปี|yearly", text, re.I):
        return "yearly"
    return "none"


_AGENT_ALIASES = {
    "เลขาธิการ": "เลขาธิการ",
    "เลขา": "เลขาธิการ",
    "นักบัญชี": "นักบัญชี",
    "บัญชี": "นักบัญชี",
    "เจ้าหน้าที่เอกสาร": "เจ้าหน้าที่เอกสาร",
    "ผู้ดูแลคลังเอกสาร": "ผู้ดูแลคลังเอกสาร",
    "คลังเอกสาร": "ผู้ดูแลคลังเอกสาร",
    "คลังสินค้า": "เจ้าหน้าที่สต็อก",
    "พี่สต็อก": "เจ้าหน้าที่สต็อก",
    "สต็อก": "เจ้าหน้าที่สต็อก",
    "สต๊อก": "เจ้าหน้าที่สต็อก",
    "สตอก": "เจ้าหน้าที่สต็อก",
    "stock": "เจ้าหน้าที่สต็อก",
    "ผู้ดูแลคลัง": "ผู้ดูแลคลังเอกสาร",
    "คลัง": "ผู้ดูแลคลังเอกสาร",
    "ธุรการ": "ธุรการปฏิบัติการ",
    "ปฏิบัติการ": "ธุรการปฏิบัติการ",
}


def find_agent(conn, text, default=None):
    """หาผู้ช่วยจากชื่อหรือบทบาทที่พิมพ์มา."""
    text = text or ""
    rows = conn.execute("SELECT * FROM agents WHERE active=1").fetchall()
    for a in rows:
        if a["name"] and a["name"] in text:
            return a
    for token, role in _AGENT_ALIASES.items():
        if token in text:
            for a in rows:
                if role in (a["role"] or ""):
                    return a
    return default


_DEPT_ALIASES = {
    "บัญชี": "ฝ่ายบัญชี",
    "เอกสาร": "ฝ่ายเอกสาร",
    "ปฏิบัติการ": "ฝ่ายปฏิบัติการ",
    "เลขา": "สำนักเลขา",
    "คลังเอกสาร": "คลังเอกสารและไฟล์",
    "คลังไฟล์": "คลังเอกสารและไฟล์",
    "คลังสินค้า": "แผนกสต็อก",
    "สต็อก": "แผนกสต็อก",
    "สต๊อก": "แผนกสต็อก",
    "สตอก": "แผนกสต็อก",
    "stock": "แผนกสต็อก",
    "คลัง": "คลังเอกสารและไฟล์",
}


def find_department(conn, text, default=None):
    text = text or ""
    rows = conn.execute("SELECT * FROM departments").fetchall()
    for d in rows:
        if d["name"] and d["name"] in text:
            return d
    m = re.search(r"(?:แผนก|ฝ่าย)\s*(บัญชี|เอกสาร|ปฏิบัติการ|เลขา|คลังสินค้า|คลัง|สต็อก|สต๊อก|สตอก|stock)", text, re.I)
    if m:
        target = _DEPT_ALIASES.get(m.group(1)) or _DEPT_ALIASES.get(m.group(1).lower())
        for d in rows:
            if d["name"] == target:
                return d
    # fallback: english/loose token match via aliases
    tl = (text or "").lower()
    for token, target in _DEPT_ALIASES.items():
        if token.lower() in tl:
            for d in rows:
                if d["name"] == target:
                    return d
    return default


_CONNECTORS = (
    "ให้|กับ|ที่|ใน|ตอน|เวลา|วันที่|แผนก|ฝ่าย|เรื่อง|ว่า|ไป|เป็น|ด้วย|"
    "ครับ|ค่ะ|นะ|คะ|หน่อย|ใหม่|ช่วย|กรุณา|รบกวน"
)

_DATE_STRIP = [
    r"\d{4}-\d{1,2}-\d{1,2}",
    r"\d{1,2}\s*(?:" + _MONTH_ALT + r")",
    r"วันที่\s*\d{1,2}",
    r"อีก\s*\d{1,2}\s*วัน",
    r"มะรืน(?:นี้)?", r"พรุ่งนี้", r"วันนี้", r"สัปดาห์หน้า", r"เดือนหน้า", r"สิ้นเดือน",
    r"วัน(?:จันทร์|อังคาร|พุธ|พฤหัสบดี|พฤหัส|ศุกร์|เสาร์|อาทิตย์|อาทิต)",
]
_TIME_STRIP = [
    r"\d{1,2}\s*[:.]\s*\d{2}\s*(?:น\.)?",
    r"เที่ยงคืน", r"เที่ยง", r"บ่าย\s*\d{1,2}", r"\d{1,2}\s*ทุ่ม",
    r"\d{1,2}\s*โมง\s*(?:เช้า|เย็น)?", r"\d{1,2}\s*น\.",
]
_META_STRIP = _DATE_STRIP + _TIME_STRIP + [
    r"ด่วนมาก|ด่วนที่สุด|ด่วน|สำคัญ|ไม่เร่ง|ค่อย\s*ๆ|urgent|high|low",
    r"ทุกวัน|ทุกสัปดาห์|ทุกอาทิตย์|ทุกเดือน|ทุกปี|ประจำวัน|ประจำสัปดาห์|"
    r"ประจำเดือน|daily|weekly|monthly|yearly",
]


def _clean_title(text):
    text = re.sub(r"\s+", " ", text or "").strip().strip("“”\"' ")
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"^(?:" + _CONNECTORS + r")\s*", "", text, flags=re.I)
        text = re.sub(r"\s*(?:" + _CONNECTORS + r")$", "", text, flags=re.I)
        text = text.strip(" ,.:;·-–—")
    return re.sub(r"\s+", " ", text).strip()


def _strip_meta(text, agent=None, dept=None):
    for pattern in _META_STRIP:
        text = re.sub(pattern, " ", text or "", flags=re.I)
    if agent and agent["name"]:
        text = text.replace(agent["name"], " ")
    if dept and dept["name"]:
        text = text.replace(dept["name"], " ")
    return text


def _norm_text(value):
    value = (value or "").lower()
    return re.sub(r"[\s\"'“”.,:;!?()\[\]{}·\-–—]+", "", value)


def _open_tasks(conn, agent_id=None):
    sql = """SELECT t.*, a.name AS agent_name, a.emoji AS agent_emoji,
                    d.name AS dept_name, d.color AS dept_color
             FROM tasks t
             LEFT JOIN agents a ON a.id=t.agent_id
             LEFT JOIN departments d ON d.id=t.department_id
             WHERE t.status IN ('todo','doing')"""
    args = []
    if agent_id:
        sql += " AND t.agent_id=?"
        args.append(agent_id)
    sql += " ORDER BY (t.due_date IS NULL), t.due_date, t.due_time"
    return conn.execute(sql, args).fetchall()


def find_task_candidates(conn, query, agent_id=None, limit=5):
    """ให้คะแนนงานที่เปิดอยู่เพื่อจับคู่กับชื่อที่ผู้ใช้พิมพ์."""
    q = _norm_text(query)
    seen, rows = set(), []
    pools = []
    if agent_id:
        pools.append(_open_tasks(conn, agent_id))
    pools.append(_open_tasks(conn, None))
    for pool in pools:
        for task in pool:
            if task["id"] not in seen:
                seen.add(task["id"])
                rows.append(task)

    scored = []
    for task in rows:
        title = _norm_text(task["title"])
        if not q:
            score = 0.0
        elif q == title:
            score = 1.0
        elif q in title or title in q:
            score = 0.92
        else:
            score = difflib.SequenceMatcher(None, q, title).ratio()
        scored.append((score, task))
    scored.sort(key=lambda item: -item[0])
    return scored[:limit], bool(q)


def pick_task(conn, query, agent_id=None):
    """เลือกงานเดียวถ้ามั่นใจ ไม่งั้นคืนตัวเลือกให้ผู้ใช้เลือก."""
    scored, has_query = find_task_candidates(conn, query, agent_id)
    if not scored:
        return None, []
    top_score, top = scored[0]
    if not has_query:
        return None, [task for _, task in scored[:3]]
    if top_score >= 0.88:
        return top, []
    if top_score >= 0.55:
        close = [task for score, task in scored if score >= max(0.55, top_score - 0.12)]
        if len(close) == 1:
            return top, []
        return None, close[:3]
    return None, [task for score, task in scored[:3] if score >= 0.3]


def parse_command(conn, agent, message):
    """แปลงข้อความภาษาไทยเป็นคำสั่งที่เรียกใช้ได้ หรือคืน None ถ้าเป็นคำถามทั่วไป."""
    text = (message or "").strip()
    if not text:
        return None

    if re.search(r"ช่วยอะไรได้บ้าง|ใช้ยังไง|วิธีใช้|คำสั่งที่ใช้ได้|^\s*(?:คำสั่ง|help)\s*$", text, re.I):
        return {"intent": "help"}

    # ---- สร้างงาน ----
    m = re.search(
        r"(?:ช่วย|กรุณา|รบกวน)?\s*(?:เพิ่ม|สร้าง|ตั้ง|บันทึก|มอบหมาย)\s*งาน(?:ใหม่)?",
        text,
    )
    if m:
        due = _parse_date(text)
        due_time = _parse_time(text)
        found_agent = find_agent(conn, text, agent)
        found_dept = find_department(conn, text)
        if found_dept is None and found_agent is not None:
            found_dept = conn.execute(
                "SELECT * FROM departments WHERE id=?", (found_agent["department_id"],)
            ).fetchone()
        rest = text[m.end():]
        quoted = re.search(r"[“\"]([^”\"]+)[”\"]", rest)
        if quoted:
            title = quoted.group(1).strip()
        else:
            title = _clean_title(_strip_meta(rest, found_agent, found_dept))
        return {
            "intent": "create",
            "title": title[:180],
            "due_date": due.isoformat() if due else None,
            "due_time": due_time,
            "priority": _parse_priority(text),
            "repeat_rule": _parse_repeat(text),
            "agent_id": found_agent["id"] if found_agent else None,
            "department_id": found_dept["id"] if found_dept else None,
        }

    # ---- ปิดงาน ----
    m = re.search(r"(?:ช่วย)?\s*(?:ปิดงาน|ปิดเคส|ทำเสร็จ(?:แล้ว)?|มาร์คงาน)", text)
    rest = None
    if m:
        rest = text[m.end():]
    else:
        m = re.search(r"(?:เสร็จแล้ว|เรียบร้อยแล้ว)\s*$", text)
        if m:
            rest = text[:m.start()]
    if rest is not None:
        query = _clean_title(_strip_meta(rest))
        task, candidates = pick_task(conn, query, agent["id"])
        return {
            "intent": "complete",
            "query": query,
            "task_id": task["id"] if task else None,
            "task_title": task["title"] if task else None,
            "candidates": [{"id": t["id"], "title": t["title"]} for t in candidates],
        }

    # ---- เลื่อนกำหนด ----
    m = re.search(r"(?:ช่วย)?\s*(?:เลื่อนงาน|เลื่อนกำหนด|เปลี่ยนกำหนด|ย้ายกำหนด|เลื่อน)", text)
    if m:
        due = _parse_date(text)
        rest = text[m.end():]
        query = _clean_title(_strip_meta(rest))
        task, candidates = pick_task(conn, query, agent["id"])
        return {
            "intent": "reschedule",
            "query": query,
            "task_id": task["id"] if task else None,
            "task_title": task["title"] if task else None,
            "due_date": due.isoformat() if due else None,
            "due_time": _parse_time(text),
            "candidates": [{"id": t["id"], "title": t["title"]} for t in candidates],
        }

    # ---- ค้นเอกสาร ----
    m = re.search(r"(?:ช่วย)?\s*(?:หา|ค้น|เปิด|ดู)\s*เอกสาร|เอกสาร(?:เรื่อง|เกี่ยวกับ)", text)
    if m:
        query = _clean_title(_strip_meta(text[m.end():]))
        return {"intent": "search_docs", "query": query}

    # ---- สรุปภาพรวม / งานด่วน (ตรวจท้ายสุด เพื่อไม่ให้ชนกับคำสั่งเพิ่ม/ปิด/เลื่อนงาน) ----
    if re.search(r"สรุปงาน(?:วันนี้|ให้หน่อย|ประจำวัน)?|ภาพรวม(?:งาน)?วันนี้|ภาพรวมงาน", text):
        return {"intent": "summary"}
    if re.search(r"งานไหนด่วนที่สุด|งานด่วน(?:ที่สุด)?|งานอะไรด่วน|ด่วนที่สุด", text):
        return {"intent": "urgent"}
    return None


def run_agents(conn, force=False):
    """ให้ทีม AI ตรวจงานทั้งหมดและสร้างการแจ้งเตือนที่ยังไม่มี."""
    now = datetime.now()
    last = get_setting(conn, "last_agent_run") or ""
    if not force and last:
        try:
            if (now - datetime.fromisoformat(last)).total_seconds() < 40:
                return {"skipped": True, "created": 0}
        except ValueError:
            pass

    today = now.date()
    created = 0
    rows = conn.execute(
        """SELECT t.*, a.name AS agent_name, d.name AS dept_name
           FROM tasks t
           LEFT JOIN agents a ON a.id = t.agent_id
           LEFT JOIN departments d ON d.id = t.department_id
           WHERE t.status IN ('todo','doing')"""
    ).fetchall()

    for t in rows:
        due = _due_dt(t["due_date"], t["due_time"])
        if due is None:
            continue
        who = t["agent_name"] or "ทีม AI"
        dept = t["dept_name"] or "ไม่ระบุแผนก"
        due_text = _fmt_due(t["due_date"], t["due_time"])
        if due < now:
            created += notify(
                conn, "overdue", f"งานเกินกำหนด: {t['title']}",
                f"{who} · {dept} · กำหนด {due_text}",
                "task", t["id"], f"overdue:{t['id']}:{today.isoformat()}",
            )
        elif t["due_date"] == today.isoformat():
            created += notify(
                conn, "reminder", f"งานครบกำหนดวันนี้: {t['title']}",
                f"{who} · {dept} · กำหนด {due_text}",
                "task", t["id"], f"due:{t['id']}",
            )
        else:
            try:
                gap = (date.fromisoformat(t["due_date"]) - today).days
            except ValueError:
                gap = 99
            if 0 <= gap <= 3:
                created += notify(
                    conn, "reminder", f"งานใกล้ถึงกำหนด: {t['title']}",
                    f"{who} · {dept} · อีก {gap} วัน ({due_text})",
                    "task", t["id"], f"soon:{t['id']}",
                )

    open_count = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE status IN ('todo','doing')"
    ).fetchone()["c"]
    overdue_count = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE status IN ('todo','doing') "
        "AND due_date IS NOT NULL AND due_date < ?", (today.isoformat(),)
    ).fetchone()["c"]
    today_count = conn.execute(
        "SELECT COUNT(*) c FROM tasks WHERE status IN ('todo','doing') AND due_date = ?",
        (today.isoformat(),),
    ).fetchone()["c"]
    doc_count = conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"]

    created += notify(
        conn, "briefing", "สรุปงานประจำวันจากน้องลิน",
        f"งานค้างทั้งหมด {open_count} งาน · ครบกำหนดวันนี้ {today_count} · "
        f"เกินกำหนด {overdue_count} · เอกสารในคลัง {doc_count} รายการ",
        None, None, f"briefing:{today.isoformat()}",
    )

    for doc in conn.execute(
        "SELECT id, title FROM documents WHERE category IS NULL OR category='' OR category='ยังไม่จัดหมวด'"
    ).fetchall():
        created += notify(
            conn, "document", f"เอกสารยังไม่จัดหมวด: {doc['title']}",
            "พี่คลังแนะนำให้ใส่หมวดหมู่เพื่อให้ค้นหาได้ง่ายขึ้น",
            "document", doc["id"], f"doc-uncat:{doc['id']}",
        )

    if created:
        conn.execute(
            "INSERT INTO activity (actor, action, detail) VALUES (?,?,?)",
            ("ทีม AI", "ตรวจงานอัตโนมัติ", f"สร้างการแจ้งเตือนใหม่ {created} รายการ"),
        )
    set_setting(conn, "last_agent_run", now.isoformat(timespec="seconds"))
    conn.commit()
    return {"skipped": False, "created": created}


def ai_status():
    return {
        "enabled": bool(os.environ.get("AI_API_KEY")),
        "model": os.environ.get("AI_MODEL", "gpt-4o-mini"),
        "base_url": os.environ.get("AI_BASE_URL", "https://api.openai.com/v1"),
    }


AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "สร้างงานใหม่ในระบบออฟฟิศ",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "ชื่องาน"},
                    "due_date": {"type": "string", "description": "วันครบกำหนด YYYY-MM-DD"},
                    "due_time": {"type": "string", "description": "เวลา HH:MM"},
                    "agent_name": {"type": "string", "description": "ชื่อผู้ช่วย เช่น น้องลิน พี่บี"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                    "repeat_rule": {"type": "string", "enum": ["none", "daily", "weekly", "monthly", "yearly"]},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "ปิดงานที่เปิดอยู่ให้เสร็จ",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string", "description": "ชื่องานหรือบางส่วนของชื่องาน"}},
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_task",
            "description": "เลื่อนวันครบกำหนดของงาน",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "ชื่องานหรือบางส่วนของชื่องาน"},
                    "due_date": {"type": "string", "description": "วันใหม่ YYYY-MM-DD"},
                    "due_time": {"type": "string", "description": "เวลาใหม่ HH:MM"},
                },
                "required": ["title", "due_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "ดูรายการงานตามเงื่อนไข",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "enum": ["open", "today", "overdue", "done"]},
                    "agent_name": {"type": "string", "description": "กรองเฉพาะผู้ช่วยคนนี้"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "ค้นหาเอกสารในศูนย์เอกสาร",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "คำค้น"}},
                "required": ["query"],
            },
        },
    },
]


def _chat_completion(messages, tools=None):
    key = os.environ.get("AI_API_KEY")
    if not key:
        return None
    base = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 700,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None


def agent_reply(conn, agent, message, history=None, tool_executor=None):
    """ตอบกลับแบบ AI จริงถ้าตั้งค่าไว้ ไม่งั้นใช้บทสรุปจากข้อมูลจริง.

    ถ้าส่ง tool_executor มาด้วย (ฟังก์ชันรับ (name, args) แล้วคืน dict)
    AI จะสั่งงานผ่าน tools ได้ เช่น สร้าง/ปิด/เลื่อนงาน และค้นเอกสาร.
    """
    tasks = conn.execute(
        """SELECT t.*, d.name AS dept_name FROM tasks t
           LEFT JOIN departments d ON d.id=t.department_id
           WHERE t.agent_id=? AND t.status IN ('todo','doing')
           ORDER BY (t.due_date IS NULL), t.due_date, t.due_time LIMIT 12""",
        (agent["id"],),
    ).fetchall()
    docs = conn.execute(
        "SELECT COUNT(*) c FROM documents WHERE agent_id=?", (agent["id"],)
    ).fetchone()["c"]
    today = date.today().isoformat()
    overdue = [t for t in tasks if t["due_date"] and t["due_date"] < today]
    due_today = [t for t in tasks if t["due_date"] == today]
    dept = conn.execute(
        "SELECT * FROM departments WHERE id=?", (agent["department_id"],)
    ).fetchone()

    actions = []
    if ai_status()["enabled"]:
        task_lines = "\n".join(
            f"- {t['title']} | กำหนด {t['due_date'] or 'ไม่ระบุ'} {t['due_time'] or ''} "
            f"| สถานะ {t['status']} | ความสำคัญ {t['priority']}"
            for t in tasks
        ) or "- ไม่มีงานค้าง"
        system_prompt = (
            f"คุณคือ {agent['name']} ตำแหน่ง {agent['role']} ในแผนก {dept['name'] if dept else '-'} "
            f"ของออฟฟิศเสมือน คุณเป็น AI ผู้ช่วยที่ทำงานแทนเจ้าของกิจการเพียงคนเดียว "
            f"บุคลิก: {agent['persona']} หน้าที่: {agent['duties']} "
            f"วันนี้คือ {datetime.now().strftime('%d/%m/%Y %H:%M')} "
            f"งานที่คุณรับผิดชอบตอนนี้:\n{task_lines}\n"
            f"คุณมีเอกสารในความดูแล {docs} รายการ "
            "ตอบเป็นภาษาไทย สุภาพ กระชับ ใช้ข้อมูลจริงที่มี ห้ามแต่งข้อมูลขึ้นเอง "
            "ถ้าไม่รู้ให้บอกว่าต้องตรวจสอบเพิ่มเติม และเสนอขั้นตอนถัดไป 1-2 ข้อ "
            "ถ้าผู้ใช้สั่งให้ทำงาน ให้เรียก tool ที่เหมาะสมแทนการบอกให้เขาทำเอง "
            "และสรุปสั้น ๆ ว่าทำอะไรไปแล้วบ้าง"
        )
        messages = [{"role": "system", "content": system_prompt}]
        for item in (history or [])[-8:]:
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)[:2000]})
        messages.append({"role": "user", "content": message})

        tools = AI_TOOLS if tool_executor else None
        for _ in range(4):
            answer = _chat_completion(messages, tools)
            if not answer:
                break
            tool_calls = answer.get("tool_calls") or []
            if tool_calls and tool_executor:
                messages.append({
                    "role": "assistant",
                    "content": answer.get("content") or "",
                    "tool_calls": tool_calls,
                })
                for call in tool_calls:
                    fn = call.get("function") or {}
                    name = fn.get("name") or ""
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    if not isinstance(args, dict):
                        args = {}
                    try:
                        result = tool_executor(name, args)
                    except Exception as exc:  # noqa: BLE001 - แจ้ง AI กลับไปแบบสุภาพ
                        result = {"ok": False, "error": f"เรียกเครื่องมือไม่สำเร็จ: {exc}"}
                    actions.append({"tool": name, **result})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                continue
            content = (answer.get("content") or "").strip()
            if content:
                return {"reply": content, "source": "ai", "actions": actions}
            break

    # --- โหมดอัตโนมัติ (ไม่ใช้ API) ---
    lines = []
    lowered = (message or "").lower()
    greeting = any(w in lowered for w in ["สวัสดี", "hello", "hi", "ทัก"])
    if greeting:
        lines.append(f"สวัสดีครับ/ค่ะ ผม/ฉันคือ {agent['name']} {agent['role']} ประจำ{dept['name'] if dept else 'ออฟฟิศ'}")
    lines.append(
        f"ตอนนี้มีงานในความดูแล {len(tasks)} งาน "
        f"(เกินกำหนด {len(overdue)} · ครบกำหนดวันนี้ {len(due_today)}) และเอกสาร {docs} รายการ"
    )
    if tasks:
        lines.append("\nงานที่ควรให้ความสำคัญ:")
        ordered = sorted(
            tasks,
            key=lambda t: (
                0 if t["due_date"] and t["due_date"] < today else 1,
                t["due_date"] or "9999-12-31",
                t["due_time"] or "23:59",
            ),
        )[:4]
        for t in ordered:
            flag = "⚠️ " if t["due_date"] and t["due_date"] < today else "• "
            lines.append(
                f"{flag}{t['title']} — กำหนด {_fmt_due(t['due_date'], t['due_time'])}"
            )
    else:
        lines.append("ยังไม่มีงานค้างในความรับผิดชอบ ตอนนี้พร้อมรับงานใหม่ได้เลย")

    if "เอกสาร" in message:
        lines.append(f"\nเอกสารในความดูแลมี {docs} รายการ สามารถเปิดดูได้ที่เมนู “ศูนย์เอกสาร”")
    if "แผนก" in message or "ทีม" in message:
        rows = conn.execute(
            """SELECT d.name, COUNT(t.id) c FROM departments d
               LEFT JOIN tasks t ON t.department_id=d.id AND t.status IN ('todo','doing')
               GROUP BY d.id ORDER BY c DESC"""
        ).fetchall()
        lines.append("\nภาระงานแต่ละแผนก: " + " · ".join(f"{r['name']} {r['c']}" for r in rows))
    if any(w in lowered for w in ["เพิ่มงาน", "สร้างงาน", "มอบหมาย"]):
        lines.append(
            "\nสั่งงานได้ทันทีด้วยการพิมพ์ เช่น “เพิ่มงาน ตรวจสต็อกพรุ่งนี้ 10:00 ให้พี่บี” "
            "ระบบจะสร้างงานและมอบหมายให้เอง"
        )
    lines.append("\nพิมพ์สั่งงานได้เลย เช่น “ปิดงาน …”, “เลื่อนงาน … ไปวันที่ 20”, “หาเอกสาร …”")
    return {"reply": "\n".join(lines), "source": "rules", "actions": actions}
