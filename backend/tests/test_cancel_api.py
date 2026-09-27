"""班次取消：状态持久、幂等、检测/时间轴/建议排除已取消班次。"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.seed import seed_if_empty

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_if_empty(db)
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def trip_id_by_no(client, trip_no):
    return next(t["id"] for t in client.get("/api/trips").json() if t["trip_no"] == trip_no)


def civic_center_events(client):
    return client.post("/api/reports/run?line_id=1&stop_name=市民中心").json()["events"]


def test_seed_has_four_active_trips(client):
    trips = client.get("/api/trips").json()
    assert [t["trip_no"] for t in trips] == ["T01", "T02", "T03", "T04"]
    assert all(t["status"] == "active" for t in trips)


def test_cancel_sets_status_and_persists(client):
    tid = trip_id_by_no(client, "T02")
    resp = client.post(f"/api/trips/{tid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    # 重新拉取（离开再进来）仍是取消
    trips = client.get("/api/trips").json()
    assert next(t for t in trips if t["trip_no"] == "T02")["status"] == "cancelled"
    assert all(t["status"] == "active" for t in trips if t["trip_no"] != "T02")


def test_cancel_unknown_trip_404(client):
    assert client.post("/api/trips/9999/cancel").status_code == 404


def test_cancel_is_idempotent_and_writes_no_arrival(client):
    tid = trip_id_by_no(client, "T02")
    arrivals_before = client.get("/api/arrivals").json()
    client.post(f"/api/trips/{tid}/cancel")
    again = client.post(f"/api/trips/{tid}/cancel")
    assert again.status_code == 200
    assert again.json()["status"] == "cancelled"
    trips = client.get("/api/trips").json()
    assert next(t for t in trips if t["trip_no"] == "T02")["status"] == "cancelled"
    # 不另写到站
    assert client.get("/api/arrivals").json() == arrivals_before


def test_cancel_does_not_change_other_trips(client):
    tid = trip_id_by_no(client, "T02")
    before = {t["trip_no"]: t for t in client.get("/api/trips").json()}
    arrivals_before = client.get("/api/arrivals").json()
    client.post(f"/api/trips/{tid}/cancel")
    after = {t["trip_no"]: t for t in client.get("/api/trips").json()}
    for no in ("T01", "T03", "T04"):
        assert after[no]["planned_depart"] == before[no]["planned_depart"]
        assert after[no]["status"] == "active"
    assert client.get("/api/arrivals").json() == arrivals_before


def test_cancel_removes_bunching_event_at_civic_center(client):
    events = civic_center_events(client)
    assert any(e["earlier_trip"] == "T01" and e["later_trip"] == "T02" for e in events)
    client.post(f"/api/trips/{trip_id_by_no(client, 'T02')}/cancel")
    events = civic_center_events(client)
    assert not any(e["earlier_trip"] == "T01" and e["later_trip"] == "T02" for e in events)
    assert not any("T02" in (e["earlier_trip"], e["later_trip"]) for e in events)


def test_cancel_removes_timeline_mark(client):
    marks = client.get("/api/reports/timeline?line_id=1").json()["marks"]
    assert [m["trip_no"] for m in marks] == ["T01", "T02", "T03", "T04"]
    client.post(f"/api/trips/{trip_id_by_no(client, 'T02')}/cancel")
    marks = client.get("/api/reports/timeline?line_id=1").json()["marks"]
    assert [m["trip_no"] for m in marks] == ["T01", "T03", "T04"]


def test_cancel_removes_trip_from_suggestions(client):
    tips = client.get("/api/reports/suggestions?line_id=1").json()["suggestions"]
    assert any("T02" in (t["earlier_trip"], t["later_trip"]) for t in tips)
    client.post(f"/api/trips/{trip_id_by_no(client, 'T02')}/cancel")
    tips = client.get("/api/reports/suggestions?line_id=1").json()["suggestions"]
    assert not any("T02" in (t["earlier_trip"], t["later_trip"]) for t in tips)
