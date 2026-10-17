"""``harness.quota.retry_at``: the reset time of a quota message, else one hour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aifactory.harness.quota import QUOTA_RECHECK, retry_at

NOW = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)  # 12:00 in Prague (CEST)


def test_try_again_in_days_and_minutes() -> None:
    assert retry_at("You've hit your usage limit. Try again in 3 days.", NOW) == NOW + timedelta(
        days=3
    )
    assert retry_at("limit reached, available in 45 minutes", NOW) == NOW + timedelta(minutes=45)
    assert retry_at("try again in 1 hour", NOW) == NOW + timedelta(hours=1)


def test_resets_at_a_time_of_day_in_a_zone() -> None:
    prague = ZoneInfo("Europe/Prague")
    later = retry_at("5-hour limit reached ∙ resets 3pm (Europe/Prague)", NOW)
    assert later == datetime(2026, 10, 17, 15, 0, tzinfo=prague).astimezone(UTC)
    with_minutes = retry_at("resets 3:30pm (Europe/Prague)", NOW)
    assert with_minutes == datetime(2026, 10, 17, 15, 30, tzinfo=prague).astimezone(UTC)
    # 9am has passed in Prague: the next 9am is tomorrow
    tomorrow = retry_at("resets 9am (Europe/Prague)", NOW)
    assert tomorrow == datetime(2026, 10, 18, 9, 0, tzinfo=prague).astimezone(UTC)


def test_unknown_zone_uses_the_local_time() -> None:
    when = retry_at("resets 3pm (Mars/Olympus)", NOW)
    local = NOW.astimezone()
    assert when.astimezone(local.tzinfo).hour == 15
    assert NOW < when <= NOW + timedelta(days=1)


def test_anything_else_rechecks_in_an_hour() -> None:
    assert retry_at("out of extra usage", NOW) == NOW + QUOTA_RECHECK
    assert retry_at("", NOW) == NOW + QUOTA_RECHECK
    assert retry_at(None, NOW) == NOW + QUOTA_RECHECK
    assert retry_at("resets 2026", NOW) == NOW + QUOTA_RECHECK
    assert retry_at("resets 13pm (Europe/Prague)", NOW) == NOW + QUOTA_RECHECK
    assert retry_at("try again in 99999999999 days", NOW) == NOW + QUOTA_RECHECK


def test_naive_now_is_utc() -> None:
    naive = NOW.replace(tzinfo=None)
    assert retry_at("try again in 2 hours", naive) == NOW + timedelta(hours=2)
