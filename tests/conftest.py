import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.models  # noqa: F401  註冊所有 model
from src.database import Base
from src.models.seat import Seat, SeatStatus


@pytest.fixture
def db():
    """每個測試使用獨立的 in-memory SQLite。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def seats(db):
    """示範座位：A1（AVAILABLE）、A2（OCCUPIED）、A3（RESERVED）。"""
    items = {
        "A1": Seat(label="A1", floor="3F", status=SeatStatus.AVAILABLE),
        "A2": Seat(label="A2", floor="3F", status=SeatStatus.OCCUPIED),
        "A3": Seat(label="A3", floor="3F", status=SeatStatus.RESERVED),
    }
    db.add_all(items.values())
    db.flush()
    return items
