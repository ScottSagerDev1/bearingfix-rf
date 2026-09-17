"""HackRF Pro + Opera Cake glue.

Uses the stock host tools (``hackrf_transfer``, ``hackrf_operacake``) via
subprocess so nothing here needs a compiled binding.

Audited 2026-09-17 against the hackrf host tools, libhackrf and firmware
source at release 2026.01.3 (the first release line that supports HackRF
Pro). Every flag below matches that source. Anything that can only be
settled with the radio plugged in is marked ``UNVERIFIED`` and has a test in
docs/hardware-day-checklist.md.

HackRF Pro vs HackRF One, as far as this file cares
----------------------------------------------------
* Same host tools, same flags, same 2-20 MSPS range, same three RX gain
  stages, same signed 8-bit interleaved IQ file format. In 2026.01.x
  firmware the Pro runs a "legacy" radio mode that behaves like a One; the
  Pro's 16-bit and 4-bit sample modes are not exposed to the host yet.
* Pro tunes 100 kHz-6 GHz (One: 1 MHz-6 GHz). hackrf_transfer still refuses
  < 1 MHz without -F. Irrelevant at 830 MHz.
* Pro has a TCXO, so f_rot drifts less. Nothing here depends on that.
* Opera Cake time mode is compiled for the Pro: firmware operacake_sctimer.c
  has a Praline (= Pro) branch that clocks the switch timer from the Pro's
  SCT_CLK instead of the One's SGPIO clock, and GSG list Opera Cake as a
  compatible add-on. UNVERIFIED: that it actually switches on this Pro. Run
  the GPIO test and the slow-LED test in the checklist before trusting a
  single bearing.

Switch timing on real hardware
------------------------------
Time mode steps port A0 through a list of ports, dwelling a set number of
samples on each, clocked by the sample clock. Firmware facts that matter for
``DFConfig.switch_start_sample``:

* ``transceiver_shutdown`` (runs whenever a transfer stops) clears the switch
  timer's counter and returns the switch to the first listed port. The
  firmware comment says why: "so the HackRF starts capturing with the same
  antenna selected each time." So every ``hackrf_transfer`` run begins with
  the switch on port[0] and the counter at zero.
* ``switch_start_sample`` should therefore be a fixed constant: the latency
  between streaming-enable and the first sample that lands in the file.
  UNVERIFIED: its value, whether it is stable run to run, and whether the
  Pro's FPGA pipeline gives a different number than a One's CPLD. Test:
  three captures of a tone at a known bearing. Same raw angle each time ->
  calibrate once and use a fixed switch_start_sample. Different -> always
  ``--recover-timing`` and accept the 90 degree ambiguity until calibrated.
* Set the dwell plan BEFORE starting hackrf_transfer (a second process can't
  claim the USB interface while one is streaming). It persists until the
  HackRF is reset or unplugged, so once per session is enough.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
import numpy as np


def read_iq_int8(path: str, max_samples: int | None = None, offset_samples: int = 0) -> np.ndarray:
    """Read interleaved signed int8 IQ as written by ``hackrf_transfer -r``.

    Byte order is I, Q, I, Q ... each a signed 8-bit value. Only the -w WAV
    path converts to unsigned; -r writes the raw signed stream.
    """
    # UNVERIFIED: a future release may expose the Pro's 16-bit sample mode
    # and change the -r file format. 2026.01.x writes int8.
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
    freq_hz: float = 830e6        # -f: Pro tunes 100 kHz-6 GHz; tool accepts 1 MHz-6 GHz without -F
    fs: float = 2e6               # -s: tool accepts 2-20 MSPS (default 10)
    # UNVERIFIED: GSG say < 8 MSPS is "not recommended" -- the ADC isn't
    # specified below 8 MHz and the narrowest baseband filter (1.75 MHz)
    # can't stop energy 1-2 MHz off-carrier aliasing into a 2 MSPS capture.
    # At 8 MSPS, dwell 250 gives f_rot = 8000.0 exactly. Checklist step 10
    # compares 2 vs 8 MSPS on the same source.
    lna_db: int = 32              # -l: IF gain 0-40 dB, 8 dB steps (tool warns otherwise)
    vga_db: int = 20              # -g: baseband gain 0-62 dB, 2 dB steps (tool warns otherwise)
    amp: bool = False             # -a 1: RF amp, ~11 dB, on/off. GSG starting point is amp off, 16/16
    bandwidth_hz: float | None = None   # -b: rounded to 1.75/2.5/3.5/5/5.5/6/7/8/9/10/12/14/15/20/24/28 MHz;
                                        # None = tool picks the widest value <= 0.75 * fs


def tools_present() -> dict:
    return {t: shutil.which(t) is not None for t in ("hackrf_info", "hackrf_transfer", "hackrf_operacake")}


def capture(path: str, settings: HackRFSettings, n_samples: int, timeout_s: float = 30) -> str:
    """Record ``n_samples`` to ``path`` with hackrf_transfer. Returns path.

    Flags verified against hackrf_transfer.c (2026.01.3). Configure the Opera
    Cake first; this call holds the device until it exits.
    """
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
    """Configure the Opera Cake to step A0 through ``ports`` every ``dwell_samples``.

    Runs ``hackrf_operacake -o <board> -m time -w <dwell> -t <port> -t <port> ...``
    (verified against hackrf_operacake.c, 2026.01.3). Rules from the tool,
    libhackrf and the docs:

    * ``-t <port[:dwell]>`` names a port for A0; with no ``:dwell`` it uses
      the ``-w`` default. Up to 16 entries. Dwell is in samples at the sample
      clock and must be > 0.
    * Ports are A1-A4 or B1-B4, either side. B0 mirrors A0 on the opposite
      side, so with the array on B1-B4 the HackRF must be cabled to **A0**;
      B0 then walks A1-A4 (leave those open).
    * The cycle starts on the first listed port, and the counter is cleared
      every time a transfer stops (see module docstring).
    * Time mode needs Opera Cake GPIO control, which the firmware disables
      when a PortaPack is attached. ``hackrf_operacake -g`` reports it.
    * Needs firmware USB API >= 0x0105; any 2026.01.x firmware qualifies.

    dwell_samples = fs / (4 * f_rot). For fs = 2 MSPS and f_rot = 8 kHz that
    is 62.5 -> use 62 or 63 and set DFConfig.f_rot to fs / (4 * dwell) so the
    lock-in reference matches exactly. At 8 MSPS, dwell 250 -> 8000.0 Hz.
    The returned list is the argv actually run so it can be printed/edited.
    """
    if shutil.which("hackrf_operacake") is None:
        raise RuntimeError("hackrf_operacake not found; install hackrf host tools")
    cmd = ["hackrf_operacake", "-o", str(board), "-m", "time", "-w", str(int(dwell_samples))]
    for p in ports:
        cmd += ["-t", p]
    subprocess.run(cmd, check=True, capture_output=True)
    return cmd


def operacake_manual(port: str = "B1", board: int = 0) -> list[str]:
    """Park A0 on one element (for spectrum checks in GQRX / SDR++).

    Runs ``hackrf_operacake -o <board> -m manual -a <port>`` (verified). B0 is
    auto-connected to the first port on the other side; A0 and B0 can never
    be on the same side.
    """
    cmd = ["hackrf_operacake", "-o", str(board), "-m", "manual", "-a", port]
    subprocess.run(cmd, check=True, capture_output=True)
    return cmd


def exact_rotation_rate(fs: float, dwell_samples: int, n_el: int = 4) -> float:
    return fs / (n_el * dwell_samples)
