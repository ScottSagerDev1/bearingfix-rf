"""LTE PRACH detection with Zadoff-Chu correlation.

Why: a phone with no usable signal does not go quiet. Every time it tries to
reach a tower it transmits a random-access preamble (PRACH): one of 64
Zadoff-Chu sequences the network assigned to that cell. Because the sequence
is KNOWN, we can correlate coherently over the whole 800 us preamble and see
it far below where an energy detector gives up. Each detection also gives an
exact burst start, which the bearing estimator needs.

Format 0 (the common one, 3GPP TS 36.211 s5.7):
    sequence length N_ZC = 839, subcarrier spacing 1.25 kHz
    T_CP = 103.13 us, T_SEQ = 800 us, total 1 ms, occupies 6 RBs (1.08 MHz)
    x_u(n) = exp(-j*pi*u*n*(n+1)/N_ZC), root u in 1..838

Unknowns and how they are handled
    * root index u: the cell's logical root is unknown -> search all roots
      (or a shortlist once one has been seen). Numpy handles the 838-root
      search on a 1600-sample window in tens of ms.
    * cyclic shift (preamble index): appears as the peak position in the
      correlation, so it is free.
    * burst timing: slide an 800 us window in steps <= CP length; anywhere
      inside the CP the sequence is a cyclic shift, still detected.
    * carrier offset: preamble is sensitive to frequency error; search a few
      1.25 kHz bin offsets.
    * PRACH frequency position within the uplink band: parameter, plus a
      coarse search on the 180 kHz RB grid if unknown.

Array switching sits on top of all of this: the Opera Cake's periodic phase
modulation spreads each subcarrier into sidebands at +-f_rot. The detector
still works on the unmodulated fraction of the energy (measured in sim, see
tests), and it hands the exact burst window to ``dsp.estimate_bearing``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

N_ZC = 839
PRACH_SCS = 1250.0            # Hz
T_SEQ = 800e-6
T_CP = 103.125e-6
T_TOTAL = 1e-3
PRACH_BW = 1.08e6


def zc_sequence(u: int) -> np.ndarray:
    n = np.arange(N_ZC)
    return np.exp(-1j * np.pi * u * n * (n + 1) / N_ZC)


def zc_freq(u: int, cyclic_shift: int = 0) -> np.ndarray:
    """839-point DFT of the (cyclically shifted) root sequence."""
    x = np.roll(zc_sequence(u), -cyclic_shift)
    return np.fft.fft(x) / np.sqrt(N_ZC)


def generate_prach(u: int, fs: float, center_hz: float = 0.0, cyclic_shift: int = 0,
                   with_cp: bool = True) -> np.ndarray:
    """Time-domain format-0 preamble at sample rate ``fs`` with the 839
    subcarriers centred on ``center_hz`` (baseband). Unit RMS."""
    n_seq = int(round(fs * T_SEQ))          # 800 us -> bins are exactly 1.25 kHz
    X = zc_freq(u, cyclic_shift)
    spec = np.zeros(n_seq, dtype=complex)
    k0 = int(round(center_hz / PRACH_SCS)) - N_ZC // 2   # first subcarrier index
    ks = (k0 + np.arange(N_ZC)) % n_seq
    spec[ks] = X
    seq = np.fft.ifft(spec) * n_seq / np.sqrt(N_ZC)
    # the half-bin offset (839 is odd) is handled by centring on k0 + 419
    if with_cp:
        n_cp = int(round(fs * T_CP))
        seq = np.concatenate([seq[-n_cp:], seq])
    return seq / np.sqrt(np.mean(np.abs(seq) ** 2))


@dataclass
class PRACHDetection:
    start: int              # sample index of the sequence part (after CP)
    root: int
    delay_bins: int         # peak position in the 839-point profile (cyclic shift + delay)
    metric: float           # peak / mean of the power-delay profile
    freq_bin_offset: int    # 1.25 kHz bins of carrier error applied
    center_hz: float


@dataclass
class PRACHDetector:
    fs: float
    center_hz: float = 0.0          # baseband centre of the PRACH block
    roots: list[int] | None = None  # None = all 1..838
    threshold_all_roots: float = 25.0   # peak/mean of PDP when searching all 838 roots
    threshold_locked: float = 16.0      # when a single root is locked
    # measured on pure noise, 2 MSPS: all-root max ~21, locked max ~12 over 200 windows
    step_s: float = 100e-6          # window slide (<= CP)
    freq_search_bins: int = 2       # +-bins of carrier error to try
    auto_lock: bool = True          # lock onto the first root detected
    _X: np.ndarray = field(default=None, repr=False)

    def __post_init__(self):
        if self.roots is None:
            self.roots = list(range(1, N_ZC))
        self._X = np.stack([zc_freq(u) for u in self.roots])    # (R, 839)
        self.n_seq = int(round(self.fs * T_SEQ))
        self.k0 = int(round(self.center_hz / PRACH_SCS)) - N_ZC // 2

    def _window_bins(self, w: np.ndarray, bin_offset: int) -> np.ndarray:
        Y = np.fft.fft(w)
        ks = (self.k0 + bin_offset + np.arange(N_ZC)) % self.n_seq
        return Y[ks]

    def _score(self, w, bo, X):
        Yk = self._window_bins(w, bo)
        pdp = np.abs(np.fft.ifft(Yk[None, :] * np.conj(X), axis=1)) ** 2   # (R, 839)
        m = pdp.max(axis=1) / (pdp.mean(axis=1) + 1e-30)
        return m, pdp

    def score_window(self, w: np.ndarray, shortlist: int = 5) -> tuple[float, int, int, int]:
        """Best (metric, root, delay, bin_offset) for one 800 us window.

        Two stages to keep the all-root search affordable: every root at zero
        frequency offset, then the top ``shortlist`` roots across the
        +-freq_search_bins offsets. A real preamble is still the top root at
        offset 0 down to roughly -15 dB SNR (a 1-bin error only halves the
        peak), so the shortlist stage does not lose it."""
        m0, pdp0 = self._score(w, 0, self._X)
        top = np.argsort(m0)[::-1][:shortlist]
        best = (float(m0[top[0]]), self.roots[top[0]], int(np.argmax(pdp0[top[0]])), 0)
        if self.freq_search_bins == 0:
            return best
        Xs = self._X[top]
        for bo in range(-self.freq_search_bins, self.freq_search_bins + 1):
            if bo == 0:
                continue
            m, pdp = self._score(w, bo, Xs)
            r = int(np.argmax(m))
            if m[r] > best[0]:
                best = (float(m[r]), self.roots[top[r]], int(np.argmax(pdp[r])), bo)
        return best

    def lock_root(self, u: int) -> None:
        """Once the cell's root is known, search only it (~800x faster)."""
        self.roots, self._X = [u], np.stack([zc_freq(u)])

    def detect(self, iq: np.ndarray, merge_s: float = 1.2e-3) -> list[PRACHDetection]:
        """Slide over the capture; return the best detection per burst."""
        step = max(int(self.fs * self.step_s), 1)
        n = self.n_seq
        hits = []
        for s in range(0, len(iq) - n + 1, step):
            m, u, d, bo = self.score_window(iq[s:s + n])
            thr = self.threshold_locked if len(self.roots) == 1 else self.threshold_all_roots
            if m >= thr:
                hits.append(PRACHDetection(s, u, d, m, bo, self.center_hz))
                if self.auto_lock and len(self.roots) > 1:
                    self.lock_root(u)
        # keep the strongest window within each burst
        out = []
        merge = int(self.fs * merge_s)
        for h in hits:
            if out and h.start - out[-1].start < merge:
                if h.metric > out[-1].metric:
                    out[-1] = h
            else:
                out.append(h)
        return out

    def refine_start(self, iq: np.ndarray, det: PRACHDetection, span_s: float = 60e-6) -> int:
        """Fine-tune the burst start by re-scoring nearby windows sample-wise."""
        span = int(self.fs * span_s)
        roots_bak = self.roots
        X_bak = self._X
        self.roots, self._X = [det.root], np.stack([zc_freq(det.root)])
        best_s, best_m = det.start, det.metric
        for s in range(max(0, det.start - span), min(len(iq) - self.n_seq, det.start + span), 4):
            m = self.score_window(iq[s:s + self.n_seq])[0]
            if m > best_m:
                best_s, best_m = s, m
        self.roots, self._X = roots_bak, X_bak
        det.start, det.metric = best_s, best_m
        return best_s


