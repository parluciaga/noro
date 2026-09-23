# noro — positional-snoring watchdog

A Raspberry Pi 3 + NoIR camera watches you sleep and fires a short pulse
(solenoid or vibration motor) whenever you have been lying on your **back**
for more than ~2 seconds — so you roll onto your side and stop snoring.

> **Not a medical device.** If you suspect sleep apnoea, see a doctor.
> Positional therapy is a recognised adjunct, not a substitute for diagnosis.

## How it works

1. The NoIR camera + an **850 nm IR illuminator** see the bed in the dark (~1 fps).
2. A tiny TFLite image classifier (trained on *your own bed*) labels each
   frame `supine` / `side` / `empty`.
3. A timestamp-based state machine fires when you are supine ≥ 2 s
   (`--hold-time`), re-firing every `--cooldown` s while you stay on your back.
4. A GPIO pin pulses a MOSFET-driven solenoid/vibrator.

## Hardware

- Raspberry Pi 3 + **Pi NoIR Camera Module v2** (CSI ribbon; enable the
  camera interface with `sudo raspi-config`)
- **850 nm IR illuminator** (a few dollars; 850 nm LEDs have a faint red
  glow — hide the panel behind something, or use 940 nm, which is fully
  invisible but the sensor is less sensitive to it)
- Actuator: a **vibration motor** (recommended — gentle, like commercial
  positional-therapy devices) or a small solenoid
- Driver: logic-level N-MOSFET (IRLZ44N / AO3400) + **flyback diode**
  (1N4007) across the load + separate 5/12 V supply. **Never wire an
  inductive load directly to a GPIO pin** (~16 mA max).

```
GPIO17 --100R--+  MOSFET gate
              10k to GND (pull-down)
+Vload -- solenoid/vibrator -- MOSFET drain
MOSFET source -- GND (shared with the Pi)
1N4007 across the load (cathode to +Vload)
```

Full driver wiring guide — parts, connection tables, bench tests:
**[docs/wiring.md](docs/wiring.md)**

- Mount the camera **overhead**, looking straight down at the bed: supine
  vs. side is far easier to separate from above.

## Repository layout

```
noro/            the app package (config, camera, detector, trigger, actuator, main)
tools/           capture_night.py (Pi), label_frames.py (Mac), train_classifier.py (Mac)
tests/           unit + end-to-end tests, runnable anywhere
deploy/          systemd service file
models/          model.tflite + labels.txt after training (not committed)
captures/        recorded nights (not committed)
dataset/         labeled frames (not committed)
```

## Development workflow (Mac ↔ Pi)

Develop on the Mac with **VS Code Remote-SSH** into the Pi: full editor UX,
while the code runs against the real camera and GPIO. Hardware access
(picamera2, gpiozero) sits behind small interfaces, so everything except
real capture/pulse runs on the Mac too.

**On the Mac:**

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

**On the Pi** (Raspberry Pi OS, camera interface enabled; prefer the **64-bit** OS — see the Trixie note below):

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-numpy python3-pillow
cd ~/git/noro
# Use /usr/bin/python3 explicitly: a bare `python3` can resolve to a
# different interpreter, and the venv must be built by the same Python
# that apt compiled picamera2's libcamera bindings for.
/usr/bin/python3 -m venv --system-site-packages .venv   # sees the apt packages
.venv/bin/python -c "import picamera2; print('tripwire OK:', picamera2.__file__)"
.venv/bin/pip install -r requirements-pi.txt   # picks tflite-runtime (Py<=3.11) or ai-edge-litert (Py>=3.12) automatically
.venv/bin/pip install -e .
.venv/bin/noro --help
```

Trixie note: Raspberry Pi OS Trixie ships Python 3.13, where the old
`tflite-runtime` has no wheels. `requirements-pi.txt` installs its official
successor `ai-edge-litert` instead via Python-version markers (aarch64
wheels only, hence the 64-bit preference; `noro/detector.py` handles both
runtimes transparently).

## The 4-step data loop (do this before trusting it at night)

1. **Capture a night** (Pi): `python tools/capture_night.py --out captures/night1`
   (~1 GB/night at 640×480 every 2 s). If frames come out black, fix the IR
   illuminator first — the tool warns you.
2. **Label** (Mac, after `scp`/rsync the folder over):
   `python tools/label_frames.py --captures captures/night1 --dataset dataset`
   Keys: `b`=back/supine, `s`=side, `e`=empty bed, space=skip, q=quit.
3. **Train** (Mac): `pip install -e ".[train]" && python tools/train_classifier.py`
   Writes `models/model.tflite` + `models/labels.txt`; copy both to the Pi's
   `models/` directory.
4. **Run** (Pi): `noro --source pi --detector tflite --actuator gpio --log-dir logs`

Repeat 1–3 for another night or two until you like the accuracy, then
install the service:

```bash
sudo cp deploy/noro.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now noro
journalctl -u noro -f          # watch it
```

## No-hardware demo (Mac)

```bash
.venv/bin/noro --source synthetic --detector mock --actuator stub \
    --hold-time 0.3 --interval 0.05 --cooldown 0.5 --max-frames 40 --log-dir /tmp/noro-demo
```

You should see `>>> SUPINE ... PULSE` warnings and a timeline CSV under
`/tmp/noro-demo`. You can also replay a labeled night:
`noro --source files --frames-dir captures/night1 --interval 1`.

## Tuning

| flag | default | meaning |
|---|---|---|
| `--hold-time` | 2.0 | supine seconds before the first pulse |
| `--cooldown` | 10 | min seconds between pulses (re-nudges while you stay supine) |
| `--pulse-width` | 0.2 | pulse length (s) |
| `--pin` | 17 | BCM GPIO pin driving the MOSFET |
| `--interval` | 1.0 | seconds between analysed frames |
| `--confidence` | 0.70 | below this a frame counts as UNKNOWN (resets the streak after `--unknown-grace`) |
| `--exposure-us` / `--gain` | 100000 / 12 | fixed night exposure; tune for your IR illuminator |

## Safety & sanity

- Start with a **vibration motor** before any solenoid poking; keep pulses gentle.
- Test the whole chain while awake for a few nights (`--log-dir` CSVs show
  exactly what it saw) before sleeping with the actuator connected.
- IR illuminator: place it away from eye level. 850 nm LED panels are safe;
  never point IR *lasers* at the bed.
- All images stay on your devices; nothing leaves the LAN.

## Tests

```bash
.venv/bin/pytest -q
```

The trigger unit tests are the specification for the "2-second rule":
fires at exactly 2 s of continuous supine, resets on side, tolerates brief
UNKNOWN flicker, re-nudges on cooldown.

