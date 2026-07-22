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


# The EXACT string Slack receives: HealthCheckIssuesWorker emits markdown
# (*`[SEV]`* … _Org's_ env *`cluster`*) and the notify_on_slack HTTP task prepends an
# emoji and appends the execution URL on its own line. Build it from those two sources
# so the parser is tested against what actually ships, not a hand-cleaned sample.
REAL_SLACK = (
    "🚨 *`[CRITICAL]`* The health-checking has FAILED for the _Vizient's_ prod "
    "*`viz-stage`* cluster with the following issue:\n"
    "*CRITICAL:* The Redis instance is at 66%, above the CRITICAL threshold of 65%\n"
    "https://ah5r-prod.orkesconductor.com/execution/364b459a-689f-11f1-94b6-de01f12a4ed9"
)


def test_parses_real_slack_markdown_alert():
    a = parse_alert(REAL_SLACK)
    assert a is not None
    # Load-bearing: the execution id always parses regardless of decoration.
    assert a.execution_id == "364b459a-689f-11f1-94b6-de01f12a4ed9"
    assert a.severity == "CRITICAL"
    # Best-effort, but must survive the markdown the worker actually emits.
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


# ── digest-channel messages (alert-aggregator app) ──────────────────────
# The aggregator posts one message per (cluster, alert-type) incident and edits
# it in place with an occurrence counter. The top-level ``text`` is only a
# headline (no execution URL); the original alert — markdown, URL and all — is
# quoted inside the section block. Captured live 2026-07-22.

DIGEST_MSG = {
    "type": "message",
    "ts": "1784727067.661959",
    "text": ":red_circle: *[MAJOR]* At-Bay · `atbay-production` — HEAP_HIGH",
    "blocks": [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":red_circle: *[MAJOR]* *At-Bay* · `atbay-production` — `HEAP_HIGH`\n"
                    "&gt;:warning: *`[MAJOR]`* The health-checking has FAILED for the _At-Bay's_ "
                    "prod *`atbay-production`* cluster with the following issue:\n"
                    "*MAJOR:* Conductor Server Heap usage is at 91.2% and exceeded the threshold "
                    "of 90.0% - orkes-conductor-deployment-cf64b9448-g5czb\n"
                    "<https://ah5r-prod.orkesconductor.com/execution/933967a4-85d1-11f1-ba93-96986d0e24f0>\n"
                    "<https://ah5r-prod.orkesconductor.com/execution/933967a4-85d1-11f1-ba93-96986d0e24f0|View source>"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": ":repeat: *1* occurrences · Last seen: <!date^1784727067^{time} {date_short}|2026-07-22T13:31:07.000Z>",
                }
            ],
        },
        {"type": "divider"},
    ],
}


def test_message_text_flattens_blocks():
    from oncall_agent.alert import message_text

    flat = message_text(DIGEST_MSG)
    assert "execution/933967a4-85d1-11f1-ba93-96986d0e24f0" in flat
    assert "1* occurrences" in flat  # occurrence count reaches the triage prompt


def test_digest_message_parses_via_blocks():
    from oncall_agent.alert import message_text, parse_alert

    a = parse_alert(message_text(DIGEST_MSG))
    assert a is not None
    assert a.execution_id == "933967a4-85d1-11f1-ba93-96986d0e24f0"
    assert a.severity == "MAJOR"
    assert a.cluster == "atbay-production"
    assert a.organization == "At-Bay"


def test_digest_headline_alone_does_not_parse():
    # Guard: the top-level text has no execution URL — blocks are load-bearing.
    from oncall_agent.alert import parse_alert

    assert parse_alert(DIGEST_MSG["text"]) is None
