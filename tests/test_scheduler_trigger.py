"""The scheduler's cron trigger: once a week, and only for a weekday name."""
from datetime import datetime, timedelta, timezone

import click
import pytest

from tombot.cli import weekly_trigger


def _fire_times(trigger, start, n):
    out, prev, now = [], None, start
    for _ in range(n):
        nxt = trigger.get_next_fire_time(prev, now)
        out.append(nxt)
        prev, now = nxt, nxt + timedelta(microseconds=1)
    return out


def test_fires_once_a_week_on_the_hour():
    trigger = weekly_trigger("sun", 4, timezone.utc)
    start = datetime(2026, 9, 14, tzinfo=timezone.utc)           # a Monday
    fires = _fire_times(trigger, start, 3)
    assert fires[0] == datetime(2026, 9, 20, 4, 0, 0, tzinfo=timezone.utc)
    assert [b - a for a, b in zip(fires, fires[1:])] == [timedelta(days=7)] * 2


def test_day_name_is_case_and_space_insensitive():
    trigger = weekly_trigger(" Sun ", 4, timezone.utc)
    start = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert trigger.get_next_fire_time(None, start).weekday() == 6


@pytest.mark.parametrize("day", ["1", "0", "", "domingo", "1-5"])
def test_refuses_anything_but_a_weekday_name(day):
    with pytest.raises(click.UsageError):
        weekly_trigger(day, 4, timezone.utc)
