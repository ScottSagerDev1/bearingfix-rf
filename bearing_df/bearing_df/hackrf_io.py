"""HackRF Pro + Opera Cake glue.

Uses the stock host tools (``hackrf_transfer``, ``hackrf_operacake``) via
subprocess so nothing here needs a compiled binding. All of it is untested
against real hardware until the radio arrives — every command line below is
built from the hackrf host-tools documentation and MUST be checked against
``hackrf_transfer -h`` / ``hackrf_operacake -h`` on the machine that has the
radio plugged in. Where I was not sure of a flag I say so.

Switch timing on real hardware
------------------------------
Opera Cake "time" mode steps ports on a dwell counted in HackRF samples,
driven by the HackRF's own sample clock. Whether the counter restarts at
the moment ``hackrf_transfer`` starts streaming determines whether
``DFConfig.switch_start_sample`` can be a fixed constant (good: absolute
bearing after one calibration) or must be recovered per capture with
``dsp.estimate_switch_timing`` (bearing then ambiguous by 90 deg multiples
until calibrated). Test this FIRST with a tone at a known bearing: run three
separate captures and see whether the raw ``angle(L)`` is the same each time.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
import numpy as np


def read_iq_int8(path: str, max_samples: int | None = None, offset_samples: int = 0) -> np.ndarray:
    """Read interleaved int8 IQ as written by hackrf_transfer -r."""
    count = -1 if max_samples is None else 2 * max_samples
    raw = np.fromfile(path, dtype=np.int8, count=count, offset=2 * offset_samples)
    raw = raw[: (len(raw) // 2) * 2]
    return (raw[0::2].astype(np.float32) + 1j * raw[1::2].astype(np.float32)) / 128.0


def write_iq_int8(path: str, iq: np.ndarray, scale: float = 100.0) -> None:
    out = np.empty(2 * len(iq), dtype=np.int8)
    out[0::2] = np.clip(np.round(iq.real * scale), -127, 127)
    out[1::2] = np.clip(np.round(iq.imag * scale), -127, 127)
    out.tofile(path)


@dataclass
class HackRFSettings:
    freq_hz: float = 830e6        # centre frequency. Cellular uplink: 600-850 MHz region
    fs: float = 2e6               # HackRF supports 2-20 Msps; 2 MSPS keeps files small
    lna_db: int = 32              # 0-40 in 8 dB steps
    vga_db: int = 20              # 0-62 in 2 dB steps
    amp: bool = False             # front-end amp; leave off until you know the levels
    bandwidth_hz: float | None = None   # baseband filter; None = auto


def tools_present() -> dict:
    return {t: shutil.which(t) is not None for t in ("hackrf_info", "hackrf_transfer", "hackrf_operacake")}


def capture(path: str, settings: HackRFSettings, n_samples: int, timeout_s: float = 30) -> str:
    """Record ``n_samples`` to ``path`` with hackrf_transfer. Returns path."""
    if shutil.which("hackrf_transfer") is None:
        raise RuntimeError("hackrf_transfer not found; install hackrf host tools")
    cmd = ["hackrf_transfer", "-r", path,
           "-f", str(int(settings.freq_hz)),
           "-s", str(int(settings.fs)),
           "-l", str(settings.lna_db),
           "-g", str(settings.vga_db),
           "-n", str(int(n_samples))]
    if settings.amp:
        cmd += ["-a", "1"]
    if settings.bandwidth_hz:
        cmd += ["-b", str(int(settings.bandwidth_hz))]
    subprocess.run(cmd, check=True, timeout=timeout_s, capture_output=True)
    return path


def operacake_time_mode(dwell_samples: int, ports: tuple[str, ...] = ("B1", "B2", "B3", "B4"),
                        board: int = 0) -> list[str]:
    """Configure the Opera Cake to step through ``ports`` every ``dwell_samples``.

    dwell_samples = fs / (4 * f_rot). For fs = 2 MSPS and f_rot = 8 kHz that
    is 62.5 -> use 62 or 63 and set DFConfig.f_rot to fs / (4 * dwell) so the
    lock-in reference matches exactly.

    FLAGS ARE FROM MEMORY OF THE hackrf_operacake DOCS — VERIFY WITH -h.
    Expected shape: hackrf_operacake -o <board> -m time -w <dwell> -T <A0port>[,<B0port>] ...
    The returned list is the argv actually run so it can be printed/edited.
    """
    if shutil.which("hackrf_operacake") is None:
        raise RuntimeError("hackrf_operacake not found; install hackrf host tools")
    cmd = ["hackrf_operacake", "-o", str(board), "-m", "time", "-w", str(int(dwell_samples))]
    for p in ports:
        cmd += ["-T", p]   # UNVERIFIED: check whether -T takes 'A0port' or 'A0port,B0port'
    subprocess.run(cmd, check=True, capture_output=True)
    return cmd


def operacake_manual(port: str = "B1", board: int = 0) -> list[str]:
    """Park the switch on one element (for spectrum checks in GQRX)."""
    cmd = ["hackrf_operacake", "-o", str(board), "-m", "manual", "-a", port]  # UNVERIFIED flag names
    subprocess.run(cmd, check=True, capture_output=True)
    return cmd


def exact_rotation_rate(fs: float, dwell_samples: int, n_el: int = 4) -> float:
    return fs / (n_el * dwell_samples)
