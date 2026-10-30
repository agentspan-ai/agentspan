from oncall_agent.kb import leads_for_alert, similar

INC = [
    {"id": "pg-restart", "clusters": ["cluster-a"], "customer": "CustomerA", "symptoms": ["restart", "liveness"],
     "cause": "PG restarted", "fix": "probe", "evidence": "pg_postmaster_start_time", "alert_executions": ["E1"]},
    {"id": "redis-aof", "clusters": ["stage2"], "customer": "Vantaca", "symptoms": ["misconf", "aof"],
     "cause": "AOF", "fix": "-", "evidence": "Errors metric"},
    {"id": "fleet", "clusters": ["*"], "customer": "various", "symptoms": ["restart"], "cause": "pattern",
     "fix": "-", "evidence": "-"},
]


def test_same_cluster_ranks_first_and_needs_a_link():
    out = similar("cluster-a", "CustomerA", "pods restart liveness", INC)
    assert [o["id"] for o in out] == ["pg-restart", "fleet"]
    assert "same cluster" in out[0]["why"] and "same customer" in out[0]["why"]
    assert similar("other", None, "disk full", INC) == []  # nothing in common -> no leads


def test_same_cluster_alone_is_not_a_lead():
    # the right cluster but no shared symptom: an old incident there says nothing about this one
    assert similar("cluster-a", "CustomerA", "failed to connect to the workers", INC) == []


def test_symptoms_alone_find_leads_on_a_new_cluster():
    assert [o["id"] for o in similar("new", None, "redis misconf aof", INC)] == ["redis-aof"]


def test_eval_leave_one_out_hides_the_cases_own_incident():
    text = "FAILED for lte: pods restart"
    assert "pg-restart" in leads_for_alert(text, incidents=INC)
    hidden = leads_for_alert(text, exclude_execution="E1", incidents=INC)
    assert "pg-restart" not in hidden and "fleet" in hidden


def test_no_leads_means_no_prompt_section():
    assert leads_for_alert("all good", incidents=INC) == ""
