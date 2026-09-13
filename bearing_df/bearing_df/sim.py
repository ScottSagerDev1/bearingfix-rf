"""Synthetic HackRF-style IQ for a pseudo-Doppler switched array.

Produces what the HackRF would see with the Opera Cake stepping through the
four elements: a single stream whose carrier phase jumps every dwell.
Supports a clean tone, a noise-like wideband source (stands in for an LTE
uplink), bursty transmission, and a switching transient glitch — all the
things that will bite on real hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import signal

from .array_geom import SquareArray


@dataclass
class SimConfig:
    fs: float = 2e6                 # sample rate (HackRF minimum-ish)
    duration_s: float = 0.02
    freq_hz: float = 830e6          # RF centre used for wavelength
    carrier_offset_hz: float = 37_000.0   # where the target sits in the baseband
    bearing_deg: float = 0.0        # true bearing of the source
    f_rot: float = 8_000.0          # full rotations of the 4-element array per second
    rotation_dir: int = +1          # +1: element 0->1->2->3 (clockwise on the plate)
    snr_db: float = 20.0            # SNR of the target within the capture bandwidth
    source: str = "tone"            # "tone", "wideband" or "prach"
    prach_root: int = 129           # only for "prach"; one preamble per burst_period_s
    prach_center_hz: float = 300e3  # where the 1.08 MHz PRACH block sits in baseband
    source_bw_hz: float = 180e3     # only for "wideband" (one LTE resource block-ish)
    burst: bool = False             # gate the source on/off
    burst_on_s: float = 1e-3        # LTE subframe
    burst_period_s: float = 5e-3
    switch_glitch: float = 0.0      # amplitude of a broadband spike at each switch edge
    freq_drift_hz_per_s: float = 0.0   # slow carrier drift (oscillator)
    seed: int | None = 0


def switching_index(n: np.ndarray, fs: float, f_rot: float, n_el: int = 4,
                    rotation_dir: int = +1, offset_samples: int = 0) -> np.ndarray:
    """Which element is selected at sample n. Element 0 starts at sample
    ``offset_samples``; dwell = fs / (n_el * f_rot) samples."""
    dwell = fs / (n_el * f_rot)
    k = np.floor((n - offset_samples) / dwell).astype(np.int64)
    if rotation_dir < 0:
        k = -k
    return np.mod(k, n_el)


def simulate(cfg: SimConfig, array: SquareArray, switch_offset_samples: int = 0):
    """Return (iq, meta). ``iq`` is complex64 baseband."""
    rng = np.random.default_rng(cfg.seed)
    n = np.arange(int(cfg.fs * cfg.duration_s))
    t = n / cfg.fs

    # --- source waveform ---------------------------------------------------
    if cfg.source == "tone":
        src = np.ones_like(t, dtype=complex)
    elif cfg.source == "wideband":
        # complex Gaussian noise band-limited to source_bw_hz: looks like SC-FDMA
        w = rng.standard_normal(len(t)) + 1j * rng.standard_normal(len(t))
        taps = signal.firwin(255, cfg.source_bw_hz / 2, fs=cfg.fs)
        src = signal.fftconvolve(w, taps, mode="same")
        src /= np.sqrt(np.mean(np.abs(src) ** 2))
    elif cfg.source == "prach":
        from .prach import generate_prach
        p = generate_prach(cfg.prach_root, cfg.fs, center_hz=0.0)   # centred; offset applied below
        src = np.zeros(len(t), dtype=complex)
        per = int(cfg.fs * cfg.burst_period_s)
        for s0 in range(0, len(t) - len(p), per):
            src[s0:s0 + len(p)] = p
    else:
        raise ValueError(cfg.source)

    if cfg.source == "prach":
        # carrier_offset_hz is ignored for prach; the block is placed at prach_center_hz
        src = src * np.exp(1j * 2 * np.pi * cfg.prach_center_hz * t)
        t_off = 0.0
    else:
        t_off = cfg.carrier_offset_hz

    phase_drift = np.pi * cfg.freq_drift_hz_per_s * t ** 2
    src = src * np.exp(1j * (2 * np.pi * t_off * t + phase_drift))

    if cfg.burst and cfg.source != "prach":
        mask = (np.mod(t, cfg.burst_period_s) < cfg.burst_on_s).astype(float)
        src = src * mask

    # --- element switching -------------------------------------------------
    k = switching_index(n, cfg.fs, cfg.f_rot, array.n_elements, cfg.rotation_dir,
                        switch_offset_samples)
    el_phase = array.element_phases(cfg.bearing_deg, cfg.freq_hz)
    x = src * np.exp(1j * el_phase[k])

    if cfg.switch_glitch > 0:
        edges = np.flatnonzero(np.diff(k) != 0) + 1
        g = np.zeros_like(x)
        g[edges] = cfg.switch_glitch * (rng.standard_normal(len(edges))
                                        + 1j * rng.standard_normal(len(edges)))
        x = x + g

    # --- noise ---------------------------------------------------------------
    sig_p = np.mean(np.abs(x) ** 2) if not (cfg.burst or cfg.source == "prach") else 1.0
    noise_p = sig_p / (10 ** (cfg.snr_db / 10))
    noise = np.sqrt(noise_p / 2) * (rng.standard_normal(len(t)) + 1j * rng.standard_normal(len(t)))
    iq = (x + noise).astype(np.complex64)

    meta = {"fs": cfg.fs, "f_rot": cfg.f_rot, "bearing_deg": cfg.bearing_deg,
            "carrier_offset_hz": cfg.carrier_offset_hz, "switch_offset_samples": switch_offset_samples,
            "rotation_dir": cfg.rotation_dir}
    return iq, meta


def to_hackrf_int8(iq: np.ndarray, scale: float = 100.0) -> np.ndarray:
    """Pack complex IQ as interleaved int8 the way hackrf_transfer writes it."""
    out = np.empty(2 * len(iq), dtype=np.int8)
    out[0::2] = np.clip(np.round(iq.real * scale), -127, 127)
    out[1::2] = np.clip(np.round(iq.imag * scale), -127, 127)
    return out
