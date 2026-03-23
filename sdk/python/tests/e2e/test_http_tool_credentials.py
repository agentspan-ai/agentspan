"""E2E: http_tool and mcp_tool credential parameter support."""
import pytest


def test_http_tool_accepts_credentials():
    from agentspan.agents.tool import http_tool
    td = http_tool(
        name="test_api",
        description="Test",
        url="http://localhost:9999/test",
        headers={"Authorization": "Bearer ${MY_TOKEN}"},
        credentials=["MY_TOKEN"],
    )
    assert td.credentials == ["MY_TOKEN"]


def test_http_tool_validates_placeholder_mismatch():
    """${NAME} in headers without matching credentials raises ValueError."""
    from agentspan.agents.tool import http_tool
    with pytest.raises(ValueError, match="MISSING_CRED"):
        http_tool(
            name="bad_api",
            description="Test",
            url="http://localhost:9999/test",
            headers={"Authorization": "Bearer ${MISSING_CRED}"},
            credentials=[],
        )


def test_http_tool_validates_placeholder_no_credentials():
    """${NAME} in headers with credentials=None also raises ValueError."""
    from agentspan.agents.tool import http_tool
    with pytest.raises(ValueError, match="ORPHAN_CRED"):
        http_tool(
            name="bad_api2",
            description="Test",
            url="http://localhost:9999/test",
            headers={"Authorization": "Bearer ${ORPHAN_CRED}"},
        )


def test_http_tool_no_placeholder_no_credentials_ok():
    """Static headers without ${} patterns need no credentials."""
    from agentspan.agents.tool import http_tool
    td = http_tool(
        name="static_api",
        description="Test",
        url="http://localhost:9999/test",
        headers={"Accept": "application/json"},
    )
    assert td.credentials == []


def test_http_tool_serializes_credentials():
    from agentspan.agents import Agent
    from agentspan.agents.tool import http_tool
    from agentspan.agents.config_serializer import AgentConfigSerializer

    tool = http_tool(
        name="cred_api",
        description="Test",
        url="http://localhost:9999/test",
        headers={"X-Auth": "Bearer ${MY_TOKEN}"},
        credentials=["MY_TOKEN"],
    )
    agent = Agent(name="http_cred_test", model="openai/gpt-4o", tools=[tool])
    config = AgentConfigSerializer().serialize(agent)
    tool_cfg = config["tools"][0]
    assert tool_cfg["config"]["credentials"] == ["MY_TOKEN"]
    assert "${MY_TOKEN}" in str(tool_cfg["config"]["headers"])


def test_mcp_tool_accepts_credentials():
    from agentspan.agents.tool import mcp_tool
    td = mcp_tool(
        server_url="http://localhost:3001/mcp",
        headers={"Authorization": "Bearer ${MCP_KEY}"},
        credentials=["MCP_KEY"],
    )
    assert td.credentials == ["MCP_KEY"]


def test_mcp_tool_validates_placeholder_mismatch():
    from agentspan.agents.tool import mcp_tool
    with pytest.raises(ValueError, match="BAD_KEY"):
        mcp_tool(
            server_url="http://localhost:3001/mcp",
            headers={"Authorization": "Bearer ${BAD_KEY}"},
            credentials=[],
        )
