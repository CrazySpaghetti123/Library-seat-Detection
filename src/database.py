"""SQLAlchemy engine 與 session 工廠。

僅使用 SQLite 與 PostgreSQL 共通的功能（見 design.md D2），
切換資料庫只需改 DATABASE_URL。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src import config


class Base(DeclarativeBase):
    pass


def engine_options(url: str) -> dict:
    """SQLite 需要 check_same_thread=False 才能讓 FastAPI 與排程執行緒共用。
    PostgreSQL：雲端資料庫（Neon）閒置會暫停，暫停前的連線會失效——使用前檢查（pre_ping），
    並定期回收（spec: cloud-deployment / Database resumed after suspension）。"""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True, "pool_recycle": 300}


engine = create_engine(config.DATABASE_URL, **engine_options(config.DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 相依注入用的 session 產生器。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
