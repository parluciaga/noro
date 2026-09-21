# Wiring the nudge driver (vibrator / small solenoid)

A beginner-friendly guide to the one piece of electronics this project
needs: turning a GPIO pin into a motor-safe pulse output. Assumes the
recommended architecture (12 V brick -> IR panel; buck to 5 V for the Pi);
the simpler all-5 V variant is at the bottom.

## Why you can't just wire the motor to the Pi

A GPIO pin is a *logic signal*, not a power output: 3.3 V, ~16 mA max per
pin, ~50 mA for the whole GPIO bank. A vibration motor wants 5 V at
100-200 mA - about ten times the current, at the wrong voltage. Direct
connection kills the pin. The fix is standard electronics: let the small
signal control a switch that handles the big current.

## The switch: MOSFET (or an NPN from your Arduino kit)

A MOSFET is a voltage-controlled switch with three pins:

| Pin | Name | Connect to |
|---|---|---|
| G | gate | Pi GPIO17 (through 220 ohm) - the "handle" |
| D | drain | the motor's minus wire |
| S | source | common ground |

Gate at 0 V = switch open = motor off. Gate at 3.3 V = switch closed =
motor runs. **Buy a "logic-level" part** - fully on already at 3.3 V:
IRLZ44N, IRLB8721, AO3400. Avoid plain IRF520/IRF540 (they want 5-10 V on
the gate and only half-turn-on with a Pi).

An NPN transistor (2N2222, in most Arduino kits) works too for a small
motor: base through 1 kohm to GPIO17, emitter to ground, collector to the
motor's minus wire.

Easiest of all: a "vibration motor module" with the driver already on the
board (3 pins: VCC / GND / SIG). Then this whole document reduces to
VCC -> 5 V, GND -> GND, SIG -> GPIO17.

## The flyback diode: the spike absorber

A motor is a coil, and coils fight sudden stops: the instant the switch
opens, the collapsing magnetic field produces a brief spike of tens of
volts. That spike punches through the transistor and, over time, the Pi.
A 1N4007 wired *backwards* across the motor gives that energy a harmless
loop to circulate in:

- cathode (end with the printed band) -> the motor's + side (supply side)
- anode -> the motor's - side (switch side)

It costs cents and saves the driver. Never omit it for any motor/solenoid.

## Connection table (MOSFET version)

| From | To |
|---|---|
| Motor + | +5 V rail (from the buck or 5 V PSU) |
| Motor - | MOSFET drain (D) |
| MOSFET source (S) | common ground |
| MOSFET gate (G) | one leg of the 220 ohm |
| 220 ohm, other leg | Pi **GPIO17** (physical pin 11) |
| 10 kohm | gate <-> ground (pull-down) |
| 1N4007, band end | +5 V side of the motor |
| 1N4007, other end | motor - / drain side |
| Pi GND (physical pin 6) | common ground |

The 10k pull-down keeps the motor silent while the Pi boots (GPIO pins
float until software takes over).

NPN version: replace the MOSFET rows with collector -> motor -, emitter ->
ground, base -> 1 kohm -> GPIO17, 10 kohm base <-> ground.

## The rest of the system

```
12 V / 2 A PSU -+- IR panel (+ and -)                     (always on)
                +- buck converter (12 V -> 5 V) -> Pi micro-USB
                +- [only for a 12 V actuator] the same MOSFET circuit
                   switching the 12 V rail instead of the 5 V one
```

All grounds are common: PSU minus, buck minus, Pi GND, MOSFET source.
If the IR panel is a small 5 V USB type, skip the 12 V brick: one 5 V / 3 A
supply split before the Pi feeds panel, motor (via the driver), and Pi.

## Bench tests (no camera, no model needed)

```bash
cd ~/git/noro
# 1) hold the pin high for 2 s - the motor should buzz the whole time
.venv/bin/python -c "import time; from gpiozero import OutputDevice; d=OutputDevice(17); d.on(); time.sleep(2); d.off()"

# 2) through noro's real trigger path (mock detector drives the pulses)
.venv/bin/noro --source synthetic --detector mock --actuator gpio \
    --hold-time 0.2 --interval 0.2 --cooldown 2 --max-frames 30
# expect ~3 short buzzes over ~6 s
```

## Pre-flight checklist before an overnight run

- [ ] Buck converter output measured **5.0-5.1 V with a multimeter before
      the Pi was ever connected** (adjustable modules ship at random voltages)
- [ ] All grounds tied together (Pi GND <-> supply minus)
- [ ] Flyback diode fitted (unless using a module with it onboard)
- [ ] 10k pull-down fitted; motor stays silent through a reboot
- [ ] `vcgencmd get_throttled` prints `throttled=0x0` with everything running
- [ ] Bench prototype on a breadboard is fine; final install uses screw
      terminals or solder