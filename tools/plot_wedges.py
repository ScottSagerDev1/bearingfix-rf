"""Draw explore_sim.py's stage-6 drive-by as a wedge map.

    python tools/plot_wedges.py            # -> docs/wedge_map_sim.png

Reproduces stage 6 exactly (same 12 stops, seeds, Tracker and WedgeMap calls)
so the numbers match docs/explore_sim_sample_output.txt, then plots it: one
translucent fan per stop along its measured bearing, the true phone position,
the fix, and the distance between them. Needs matplotlib (pip install -e .[sweep]).
"""
from __future__ import annotations

from pathlib import Path
import numpy as np

from bearing_df.array_geom import SquareArray
from bearing_df.sim import SimConfig, simulate
from bearing_df.dsp import DFConfig
from bearing_df.burst import bearings_from_bursts
from bearing_df.tracker import Tracker, Ping
from bearing_df.geo import WedgeMap, Wedge, bearing_between, distance_m, enu_from_latlon

# explore_sim.py defaults
TRUE_BEARING_DEG, SNR_DB, BURST_MS, SPACING_IN, SOURCE = 137.0, 3.0, 1.0, 3.5, "wideband"
FREQ_HZ, FS, F_ROT = 830e6, 2e6, 8000.0
TLAT, TLON = 39.72, -84.10
ORIGIN = (39.66, -84.20)
FAN_KM = 20.0

SERIES, TRUTH, FIX = "#2a78d6", "#1baf7a", "#eb6834"      # validated categorical slots 1, 3, 2
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"


def drive_by():
    """Stage 6 of explore_sim.py, verbatim. Returns (stops, wedge map, fix)."""
    arr = SquareArray(spacing_m=SPACING_IN * 0.0254)
    cfg = DFConfig()
    sc = SimConfig(fs=FS, f_rot=F_ROT, freq_hz=FREQ_HZ, bearing_deg=TRUE_BEARING_DEG,
                   snr_db=SNR_DB, source=SOURCE, duration_s=0.02, seed=0)
    sc_b = SimConfig(**{**sc.__dict__, "burst": True, "burst_on_s": BURST_MS * 1e-3, "duration_s": 0.1})
    wm = WedgeMap(ORIGIN, size_m=30_000, cell_m=150)
    stops = []
    print("6. stop  true rel. bearing  measured")
    for i in range(12):
        lat, lon, hdg = 39.65, -84.26 + 0.015 * i, 90.0
        rel = (bearing_between(lat, lon, TLAT, TLON) - hdg) % 360
        iq_i, _ = simulate(SimConfig(**{**sc_b.__dict__, "bearing_deg": rel, "seed": 100 + i}), arr)
        tr = Tracker()
        for b, eb in bearings_from_bursts(iq_i, cfg):
            st = tr.add(Ping(t=b.start / FS, bearing_deg=eb.bearing_deg, sigma_deg=eb.sigma_deg,
                             strength_db=b.mean_db, ok=eb.ok))
        w = Wedge(lat, lon, (hdg + st.bearing_deg) % 360, max(st.half_width_deg, 3.0), t=3.0 * i)
        wm.add(w)
        stops.append(w)
        print(f"   {i:4d}  {rel:9.1f}          {st.bearing_deg:6.1f} +- {st.half_width_deg:4.1f}")
    f = wm.fix()
    print(f"\n   FIX {f.lat:.4f}, {f.lon:.4f}: {distance_m(f.lat, f.lon, TLAT, TLON):.0f} m from the phone,"
          f" 50% spread {f.spread_m:.0f} m, from {f.n_wedges} wedges")
    return stops, wm, f


def fan(e_km, n_km, bearing_deg, half_deg, r_km=FAN_KM, n_pts=24):
    """Polygon (x, y) of a wedge from (e, n) along a compass bearing."""
    a = np.deg2rad(np.linspace(bearing_deg - half_deg, bearing_deg + half_deg, n_pts))
    return np.column_stack([np.r_[e_km, e_km + r_km * np.sin(a)], np.r_[n_km, n_km + r_km * np.cos(a)]])


def plot(stops, wm, f, out: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    km = lambda lat, lon: tuple(v / 1e3 for v in enu_from_latlon(lat, lon, *ORIGIN))
    fig, ax = plt.subplots(figsize=(7.5, 6.9))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for w in stops:
        e, n = km(w.lat, w.lon)
        ax.add_patch(Polygon(fan(e, n, w.bearing_deg, w.half_width_deg), closed=True,
                             facecolor=SERIES, edgecolor="none", alpha=0.10))
    se, sn = zip(*(km(w.lat, w.lon) for w in stops))
    ax.plot(se, sn, "o", color=SERIES, markersize=5, markeredgecolor=SURFACE, label="truck stop + its wedge")
    te, tn = km(TLAT, TLON)
    fe, fn = km(f.lat, f.lon)
    d_m = distance_m(f.lat, f.lon, TLAT, TLON)
    ax.plot([fe, te], [fn, tn], "-", color=INK2, linewidth=1)
    ax.plot(te, tn, "*", color=TRUTH, markersize=15, markeredgecolor=SURFACE, label="phone (true)")
    ax.plot(fe, fn, "X", color=FIX, markersize=11, markeredgecolor=SURFACE, label="fix (brightest cell)")
    ax.annotate(f"{d_m:.0f} m", ((fe + te) / 2, (fn + tn) / 2), xytext=(10, -3), textcoords="offset points",
                color=INK2, fontsize=9, va="center")
    ax.annotate("phone (true)", (te, tn), xytext=(12, -14), textcoords="offset points", color=INK2, fontsize=9)
    ax.annotate("fix", (fe, fn), xytext=(-24, 4), textcoords="offset points", color=INK2, fontsize=9)

    # the grid is 30 km square; show the part with wedges in it, coordinates still relative to the origin
    ax.set_xlim(-7, 15)
    ax.set_ylim(-4, 15)
    ax.set_aspect("equal")
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_xlabel("east of map origin (km)", color=INK2)
    ax.set_ylabel("north of map origin (km)", color=INK2)
    ax.set_title(f"12 wedges from a drive-by, simulated: fix {d_m:.0f} m from the phone",
                 color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="lower right")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"wrote {out}")


if __name__ == "__main__":
    stops, wm, f = drive_by()
    plot(stops, wm, f, Path(__file__).resolve().parents[1] / "docs" / "wedge_map_sim.png")
