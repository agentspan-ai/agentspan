"""Tests for TUI command parsing."""

from autopilot.tui.commands import parse_command


class TestParseCommand:
    """Test command parsing."""

    def test_empty_input(self):
        result = parse_command("")
        assert result.handled is True
        assert result.action is None

    def test_help_command(self):
        result = parse_command("/help")
        assert result.handled is True
        assert result.output is not None
        assert "Commands:" in result.output

    def test_quit_command(self):
        result = parse_command("quit")
        assert result.action == "quit"

    def test_exit_command(self):
        result = parse_command("exit")
        assert result.action == "quit"

    def test_stop_command(self):
        result = parse_command("/stop")
        assert result.action == "stop"

    def test_cancel_command(self):
        result = parse_command("/cancel")
        assert result.action == "cancel"

    def test_disconnect_command(self):
        result = parse_command("/disconnect")
        assert result.action == "disconnect"

    def test_agents_command(self):
        result = parse_command("/agents")
        assert result.action == "list_agents"

    def test_dashboard_command(self):
        result = parse_command("/dashboard")
        assert result.action == "dashboard"

    def test_notifications_command(self):
        result = parse_command("/notifications")
        assert result.action == "notifications"

    def test_signal_command(self):
        result = parse_command("/signal email-summary skip newsletters")
        assert result.action == "signal"
        assert result.agent_name == "email-summary"
        assert result.message == "skip newsletters"

    def test_signal_missing_message(self):
        result = parse_command("/signal email-summary")
        assert result.output is not None
        assert "Usage" in result.output

    def test_change_command(self):
        result = parse_command("/change email-summary also include calendar")
        assert result.action == "change"
        assert result.agent_name == "email-summary"
        assert result.message == "also include calendar"

    def test_change_missing_instruction(self):
        result = parse_command("/change email-summary")
        assert result.output is not None
        assert "Usage" in result.output

    def test_pause_command(self):
        result = parse_command("/pause email-summary")
        assert result.action == "pause"
        assert result.agent_name == "email-summary"

    def test_resume_command(self):
        result = parse_command("/resume email-summary")
        assert result.action == "resume"
        assert result.agent_name == "email-summary"

    def test_status_command_no_agent(self):
        result = parse_command("/status")
        assert result.action == "status"
        assert result.agent_name is None

    def test_status_command_with_agent(self):
        result = parse_command("/status email-summary")
        assert result.action == "status"
        assert result.agent_name == "email-summary"

    def test_normal_message(self):
        result = parse_command("scan my emails and send me a summary")
        assert result.handled is False
        assert result.message == "scan my emails and send me a summary"

    def test_whitespace_stripped(self):
        result = parse_command("  /help  ")
        assert result.handled is True
        assert result.output is not None
