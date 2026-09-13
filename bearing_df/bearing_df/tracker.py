"""Track-while-scan accumulation of sparse pings.

Feeds the three display elements: fused bearing + width (wedge), strength bar
with high-water mark, and trend arrows (strength rising/falling, bearing
drifting left/right).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .dsp import circ_mean_deg, wrap_deg


@dataclass
class Ping:
    t: float                 # seconds (monotonic)
    bearing_deg: float       # relative to array forward mark
    sigma_deg: float
    strength_db: float
    ok: bool = True
    lat: float | None = None
    lon: float | None = None
    heading_deg: float | None = None   # vehicle/aircraft heading; abs bearing = heading + relative

    @property
    def abs_bearing_deg(self) -> float | None:
        if self.heading_deg is None:
            return None
        return float(wrap_deg(self.heading_deg + self.bearing_deg))


@dataclass
class TrackState:
    bearing_deg: float | None = None
    half_width_deg: float = 90.0
    n_used: int = 0
    strength_db: float | None = None       # smoothed
    strength_hwm_db: float | None = None   # high-water mark
    strength_trend: str = "flat"           # rising | falling | flat
    bearing_trend: str = "steady"          # left | right | steady
    approaching: bool | None = None
    age_s: float = 0.0


@dataclass
class Tracker:
    window_s: float = 20.0          # pings older than this are dropped from the fuse
    min_half_width_deg: float = 5.0
    max_half_width_deg: float = 90.0
    strength_alpha: float = 0.3
    trend_db_per_s: float = 0.3     # slope needed to call rising/falling
    trend_deg_per_s: float = 0.5    # slope needed to call left/right
    pings: list = field(default_factory=list)
    state: TrackState = field(default_factory=TrackState)

    def add(self, p: Ping) -> TrackState:
        self.pings.append(p)
        self.pings = [q for q in self.pings if p.t - q.t <= self.window_s]
        return self._update(p.t)

    def _update(self, now: float) -> TrackState:
        st = self.state
        good = [q for q in self.pings if q.ok]
        st.age_s = now - self.pings[-1].t if self.pings else 0.0

        # --- fused bearing (inverse-variance weighted, aged) ------------------
        if good:
            ages = np.array([now - q.t for q in good])
            w = np.array([1.0 / max(q.sigma_deg, 1.0) ** 2 for q in good]) * np.exp(-ages / self.window_s)
            b = np.array([q.bearing_deg for q in good])
            mean, R = circ_mean_deg(b, w)
            # spread from resultant length plus the per-ping floor
            R = min(max(R, 1e-6), 1.0)
            spread = np.rad2deg(np.sqrt(-2 * np.log(R))) if len(good) > 1 else good[-1].sigma_deg
            n_eff = np.sum(w) ** 2 / np.sum(w ** 2)              # effective ping count
            floor = np.mean([q.sigma_deg for q in good]) / np.sqrt(n_eff)
            hw = float(np.clip(max(spread, floor), self.min_half_width_deg, self.max_half_width_deg))
            st.bearing_deg, st.half_width_deg, st.n_used = float(mean), hw, len(good)

        # --- strength ------------------------------------------------------------
        last = self.pings[-1]
        if st.strength_db is None:
            st.strength_db = last.strength_db
        else:
            st.strength_db = (1 - self.strength_alpha) * st.strength_db + self.strength_alpha * last.strength_db
        st.strength_hwm_db = last.strength_db if st.strength_hwm_db is None else max(st.strength_hwm_db, last.strength_db)

        # --- trends (least-squares slope over the window) ---------------------
        if len(self.pings) >= 4:
            t = np.array([q.t for q in self.pings])
            s = np.array([q.strength_db for q in self.pings])
            k = _significant_slope(t, s, self.trend_db_per_s)
            st.strength_trend = "rising" if k > 0 else "falling" if k < 0 else "flat"
            st.approaching = None if k == 0 else k > 0
        if len(good) >= 4:
            t = np.array([q.t for q in good])
            b = np.rad2deg(np.unwrap(np.deg2rad([q.bearing_deg for q in good])))
            k = _significant_slope(t, b, self.trend_deg_per_s)
            st.bearing_trend = "right" if k > 0 else "left" if k < 0 else "steady"
        return st


def _significant_slope(t, y, min_slope, z: float = 2.0) -> float:
    """Least-squares slope, or 0 if it is smaller than ``min_slope`` or not
    distinguishable from zero at ``z`` standard errors (guards against calling
    a drift on pure noise)."""
    t = t - t[0]
    (k, _), cov = np.polyfit(t, y, 1, cov=True)
    se = np.sqrt(cov[0, 0])
    if abs(k) < min_slope or abs(k) < z * se:
        return 0.0
    return float(k)
