from oncall_agent.grading import describe, grade, passed, sections

GOOD = (
    "*Cause*: workers pod leaks pgvector connections until RDS max_connections (403) is full.\n"
    "*Action*: restart the workers pod; ship the provider cache fix.\n"
    "*Evidence*: DatabaseConnections pinned at 394/403 from 10-21 19:00Z; workers IP holds 330 idle."
)
CASE = {
    "cause_any": [["pgvector", "vector"], ["connection"]],
    "action_any": [["restart the workers", "restart workers"]],
    "must_not_mention": ["restart postgres"],
}


def test_sections_split_the_three_lines():
    s = sections(GOOD)
    assert s["cause"].startswith("workers pod leaks")
    assert s["action"].startswith("restart the workers")
    assert "394/403" in s["evidence"]


def test_good_answer_passes_every_dimension():
    r = grade(CASE, GOOD)
    assert passed(r), describe(r)


def test_failures_are_reported_per_dimension():
    bad = GOOD.replace("pgvector", "redis").replace("restart the workers pod", "restart postgres")
    r = grade(CASE, bad)
    assert r["cause"] and r["action"] and r["forbidden"]
    assert not r["format"] and not r["evidence"]


def test_cause_terms_only_count_on_the_cause_line():
    moved = "*Cause*: unknown.\n*Action*: check pgvector connection pools.\n*Evidence*: 394/403 at 21:28."
    assert grade({"cause_any": [["pgvector"]]}, moved)["cause"]


def test_format_rejects_extra_lines_and_missing_sections():
    r = grade({}, GOOD + "\nAlso I looked at the heap.\nAnd threads.")
    assert any("lines" in f for f in r["format"])
    assert grade({}, "*Cause*: x 1")["format"] == ["no *Action* line", "no *Evidence* line"]


def test_evidence_must_cite_a_time_or_number():
    assert grade({}, "*Cause*: a\n*Action*: b\n*Evidence*: the logs say so")["evidence"]
