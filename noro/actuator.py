"""Actuators: deliver the physical 'nudge'."""

from __future__ import annotations

import abc
import logging
import time

logger = logging.getLogger(__name__)


class BaseActuator(abc.ABC):
    """Fires one physical pulse."""

    @abc.abstractmethod
    def fire(self, duration_s: float) -> None:
        ...

    def close(self) -> None:
        pass


class StubActuator(BaseActuator):
    """No hardware: just logs the pulse. Used for development on the Mac."""

    def fire(self, duration_s: float) -> None:
        logger.warning("PULSE %.0f ms (stub actuator)", duration_s * 1000.0)


class GpioPulseActuator(BaseActuator):
    """Drives a GPIO pin HIGH for `duration_s` (Raspberry Pi only).

    IMPORTANT: a GPIO pin sources at most ~16 mA at 3.3 V. NEVER wire a
    solenoid or motor directly to it. Use the pin to switch a logic-level
    N-channel MOSFET (IRLZ44N, AO3400, ...) with a flyback diode across the
    load and a separate supply for the load:

        GPIO17 --100R--+  gate
                      10k to GND (pull-down)
        +Vload -- solenoid/vibrator -- drain
        source -- GND (shared with the Pi)
        flyback diode (1N4007) across the load, cathode to +Vload
    """

    def __init__(self, pin: int = 17, active_high: bool = True) -> None:
        try:
            from gpiozero import OutputDevice
        except ImportError as exc:  # pragma: no cover - Mac / non-Pi
            raise RuntimeError(
                "gpiozero is not available (expected on the Mac). "
                "Run on the Pi, or pass --actuator stub."
            ) from exc
        self._device = OutputDevice(
            pin=pin, active_high=active_high, initial_value=False
        )

    def fire(self, duration_s: float) -> None:
        self._device.on()
        try:
            time.sleep(duration_s)
        finally:
            self._device.off()

    def close(self) -> None:
        self._device.close()
