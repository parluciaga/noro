"""The supine-watchdog state machine (pure logic, no hardware deps).

Fires a pulse event when the sleeper has been continuously SUPINE for at
least `hold_time_s` (2 s by default). Timing is based on frame timestamps
(time.monotonic), never on frame counts, so behaviour is independent of the
camera frame rate.
"""

from __future__ import annotations

from typing import Optional

from .detector import BodyPosition


class SupineTrigger:
    def __init__(
        self,
        hold_time_s: float = 2.0,
        cooldown_s: Optional[float] = 10.0,
        unknown_grace_s: float = 0.5,
    ) -> None:
        self.hold_time_s = hold_time_s
        self.cooldown_s = cooldown_s
        self.unknown_grace_s = unknown_grace_s
        self._streak_start: Optional[float] = None
        self._last_supine_ts: Optional[float] = None
        self._last_fire_ts: Optional[float] = None
        self._fired_this_streak = False

    def update(self, position: BodyPosition, timestamp: float) -> bool:
        """Feed one classified frame; returns True when a pulse should fire.

        - SUPINE: starts/keeps a streak; fires once the streak is older than
          hold_time_s, then re-fires at most every cooldown_s while the
          sleeper stays supine (so the nudge repeats until they roll over).
        - SIDE: immediately resets the streak.
        - UNKNOWN: tolerated for up to unknown_grace_s inside an ongoing
          streak (classifier flicker); longer, or outside a streak, resets.
        """
        fired = False
        if position is BodyPosition.SUPINE:
            if self._streak_start is None:
                self._streak_start = timestamp
                self._fired_this_streak = False
            self._last_supine_ts = timestamp
            if (
                timestamp - self._streak_start >= self.hold_time_s
                and self._may_fire(timestamp)
            ):
                self._last_fire_ts = timestamp
                self._fired_this_streak = True
                fired = True
        else:
            if not self._tolerate_unknown(position, timestamp):
                self._reset()
        return fired

    def _may_fire(self, timestamp: float) -> bool:
        if self.cooldown_s is None:
            return not self._fired_this_streak
        return (
            self._last_fire_ts is None
            or timestamp - self._last_fire_ts >= self.cooldown_s
        )

    def _tolerate_unknown(self, position: BodyPosition, timestamp: float) -> bool:
        """A brief UNKNOWN blip must not reset an ongoing supine streak."""
        return (
            position is BodyPosition.UNKNOWN
            and self._streak_start is not None
            and self._last_supine_ts is not None
            and timestamp - self._last_supine_ts <= self.unknown_grace_s
        )

    def _reset(self) -> None:
        self._streak_start = None
        self._last_supine_ts = None
        self._fired_this_streak = False
