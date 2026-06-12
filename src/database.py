"""SQLAlchemy engine 與 session 工廠。

僅使用 SQLite 與 PostgreSQL 共通的功能（見 design.md D2），
切換資料庫只需改 DATABASE_URL。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src import config


class Base(DeclarativeBase):
    pass


# SQLite 需要 check_same_thread=False 才能讓 FastAPI 與排程執行緒共用
_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(config.DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 相依注入用的 session 產生器。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
