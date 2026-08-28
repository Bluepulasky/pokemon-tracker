"""The TCG era for a set is its release date placed in the era timeline.

The eras are chronological and non-overlapping, so a date falls in exactly one.
These cases are the ones that surprised the naive 'group by tcggo series' code:
sets whose era name is nothing like the set name (Evolutions is XY-era,
Celebrations is Sword & Shield-era, EX Team Rocket Returns is EX-era).
"""
import pytest

from tombot.services.tcg_series import series_for_date


@pytest.mark.parametrize("date,era", [
    ("1999/01/09", "Base"),                    # Base Set
    ("1999/07/01", "Base"),                    # Wizards promos
    ("2000/02/24", "Base"),                    # Base Set 2
    ("2000/04/24", "Base"),                    # Team Rocket
    ("2000/08/14", "Gym"),                     # Gym Heroes
    ("2000/12/16", "Neo"),                     # Neo Genesis
    ("2002/02/28", "Neo"),                     # Neo Destiny
    ("2002/05/24", "Legendary Collection"),
    ("2002/09/15", "E-Card"),                  # Expedition
    ("2004/11/01", "EX"),                      # EX Team Rocket Returns
    ("2010/02/10", "HeartGold & SoulSilver"),
    ("2016/11/02", "XY"),                      # Evolutions — NOT its own era
    ("2021/10/08", "Sword & Shield"),          # Celebrations — NOT its own era
    ("2024/01/26", "Scarlet & Violet"),        # Paldean Fates
    ("2025/09/26", "Mega Evolution"),
])
def test_date_maps_to_era(date, era):
    assert series_for_date(date) == era


def test_boundaries_are_inclusive_on_the_start():
    # A set released on the exact day an era begins belongs to that new era.
    assert series_for_date("2003/07/01") == "EX"          # Ruby & Sapphire, era start
    assert series_for_date("2003/06/30") == "E-Card"      # the day before


def test_missing_or_pre_history_date_is_none():
    assert series_for_date(None) is None
    assert series_for_date("") is None
    assert series_for_date("1998/01/01") is None          # before Base Set
