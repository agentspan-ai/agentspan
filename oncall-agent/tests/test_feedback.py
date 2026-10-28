import json
import time

from oncall_agent import feedback
from oncall_agent.slack_app import _followup_prompt

BOT = "UBOT"


class Slack:
    def __init__(self, replies):
        self.replies, self.posts = replies, []

    def read_replies(self, channel, thread):
        return self.replies

    def post_reply(self, channel, thread, text):
        self.posts.append(text)


def test_parse_feedback_words():
    assert feedback.parse("correct") == {"verdict": "correct"}
    assert feedback.parse("✅ spot on")["verdict"] == "correct"
    assert feedback.parse("wrong, it was redis") == {"verdict": "wrong", "note": "wrong, it was redis"}
    assert feedback.parse("Cause: workers pgvector pool leak") == {"verdict": "wrong", "cause": "workers pgvector pool leak"}
    assert feedback.parse("action: restart workers") == {"action": "restart workers"}
    assert feedback.parse("looking into it") is None


def test_questions_need_a_mention_or_question_mark_and_are_not_decisions():
    assert feedback.is_question(f"<@{BOT}> why not the conductor pods?", BOT)
    assert feedback.is_question("? which pod holds the connections", BOT)
    assert not feedback.is_question("approve", BOT)
    assert not feedback.is_question("why is this happening", BOT)  # people talking to each other


def test_collect_records_feedback_and_queues_questions_once(tmp_path):
    now = time.time()
    state = {}
    feedback.watch(state, "C", "1.0", "ALERT1", "orkes-devops", now - 60)
    slack = Slack([
        {"ts": str(now - 120), "user": "U1", "text": "correct"},  # before the answer: ignored
        {"ts": str(now - 30), "user": "U1", "text": "cause: workers leak", },
        {"ts": str(now - 20), "bot_id": "B", "text": "correct"},  # bot: ignored
        {"ts": str(now - 10), "user": "U2", "text": f"<@{BOT}> which pod?"},
    ])
    assert feedback.collect(slack, state, tmp_path, lambda: None, bot_user_id=BOT) == 2
    assert feedback.collect(slack, state, tmp_path, lambda: None, bot_user_id=BOT) == 0  # seen once
    rows = [json.loads(l) for l in (tmp_path / "feedback.jsonl").read_text().splitlines()]
    assert rows[0]["cause"] == "workers leak" and rows[0]["alert_execution"] == "ALERT1"
    assert rows[1]["question"].endswith("which pod?")
    assert [q["text"] for q in state["questions"]] == [f"<@{BOT}> which pod?"]
    assert len(slack.posts) == 1  # only the feedback is acknowledged; the question gets an answer


def test_watch_expires(tmp_path):
    state = {}
    feedback.watch(state, "C", "1.0", "A", None, time.time() - feedback.WATCH_S - 1)
    feedback.collect(Slack([]), state, tmp_path, lambda: None)
    assert state["feedback_watch"] == {}


def test_followup_prompt_carries_the_thread_and_the_question():
    thread = [{"ts": "2", "bot_id": "B", "text": "*Cause*: workers leak"},
              {"ts": "1", "text": "ALERT orkes-devops"}]
    p = _followup_prompt({"alert_execution": "E1", "cluster": "orkes-devops", "text": "why workers?"}, thread)
    assert p.index("[engineer] ALERT orkes-devops") < p.index("[agent] *Cause*: workers leak")
    assert "E1" in p and p.rstrip().endswith("Answer that question.") and "why workers?" in p


def test_followup_prompt_includes_prior_findings_from_the_recording(tmp_path, monkeypatch):
    rec = tmp_path / "E1.jsonl"
    rec.write_text(json.dumps({"tool": "get_db_connections", "args": {"execution_id": "E1"},
                               "result": {"verdict": "LEAK", "detail": "workers holds 115"}}) + "\n")
    monkeypatch.setenv("ONCALL_RECORD_DIR", str(tmp_path))
    p = _followup_prompt({"alert_execution": "E1", "cluster": "c", "text": "? dig into it"}, [])
    assert "PRIOR FINDINGS" in p and "get_db_connections({}) -> " in p and "workers holds 115" in p
    monkeypatch.setenv("ONCALL_RECORD_DIR", str(tmp_path / "none"))
    assert "PRIOR FINDINGS" not in _followup_prompt({"alert_execution": "E1", "text": "?"}, [])
