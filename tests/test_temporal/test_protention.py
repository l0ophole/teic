"""Tests for ProtentionBuffer and ProtentionEntry."""

from datetime import datetime

import pytest

from teic.temporal.protention import ProtentionBuffer, ProtentionEntry


class TestProtentionEntry:
    """Test the ProtentionEntry model."""

    def test_protention_entry_creation(self) -> None:
        """A ProtentionEntry can be created with all required fields."""
        entry = ProtentionEntry(
            made_at_tick_id=42,
            predicted_at=datetime(2025, 1, 1, 12, 0, 0),
            predicted_dt_real=0.1,
            predicted_registers={"channel": 0.5},
        )
        assert entry.made_at_tick_id == 42
        assert entry.predicted_at == datetime(2025, 1, 1, 12, 0, 0)
        assert entry.predicted_dt_real == 0.1
        assert entry.predicted_registers == {"channel": 0.5}


class TestProtentionBuffer:
    """Test the single-slot protention buffer."""

    def test_push_then_pop_returns_same_entry(self) -> None:
        """Pushing an entry and then popping returns the same entry."""
        buffer = ProtentionBuffer()
        entry = ProtentionEntry(
            made_at_tick_id=1,
            predicted_at=datetime(2025, 1, 1, 12, 0, 0),
            predicted_dt_real=0.1,
            predicted_registers={"a": 1.0},
        )

        buffer.push(entry)
        popped = buffer.pop()

        assert popped == entry

    def test_pop_without_push_returns_none(self) -> None:
        """Popping from an empty buffer returns None."""
        buffer = ProtentionBuffer()
        result = buffer.pop()
        assert result is None

    def test_second_pop_after_push_returns_none(self) -> None:
        """A second pop with nothing pushed since returns None."""
        buffer = ProtentionBuffer()
        entry = ProtentionEntry(
            made_at_tick_id=1,
            predicted_at=datetime(2025, 1, 1, 12, 0, 0),
            predicted_dt_real=0.1,
            predicted_registers={},
        )

        buffer.push(entry)
        buffer.pop()
        second_pop = buffer.pop()

        assert second_pop is None

    def test_push_twice_keeps_only_most_recent(self) -> None:
        """Pushing twice without popping keeps only the most recent entry (single-slot)."""
        buffer = ProtentionBuffer()
        entry1 = ProtentionEntry(
            made_at_tick_id=1,
            predicted_at=datetime(2025, 1, 1, 12, 0, 0),
            predicted_dt_real=0.1,
            predicted_registers={"a": 1.0},
        )
        entry2 = ProtentionEntry(
            made_at_tick_id=2,
            predicted_at=datetime(2025, 1, 1, 12, 0, 1),
            predicted_dt_real=0.11,
            predicted_registers={"b": 2.0},
        )

        buffer.push(entry1)
        buffer.push(entry2)
        popped = buffer.pop()

        assert popped == entry2
        assert popped != entry1
