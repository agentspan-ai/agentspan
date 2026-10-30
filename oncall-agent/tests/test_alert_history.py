from oncall_agent import alert_history as ah


def _conn(tmp_path, monkeypatch):
    from oncall_agent import release_index
    monkeypatch.setattr(release_index, "DB", tmp_path / "ops.db")
    return ah.db()


def test_chronic_new_and_recurring(tmp_path, monkeypatch):
    c = _conn(tmp_path, monkeypatch)
    now = 1_800_000_000.0
    for d in range(1, 21):  # a CPU alert on 20 of the last 30 days
        ah.record(c, now - d * 86400, "C", "busy", "Conductor Server CPU usage is at 97%", None)
    ah.record(c, now - 3 * 86400 + 17, "C", "once", "Redis memory high", None)
    busy = ah.history(c, "busy", "CPU usage is at 99%", now=now)
    assert busy["verdict"].startswith("CHRONIC") and busy["daysWithThisKind"] == 20
    assert "never call it transient" in busy["verdict"]
    assert ah.history(c, "quiet", "CPU usage", now=now)["verdict"].startswith("NEW")
    assert ah.history(c, "once", "Redis memory", now=now)["verdict"].startswith("RECURRING")
    assert "never with this kind" in ah.history(c, "once", "CPU usage", now=now)["verdict"]


def test_kinds_are_coarse_and_stable():
    assert ah.kinds_of("Conductor Server CPU usage is at 95.4%") == ["cpu"]
    assert "timed_out" in ah.kinds_of("Task poll timed out after 20 seconds")
    assert ah.kinds_of("something odd") == ["other"]
