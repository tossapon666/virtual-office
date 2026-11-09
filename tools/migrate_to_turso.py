"""ย้ายข้อมูลจาก SQLite ในเครื่อง (office.db) ไปยัง Turso (libSQL) แบบครั้งเดียว.

วิธีใช้ (Windows PowerShell):
  $env:TURSO_DATABASE_URL = "libsql://<db>-<org>.turso.io"
  $env:TURSO_AUTH_TOKEN   = "<token>"
  python tools\\migrate_to_turso.py --sqlite office.db --wipe

ตัวเลือก:
  --sqlite PATH   ไฟล์ SQLite ต้นทาง (ค่าเริ่มต้น: office.db)
  --wipe          ล้างข้อมูลใน Turso ก่อนนำเข้า (ระวัง: ลบของเดิมทั้งหมด)
  --dry-run       แสดงจำนวนแถวที่จะย้ายโดยไม่เขียนปลายทาง

หมายเหตุ: รันครั้งเดียวหลังสร้างฐานข้อมูล Turso แล้ว (ก่อนเปิดแอปกับ Turso)
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import db as database  # noqa: E402  (ใช้ SCHEMA ร่วมกัน)

TABLES = [
    "users",
    "departments",
    "agents",
    "tasks",
    "documents",
    "notifications",
    "activity",
    "widgets",
    "settings",
]


def source_rows(src, table):
    exists = src.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return [], []
    cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()]
    rows = src.execute(f"SELECT * FROM {table}").fetchall()
    return cols, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default=str(BASE_DIR / "office.db"))
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src_path = Path(args.sqlite)
    if not src_path.exists():
        print(f"ไม่พบไฟล์ต้นทาง: {src_path}")
        return 2

    url = (os.environ.get("TURSO_DATABASE_URL") or os.environ.get("LIBSQL_URL") or "").strip()
    token = (os.environ.get("TURSO_AUTH_TOKEN") or os.environ.get("LIBSQL_AUTH_TOKEN") or "").strip()

    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row

    plan = {}
    for table in TABLES:
        cols, rows = source_rows(src, table)
        plan[table] = (cols, rows)

    print(f"ต้นทาง: {src_path}")
    print(f"ปลายทาง: {url or '(dry-run)'}")
    for table, (cols, rows) in plan.items():
        print(f"  {table:14s} {len(rows):5d} แถว")
    if args.dry_run:
        src.close()
        print("dry-run: ไม่ได้เขียนข้อมูล")
        return 0

    if not url:
        src.close()
        print("ยังไม่ได้ตั้ง TURSO_DATABASE_URL (หรือ LIBSQL_URL)")
        return 2
    try:
        import libsql
    except Exception as exc:
        src.close()
        print(f"ต้องติดตั้ง libsql ก่อน: pip install libsql ({exc})")
        return 2

    target = libsql.connect(database=url, auth_token=token)
    target.executescript(database.SCHEMA)

    if args.wipe:
        print("ล้างข้อมูลปลายทาง...")
        for table in reversed(TABLES):
            try:
                target.execute(f"DELETE FROM {table}")
            except Exception as exc:
                print(f"  ข้าม {table}: {exc}")
        target.commit()

    copied = 0
    for table in TABLES:
        cols, rows = plan[table]
        if not rows:
            continue
        # ใช้เฉพาะคอลัมน์ที่มีอยู่จริงทั้งสองฝั่ง
        tcols = [r[1] for r in target.execute(f"PRAGMA table_info({table})").fetchall()]
        use = [c for c in cols if c in tcols]
        if not use:
            print(f"  ข้าม {table}: ไม่มีคอลัมน์ที่ตรงกัน")
            continue
        placeholders = ",".join("?" for _ in use)
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(use)}) VALUES ({placeholders})"
        batch = []
        for row in rows:
            batch.append(tuple(row[c] for c in use))
            if len(batch) >= 200:
                target.executemany(sql, batch)
                copied += len(batch)
                batch = []
        if batch:
            target.executemany(sql, batch)
            copied += len(batch)
        target.commit()
        print(f"  นำเข้า {table}: {len(rows)} แถว")

    print(f"รวม {copied} แถว — ตรวจสอบจำนวนปลายทาง:")
    ok = True
    for table in TABLES:
        scols, srows = plan[table]
        if not scols:
            continue
        try:
            tcount = target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception as exc:
            print(f"  {table}: ตรวจสอบไม่ได้ ({exc})")
            ok = False
            continue
        mark = "OK" if tcount >= len(srows) else "!!"
        if tcount < len(srows):
            ok = False
        print(f"  {table:14s} ต้นทาง {len(srows):5d} / ปลายทาง {tcount:5d}  {mark}")

    target.close()
    src.close()
    print("เสร็จสิ้น" if ok else "มีตารางที่จำนวนไม่ตรง — ตรวจสอบก่อนใช้งาน")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
