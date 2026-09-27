"""取消班次：状态持久、幂等、报告/时间轴/建议剔除、不影响其它班次。"""


def _trip_id(client, trip_no):
    trips = client.get("/api/trips").json()
    return next(t["id"] for t in trips if t["trip_no"] == trip_no)


def _run_events(client):
    return client.post("/api/reports/run?line_id=1").json()["events"]


def test_seed_has_four_active_trips(client):
    trips = client.get("/api/trips").json()
    assert {t["trip_no"] for t in trips} == {"T01", "T02", "T03", "T04"}
    assert all(t["status"] == "active" for t in trips)


def test_cancel_marks_status_and_persists(client):
    tid = _trip_id(client, "T02")
    res = client.post(f"/api/trips/{tid}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    # 重新拉取（相当于离开再进来）仍是取消
    trips = client.get("/api/trips").json()
    assert next(t for t in trips if t["trip_no"] == "T02")["status"] == "cancelled"
    assert all(t["status"] == "active" for t in trips if t["trip_no"] != "T02")


def test_cancel_is_idempotent_and_writes_no_arrivals(client):
    tid = _trip_id(client, "T02")
    before = client.get("/api/arrivals").json()
    client.post(f"/api/trips/{tid}/cancel")
    mid = client.get("/api/arrivals").json()
    res = client.post(f"/api/trips/{tid}/cancel")  # 已取消再取消一次
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    after = client.get("/api/arrivals").json()
    assert len(mid) == len(before)
    assert len(after) == len(before)


def test_cancel_removes_bunching_event(client):
    events = _run_events(client)
    assert any(e["stop_name"] == "市民中心" and e["earlier_trip"] == "T01" and e["later_trip"] == "T02"
               for e in events)
    client.post(f"/api/trips/{_trip_id(client, 'T02')}/cancel")
    events = _run_events(client)
    assert not any(e["stop_name"] == "市民中心" and e["earlier_trip"] == "T01" and e["later_trip"] == "T02"
                   for e in events)
    assert not any(e["earlier_trip"] == "T02" or e["later_trip"] == "T02" for e in events)


def test_cancel_removes_timeline_mark(client):
    marks = client.get("/api/reports/timeline?line_id=1").json()["marks"]
    assert len(marks) == 4
    client.post(f"/api/trips/{_trip_id(client, 'T02')}/cancel")
    marks = client.get("/api/reports/timeline?line_id=1").json()["marks"]
    assert len(marks) == 3
    assert all(m["trip_no"] != "T02" for m in marks)


def test_cancel_excluded_from_suggestions(client):
    client.post(f"/api/trips/{_trip_id(client, 'T02')}/cancel")
    sugg = client.get("/api/reports/suggestions?line_id=1").json()["suggestions"]
    assert all(s["earlier_trip"] != "T02" and s["later_trip"] != "T02" for s in sugg)


def test_cancel_does_not_change_other_trips(client):
    before = {t["trip_no"]: t["planned_depart"] for t in client.get("/api/trips").json()}
    before_arr = {a["id"]: a["actual_arrive"] for a in client.get("/api/arrivals").json()
                  if a["trip_no"] != "T02"}
    client.post(f"/api/trips/{_trip_id(client, 'T02')}/cancel")
    after = {t["trip_no"]: t["planned_depart"] for t in client.get("/api/trips").json()}
    after_arr = {a["id"]: a["actual_arrive"] for a in client.get("/api/arrivals").json()
                 if a["trip_no"] != "T02"}
    for no in ("T01", "T03", "T04"):
        assert before[no] == after[no]
    assert before_arr == after_arr


def test_cancel_unknown_trip_404(client):
    assert client.post("/api/trips/9999/cancel").status_code == 404
