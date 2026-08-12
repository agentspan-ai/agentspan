"""Tests for the notification manager."""

from autopilot.config import AutopilotConfig
from autopilot.tui.notifications import Notification, NotificationManager


def _make_notification(
    agent_name: str = "test-agent",
    summary: str = "test summary",
    priority: str = "normal",
    read: bool = False,
) -> Notification:
    """Helper to create a Notification with defaults."""
    return Notification(
        agent_name=agent_name,
        timestamp="2026-04-12T09:00:00Z",
        summary=summary,
        priority=priority,
        read=read,
    )


class TestAddNotification:
    """Test adding notifications."""

    def test_add_notification(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        n = _make_notification()
        mgr.add(n)
        all_notifs = mgr.get_all()
        assert len(all_notifs) == 1
        assert all_notifs[0] is n
        assert all_notifs[0].agent_name == "test-agent"
        assert all_notifs[0].summary == "test summary"

    def test_add_multiple_notifications_newest_first(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        n1 = _make_notification(agent_name="agent-1", summary="first")
        n2 = _make_notification(agent_name="agent-2", summary="second")
        mgr.add(n1)
        mgr.add(n2)
        all_notifs = mgr.get_all()
        assert len(all_notifs) == 2
        # Newest first
        assert all_notifs[0].summary == "second"
        assert all_notifs[1].summary == "first"

    def test_get_all_respects_limit(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        for i in range(10):
            mgr.add(_make_notification(summary=f"notif-{i}"))
        assert len(mgr.get_all(limit=3)) == 3
        assert len(mgr.get_all(limit=20)) == 10


class TestUnreadCount:
    """Test unread counting and marking."""

    def test_unread_count(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1"))
        mgr.add(_make_notification(agent_name="a2"))
        mgr.add(_make_notification(agent_name="a3"))
        assert mgr.unread_count() == 3

        mgr.mark_read("a1")
        assert mgr.unread_count() == 2

    def test_unread_count_with_pre_read(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1", read=True))
        mgr.add(_make_notification(agent_name="a2", read=False))
        assert mgr.unread_count() == 1


class TestMarkAllRead:
    """Test marking all notifications as read."""

    def test_mark_all_read(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1"))
        mgr.add(_make_notification(agent_name="a2"))
        mgr.add(_make_notification(agent_name="a3"))
        assert mgr.unread_count() == 3

        mgr.mark_all_read()
        assert mgr.unread_count() == 0

    def test_mark_all_read_updates_config_last_seen(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1"))
        mgr.add(_make_notification(agent_name="a2"))
        mgr.mark_all_read()
        # last_seen should have entries for both agents
        assert "a1" in config.last_seen
        assert "a2" in config.last_seen


class TestGetUnread:
    """Test getting only unread notifications."""

    def test_get_unread(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1", read=False))
        mgr.add(_make_notification(agent_name="a2", read=True))
        mgr.add(_make_notification(agent_name="a3", read=False))

        unread = mgr.get_unread()
        assert len(unread) == 2
        names = {n.agent_name for n in unread}
        assert names == {"a1", "a3"}

    def test_get_unread_after_mark_read(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1"))
        mgr.add(_make_notification(agent_name="a2"))
        mgr.mark_read("a1")

        unread = mgr.get_unread()
        assert len(unread) == 1
        assert unread[0].agent_name == "a2"

    def test_get_unread_empty_when_all_read(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1"))
        mgr.mark_all_read()
        assert mgr.get_unread() == []

    def test_mark_read_only_affects_named_agent(self):
        config = AutopilotConfig()
        mgr = NotificationManager(config)
        mgr.add(_make_notification(agent_name="a1"))
        mgr.add(_make_notification(agent_name="a1"))
        mgr.add(_make_notification(agent_name="a2"))
        mgr.mark_read("a1")
        unread = mgr.get_unread()
        assert len(unread) == 1
        assert unread[0].agent_name == "a2"
