"""Command line entry points.

    python -m bearing_df.cli sim  --bearing 135 --source wideband --snr 0 --burst
    python -m bearing_df.cli file capture.iq --fs 2e6 --frot 8000 [--burst]
    python -m bearing_df.cli calibrate capture.iq --true-bearing 90 --fs 2e6 --frot 8000
    python -m bearing_df.cli drive   (simulated truck run -> wedge map -> fix)
"""
from __future__ import annotations

import argparse
import json
import sys
import numpy as np

from .array_geom import cellular_plate
from .sim import SimConfig, simulate
from .dsp import DFConfig, Calibration, estimate_bearing
from .burst import bearings_from_bursts
from .tracker import Tracker, Ping
from .geo import WedgeMap, Wedge, bearing_between, distance_m
from .hackrf_io import read_iq_int8


def _cfg(a, cal=None) -> DFConfig:
    c = DFConfig(fs=a.fs, f_rot=a.frot,
                 switch_start_sample=None if a.recover_timing else a.switch_start)
    if cal is not None:
        c.cal = cal
    if a.slice_bw:
        c.slice_bw = a.slice_bw
    return c


def _report(res):
    for i, (b, e) in enumerate(res):
        print(f"burst {i:3d}  {b.n/1000:5.1f} ksamp  bearing {e.bearing_deg:6.1f}  sigma {e.sigma_deg:5.1f}  "
              f"snr {e.snr_lockin_db:5.1f} dB  {'ok' if e.ok else '--'}")


def cmd_sim(a):
    arr = cellular_plate()
    sc = SimConfig(fs=a.fs, f_rot=a.frot, bearing_deg=a.bearing, source=a.source,
                   snr_db=a.snr, burst=a.burst, duration_s=a.duration, seed=a.seed)
    iq, _ = simulate(sc, arr, switch_offset_samples=a.switch_start)
    cfg = _cfg(a)
    if a.burst:
        res = bearings_from_bursts(iq, cfg)
        _report(res)
        tr = Tracker()
        for i, (b, e) in enumerate(res):
            st = tr.add(Ping(t=b.start / a.fs, bearing_deg=e.bearing_deg, sigma_deg=e.sigma_deg,
                             strength_db=b.mean_db, ok=e.ok))
        print(f"\nfused: {st.bearing_deg:.1f} deg +- {st.half_width_deg:.1f}  (true {a.bearing})  from {st.n_used} pings")
    else:
        e = estimate_bearing(iq, cfg)
        err = (e.bearing_deg - a.bearing + 180) % 360 - 180
        print(f"bearing {e.bearing_deg:.1f} deg  (true {a.bearing}, err {err:+.1f})  sigma {e.sigma_deg:.1f}  "
              f"snr {e.snr_lockin_db:.1f} dB  edges {e.detail['n_edges']}  ok={e.ok}")


def _load_cal(path):
    if not path:
        return None
    with open(path) as f:
        d = json.load(f)
    return Calibration(**d)


def cmd_file(a):
    iq = read_iq_int8(a.path, max_samples=int(a.max_seconds * a.fs) if a.max_seconds else None)
    cfg = _cfg(a, _load_cal(a.cal))
    if a.burst:
        _report(bearings_from_bursts(iq, cfg, threshold_db=a.threshold))
    else:
        e = estimate_bearing(iq, cfg)
        print(f"carrier {e.carrier_hz/1e3:+.1f} kHz  bearing {e.bearing_deg:.1f}  sigma {e.sigma_deg:.1f}  "
              f"snr {e.snr_lockin_db:.1f} dB  edges {e.detail['n_edges']}  "
              f"switch_start {e.detail['switch_start_sample']:.1f}  ok={e.ok}")


def cmd_calibrate(a):
    """One known source at a known bearing -> calibration constant."""
    iq = read_iq_int8(a.path, max_samples=int(a.max_seconds * a.fs) if a.max_seconds else None)
    cfg = _cfg(a)
    e = estimate_bearing(iq, cfg)
    cal = Calibration.from_known_source(e.lockin, a.true_bearing, rotation_dir=a.rotation_dir)
    print(f"raw angle(L) = {np.rad2deg(np.angle(e.lockin)):.1f}  sigma {e.sigma_deg:.1f}  snr {e.snr_lockin_db:.1f} dB")
    print(f"calibration: offset_deg={cal.offset_deg:.1f} rotation_dir={cal.rotation_dir}")
    if a.out:
        with open(a.out, "w") as f:
            json.dump({"offset_deg": cal.offset_deg, "rotation_dir": cal.rotation_dir}, f)
        print("wrote", a.out)
    if e.sigma_deg > 10:
        print("WARNING: sigma > 10 deg; use a stronger/steadier source for calibration")


def cmd_drive(a):
    """Simulated truck run past a target: pings -> wedges -> fix."""
    rng = np.random.default_rng(a.seed)
    tlat, tlon = 39.72, -84.10
    wm = WedgeMap((39.66, -84.20), size_m=30_000, cell_m=150)
    tr = Tracker(window_s=60)
    for i in range(a.n):
        lat, lon, hdg = 39.65, -84.26 + 0.004 * i, 90.0
        rel = (bearing_between(lat, lon, tlat, tlon) - hdg) % 360
        p = Ping(t=3.0 * i, bearing_deg=rel + rng.normal(0, a.sigma), sigma_deg=a.sigma,
                 strength_db=-90 + 0.3 * i, lat=lat, lon=lon, heading_deg=hdg)
        st = tr.add(p)
        wm.add(Wedge(lat, lon, p.abs_bearing_deg, a.sigma, t=p.t))
    f = wm.fix()
    print(f"fix {f.lat:.4f},{f.lon:.4f}  error {distance_m(f.lat, f.lon, tlat, tlon):.0f} m  "
          f"50%-spread {f.spread_m:.0f} m  from {f.n_wedges} wedges")
    print(f"trend: strength {st.strength_trend}, bearing drifting {st.bearing_trend}, approaching={st.approaching}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="bearing_df")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--fs", type=float, default=2e6)
        sp.add_argument("--frot", type=float, default=8000.0)
        sp.add_argument("--slice-bw", type=float, default=0.0)
        sp.add_argument("--switch-start", type=float, default=0.0)
        sp.add_argument("--recover-timing", action="store_true", help="estimate switch timing from the capture")

    s = sub.add_parser("sim"); common(s)
    s.add_argument("--bearing", type=float, default=135.0)
    s.add_argument("--source", choices=["tone", "wideband"], default="tone")
    s.add_argument("--snr", type=float, default=10.0)
    s.add_argument("--burst", action="store_true")
    s.add_argument("--duration", type=float, default=0.05)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=cmd_sim)

    s = sub.add_parser("file"); common(s)
    s.add_argument("path")
    s.add_argument("--burst", action="store_true")
    s.add_argument("--threshold", type=float, default=5.0)
    s.add_argument("--max-seconds", type=float, default=0.0)
    s.add_argument("--cal", default="")
    s.set_defaults(fn=cmd_file)

    s = sub.add_parser("calibrate"); common(s)
    s.add_argument("path")
    s.add_argument("--true-bearing", type=float, required=True)
    s.add_argument("--rotation-dir", type=int, default=1)
    s.add_argument("--max-seconds", type=float, default=0.0)
    s.add_argument("--out", default="calibration.json")
    s.set_defaults(fn=cmd_calibrate)

    s = sub.add_parser("drive")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--sigma", type=float, default=8.0)
    s.add_argument("--seed", type=int, default=1)
    s.set_defaults(fn=cmd_drive)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
