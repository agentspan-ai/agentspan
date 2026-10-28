import importlib.util
import json
import pathlib
import time

_spec = importlib.util.spec_from_file_location(
    "report", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "report.py")
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)


def test_report_counts_judged_accuracy_and_approvals(tmp_path):
    now = time.time()
    tri = [{"at": now, "alert_execution": "A1", "cluster": "c1", "answer": "*Cause*: x"},
           {"at": now, "alert_execution": "A2", "cluster": "c1", "answer": "*Cause*: unknown — y"},
           {"at": now - 30 * 86400, "alert_execution": "OLD", "answer": "*Cause*: z"},
           {"at": now, "approval": {"outcome": "approved"}}, {"at": now, "approval": {"outcome": "expired"}}]
    fb = [{"at": now, "alert_execution": "A1", "verdict": "correct"},
          {"at": now, "alert_execution": "A2", "verdict": "wrong", "cause": "real"},
          {"at": now, "alert_execution": "A2", "question": "? why"}]
    (tmp_path / "triages.jsonl").write_text("\n".join(map(json.dumps, tri)))
    (tmp_path / "feedback.jsonl").write_text("\n".join(map(json.dumps, fb)))
    r = report.build(tmp_path, 7, now)
    assert (r["triages"], r["causeUnknown"], r["accuracy"], r["followUpQuestions"]) == (2, 1, 0.5, 1)
    assert r["approvalOutcomes"] == {"approved": 1, "expired": 1}
    assert "accuracy 50%" in report.render(r)
