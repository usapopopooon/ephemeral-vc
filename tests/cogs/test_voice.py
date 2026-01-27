"""Tests for VoiceCog join tracking helpers."""

from unittest.mock import MagicMock

import discord

from src.cogs.voice import VoiceCog


def _make_cog() -> VoiceCog:
    """Create a VoiceCog instance with a mock bot."""
    bot = MagicMock(spec=discord.ext.commands.Bot)
    return VoiceCog(bot)


def _make_member(user_id: int, *, bot: bool = False) -> MagicMock:
    """Create a mock discord.Member."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = bot
    return member


def _make_channel(
    channel_id: int, members: list[MagicMock] | None = None
) -> MagicMock:
    """Create a mock discord.VoiceChannel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = channel_id
    channel.members = members or []
    return channel


class TestRecordJoin:
    """Tests for _record_join."""

    def test_new_member(self) -> None:
        """Test recording a new member join."""
        cog = _make_cog()
        cog._record_join(100, 1)
        assert 1 in cog._join_times[100]

    def test_no_overwrite(self) -> None:
        """Test that existing join time is not overwritten."""
        cog = _make_cog()
        cog._record_join(100, 1)
        first_time = cog._join_times[100][1]
        cog._record_join(100, 1)
        assert cog._join_times[100][1] == first_time

    def test_multiple_members(self) -> None:
        """Test recording multiple members in the same channel."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._record_join(100, 2)
        assert len(cog._join_times[100]) == 2

    def test_multiple_channels(self) -> None:
        """Test recording joins across different channels."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._record_join(200, 2)
        assert 100 in cog._join_times
        assert 200 in cog._join_times


class TestRemoveJoin:
    """Tests for _remove_join."""

    def test_existing_member(self) -> None:
        """Test removing an existing member's join record."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._remove_join(100, 1)
        assert 1 not in cog._join_times[100]

    def test_missing_channel(self) -> None:
        """Test removing from a non-existent channel does not raise."""
        cog = _make_cog()
        cog._remove_join(999, 1)  # Should not raise

    def test_missing_member(self) -> None:
        """Test removing a non-existent member does not raise."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._remove_join(100, 999)  # Should not raise
        assert 1 in cog._join_times[100]


class TestCleanupChannel:
    """Tests for _cleanup_channel."""

    def test_removes_records(self) -> None:
        """Test that cleanup removes all records for a channel."""
        cog = _make_cog()
        cog._record_join(100, 1)
        cog._record_join(100, 2)
        cog._cleanup_channel(100)
        assert 100 not in cog._join_times

    def test_missing_channel(self) -> None:
        """Test cleaning up a non-existent channel does not raise."""
        cog = _make_cog()
        cog._cleanup_channel(999)  # Should not raise


class TestGetLongestMember:
    """Tests for _get_longest_member."""

    def test_longest_staying(self) -> None:
        """Test that the member with the earliest join time is returned."""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])

        cog._join_times[100] = {1: 10.0, 2: 20.0}
        result = cog._get_longest_member(channel, exclude_id=999)
        assert result is m1

    def test_excludes_specified(self) -> None:
        """Test that the excluded member is not returned."""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])

        cog._join_times[100] = {1: 10.0, 2: 20.0}
        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is m2

    def test_none_remaining(self) -> None:
        """Test that None is returned when no members remain."""
        cog = _make_cog()
        m1 = _make_member(1)
        channel = _make_channel(100, [m1])

        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is None

    def test_empty_channel(self) -> None:
        """Test that None is returned for an empty channel."""
        cog = _make_cog()
        channel = _make_channel(100, [])

        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is None

    def test_fallback_without_records(self) -> None:
        """Test fallback when no join records exist."""
        cog = _make_cog()
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_channel(100, [m1, m2])

        # No join records - should still return a member
        result = cog._get_longest_member(channel, exclude_id=999)
        assert result is not None
