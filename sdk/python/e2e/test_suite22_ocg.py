"""Suite 22: OCG multi-instance — per-tool instance binding isolation.

The multi-tenancy guarantee of the SDK-defined OCG design: two retrieval
agents bound to two different OCG instances (`ocg_agent(url=...)`) each hit
their own instance and ONLY that instance. Validation is purely structural —
recorded HTTP traffic on the stubs — never LLM-judged output quality.

  1. US agent (agent_tool → ocg_agent bound to stub A) → traffic on A, none on B
  2. Canada agent (bound to stub B) → traffic on B, none on A
  3. Negative: agent with no OCG tools → no traffic on either stub

Manages two stub OCG instances on dedicated ports.
No mocks of agentspan itself. Real server, real LLM, stub OCG backends.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conductor.ai.agents import Agent, agent_tool
from conductor.ai.agents.ocg import ocg_agent

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.xdist_group("ocg"),
]

# ── Configuration ────────────────────────────────────────────────────────

US_PORT = 3061
CA_PORT = 3062
TIMEOUT = 120

MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")

# The agentspan server resolves the per-tool OCG URL server-side, so the
# stubs must be reachable from the server process — localhost works for the
# local e2e topology (server and tests on the same host).
US_URL = f"http://localhost:{US_PORT}"
CA_URL = f"http://localhost:{CA_PORT}"


# ── Stub OCG instance ────────────────────────────────────────────────────


class _StubOcg:
    """Minimal OCG lookalike: answers /api/v1/agent/query with canned
    citations and records every request it receives."""

    def __init__(self, port: int, region: str):
        self.port = port
        self.region = region
        self.requests: list = []  # (method, path, body) tuples
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _record_and_reply(self, body: str):
                stub.requests.append((self.command, self.path, body))
                payload = {
                    "citations": [
                        {
                            "source_item_id": f"{stub.region}-item-1",
                            "title": f"{stub.region} maintenance window",
                            "container_id": f"#{stub.region}-ops",
                            "snippet": f"The {stub.region} maintenance window is Saturday 02:00 UTC.",
                        }
                    ]
                }
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self._record_and_reply(self.rfile.read(length).decode())

            def do_GET(self):
                self._record_and_reply("")

            def do_DELETE(self):
                self._record_and_reply("")

            def log_message(self, *args):  # silence per-request stderr noise
                pass

        self._server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    @property
    def query_requests(self):
        return [r for r in self.requests if r[1].startswith("/api/v1/agent/query")]


@pytest.fixture(scope="module")
def stubs():
    us = _StubOcg(US_PORT, "us").start()
    ca = _StubOcg(CA_PORT, "canada").start()
    try:
        yield us, ca
    finally:
        us.stop()
        ca.stop()


def _retrieval_main(name: str, retriever) -> Agent:
    return Agent(
        name=name,
        model=MODEL,
        instructions=(
            "You answer operational questions. You MUST call your retrieval "
            "tool to look up the answer before responding — never answer "
            "from memory and never ask the user clarifying questions. Pass "
            "the user's question to the retrieval tool verbatim."
        ),
        tools=[agent_tool(retriever)],
        max_turns=6,
    )


PROMPT = (
    "Search for recent messages about the maintenance window for cluster "
    "prod-east and report exactly what the messages say. Do not ask "
    "clarifying questions — search first."
)


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.timeout(TIMEOUT * 2)
def test_us_agent_hits_only_us_instance(runtime, stubs):
    us, ca = stubs
    us_before, ca_before = len(us.query_requests), len(ca.query_requests)

    retriever = ocg_agent(name="ocg_us_e2e", model=MODEL, url=US_URL)
    main = _retrieval_main("ocg_e2e_us_main", retriever)

    result = runtime.run(main, PROMPT, timeout=TIMEOUT)
    assert result is not None

    # The multi-tenancy guarantee, asserted on recorded traffic:
    assert len(us.query_requests) > us_before, (
        f"US-bound retriever never queried the US OCG stub — stub saw: {us.requests}"
    )
    assert len(ca.query_requests) == ca_before, (
        f"US-bound retriever leaked traffic to the Canada stub: {ca.requests}"
    )


@pytest.mark.timeout(TIMEOUT * 2)
def test_canada_agent_hits_only_canada_instance(runtime, stubs):
    us, ca = stubs
    us_before, ca_before = len(us.query_requests), len(ca.query_requests)

    retriever = ocg_agent(name="ocg_ca_e2e", model=MODEL, url=CA_URL)
    main = _retrieval_main("ocg_e2e_ca_main", retriever)

    result = runtime.run(main, PROMPT, timeout=TIMEOUT)
    assert result is not None

    assert len(ca.query_requests) > ca_before, (
        f"Canada-bound retriever never queried the Canada OCG stub — stub saw: {ca.requests}"
    )
    assert len(us.query_requests) == us_before, (
        f"Canada-bound retriever leaked traffic to the US stub: {us.requests}"
    )


@pytest.mark.timeout(TIMEOUT * 2)
def test_agent_without_ocg_tools_generates_no_ocg_traffic(runtime, stubs):
    us, ca = stubs
    us_before, ca_before = len(us.requests), len(ca.requests)

    plain = Agent(
        name="ocg_e2e_plain",
        model=MODEL,
        instructions="Answer briefly from your own knowledge.",
        max_turns=2,
    )

    result = runtime.run(plain, "Say hello in one word.", timeout=TIMEOUT)
    assert result is not None

    # Inverse of the deleted auto-expose behavior: no OCG opt-in, no OCG calls.
    assert len(us.requests) == us_before
    assert len(ca.requests) == ca_before
