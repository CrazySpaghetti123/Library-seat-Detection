"""共用小工具。"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """回傳 naive UTC 時間。

    全系統一律以 naive UTC 存取 DB，避免 SQLite 不支援時區
    造成 aware/naive 比較錯誤（PostgreSQL 行為亦一致）。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
