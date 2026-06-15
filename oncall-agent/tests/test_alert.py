from oncall_agent.alert import parse_alert

SAMPLE = (
    "[CRITICAL] The health-checking has FAILED for the Vizient's prod viz-stage "
    "cluster with the following issue:\n"
    "CRITICAL: The Redis instance is at 66%, above the CRITICAL threshold of 65%\n"
    "https://ah5r-prod.orkesconductor.com/execution/364b459a-689f-11f1-94b6-de01f12a4ed9"
)


def test_parses_real_alert():
    a = parse_alert(SAMPLE)
    assert a is not None
    assert a.execution_id == "364b459a-689f-11f1-94b6-de01f12a4ed9"
    assert a.severity == "CRITICAL"
    assert a.cluster == "viz-stage"
    assert a.organization == "Vizient"


def test_warning_severity_and_no_org_block():
    text = "[WARNING] something off https://ah5r-prod.orkesconductor.com/execution/abc12345-dead-beef"
    a = parse_alert(text)
    assert a is not None
    assert a.severity == "WARNING"
    assert a.execution_id == "abc12345-dead-beef"


def test_non_alert_returns_none():
    assert parse_alert("hey team, deploy finished, all green") is None
    assert parse_alert("") is None
    assert parse_alert(None) is None


def test_requires_execution_link():
    # Looks like an alert but has no execution link -> not actionable.
    assert parse_alert("[CRITICAL] cluster down, no link here") is None
