"""Wedge accumulation -> position fix.

Every ping is stamped with own position + heading and becomes a wedge on the
map (absolute bearing, half-width = confidence). Wedges from different
positions overlap; the brightest cell is the fix. This is the "novel work is
the display" part: sparse, noisy pings become a location as the aircraft
(or truck) moves.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

R_EARTH = 6_371_000.0


def enu_from_latlon(lat, lon, lat0, lon0):
    """Local east/north metres relative to (lat0, lon0). Fine for < ~100 km."""
    dlat = np.deg2rad(np.asarray(lat) - lat0)
    dlon = np.deg2rad(np.asarray(lon) - lon0)
    return R_EARTH * dlon * np.cos(np.deg2rad(lat0)), R_EARTH * dlat


def latlon_from_enu(e, n, lat0, lon0):
    lat = lat0 + np.rad2deg(n / R_EARTH)
    lon = lon0 + np.rad2deg(e / (R_EARTH * np.cos(np.deg2rad(lat0))))
    return lat, lon


@dataclass
class Wedge:
    lat: float
    lon: float
    bearing_deg: float       # absolute compass bearing
    half_width_deg: float
    weight: float = 1.0
    t: float = 0.0


@dataclass
class Fix:
    lat: float
    lon: float
    score: float             # peak cell value
    n_wedges: int
    spread_m: float          # radius containing the cells within 50% of peak
    grid: np.ndarray         # (ny, nx) accumulated map
    e_axis: np.ndarray
    n_axis: np.ndarray
    lat0: float
    lon0: float


class WedgeMap:
    """Accumulates wedges on a fixed local grid.

    ``origin`` = (lat, lon) of the grid centre, ``size_m`` = full width,
    ``cell_m`` = resolution, ``max_range_m`` = how far a wedge reaches.
    """

    def __init__(self, origin: tuple[float, float], size_m: float = 30_000.0,
                 cell_m: float = 200.0, max_range_m: float = 25_000.0,
                 fade_s: float | None = None):
        self.lat0, self.lon0 = origin
        half = size_m / 2
        self.e_axis = np.arange(-half, half + cell_m, cell_m)
        self.n_axis = np.arange(-half, half + cell_m, cell_m)
        self.E, self.N = np.meshgrid(self.e_axis, self.n_axis)
        self.grid = np.zeros_like(self.E)
        self.max_range_m = max_range_m
        self.fade_s = fade_s
        self.wedges: list[Wedge] = []
        self._last_t = 0.0

    def add(self, w: Wedge):
        if self.fade_s is not None and w.t > self._last_t:
            self.grid *= np.exp(-(w.t - self._last_t) / self.fade_s)
            self._last_t = w.t
        self.wedges.append(w)
        e0, n0 = enu_from_latlon(w.lat, w.lon, self.lat0, self.lon0)
        de, dn = self.E - e0, self.N - n0
        rng = np.hypot(de, dn)
        brg = np.rad2deg(np.arctan2(de, dn))                # compass bearing of each cell
        diff = np.abs((brg - w.bearing_deg + 180) % 360 - 180)
        hw = max(w.half_width_deg, 1.0)
        # soft wedge: gaussian in angle with sigma = half width, cut at 2 sigma
        inside = (diff <= 2 * hw) & (rng > 0) & (rng <= self.max_range_m)
        val = np.exp(-0.5 * (diff / hw) ** 2)
        # normalise so a wide wedge doesn't outvote a narrow one just by area
        val = val / hw
        self.grid += np.where(inside, w.weight * val, 0.0)

    def fix(self) -> Fix | None:
        if not self.wedges or self.grid.max() <= 0:
            return None
        iy, ix = np.unravel_index(np.argmax(self.grid), self.grid.shape)
        peak = self.grid[iy, ix]
        # spread: RMS distance of cells >= 50% of peak from the peak cell
        m = self.grid >= 0.5 * peak
        d = np.hypot(self.E[m] - self.E[iy, ix], self.N[m] - self.N[iy, ix])
        spread = float(np.sqrt(np.mean(d ** 2))) if d.size else 0.0
        lat, lon = latlon_from_enu(self.E[iy, ix], self.N[iy, ix], self.lat0, self.lon0)
        return Fix(float(lat), float(lon), float(peak), len(self.wedges), spread,
                   self.grid.copy(), self.e_axis, self.n_axis, self.lat0, self.lon0)


def bearing_between(lat1, lon1, lat2, lon2) -> float:
    """Compass bearing from point 1 to point 2 (deg)."""
    e, n = enu_from_latlon(lat2, lon2, lat1, lon1)
    return float(np.rad2deg(np.arctan2(e, n)) % 360)


def distance_m(lat1, lon1, lat2, lon2) -> float:
    e, n = enu_from_latlon(lat2, lon2, lat1, lon1)
    return float(np.hypot(e, n))
