"""End-to-end dry run: source -> detector -> trigger -> stub actuator.

This exercises main() exactly as on the Pi, but with the mock detector and
the stub actuator, so it validates all the wiring without hardware.
"""

import csv
import logging

from noro.main import main


def test_dry_run_end_to_end(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    log_dir = tmp_path / "logs"

    rc = main(
        [
            "--source", "synthetic",
            "--detector", "mock",
            "--actuator", "stub",
            "--interval", "0.05",
            "--hold-time", "0.2",
            "--cooldown", "0.3",
            "--max-frames", "40",
            "--log-dir", str(log_dir),
        ]
    )

    assert rc == 0
    # the stub actuator logged real pulse events
    assert "PULSE" in caplog.text
    assert ">>> SUPINE" in caplog.text

    # the timeline CSV recorded every frame and the fires
    csvs = list(log_dir.glob("timeline_*.csv"))
    assert len(csvs) == 1
    with csvs[0].open() as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["wall_time", "monotonic_s", "position", "confidence", "fired"]
    assert len(rows) == 41  # header + 40 frames

    fires = sum(1 for r in rows[1:] if r[4] == "1")
    assert 3 <= fires <= 4  # one per mock supine stretch (7 frames x 0.05s)

    positions = {r[2] for r in rows[1:]}
    assert positions == {"supine", "side"}


def test_missing_frames_dir_is_a_clean_error(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    rc = main(["--source", "files", "--actuator", "stub", "--detector", "mock"])
    assert rc == 2
    assert "frames-dir" in caplog.text


def test_gpio_actuator_on_dev_machine_gives_clean_error(caplog):
    import pytest

    try:
        import gpiozero  # noqa: F401

        pytest.skip("gpiozero is installed (running on the Pi)")
    except ImportError:
        pass

    caplog.set_level(logging.INFO)
    rc = main(
        [
            "--source", "synthetic",
            "--detector", "mock",
            "--actuator", "gpio",   # no gpiozero on a dev machine
            "--max-frames", "1",
        ]
    )
    assert rc == 2
    assert "gpiozero" in caplog.text
