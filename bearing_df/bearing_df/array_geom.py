"""Square 4-element pseudo-Doppler array geometry.

Conventions used throughout the package
---------------------------------------
* Bearings are COMPASS degrees: 0 = the array's "forward" mark (north when the
  plate is aligned north), increasing clockwise.
* Element k (k = 0..3) sits at the corner of a square at compass angle
  45 + 90*k degrees from the plate centre. Opera Cake port B1 -> element 0,
  B2 -> element 1, ... in that order. Wire it the other way round and the
  recovered bearing flips sign; see ``rotation_dir`` in ``dsp``.
* "Spacing" is the side of the square (adjacent-element distance).
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

C = 299_792_458.0  # m/s


def wavelength(freq_hz: float) -> float:
    return C / freq_hz


@dataclass(frozen=True)
class SquareArray:
    """Four vertical omnis at the corners of a square."""

    spacing_m: float
    n_elements: int = 4

    @property
    def radius_m(self) -> float:
        """Distance from plate centre to each element."""
        return self.spacing_m / np.sqrt(2.0)

    def element_compass_deg(self) -> np.ndarray:
        return 45.0 + 90.0 * np.arange(self.n_elements)

    def element_xy(self) -> np.ndarray:
        """(N, 2) positions in metres, x = east, y = north."""
        a = np.deg2rad(self.element_compass_deg())
        return self.radius_m * np.stack([np.sin(a), np.cos(a)], axis=1)

    def element_phases(self, bearing_deg: float, freq_hz: float) -> np.ndarray:
        """Carrier phase (rad) seen at each element for a plane wave arriving
        from ``bearing_deg``. The element nearest the source leads."""
        beta = 2 * np.pi * self.radius_m / wavelength(freq_hz)
        a = np.deg2rad(self.element_compass_deg())
        return beta * np.cos(np.deg2rad(bearing_deg) - a)

    def spacing_check(self, freq_hz: float) -> dict:
        """Report the spacing against the lambda/4 rule and lambda/2 ceiling."""
        lam = wavelength(freq_hz)
        frac = self.spacing_m / lam
        return {
            "wavelength_m": lam,
            "spacing_over_lambda": frac,
            "ambiguous": frac >= 0.5,
            "note": (
                "over lambda/2: bearing ambiguous" if frac >= 0.5 else
                "lambda/3..lambda/2: sharp but multipath-prone" if frac > 1 / 3 else
                "near lambda/4: recommended compromise" if frac > 0.18 else
                "small: unambiguous but low sensitivity"
            ),
        }


def cellular_plate() -> SquareArray:
    """3.5 in square, per the build plan (600-850 MHz uplink)."""
    return SquareArray(spacing_m=3.5 * 0.0254)


def wifi_plate() -> SquareArray:
    """1.3 in square for 2.4 GHz."""
    return SquareArray(spacing_m=1.3 * 0.0254)
