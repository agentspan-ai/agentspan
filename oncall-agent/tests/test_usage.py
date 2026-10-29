from oncall_agent import usage


def test_tokens_are_summed_over_llm_calls(monkeypatch):
    wf = {"tasks": [{"taskType": "LLM_CHAT_COMPLETE", "outputData": {"promptTokens": 1000, "completionTokens": 50}},
                    {"taskType": "SIMPLE", "outputData": {}},
                    {"taskType": "LLM_CHAT_COMPLETE", "outputData": {"promptTokens": 2000, "completionTokens": 70}}]}
    monkeypatch.setattr(usage.requests, "get", lambda *a, **k: type("R", (), {"json": lambda self: wf})())
    assert usage.tokens("http://x/api", "E1") == {"llm_calls": 2, "tokens_in": 3000, "tokens_out": 120}
    assert usage.tokens("http://x/api", None)["llm_calls"] == 0


def test_dollars_only_when_prices_are_configured(monkeypatch):
    monkeypatch.delenv("ONCALL_USD_PER_MTOK_IN", raising=False)
    monkeypatch.delenv("ONCALL_USD_PER_MTOK_OUT", raising=False)
    assert usage.usd(1_000_000, 0) is None
    monkeypatch.setenv("ONCALL_USD_PER_MTOK_IN", "2")
    monkeypatch.setenv("ONCALL_USD_PER_MTOK_OUT", "10")
    assert usage.usd(1_000_000, 100_000) == 3.0
