"""Adversarial assertions targeting `helpers.get_current_price` survivors.

Lane-8 of the mutation-score push: targets the 8 remaining mutmut survivors
in ``helpers.get_current_price``. Uses ``freezegun`` to pin ``now`` so the
boundary conditions compare against a real timezone-aware instant — the
patch-based approach in ``test_helpers.py`` masks a few mutations because
the ``datetime`` symbol inside ``helpers`` is replaced wholesale.
"""

from __future__ import annotations

import datetime

from freezegun import freeze_time
from helpers import get_current_price  # type: ignore[import-not-found]

UTC = datetime.UTC


class TestGetCurrentPriceBoundaries:
    """Nail down the strict-``>`` boundary and the best-time replacement."""

    @freeze_time("2026-04-26T10:45:00+00:00")
    def test_slot_exactly_at_now_is_excluded(self) -> None:
        """`slot_time > now` is strict — a slot whose end equals now is in the past."""
        prices = {"2026-04-26T10:45:00+00:00": 0.42}
        assert get_current_price(prices) is None

    @freeze_time("2026-04-26T10:44:59+00:00")
    def test_slot_one_second_after_now_is_picked(self) -> None:
        """Guard against ``>=`` mutation: 1 s past now must still be ``> now``."""
        prices = {"2026-04-26T10:45:00+00:00": 0.42}
        assert get_current_price(prices) == 0.42

    @freeze_time("2026-04-26T10:36:00+00:00")
    def test_earlier_future_slot_wins_over_later(self) -> None:
        """`slot_time < best_time` must stay strict ``<`` (not ``<=`` or ``>``)."""
        prices = {
            "2026-04-26T10:45:00+00:00": 0.10,  # 9 min away — should win
            "2026-04-26T11:00:00+00:00": 0.20,  # 24 min away
            "2026-04-26T11:15:00+00:00": 0.30,  # 39 min away
        }
        assert get_current_price(prices) == 0.10

    @freeze_time("2026-04-26T10:36:00+00:00")
    def test_insertion_order_does_not_matter(self) -> None:
        """Winner stays the same regardless of dict iteration order."""
        later_first = {
            "2026-04-26T11:00:00+00:00": 0.20,
            "2026-04-26T10:45:00+00:00": 0.10,  # inserted later, still wins
        }
        earlier_first = {
            "2026-04-26T10:45:00+00:00": 0.10,
            "2026-04-26T11:00:00+00:00": 0.20,
        }
        assert get_current_price(later_first) == 0.10
        assert get_current_price(earlier_first) == 0.10

    @freeze_time("2026-04-26T10:36:00+00:00")
    def test_best_time_initial_none_accepts_first_future_slot(self) -> None:
        """`best_time is None or ...` — the ``or`` must stay, not become ``and``."""
        prices = {"2026-04-26T10:45:00+00:00": 0.42}
        assert get_current_price(prices) == 0.42


class TestGetCurrentPriceTimezoneHandling:
    """Pin the naive-to-UTC tagging — mut_8 / mut_9 / mut_10 class."""

    @freeze_time("2026-04-26T10:30:00+00:00")
    def test_naive_iso_key_is_treated_as_utc(self) -> None:
        """Original tags naive → UTC; mutations that invert or drop the tag
        leave the parsed datetime naive, which raises ``TypeError`` on the
        later ``slot_time > now`` comparison — mutmut counts that as killed."""
        prices = {"2026-04-26T10:45:00": 0.42}  # no offset — naive
        assert get_current_price(prices) == 0.42


class TestGetCurrentPricePastOnlyPath:
    """`and now` must stay ``and`` — mut_11 (``and`` → ``or``) class."""

    @freeze_time("2026-04-26T12:00:00+00:00")
    def test_single_past_slot_returns_none(self) -> None:
        """`slot_time > now AND ...`: a past slot must NOT win when it would
        trivially satisfy ``best_time is None``."""
        prices = {"2026-04-26T08:00:00+00:00": 0.42}
        assert get_current_price(prices) is None

    @freeze_time("2026-04-26T12:00:00+00:00")
    def test_past_slots_do_not_beat_future_slot(self) -> None:
        prices = {
            "2026-04-26T08:00:00+00:00": 0.10,  # past
            "2026-04-26T11:30:00+00:00": 0.20,  # past
            "2026-04-26T12:15:00+00:00": 0.30,  # future — the only winner
        }
        assert get_current_price(prices) == 0.30


class TestGetCurrentPriceErrorBranch:
    """Pin the ``except ValueError: continue`` path."""

    @freeze_time("2026-04-26T10:36:00+00:00")
    def test_malformed_key_skipped_then_valid_key_wins(self) -> None:
        """`continue` after ValueError lets the loop progress; a later valid key wins."""
        prices = {
            "garbage-timestamp": 9.99,
            "2026-04-26T10:45:00+00:00": 0.42,
        }
        assert get_current_price(prices) == 0.42

    @freeze_time("2026-04-26T10:36:00+00:00")
    def test_only_malformed_keys_returns_none(self) -> None:
        """If every ValueError triggers, ``best_value`` stays at the initial ``None``."""
        prices = {"nope": 1.0, "also-no": 2.0}
        assert get_current_price(prices) is None
