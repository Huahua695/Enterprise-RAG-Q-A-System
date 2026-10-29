from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# SQLite 需要 check_same_thread=False；PostgreSQL 不需要额外参数
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    echo=False
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        """WAL + busy_timeout。

        后台向量化线程会写 documents 表，同时前台请求在读；默认的 rollback
        journal 模式下并发读写容易直接抛 `database is locked`。WAL 允许读写并行，
        busy_timeout 则让写锁冲突时等待而不是立即失败。
        """
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA synchronous=NORMAL")  # WAL 下兼顾安全与性能
        finally:
            cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