def find_prach_center(iq: np.ndarray, fs: float, candidates_hz: np.ndarray | None = None,
                      roots: list[int] | None = None, n_windows: int = 12) -> tuple[float, float]:
    """Coarse search for where the PRACH block sits in the capture: try each
    candidate centre on a few windows spread through the capture, return
    (best_center_hz, best_metric). ``candidates_hz`` defaults to the 180 kHz
    RB grid across the capture bandwidth."""
    if candidates_hz is None:
        half = fs / 2 - PRACH_BW / 2
        candidates_hz = np.arange(-half, half + 1, 180e3)
    n_seq = int(round(fs * T_SEQ))
    starts = np.linspace(0, len(iq) - n_seq, n_windows).astype(int)
    best = (0.0, 0.0)
    for c in candidates_hz:
        det = PRACHDetector(fs, center_hz=float(c), roots=roots, freq_search_bins=1)
        m = max(det.score_window(iq[s:s + n_seq])[0] for s in starts)
        if m > best[1]:
            best = (float(c), m)
    return best


# ---------------------------------------------------------------------------
# despread: turn a detected preamble into a tone-like signal for the DF chain
# ---------------------------------------------------------------------------

def despread(iq_window: np.ndarray, det: PRACHDetection, fs: float) -> np.ndarray:
    """Multiply the detected 800 us window by the conjugate of the
    reconstructed preamble. What remains is constant-amplitude x the array
    switching pattern x noise, i.e. the clean-tone case, so the DF chain can
    then narrow its slice to ~50-100 kHz and gain 10-15 dB over working on
    the raw noise-like burst. Any leftover frequency error (the ZC
    delay/frequency ambiguity) shows up as a tone offset, which the
    discriminator rejects as DC."""
    n_seq = int(round(fs * T_SEQ))
    w = iq_window[:n_seq]
    ref = generate_prach(det.root, fs, center_hz=det.center_hz + det.freq_bin_offset * PRACH_SCS,
                         cyclic_shift=0, with_cp=False)
    # the PDP peak position is a cyclic shift of the 839-chip sequence, which
    # maps to a circular time shift of the 800 us waveform by peak/839 * n_seq
    shift = int(round(det.delay_bins * n_seq / N_ZC))
    ref = np.roll(ref, shift)
    return w * np.conj(ref[:len(w)])
