"""Tests for the dashboard rendering with box-drawing characters."""

from autopilot.tui.dashboard import render_dashboard


class TestRenderDashboardEmpty:
    """Test dashboard rendering with no agents."""

    def test_render_dashboard_empty(self):
        result = render_dashboard(agents=[], notifications=[])
        assert "AGENTSPAN CLAW" in result
        assert "Dashboard" in result
        assert "No agents configured." in result
        assert "No notifications." in result

    def test_render_dashboard_empty_shows_zero_new(self):
        result = render_dashboard(agents=[], notifications=[])
        assert "0 new" in result

    def test_render_dashboard_contains_box_drawing(self):
        """Dashboard must use box-drawing characters."""
        result = render_dashboard(agents=[], notifications=[])
        assert "\u2554" in result  # double top-left
        assert "\u2557" in result  # double top-right
        assert "\u255a" in result  # double bottom-left
        assert "\u255d" in result  # double bottom-right
        assert "\u2551" in result  # double vertical
        assert "\u2550" in result  # double horizontal


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

        # Status indicators must use circle icons
        assert "\u25cf" in result  # filled circle (active/error)
        assert "\u25cb" in result  # empty circle (paused)

        # Trigger types must appear
        assert "cron" in result
        assert "daemon" in result

    def test_render_dashboard_missing_fields_uses_defaults(self):
        """Agents with missing fields should not crash."""
        agents = [{"name": "minimal-agent"}]
        result = render_dashboard(agents=agents, notifications=[])
        assert "minimal-agent" in result

    def test_render_dashboard_agent_statuses_produce_icons(self):
        """Verify different statuses produce icon characters."""
        for status in ["active", "paused", "waiting", "error"]:
            agents = [{"name": f"agent-{status}", "status": status, "last_run": "", "trigger": ""}]
            result = render_dashboard(agents=agents, notifications=[])
            # Every status should produce some kind of circle icon
            assert "\u25cf" in result or "\u25cb" in result or "\u25d4" in result, (
                f"Expected a circle icon for status '{status}'"
            )

    def test_render_dashboard_header_row(self):
        """Verify the agent table has a header."""
        agents = [{"name": "test", "status": "active", "last_run": "", "trigger": "cron"}]
        result = render_dashboard(agents=agents, notifications=[])
        assert "AGENTS" in result
        assert "STATUS" in result
        assert "TRIGGER" in result
        assert "LAST RUN" in result


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
        assert "1 new" in result

        # Notification content
        assert "email-summary" in result
        assert "2 urgent emails flagged" in result
        assert "docs-reviewer" in result
        assert "Review complete" in result

        # Unread marker: '*' for unread, ' ' for read
        lines = result.split("\n")
        email_lines = [l for l in lines if "email-summary" in l and "2 urgent" in l]
        assert len(email_lines) == 1
        assert "*" in email_lines[0]

        docs_lines = [l for l in lines if "docs-reviewer" in l and "Review complete" in l]
        assert len(docs_lines) == 1
        # Read notifications should not have the '*' marker
        # Find the notification-specific portion
        doc_line = docs_lines[0]
        # The read notification's marker position should have a space, not '*'
        # Look at the content after the border character
        content_start = doc_line.find("\u2551") + 1
        notif_text = doc_line[content_start:].lstrip()
        assert not notif_text.startswith("*")

    def test_render_dashboard_all_unread(self):
        notifications = [
            {"agent_name": "a1", "timestamp": "", "summary": "s1", "priority": "normal", "read": False},
            {"agent_name": "a2", "timestamp": "", "summary": "s2", "priority": "normal", "read": False},
            {"agent_name": "a3", "timestamp": "", "summary": "s3", "priority": "normal", "read": False},
        ]
        result = render_dashboard(agents=[], notifications=notifications)
        assert "3 new" in result

    def test_render_dashboard_all_read(self):
        notifications = [
            {"agent_name": "a1", "timestamp": "", "summary": "s1", "priority": "normal", "read": True},
        ]
        result = render_dashboard(agents=[], notifications=notifications)
        assert "0 new" in result

    def test_render_dashboard_notifications_section(self):
        """Verify the notifications section header is present."""
        result = render_dashboard(agents=[], notifications=[])
        assert "NOTIFICATIONS" in result
