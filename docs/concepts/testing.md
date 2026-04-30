---
title: Testing
description: Test agents without an LLM — mock_run, MockEvent, expect, record/replay, pytest
---

# Testing

Agentspan has a first-class testing module that lets you test agent behavior without making LLM API calls or running a server. Tests are deterministic, fast, and runnable in CI.

## Import

```python
from agentspan.agents.testing import mock_run, MockEvent, expect, record, replay
```

## mock_run

`mock_run` runs an agent with a scripted sequence of events instead of calling an LLM:

```python
from agentspan.agents import Agent, tool
from agentspan.agents.testing import mock_run, MockEvent, expect

@tool
def search_web(query: str) -> str:
    """Search the web."""
    return "results"

agent = Agent(
    name="research_bot",
    model="openai/gpt-4o",
    tools=[search_web],
)

result = mock_run(
    agent,
    "What is agentspan?",
    events=[
        MockEvent.thinking("I should search for information about agentspan."),
        MockEvent.tool_call("search_web", {"query": "agentspan Python agent runtime"}),
        MockEvent.tool_result("search_web", "Agentspan is an open source Python runtime for AI agents."),
        MockEvent.done("Agentspan is an open source Python runtime for building AI agents."),
    ]
)

expect(result).completed().output_contains("Agentspan").used_tool("search_web")
```

`mock_run` signature:

```python
mock_run(
    agent: Agent,
    prompt: str,
    events: list[MockEvent],
    context_state: dict | None = None,   # initial ToolContext.state
) -> AgentResult
```

## MockEvent factory methods

| Method | Description |
|--------|-------------|
| `MockEvent.thinking(content)` | Agent internal reasoning step |
| `MockEvent.tool_call(tool_name, args)` | LLM calls a tool with given arguments |
| `MockEvent.tool_result(tool_name, result)` | Tool returns a result |
| `MockEvent.message(content)` | Agent sends an intermediate message |
| `MockEvent.handoff(target)` | Control passes to a named agent |
| `MockEvent.guardrail_pass(name)` | A guardrail passes |
| `MockEvent.guardrail_fail(name, message)` | A guardrail fails (triggers retry/fix/etc.) |
| `MockEvent.waiting(content)` | Agent pauses for human approval |
| `MockEvent.error(message)` | An error occurs |
| `MockEvent.done(output)` | Agent completes with this output |

## expect() fluent assertions

Chain assertions on the result:

```python
expect(result)
    .completed()                          # status is COMPLETED
    .output_contains("Paris")             # output contains substring
    .output_matches(r"capital.*France")   # output matches regex
    .used_tool("search_web")              # tool was called at least once
    .used_tool("search_web", args={"query": "capital of France"})  # with specific args
    .max_turns(5)                         # used at most 5 turns
    .no_errors()                          # no error events
    .guardrail_passed("no_pii")           # named guardrail passed
```

All assertions raise `AssertionError` with descriptive messages on failure. You can also assert failure cases:

```python
expect(result).failed()                          # status is FAILED
expect(result).guardrail_failed("safety_check")  # named guardrail failed
```

## Function-based assertions

For more complex checks, inspect the result directly:

```python
result = mock_run(agent, "prompt", events=[...])

# Check output — result.output is always a dict {'result': str, 'finishReason': str}
assert "expected phrase" in result.output['result']
assert result.status == "COMPLETED"

# Check tool calls
tool_calls = [t for t in result.tool_calls if t['name'] == "search_web"]
assert len(tool_calls) == 1
assert tool_calls[0]['args']["query"] == "expected query"

# Check structured output (parse JSON from result.output['result'])
import json
data = json.loads(result.output['result'])
assert data["city"] == "San Francisco"
```

## Testing tool side effects

Test that tools are called with correct arguments and that state is managed properly:

```python
from agentspan.agents import Agent, tool
from agentspan.agents.testing import mock_run, MockEvent, expect

@tool
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email."""
    return {"sent": True, "to": to}

agent = Agent(
    name="email_bot",
    model="openai/gpt-4o",
    tools=[send_email],
)

result = mock_run(
    agent,
    "Send a welcome email to alice@example.com",
    events=[
        MockEvent.tool_call("send_email", {
            "to": "alice@example.com",
            "subject": "Welcome!",
            "body": "Welcome to our platform...",
        }),
        MockEvent.tool_result("send_email", {"sent": True, "to": "alice@example.com"}),
        MockEvent.done("Email sent successfully to alice@example.com."),
    ]
)

expect(result).completed().used_tool("send_email", args={
    "to": "alice@example.com",
    "subject": "Welcome!",
})
```

## Testing HITL flows

Test human-in-the-loop interactions:

