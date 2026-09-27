import os

# 在导入 app 之前指向本地 sqlite，避免测试触达真实 Postgres（例如 lifespan 建表/播种）
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/busgap_test.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.seed import seed_if_empty


@pytest.fixture()
def client():
    # 每个用例一份独立的内存库，并重新播种（T01~T04 四班）
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    try:
        seed_if_empty(db)
    finally:
        db.close()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        # 不以 with 方式进入，避免触发 lifespan 连接真实数据库
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
