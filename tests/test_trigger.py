"""Unit tests for the 2-second supine trigger - the heart of the app."""

from noro.detector import BodyPosition
from noro.trigger import SupineTrigger

SUPINE = BodyPosition.SUPINE
SIDE = BodyPosition.SIDE
UNKNOWN = BodyPosition.UNKNOWN


def test_no_fire_before_hold_time():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None)
    assert t.update(SUPINE, timestamp=0.0) is False
    assert t.update(SUPINE, timestamp=1.0) is False
    assert t.update(SUPINE, timestamp=1.999) is False


def test_fires_exactly_at_hold_time():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None)
    assert t.update(SUPINE, timestamp=10.0) is False   # streak starts here
    assert t.update(SUPINE, timestamp=11.0) is False
    assert t.update(SUPINE, timestamp=12.0) is True    # 2.0 s reached


def test_side_resets_the_streak():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None)
    assert t.update(SUPINE, timestamp=0.0) is False
    assert t.update(SUPINE, timestamp=1.0) is False
    assert t.update(SIDE, timestamp=1.5) is False      # rolled over -> reset
    assert t.update(SUPINE, timestamp=2.0) is False    # new streak
    assert t.update(SUPINE, timestamp=3.0) is False
    assert t.update(SUPINE, timestamp=4.0) is True     # 2 s from the new start


def test_side_resets_even_within_unknown_grace():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None, unknown_grace_s=0.5)
    t.update(SUPINE, timestamp=0.0)
    t.update(SUPINE, timestamp=1.0)
    assert t.update(SIDE, timestamp=1.2) is False      # SIDE always resets
    assert t.update(SUPINE, timestamp=2.0) is False
    assert t.update(SUPINE, timestamp=3.0) is False
    assert t.update(SUPINE, timestamp=4.0) is True


def test_brief_unknown_keeps_streak_alive():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None, unknown_grace_s=0.5)
    assert t.update(SUPINE, timestamp=0.0) is False
    assert t.update(SUPINE, timestamp=1.0) is False
    assert t.update(UNKNOWN, timestamp=1.3) is False   # flicker, within grace
    assert t.update(SUPINE, timestamp=1.8) is False
    assert t.update(SUPINE, timestamp=2.8) is True     # streak survived the blip


def test_prolonged_unknown_resets_streak():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None, unknown_grace_s=0.5)
    t.update(SUPINE, timestamp=0.0)
    t.update(SUPINE, timestamp=1.0)
    t.update(UNKNOWN, timestamp=1.8)                  # gap > grace -> reset
    assert t.update(SUPINE, timestamp=2.0) is False
    assert t.update(SUPINE, timestamp=3.0) is False
    assert t.update(SUPINE, timestamp=4.0) is True


def test_cooldown_limits_pulse_rate_while_supine():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=3.0)
    assert t.update(SUPINE, timestamp=0.0) is False
    assert t.update(SUPINE, timestamp=1.0) is False
    assert t.update(SUPINE, timestamp=2.0) is True     # fire #1
    assert t.update(SUPINE, timestamp=3.0) is False   # only 1 s since fire
    assert t.update(SUPINE, timestamp=4.0) is False   # only 2 s since fire
    assert t.update(SUPINE, timestamp=5.0) is True    # 3 s since fire -> re-nudge


def test_no_cooldown_fires_once_per_streak():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None)
    assert t.update(SUPINE, timestamp=0.0) is False
    assert t.update(SUPINE, timestamp=2.0) is True
    assert t.update(SUPINE, timestamp=10.0) is False   # already fired this streak
    assert t.update(SUPINE, timestamp=100.0) is False


def test_new_streak_can_fire_again_after_cooldown_none():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None)
    t.update(SUPINE, timestamp=0.0)
    t.update(SUPINE, timestamp=2.0)                    # fired
    t.update(SIDE, timestamp=3.0)                      # moved
    assert t.update(SUPINE, timestamp=4.0) is False
    assert t.update(SUPINE, timestamp=6.0) is True     # fresh streak -> fires again


def test_unknown_without_prior_streak_is_ignored():
    t = SupineTrigger(hold_time_s=2.0, cooldown_s=None)
    assert t.update(UNKNOWN, timestamp=0.0) is False
    assert t.update(UNKNOWN, timestamp=5.0) is False
    assert t.update(SUPINE, timestamp=6.0) is False
    assert t.update(SUPINE, timestamp=8.0) is True
