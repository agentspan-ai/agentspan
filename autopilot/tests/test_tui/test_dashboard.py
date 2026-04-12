"""Tests for the dashboard rendering."""

from autopilot.tui.dashboard import render_dashboard


class TestRenderDashboardEmpty:
    """Test dashboard rendering with no agents."""

    def test_render_dashboard_empty(self):
        result = render_dashboard(agents=[], notifications=[])
        assert "DASHBOARD" in result
        assert "No agents configured." in result
        assert "No notifications." in result

    def test_render_dashboard_empty_shows_zero_unread(self):
        result = render_dashboard(agents=[], notifications=[])
        assert "0 unread" in result


class TestRenderDashboardWithAgents:
    """Test dashboard rendering with agent data."""

    def test_render_dashboard_with_agents(self):
        agents = [
            {"name": "email-summary", "status": "active", "last_run": "2026-04-12T08:30:00Z", "trigger": "cron"},
            {"name": "docs-reviewer", "status": "paused", "last_run": "", "trigger": "daemon"},
            {"name": "tax-review", "status": "error", "last_run": "2026-04-11T14:00:00Z", "trigger": "cron"},
        ]
        result = render_dashboard(agents=agents, notifications=[])

        # All agent names must appear
        assert "email-summary" in result
        assert "docs-reviewer" in result
        assert "tax-review" in result

        # Status indicators must appear
        assert "[*]" in result  # active
        assert "[-]" in result  # paused
        assert "[!]" in result  # error

        # Trigger types must appear
        assert "cron" in result
        assert "daemon" in result

    def test_render_dashboard_missing_fields_uses_defaults(self):
        """Agents with missing fields should not crash."""
        agents = [{"name": "minimal-agent"}]
        result = render_dashboard(agents=agents, notifications=[])
        assert "minimal-agent" in result

    def test_render_dashboard_agent_statuses_are_correct(self):
        """Verify each status maps to its expected icon."""
        for status, icon in [
            ("active", "[*]"),
            ("paused", "[-]"),
            ("waiting", "[?]"),
            ("error", "[!]"),
            ("archived", "[x]"),
        ]:
            agents = [{"name": f"agent-{status}", "status": status, "last_run": "", "trigger": ""}]
            result = render_dashboard(agents=agents, notifications=[])
            assert icon in result, f"Expected {icon} for status '{status}' in output"


class TestRenderDashboardWithNotifications:
    """Test dashboard rendering with notifications."""

    def test_render_dashboard_with_notifications(self):
        notifications = [
            {
                "agent_name": "email-summary",
                "timestamp": "2026-04-12T09:00:00Z",
                "summary": "2 urgent emails flagged",
                "priority": "urgent",
                "read": False,
            },
            {
                "agent_name": "docs-reviewer",
                "timestamp": "2026-04-12T08:30:00Z",
                "summary": "Review complete",
                "priority": "info",
                "read": True,
            },
        ]
        result = render_dashboard(agents=[], notifications=notifications)

        # Unread count should be 1 (only the first is unread)
        assert "1 unread" in result

        # Notification content
        assert "email-summary" in result
        assert "2 urgent emails flagged" in result
        assert "docs-reviewer" in result
        assert "Review complete" in result

        # Unread marker: '*' for unread, ' ' for read
        lines = result.split("\n")
        email_lines = [l for l in lines if "email-summary" in l and "2 urgent" in l]
        assert len(email_lines) == 1
        assert email_lines[0].lstrip().startswith("*")

        docs_lines = [l for l in lines if "docs-reviewer" in l and "Review complete" in l]
        assert len(docs_lines) == 1
        # Read notifications don't start with '*'
        assert not docs_lines[0].lstrip().startswith("*")

    def test_render_dashboard_all_unread(self):
        notifications = [
            {"agent_name": "a1", "timestamp": "", "summary": "s1", "priority": "normal", "read": False},
            {"agent_name": "a2", "timestamp": "", "summary": "s2", "priority": "normal", "read": False},
            {"agent_name": "a3", "timestamp": "", "summary": "s3", "priority": "normal", "read": False},
        ]
        result = render_dashboard(agents=[], notifications=notifications)
        assert "3 unread" in result

    def test_render_dashboard_all_read(self):
        notifications = [
            {"agent_name": "a1", "timestamp": "", "summary": "s1", "priority": "normal", "read": True},
        ]
        result = render_dashboard(agents=[], notifications=notifications)
        assert "0 unread" in result
