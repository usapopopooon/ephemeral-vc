"""Tests for VoiceCog join tracking and owner transfer logic."""

import time
from unittest.mock import MagicMock

import discord
import pytest
from discord.ext import commands

from src.cogs.voice import VoiceCog


@pytest.fixture
def cog() -> VoiceCog:
    """Create a VoiceCog instance with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    return VoiceCog(bot)


def _make_member(user_id: int) -> MagicMock:
    """Create a mock discord.Member."""
    m = MagicMock(spec=discord.Member)
    m.id = user_id
    return m


def _make_voice_channel(
    channel_id: int, members: list[MagicMock]
) -> MagicMock:
    """Create a mock discord.VoiceChannel."""
    ch = MagicMock(spec=discord.VoiceChannel)
    ch.id = channel_id
    ch.members = members
    return ch


class TestRecordJoin:
    """Tests for _record_join."""

    def test_records_new_member(self, cog: VoiceCog) -> None:
        """Test recording a new member join."""
        cog._record_join(100, 1)
        assert 1 in cog._join_times[100]

    def test_does_not_overwrite_existing(self, cog: VoiceCog) -> None:
        """Test that re-joining does not overwrite timestamp."""
        cog._record_join(100, 1)
        first_time = cog._join_times[100][1]
        cog._record_join(100, 1)
        assert cog._join_times[100][1] == first_time

    def test_multiple_members(self, cog: VoiceCog) -> None:
        """Test recording multiple members in same channel."""
        cog._record_join(100, 1)
        cog._record_join(100, 2)
        assert len(cog._join_times[100]) == 2

    def test_multiple_channels(self, cog: VoiceCog) -> None:
        """Test recording joins across different channels."""
        cog._record_join(100, 1)
        cog._record_join(200, 1)
        assert 100 in cog._join_times
        assert 200 in cog._join_times


class TestRemoveJoin:
    """Tests for _remove_join."""

    def test_removes_existing(self, cog: VoiceCog) -> None:
        """Test removing an existing member record."""
        cog._record_join(100, 1)
        cog._remove_join(100, 1)
        assert 1 not in cog._join_times[100]

    def test_noop_for_missing_channel(self, cog: VoiceCog) -> None:
        """Test removing from non-existent channel is a no-op."""
        cog._remove_join(999, 1)  # Should not raise

    def test_noop_for_missing_member(self, cog: VoiceCog) -> None:
        """Test removing non-existent member is a no-op."""
        cog._record_join(100, 1)
        cog._remove_join(100, 999)  # Should not raise
        assert 1 in cog._join_times[100]


class TestCleanupChannel:
    """Tests for _cleanup_channel."""

    def test_removes_channel_records(self, cog: VoiceCog) -> None:
        """Test cleaning up all records for a channel."""
        cog._record_join(100, 1)
        cog._record_join(100, 2)
        cog._cleanup_channel(100)
        assert 100 not in cog._join_times

    def test_noop_for_missing_channel(self, cog: VoiceCog) -> None:
        """Test cleanup for non-existent channel is a no-op."""
        cog._cleanup_channel(999)  # Should not raise


class TestGetLongestMember:
    """Tests for _get_longest_member."""

    def test_returns_longest_staying(self, cog: VoiceCog) -> None:
        """Test that the longest-staying member is returned."""
        m1 = _make_member(1)
        m2 = _make_member(2)
        m3 = _make_member(3)
        channel = _make_voice_channel(100, [m1, m2, m3])

        # m1 joined first, m2 second, m3 third
        cog._join_times[100] = {
            1: time.monotonic() - 30,
            2: time.monotonic() - 20,
            3: time.monotonic() - 10,
        }

        result = cog._get_longest_member(channel, exclude_id=999)
        assert result is m1

    def test_excludes_specified_member(self, cog: VoiceCog) -> None:
        """Test that the excluded member is skipped."""
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_voice_channel(100, [m1, m2])

        cog._join_times[100] = {
            1: time.monotonic() - 30,
            2: time.monotonic() - 10,
        }

        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is m2

    def test_returns_none_when_no_remaining(
        self, cog: VoiceCog
    ) -> None:
        """Test returns None when only the excluded member is left."""
        m1 = _make_member(1)
        channel = _make_voice_channel(100, [m1])

        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is None

    def test_returns_none_for_empty_channel(
        self, cog: VoiceCog
    ) -> None:
        """Test returns None for empty channel."""
        channel = _make_voice_channel(100, [])
        result = cog._get_longest_member(channel, exclude_id=1)
        assert result is None

    def test_fallback_when_no_join_records(
        self, cog: VoiceCog
    ) -> None:
        """Test fallback to first member when no join records exist."""
        m1 = _make_member(1)
        m2 = _make_member(2)
        channel = _make_voice_channel(100, [m1, m2])

        # No join records at all
        result = cog._get_longest_member(channel, exclude_id=999)
        assert result is not None
        assert result.id in (1, 2)
