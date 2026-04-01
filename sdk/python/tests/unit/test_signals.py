from agentspan.agents.signal import SignalReceipt, SignalStatus
from agentspan.agents.result import EventType


def test_signal_receipt_fields():
    r = SignalReceipt(signal_id="uuid-1", execution_id="wf-1", status="queued")
    assert r.signal_id == "uuid-1"
    assert r.execution_id == "wf-1"
    assert r.status == "queued"


def test_signal_status_fields():
    s = SignalStatus(signal_id="uuid-1", execution_id="wf-1",
                     delivered=True, disposition="accepted")
    assert s.delivered is True
    assert s.rejection_reason is None


def test_signal_status_rejected():
    s = SignalStatus(signal_id="uuid-2", execution_id="wf-1",
                     delivered=True, disposition="rejected",
                     rejection_reason="not relevant")
    assert s.rejection_reason == "not relevant"


def test_event_type_signal_values():
    assert EventType.SIGNAL_RECEIVED == "signal_received"
    assert EventType.SIGNAL_ACCEPTED == "signal_accepted"
    assert EventType.SIGNAL_REJECTED == "signal_rejected"
