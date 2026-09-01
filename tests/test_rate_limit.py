"""The per-minute request throttle (#50).

The tcggo freemium plan caps requests per minute as well as per day. Going over
the per-minute cap only earns a 429 (no money, unlike the daily cap), so the
budget waits for a slot to free rather than failing — bounded by the 60s window.
"""
import pytest

from tombot.services.budget import RequestBudget
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "b.db")
    r.init_db()
    return r


def _fill(repo, provider, n):
    with repo.tx() as c:
        c.executemany("INSERT INTO api_requests(provider, sent_at) "
                      "VALUES(?, datetime('now'))", [(provider,)] * n)


def test_minute_window_wait_is_zero_under_the_cap(repo):
    assert repo.minute_window_wait("tcggo", 30, 1) == 0.0
    _fill(repo, "tcggo", 10)
    assert repo.minute_window_wait("tcggo", 30, 1) == 0.0     # 11 <= 30


def test_minute_window_wait_positive_and_bounded_at_the_cap(repo):
    _fill(repo, "tcggo", 3)
    wait = repo.minute_window_wait("tcggo", 3, 1)             # 3 + 1 > 3
    assert 0.0 < wait <= 60.0


def test_reserve_does_not_wait_under_the_cap(repo):
    slept = []
    b = RequestBudget(repo, "tcggo", limit=100, per_minute=30,
                      sleep=lambda s: slept.append(s))
    for _ in range(10):
        b.reserve(1)
    assert slept == []
    assert b.used() == 10


def test_reserve_waits_when_the_per_minute_cap_is_hit(repo):
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        # Simulate the minute passing: age every request out of the window so
        # the next check finds a free slot (real time doesn't move in a test).
        with repo.tx() as c:
            c.execute("UPDATE api_requests SET sent_at = datetime('now', '-2 minutes')")

    b = RequestBudget(repo, "tcggo", limit=100, per_minute=3, sleep=fake_sleep)
    for _ in range(3):
        b.reserve(1)               # fills the minute window, no wait yet
    assert slept == []

    b.reserve(1)                   # 4th within the minute must wait for a slot
    assert len(slept) == 1 and slept[0] > 0


def test_per_minute_zero_disables_the_throttle(repo):
    slept = []
    b = RequestBudget(repo, "tcggo", limit=100, per_minute=0,
                      sleep=lambda s: slept.append(s))
    for _ in range(50):
        b.reserve(1)
    assert slept == []             # never throttles when unset
