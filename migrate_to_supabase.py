"""SQLite → Supabase PostgreSQL 데이터 이전 스크립트"""
import sqlite3
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "inventory.db")
PG_URL = os.environ["DATABASE_URL"]

print(f"SQLite: {SQLITE_PATH}")
print(f"PostgreSQL: {PG_URL[:50]}...")

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row
pg_engine = create_engine(PG_URL, pool_pre_ping=True)

TABLES = ["products", "supplier_sku_map", "orders", "order_items", "stock_movements"]

BOOL_COLS = {"is_active"}

def clean_row(row):
    d = dict(row)
    for k, v in d.items():
        if v == "None" or v == "":
            d[k] = None
        elif k in BOOL_COLS and v is not None:
            d[k] = bool(v)
    return d

with pg_engine.begin() as pg:
    for table in reversed(TABLES):
        try:
            pg.execute(text(f"DELETE FROM {table}"))
            print(f"  [{table}] 기존 데이터 삭제")
        except Exception as e:
            print(f"  [{table}] 삭제 건너뜀: {e}")

for table in TABLES:
    rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        print(f"  [{table}] 데이터 없음")
        continue

    cols = rows[0].keys()
    col_str = ", ".join(cols)
    param_str = ", ".join([f":{c}" for c in cols])
    sql = text(f"INSERT INTO {table} ({col_str}) VALUES ({param_str})")

    success = 0
    fail = 0
    for row in rows:
        try:
            with pg_engine.begin() as pg:
                pg.execute(sql, clean_row(row))
            success += 1
        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"    에러 (id={dict(row).get('id')}): {e}")

    # sequence 재설정
    with pg_engine.begin() as pg:
        pg.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table}"))

    print(f"  [{table}] 성공 {success}건 / 실패 {fail}건")

sqlite_conn.close()
print("\n✅ 이전 완료!")
