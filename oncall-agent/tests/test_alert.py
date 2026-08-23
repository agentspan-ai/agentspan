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


# ── alert signatures (raw-channel flapper cooldown) ─────────────────────
# The raw channel fires the same incident every ~5 min with a fresh execution
# id. The signature must be identical across firings of one incident (exec ids,
# uuids and numbers ignored) and different across clusters/alert types.

TIMED_OUT_A1 = (
    ":x: The health-checking for the cluster *Orkes Production (Important) - shailesh-test-gcp* has failed \n"
    "Failure Status: `TIMED_OUT` \n"
    "Reason: `Task poll timed out after 20 seconds. Poll timeout configured as 10 seconds. Timeout policy configured to RETRY` \n"
    ":warning: It doesn't mean the cluster is not healthy, but *we've lost telemetry and that should be addressed urgently* \n"
    "<https://ah5r-prod.orkesconductor.com/execution/427e9743-85e2-11f1-b58b-5614587b91fd>"
)
TIMED_OUT_A2 = TIMED_OUT_A1.replace(
    "427e9743-85e2-11f1-b58b-5614587b91fd", "5b203452-85e4-11f1-a198-2ef8a3df853f"
).replace("after 20 seconds", "after 36 seconds")
TIMED_OUT_OTHER_CLUSTER = TIMED_OUT_A1.replace("shailesh-test-gcp", "elementor-poc")


def test_signature_stable_across_firings_of_one_incident():
    from oncall_agent.alert import alert_signature

    assert alert_signature(TIMED_OUT_A1) == alert_signature(TIMED_OUT_A2)


def test_signature_differs_across_clusters():
    from oncall_agent.alert import alert_signature

    assert alert_signature(TIMED_OUT_A1) != alert_signature(TIMED_OUT_OTHER_CLUSTER)


def test_signature_ignores_pod_name_suffixes():
    # Live 2026-07-22: one-staging fired CPU-100% twice, 10 min apart, naming a
    # DIFFERENT conductor pod each time (…-65pkn vs …-pv6m5). Same incident —
    # k8s pod suffixes (mixed digit+letter tokens) must not split the signature.
    from oncall_agent.alert import alert_signature

    a = (":warning: *`[MAJOR]`* ... *`one-staging`* cluster with the following issue:\n"
         "*MAJOR:* Conductor Server CPU usage is at 100.0% and exceeded the threshold "
         "of 95.0% - orkes-conductor-deployment-867cf94585-65pkn")
    b = a.replace("65pkn", "pv6m5")
    assert alert_signature(a) == alert_signature(b)
    # ...but a different alert type on the same cluster still differs
    c = a.replace("CPU usage", "Heap usage")
    assert alert_signature(a) != alert_signature(c)


def test_signature_stable_across_issue_count_and_letter_only_pod_suffixes():
    # Live 2026-07-22 (orkes-prod): the same CPU condition fired as a 1-issue
    # message naming pod …-q9h9d, then as a "following 2 issues" message adding
    # pod …-pvxjg (an ALL-LETTER k8s suffix — the digit+letter rule misses it).
    # k8s suffixes are vowel-free by design; issue-count wording is boilerplate.
    from oncall_agent.alert import alert_signature

    one = (":warning: *`[MAJOR]`* The health-checking has FAILED for the _Orkes's_ prod "
           "*`orkes-prod`* cluster with the following issue:\n"
           "*MAJOR:* Conductor Server CPU usage is at 100.0% and exceeded the threshold "
           "of 95.0% - orkes-conductor-deployment-f749b67d5-q9h9d")
    two = (":warning: *`[MAJOR]`* The health-checking has FAILED for the _Orkes's_ prod "
           "*`orkes-prod`* cluster with the following 2 issues:\n"
           "*MAJOR:* Conductor Server CPU usage is at 100.0% and exceeded the threshold "
           "of 95.0% - orkes-conductor-deployment-f749b67d5-pvxjg\n"
           "*MAJOR:* Conductor Server CPU usage is at 97.4% and exceeded the threshold "
           "of 95.0% - orkes-conductor-deployment-f749b67d5-q9h9d")
    assert alert_signature(one) == alert_signature(two)


def test_digest_and_raw_forms_share_a_signature():
    # Live 2026-07-24: endpoint-dev's memory was seeded from the raw-channel
    # form, then the digest form of the SAME incident signed differently (the
    # aggregator adds headline/occurrence tokens) and bought a duplicate full
    # triage. Signatures must be computed on the quoted original alert only.
    from oncall_agent.alert import alert_signature, message_text, signable_text

    raw = (
        ":warning: *`[MAJOR]`* The health-checking has FAILED for the _At-Bay's_ "
        "prod *`atbay-production`* cluster with the following issue:\n"
        "*MAJOR:* Conductor Server Heap usage is at 91.2% and exceeded the threshold "
        "of 90.0% - orkes-conductor-deployment-cf64b9448-g5czb\n"
        "<https://ah5r-prod.orkesconductor.com/execution/933967a4-85d1-11f1-ba93-96986d0e24f0>"
    )
    digest_flat = message_text(DIGEST_MSG)  # same incident, digest wrapper
    assert alert_signature(signable_text(digest_flat)) == alert_signature(signable_text(raw))
    # and a raw message without any quote marker is passed through unchanged
    assert signable_text(raw) == raw
