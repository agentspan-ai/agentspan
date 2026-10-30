import importlib.util
import json
import pathlib

_spec = importlib.util.spec_from_file_location(
    "harvest_cases", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "harvest_cases.py")
harvest_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harvest_cases)


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_feedback_becomes_cases_with_replayable_alert(tmp_path):
    _write(tmp_path / "triages.jsonl", [
        {"at": 1793100000.0, "alert_execution": "A1", "answer": "*Cause*: redis", "alert_text": "ALERT one"},
        {"at": 1793100000.0, "alert_execution": "A2", "answer": "*Cause*: node upgrade", "alert_text": "ALERT two"},
        {"at": 1793100000.0, "alert_execution": "A3", "answer": "*Cause*: unknown", "alert_text": "ALERT three"}])
    _write(tmp_path / "feedback.jsonl", [
        {"alert_execution": "A1", "cluster": "orkes-devops", "verdict": "wrong", "cause": "workers pgvector leak"},
        {"alert_execution": "A2", "cluster": "pentest", "verdict": "correct"},
        {"alert_execution": "A3", "cluster": "x", "question": "? why"}])
    drafts = []

    def draft(answer, verdict, cause, action):
        drafts.append((answer, verdict, cause))
        return {"cause_any": [["pgvector"]], "action_any": [], "must_not_mention": ["redis"]}

    new = {c["execution_id"]: c for c in harvest_cases.harvest(tmp_path, draft)}
    assert new["A1"]["cause"] == "workers pgvector leak" and new["A1"]["must_not_mention"] == ["redis"]
    assert new["A2"]["cause"] == "*Cause*: node upgrade"  # correct -> regression lock on its own answer
    assert new["A3"].get("needs_truth") and "cause_any" not in new["A3"]
    assert ("*Cause*: redis", "wrong", "workers pgvector leak") in drafts
    meta = json.loads((tmp_path / "recordings" / "A1.meta.json").read_text())
    assert meta == {"start_time": 1793100000000, "reason": "ALERT one"}
    # idempotent: a second harvest adds nothing
    assert harvest_cases.harvest(tmp_path, draft) == []
    assert len(json.loads((tmp_path / "cases.json").read_text())) == 3


def test_confirmed_causes_become_incidents_once(tmp_path):
    cases = [{"id": "c1", "execution_id": "A1", "cause": "workers pgvector leak", "cause_any": [["pgvector", "leak"]],
              "human": {"cluster": "orkes-devops", "action": "restart workers"}},
             {"id": "c2", "execution_id": "A2", "cause": "*Cause*: node upgrade\n*Action*: none", "cause_any": [],
              "human": {"cluster": "pentest"}},
             {"id": "c3", "execution_id": "A3", "cause": "(not given)", "needs_truth": True, "human": {}}]
    assert harvest_cases.add_incidents(tmp_path, cases) == 2
    assert harvest_cases.add_incidents(tmp_path, cases) == 0
    rows = [json.loads(l) for l in (tmp_path / "incidents.jsonl").read_text().splitlines()]
    assert rows[0]["symptoms"] == ["leak", "pgvector"] and rows[0]["fix"] == "restart workers"
    assert rows[1]["cause"] == "node upgrade"
