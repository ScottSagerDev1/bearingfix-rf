"""The peak-hold lesson as a test: a bursty signal is obvious in peak mode
and nearly invisible in average mode."""
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from power_meter import window_levels          # noqa: E402

RATE = 2_000_000
SECONDS = 2.0


def make_fake(tmp_path):
    out = tmp_path / "fake.iq"
    subprocess.run([sys.executable, str(Path(__file__).with_name("make_fake_iq.py")),
                    "--out", str(out), "--rate", str(RATE), "--seconds", str(SECONDS)], check=True)
    return out.read_bytes()


def halves(levels):
    """Median dBFS of the 'off' half and of the 'on' half."""
    mid = len(levels) // 2
    return float(np.median(levels[:mid])), float(np.median(levels[mid:]))


def test_peak_mode_sees_the_bursts(tmp_path):
    data = make_fake(tmp_path)
    off, on = halves(window_levels(data, RATE, mode="peak"))
    assert on - off >= 12.0, f"peak: on {on:.1f} vs off {off:.1f} dBFS"


def test_average_mode_hides_the_bursts(tmp_path):
    data = make_fake(tmp_path)
    off, on = halves(window_levels(data, RATE, mode="average"))
    assert on - off < 4.0, f"average: on {on:.1f} vs off {off:.1f} dBFS"
