from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "inventory.db")
DATABASE_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=5,
    max_overflow=10,
)

@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")      # 읽기/쓰기 동시 허용
    cur.execute("PRAGMA cache_size=-65536")     # 64MB 메모리 캐시
    cur.execute("PRAGMA synchronous=NORMAL")    # fsync 횟수 감소
    cur.execute("PRAGMA temp_store=MEMORY")     # 임시 테이블 메모리 처리
    cur.execute("PRAGMA mmap_size=268435456")   # 256MB mmap
    cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
