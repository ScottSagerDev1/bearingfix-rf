"""Pseudo-Doppler bearing extraction.

Pipeline (mirrors the arXiv 2003.00386 / Ossmann flowgraph, in numpy):

    IQ -> find strongest narrowband slice -> mix to 0 Hz -> low-pass to
    slice_bw -> FM discriminator -> lock-in at the rotation frequency f_rot
    -> bearing = calibration - angle(lock-in)

Why the FM discriminator: the element switching adds a staircase to the
carrier phase. Its derivative is an impulse train at the switching rate whose
fundamental (at f_rot) carries the bearing. Any carrier offset or slow drift
becomes DC in the discriminator output and the lock-in ignores DC, so an
uncorrected frequency error does NOT bias the bearing. That is the reason not
to compare raw per-element phases.

Why the slice must be WIDE, not narrow: the switching sidebands sit at
+-f_rot, +-2 f_rot, ... around the carrier. A filter narrower than a few
times f_rot removes the very modulation that carries the bearing (this was
measured, not guessed: a 2 kHz slice fails, a 400 kHz slice works). Default
slice_bw is 0.2 * fs. Narrow it only to exclude a neighbouring transmitter.

Why edge-only lock-in: the bearing information lives entirely in the phase
step at each switch instant. The samples between edges add noise and (for a
noise-like LTE-type source) the source's own random phase. Taking only a
short window either side of each edge cut the wideband-source error from
~10 deg to ~2-5 deg at 0 dB SNR in simulation. This needs the switch timing,
which ``estimate_switch_timing`` recovers from the capture itself.

Analytic result (see tests): for a clean tone with element 0 starting at
sample 0 and clockwise switching, bearing = 90 deg - angle(L). Hardware adds
a constant (cable delay, switch phase, filter group delay) which
``Calibration`` measures from one known source. Rotation sense reversed ->
bearing = angle(L) + const instead; that is the ``rotation_dir`` flag.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from scipy import signal


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def wrap_deg(a):
    return np.mod(np.asarray(a, dtype=float), 360.0)


def circ_mean_deg(angles_deg, weights=None):
    a = np.deg2rad(np.asarray(angles_deg, dtype=float))
    w = np.ones_like(a) if weights is None else np.asarray(weights, dtype=float)
    z = np.sum(w * np.exp(1j * a)) / max(np.sum(w), 1e-12)
    return wrap_deg(np.rad2deg(np.angle(z))), float(np.abs(z))  # (mean, resultant length R)


def circ_std_deg(angles_deg, weights=None):
    """Circular standard deviation (deg) from resultant length."""
    _, R = circ_mean_deg(angles_deg, weights)
    R = min(max(R, 1e-9), 1.0)
    return float(np.rad2deg(np.sqrt(-2.0 * np.log(R))))


def estimate_carrier(iq: np.ndarray, fs: float, nfft: int = 1 << 14,
                     exclude_dc_hz: float = 2e3, band: tuple | None = None) -> tuple[float, float]:
    """Frequency (Hz, baseband) and power (dB) of the strongest spectral slice.
    Averages FFT power over the whole capture so a bursty signal still shows.
    ``band`` restricts the search to (f_lo, f_hi)."""
    nfft = min(nfft, len(iq))
    f, p = signal.welch(iq, fs=fs, nperseg=nfft, return_onesided=False, scaling="spectrum")
    f = np.fft.fftshift(f)
    p = np.fft.fftshift(p)
    m = np.abs(f) > exclude_dc_hz          # HackRF DC spur
    if band is not None:
        m &= (f >= band[0]) & (f <= band[1])
    i = np.argmax(np.where(m, p, -np.inf))
    return float(f[i]), float(10 * np.log10(p[i] + 1e-30))


def slice_baseband(iq: np.ndarray, fs: float, f_center: float, bw: float,
                   numtaps: int = 401) -> np.ndarray:
    """Mix ``f_center`` to 0 Hz and low-pass to +-bw/2. No decimation, so the
    rotation-frequency impulses keep their timing."""
    n = np.arange(len(iq))
    x = iq * np.exp(-2j * np.pi * f_center * n / fs)
    taps = signal.firwin(numtaps, bw / 2, fs=fs)
    return signal.fftconvolve(x, taps, mode="same")


def fm_discriminate(x: np.ndarray) -> np.ndarray:
    """Instantaneous frequency proxy: phase step between consecutive samples.
    Output d[n] corresponds to the step from sample n to n+1."""
    d = np.zeros(len(x))
    d[:-1] = np.angle(x[1:] * np.conj(x[:-1]))
    return d


def lockin(d: np.ndarray, fs: float, f_rot: float, start_sample: int = 0,
           weights: np.ndarray | None = None) -> complex:
    """Complex lock-in of ``d`` against the rotation reference, trimmed to a
    whole number of rotation periods so DC and harmonics cancel exactly."""
    period = fs / f_rot
    n_use = int(np.floor(len(d) / period) * period)
    if n_use < period:
        n_use = len(d)
    n = np.arange(n_use) + start_sample + 0.5  # +0.5: d[n] sits between n and n+1
    ref = np.exp(-2j * np.pi * f_rot * n / fs)
    dd = d[:n_use]
    if weights is not None:
        w = weights[:n_use]
        return complex(np.sum(dd * w * ref) / max(np.sum(w), 1e-12))
    return complex(np.mean(dd * ref))


def lockin_noise_floor(d: np.ndarray, fs: float, f_rot: float, n_probe: int = 8) -> float:
    """Typical |lock-in| at frequencies near, but not at, f_rot or its
    harmonics. Used to turn |L| into an SNR-like confidence."""
    probes = f_rot * (1 + np.linspace(0.13, 0.43, n_probe))
    vals = [abs(lockin(d, fs, fp)) for fp in probes]
    return float(np.median(vals) + 1e-12)


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------

@dataclass
class Calibration:
    """bearing = wrap(offset_deg - rotation_dir * angle_deg(L))."""

    offset_deg: float = 90.0
    rotation_dir: int = +1

    def bearing_from_lockin(self, L: complex) -> float:
        return float(wrap_deg(self.offset_deg - self.rotation_dir * np.rad2deg(np.angle(L))))

    @classmethod
    def from_known_source(cls, L: complex, true_bearing_deg: float, rotation_dir: int = +1):
        """One known transmitter at a known bearing fixes the constant."""
        off = true_bearing_deg + rotation_dir * np.rad2deg(np.angle(L))
        return cls(offset_deg=float(wrap_deg(off)), rotation_dir=rotation_dir)


# ---------------------------------------------------------------------------
# edge-only lock-in
# ---------------------------------------------------------------------------

def edge_lockin(x: np.ndarray, fs: float, f_rot: float, switch_start_sample: float,
                window: int = 4, amp_weight: bool = False, n_el: int = 4) -> tuple[complex, int]:
    """Lock-in using only the phase step across each switch edge.

    For each edge, average ``window`` samples before and after, take the phase
    of the product, and correlate with the rotation reference. Returns
    (L, n_edges). ``switch_start_sample`` is where element 0 begins (may be
    fractional). If only an edge position modulo one dwell is known, the
    result is correct up to a multiple of 90 deg.
    """
    dwell = fs / (n_el * f_rot)
    first = np.mod(switch_start_sample, dwell)
    edges = np.arange(first, len(x) - window, dwell)
    edges = edges[edges >= window]
    if len(edges) == 0:
        return 0j, 0
    idx = np.ceil(edges - 1e-9).astype(int)        # first sample of the new element
    # vectorised windows
    before = np.zeros(len(idx), dtype=complex)
    after = np.zeros(len(idx), dtype=complex)
    for m in range(window):
        before += x[idx - 1 - m]
        after += x[idx + m]
    before /= window
    after /= window
    step = np.angle(after * np.conj(before))
    # reference phase is measured from the start of element 0, so the
    # bearing comes out absolute when switch_start_sample is the true start.
    ref = np.exp(-2j * np.pi * f_rot * (idx - 0.5 - switch_start_sample) / fs)
    if amp_weight:
        w = np.abs(before) * np.abs(after)
        w = np.minimum(w, np.percentile(w, 90))    # cap so one loud edge can't dominate
    else:
        w = np.ones(len(idx))
    L = np.sum(w * step * ref) / max(np.sum(w), 1e-12)
    return complex(L), len(idx)


# ---------------------------------------------------------------------------
# main estimator
# ---------------------------------------------------------------------------

@dataclass
class BearingEstimate:
    bearing_deg: float
    sigma_deg: float          # spread across sub-blocks (circular std)
    snr_lockin_db: float      # |L| vs off-frequency floor (full-stream lock-in)
    carrier_hz: float
    lockin: complex
    n_blocks: int
    ok: bool
    detail: dict = field(default_factory=dict)


@dataclass
class DFConfig:
    fs: float = 2e6
    f_rot: float = 8_000.0
    slice_bw: float | None = None       # default 0.2 * fs
    numtaps: int = 401
    block_rotations: int = 20           # sub-block length for sigma estimate
    switch_start_sample: float | None = 0.0   # None = recover from the capture
    edge_window: int = 4                # samples averaged each side of an edge
    amp_weight: bool = False
    min_lockin_snr_db: float = 6.0
    max_sigma_deg: float = 30.0
    carrier_band: tuple | None = None   # (lo, hi) Hz to search, None = whole capture
    cal: Calibration = field(default_factory=Calibration)

    def __post_init__(self):
        if self.slice_bw is None:
            self.slice_bw = 0.2 * self.fs


def estimate_bearing(iq: np.ndarray, cfg: DFConfig, carrier_hz: float | None = None) -> BearingEstimate:
    """Bearing from one capture (or one burst) of switched-array IQ."""
    if carrier_hz is None:
        carrier_hz, _ = estimate_carrier(iq, cfg.fs, band=cfg.carrier_band)

    x = slice_baseband(iq, cfg.fs, carrier_hz, cfg.slice_bw, cfg.numtaps)

    if cfg.switch_start_sample is None:
        t_edge, _ = estimate_switch_timing(x, cfg.fs, cfg.f_rot)
        start = t_edge      # an edge position modulo dwell is all edge_lockin needs
        timing_recovered = True
    else:
        start = cfg.switch_start_sample
        timing_recovered = False

    L, n_edges = edge_lockin(x, cfg.fs, cfg.f_rot, start, cfg.edge_window, cfg.amp_weight)

    # confidence: full-stream lock-in vs off-frequency floor
    d = fm_discriminate(x)
    Lfull = lockin(d, cfg.fs, cfg.f_rot, 0)
    floor = lockin_noise_floor(d, cfg.fs, cfg.f_rot)
    snr_db = 20 * np.log10(abs(Lfull) / floor + 1e-12)

    # sub-block spread
    blk = int(cfg.block_rotations * cfg.fs / cfg.f_rot)
    bearings, wts = [], []
    for s in range(0, len(x) - blk + 1, blk):
        Lb, ne = edge_lockin(x[s:s + blk], cfg.fs, cfg.f_rot, start - s, cfg.edge_window, cfg.amp_weight)
        if ne:
            bearings.append(cfg.cal.bearing_from_lockin(Lb))
            wts.append(abs(Lb))
    sigma = circ_std_deg(bearings, wts) if len(bearings) >= 2 else 45.0

    bearing = cfg.cal.bearing_from_lockin(L)
    # short bursts make the full-stream SNR unreliable; accept on block spread too
    ok = n_edges >= 8 and (snr_db >= cfg.min_lockin_snr_db or sigma <= cfg.max_sigma_deg)
    return BearingEstimate(bearing, sigma, float(snr_db), float(carrier_hz), L,
                           len(bearings), ok,
                           {"lockin_abs": abs(L), "floor": floor, "block_bearings": bearings,
                            "n_edges": n_edges, "timing_recovered": timing_recovered,
                            "switch_start_sample": float(start)})


# ---------------------------------------------------------------------------
# switch-timing recovery (for when the capture start is not phase-locked to
# the Opera Cake sequence)
# ---------------------------------------------------------------------------

def estimate_switch_timing(iq: np.ndarray, fs: float, f_rot: float, n_el: int = 4) -> tuple[float, float]:
    """Find WHEN switch edges occur, modulo one dwell, from the broadband
    transients they leave in the signal envelope / phase.

    Returns (offset_samples, strength). ``offset_samples`` is the position of
    an edge within [0, dwell). Because every edge looks the same, this only
    pins the timing modulo one dwell: the identity of element 0 is still
    unknown, so the bearing is ambiguous by multiples of 90 deg until a
    one-time calibration with a known source resolves it.
    """
    dwell = fs / (n_el * f_rot)
    f_sw = n_el * f_rot
    d = np.abs(fm_discriminate(iq))          # edges make big phase steps
    d = d - np.mean(d)
    n = np.arange(len(d)) + 0.5
    Z = np.mean(d * np.exp(-2j * np.pi * f_sw * n / fs))
    # a positive spike at time t0 gives angle(Z) = -2*pi*f_sw*t0/fs
    t0 = np.mod(-np.angle(Z) / (2 * np.pi) * dwell, dwell)
    return float(t0), float(abs(Z))