```python
from agentspan.agents import Agent, tool
from agentspan.agents.testing import mock_run, MockEvent, expect

@tool(approval_required=True)
def delete_file(path: str) -> dict:
    """Delete a file. Requires approval."""
    return {"deleted": True, "path": path}

agent = Agent(name="file_manager", model="openai/gpt-4o", tools=[delete_file])

# Test the approval path
result = mock_run(
    agent,
    "Delete /tmp/old-logs.txt",
    events=[
        MockEvent.tool_call("delete_file", {"path": "/tmp/old-logs.txt"}),
        MockEvent.waiting("Agent wants to delete /tmp/old-logs.txt. Approve?"),
        MockEvent.tool_result("delete_file", {"deleted": True, "path": "/tmp/old-logs.txt"}),
        MockEvent.done("File /tmp/old-logs.txt has been deleted."),
    ]
)
expect(result).completed().used_tool("delete_file")

# Test the rejection path
result = mock_run(
    agent,
    "Delete /etc/hosts",
    events=[
        MockEvent.tool_call("delete_file", {"path": "/etc/hosts"}),
        MockEvent.waiting("Agent wants to delete /etc/hosts. Approve?"),
        MockEvent.done("I was not able to delete /etc/hosts — the action was denied."),
    ]
)
expect(result).completed().output_contains("denied")
```

## Testing multi-agent pipelines

Test sequential pipelines:

```python
researcher = Agent(name="researcher", model="openai/gpt-4o",
                   tools=[search_web], instructions="Research the topic.")
writer = Agent(name="writer", model="openai/gpt-4o",
               instructions="Write an article.")

pipeline = researcher >> writer

result = mock_run(
    pipeline,
    "Write about Python asyncio",
    events=[
        # Researcher turn
        MockEvent.tool_call("search_web", {"query": "Python asyncio overview"}),
        MockEvent.tool_result("search_web", "asyncio is Python's async I/O framework..."),
        MockEvent.handoff("writer"),
        # Writer turn
        MockEvent.done("# Python asyncio\nasyncio enables concurrent code using async/await..."),
    ]
)

expect(result).completed().used_tool("search_web")
```

## Record and replay

Record a real execution (with an actual LLM) and replay it deterministically in tests:

```python
from agentspan.agents.testing import record, replay

# Record a real run (calls LLM)
recording = record(agent, "What's the capital of France?")
recording.save("tests/fixtures/capital_query.json")

# Replay it (no LLM, no server)
result = replay("tests/fixtures/capital_query.json")
expect(result).completed().output_contains("Paris")
```

This is useful for:
- Capturing known-good behavior as regression tests
- Running existing test cases against new model versions
- Debugging: record a failing production execution, replay locally

## pytest integration

```python
import pytest
from agentspan.agents.testing import mock_run, MockEvent, expect

# Mark as unit test — no LLM, no server, fast
class TestWeatherAgent:
    def test_weather_query(self, weather_agent):
        result = mock_run(
            weather_agent,
            "Weather in NYC?",
            events=[
                MockEvent.tool_call("get_weather", {"city": "New York"}),
                MockEvent.tool_result("get_weather", {"temp_f": 65, "condition": "Cloudy"}),
                MockEvent.done("New York is currently 65°F and cloudy."),
            ]
        )
        expect(result).completed().output_contains("65").used_tool("get_weather")

    def test_handles_unknown_city(self, weather_agent):
        result = mock_run(
            weather_agent,
            "Weather in Atlantis?",
            events=[
                MockEvent.tool_call("get_weather", {"city": "Atlantis"}),
                MockEvent.tool_result("get_weather", {"error": "City not found"}),
                MockEvent.done("I couldn't find weather data for Atlantis."),
            ]
        )
        expect(result).completed().output_contains("couldn't find")

# Mark as integration test — calls real LLM, requires server
@pytest.mark.integration
class TestWeatherAgentIntegration:
    def test_real_weather_query(self, weather_agent):
        from agentspan.agents import run
        result = run(weather_agent, "Weather in San Francisco?")
        assert result.status == "COMPLETED"
        assert len(result.output) > 10
```

Run unit tests only:
```bash
pytest tests/ -m "not integration"
```

Run integration tests:
```bash
pytest tests/ -m integration
```

## Evaluating output correctness

For evaluating LLM output quality (not just structure), use `CorrectnessEval`:

```python
from agentspan.agents import AgentRuntime
from agentspan.agents.testing import CorrectnessEval, EvalCase

eval_runner = CorrectnessEval(runtime=AgentRuntime())

cases = [
    EvalCase(
        name="capital_of_france",
        agent=agent,
        prompt="What is the capital of France?",
        expect_output_contains=["Paris"],
        expect_status="COMPLETED",
    ),
]

suite = eval_runner.run(cases)
suite.print_summary()
assert suite.all_passed
```
