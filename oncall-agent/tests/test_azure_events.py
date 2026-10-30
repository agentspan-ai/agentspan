from oncall_agent.azure_events import summarize_db_alive


def _ts(points):
    return [{"data": points}]


def test_down_minutes_and_short_gaps_are_flagged():
    pts = [{"timeStamp": "17:20", "minimum": 1.0, "count": 6.0},
           {"timeStamp": "17:21", "minimum": 0.0, "count": 6.0},   # reported down
           {"timeStamp": "17:22", "minimum": 1.0, "count": 2.0}]   # short restart: samples missing
    assert summarize_db_alive(_ts(pts)) == ["17:21", "17:22"]


def test_minutes_without_any_data_are_unknown_not_down():
    # poc-cfc 2026-10-28: minutes not yet ingested came back empty and were read as a 30-min outage
    pts = [{"timeStamp": "17:23", "minimum": None, "count": None},
           {"timeStamp": "17:24", "count": 0.0}]
    assert summarize_db_alive(_ts(pts)) == []
