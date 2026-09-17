"""Burst detection and per-burst bearing.

A phone with no bars transmits in short bursts (LTE uplink ~1 ms subframes,
PRACH attempts, BLE advertisements). Each burst contains many array
rotations (1 ms at f_rot = 8 kHz is 8 rotations, 32 edges), so one burst
yields one bearing; bursts are then accumulated in ``tracker``.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import signal

from .dsp import DFConfig, BearingEstimate, estimate_bearing, estimate_carrier, slice_baseband


@dataclass
class Burst:
    start: int          # sample index
    stop: int           # exclusive
    peak_db: float
    mean_db: float

    @property
    def n(self) -> int:
        return self.stop - self.start


def smoothed_power_db(x: np.ndarray, fs: float, window_s: float = 50e-6) -> np.ndarray:
    w = max(int(fs * window_s), 1)
    p = signal.fftconvolve(np.abs(x) ** 2, np.ones(w) / w, mode="same")
    return 10 * np.log10(p + 1e-20)


def detect_bursts(x: np.ndarray, fs: float, threshold_db: float = 5.0,
                  min_len_s: float = 250e-6, gap_s: float = 250e-6,
                  window_s: float = 150e-6) -> tuple[list[Burst], float]:
    """Energy detector. Noise floor = median of smoothed power (assumes the
    target is on for less than half the capture). Returns (bursts, floor_db)."""
    p = smoothed_power_db(x, fs, window_s)
    floor = float(np.median(p))
    on = p > floor + threshold_db
    # close small gaps
    gap = max(int(fs * gap_s), 1)
    on = signal.fftconvolve(on.astype(float), np.ones(gap), mode="same") > 0.5
    # find runs
    d = np.diff(np.concatenate([[0], on.astype(int), [0]]))
    starts = np.flatnonzero(d == 1)
    stops = np.flatnonzero(d == -1)
    min_len = int(fs * min_len_s)
    bursts = []
    for s, e in zip(starts, stops):
        if e - s >= min_len:
            seg = p[s:e]
            bursts.append(Burst(int(s), int(e), float(seg.max()), float(seg.mean())))
    return bursts, floor


def bearings_from_bursts(iq: np.ndarray, cfg: DFConfig, threshold_db: float = 5.0,
                         carrier_hz: float | None = None, guard_s: float = 30e-6):
    """Detect bursts in a capture and estimate a bearing for each.

    The carrier is found once over the whole capture (bursts average up in
    the spectrum even when individually short), the capture is sliced once,
    bursts are found in the sliced signal, and each burst is fed to the
    estimator with its own switch-phase origin preserved.
    Returns list of (Burst, BearingEstimate).
    """
    if carrier_hz is None:
        carrier_hz, _ = estimate_carrier(iq, cfg.fs, band=cfg.carrier_band)
    x = slice_baseband(iq, cfg.fs, carrier_hz, cfg.slice_bw, cfg.numtaps)
    bursts, floor = detect_bursts(x, cfg.fs, threshold_db)
    guard = int(cfg.fs * guard_s)
    out = []
    for b in bursts:
        s, e = b.start + guard, b.stop - guard
        if e - s < int(2 * cfg.fs / cfg.f_rot):     # need >= 2 rotations
            continue
        seg = iq[s:e]
        # keep the switch-phase origin consistent with the full capture
        sub = DFConfig(**{**cfg.__dict__})
        if cfg.switch_start_sample is not None:
            sub.switch_start_sample = cfg.switch_start_sample - s
        sub.block_rotations = max(2, min(cfg.block_rotations, (e - s) // int(cfg.fs / cfg.f_rot) // 3))
        est = estimate_bearing(seg, sub, carrier_hz=carrier_hz)
        est.detail["burst"] = b
        est.detail["floor_db"] = floor
        out.append((b, est))
    return out


def bearings_from_prach(iq: np.ndarray, cfg: DFConfig, detector, slice_bw: float = 64e3,
                        refine: bool = False):
    """Coherent path for a no-bars phone: detect PRACH preambles with the
    Zadoff-Chu correlator, despread each one to a tone-like signal, then run
    the DF chain with a narrow slice. In simulation this gives usable
    single-burst bearings down to about -10 dB SNR in 2 MHz, where the energy
    detector cannot even see the burst. Returns list of (PRACHDetection,
    BearingEstimate)."""
    from .prach import despread, T_SEQ
    n_seq = int(round(cfg.fs * T_SEQ))
    out = []
    for h in detector.detect(iq):
        if refine:
            detector.refine_start(iq, h)
        seg = iq[h.start:h.start + n_seq]
        if len(seg) < n_seq:
            continue
        z = despread(seg, h, cfg.fs)
        sub = DFConfig(**{**cfg.__dict__})
        sub.slice_bw = slice_bw
        sub.block_rotations = 2
        if cfg.switch_start_sample is not None:
            sub.switch_start_sample = cfg.switch_start_sample - h.start
        est = estimate_bearing(z, sub)
        est.detail["prach"] = h
        out.append((h, est))
    return out
