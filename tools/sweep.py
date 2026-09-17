"""Sweep bearing error against SNR, burst length, plate spacing and sample rate.

    python tools/sweep.py                  # full run -> docs/sweeps/
    python tools/sweep.py --quick          # few points, few trials, same code path
    python tools/sweep.py --trials 20 --workers 8 --out /tmp/sweeps

Every point is N bearings evenly spaced around the circle x N trials of a
noise-like (LTE stand-in) source. Error is the mean absolute circular error
of ``estimate_bearing`` on a 20 ms capture, or of every per-burst estimate
from ``bearings_from_bursts`` on a 100 ms bursty capture. Switch timing is
known (``switch_start_sample = 0``), as after a one-time calibration.

The SNR axis is "SNR in 2 MHz". ``SimConfig.snr_db`` is SNR within the
capture bandwidth, so at 8 MSPS the same number would mean a transmitter
4x (6 dB) stronger; ``snr_in_capture`` converts so both rates describe the
same transmitter and the same noise density.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path

import numpy as np

from bearing_df.array_geom import SquareArray, cellular_plate, wavelength
from bearing_df.sim import SimConfig, simulate
from bearing_df.dsp import DFConfig, estimate_bearing
from bearing_df.burst import bearings_from_bursts

F_ROT = 8000.0
FREQ_HZ = 830e6
REF_BW = 2e6
CONT_CAPTURE_S = 0.02
BURST_CAPTURE_S = 0.1
BURST_PERIOD_S = 5e-3
ERR_THRESH_DEG = 10.0
DETECT_THRESH = 0.8


def circ_err_deg(est, true):
    return (est - true + 180.0) % 360.0 - 180.0


def snr_in_capture(snr_ref_db: float, fs: float) -> float:
    return snr_ref_db - 10.0 * np.log10(fs / REF_BW)


def even_bearings(n: int) -> np.ndarray:
    return np.arange(n) * 360.0 / n


@dataclass
class Job:
    sweep: str            # "snr" | "burst" | "spacing"
    label: str            # curve name, fixed order within a sweep
    x: float              # SNR dB | burst ms | spacing / lambda
    kind: str             # "continuous" | "bursty"
    params: dict
    n_bearings: int
    trials: int
    seed: int


@dataclass
class Point:
    sweep: str
    label: str
    x: float
    mean_abs_deg: float
    p90_deg: float
    ok_frac: float
    detect_frac: float | None       # bursty only: bursts found / bursts transmitted
    fused_abs_deg: float | None     # bursty only: error of the circular mean of one capture's bursts
    n: int


def _continuous(p: dict, bearings, trials, seed):
    arr = SquareArray(p["spacing_m"])
    cfg = DFConfig(fs=p["fs"], f_rot=F_ROT, **p.get("dfcfg", {}))
    errs, oks = [], []
    for bi, b in enumerate(bearings):
        for t in range(trials):
            sc = SimConfig(fs=p["fs"], f_rot=F_ROT, freq_hz=FREQ_HZ, source="wideband",
                           bearing_deg=float(b), snr_db=snr_in_capture(p["snr_ref_db"], p["fs"]),
                           duration_s=CONT_CAPTURE_S, seed=seed + 1000 * bi + t)
            iq, _ = simulate(sc, arr)
            e = estimate_bearing(iq, cfg)
            errs.append(abs(circ_err_deg(e.bearing_deg, b)))
            oks.append(e.ok)
    return errs, oks, None, None


def _bursty(p: dict, bearings, trials, seed):
    fs = 2e6
    arr = cellular_plate()
    cfg = DFConfig(fs=fs, f_rot=F_ROT)
    expected = int(BURST_CAPTURE_S / BURST_PERIOD_S)
    errs, oks, fused, n_det = [], [], [], 0
    for bi, b in enumerate(bearings):
        for t in range(trials):
            sc = SimConfig(fs=fs, f_rot=F_ROT, freq_hz=FREQ_HZ, source="wideband", burst=True,
                           burst_on_s=p["burst_on_s"], burst_period_s=BURST_PERIOD_S,
                           duration_s=BURST_CAPTURE_S, bearing_deg=float(b),
                           snr_db=p["snr_ref_db"], seed=seed + 1000 * bi + t)
            iq, _ = simulate(sc, arr)
            res = bearings_from_bursts(iq, cfg)
            n_det += len(res)
            errs += [abs(circ_err_deg(e.bearing_deg, b)) for _, e in res]
            oks += [e.ok for _, e in res]
            if res:
                z = np.mean([np.exp(1j * np.deg2rad(e.bearing_deg)) for _, e in res])
                fused.append(abs(circ_err_deg(np.rad2deg(np.angle(z)), b)))
    detect = n_det / (expected * len(bearings) * trials)
    return errs, oks, detect, (float(np.mean(fused)) if fused else float("nan"))


def run_job(job: Job) -> Point:
    bearings = even_bearings(job.n_bearings)
    fn = _continuous if job.kind == "continuous" else _bursty
    errs, oks, detect, fused = fn(job.params, bearings, job.trials, job.seed)
    if errs:
        mean_abs, p90, ok = float(np.mean(errs)), float(np.percentile(errs, 90)), float(np.mean(oks))
    else:
        mean_abs, p90, ok = float("nan"), float("nan"), 0.0
    return Point(job.sweep, job.label, float(job.x), mean_abs, p90, ok, detect, fused, len(errs))


def plan(trials: int = 50, n_bearings: int = 8, quick: bool = False) -> list[Job]:
    plate = cellular_plate().spacing_m
    lam = wavelength(FREQ_HZ)

    snr_x = [-6.0, 14.0] if quick else [float(s) for s in range(-10, 21, 2)]
    snr_curves = [("2 MSPS", 2e6, {}), ("8 MSPS", 8e6, {})]
    if not quick:
        snr_curves += [("8 MSPS, slice 400 kHz", 8e6, {"slice_bw": 400e3}),
                       ("8 MSPS, slice 400 kHz, edge_window 16", 8e6, {"slice_bw": 400e3, "edge_window": 16})]

    burst_x_ms = [0.2, 1.0] if quick else [float(v) for v in np.linspace(0.2, 2.0, 10)]
    burst_curves = [("10 dB", 10.0)] + ([] if quick else [("3 dB", 3.0)])

    spacing_x = [0.25, 0.5] if quick else [float(v) for v in np.linspace(1 / 6, 1 / 2, 9)]
    spacing_curves = [("0 dB", 0.0)] + ([] if quick else [("-6 dB", -6.0)])

    jobs: list[Job] = []

    def add(sweep, label, x, kind, params):
        jobs.append(Job(sweep, label, x, kind, params, n_bearings, trials, seed=10_000 * len(jobs)))

    for label, fs, dfcfg in snr_curves:
        for s in snr_x:
            add("snr", label, s, "continuous", {"fs": fs, "snr_ref_db": s, "spacing_m": plate, "dfcfg": dfcfg})
    for label, snr in burst_curves:
        for ms in burst_x_ms:
            add("burst", label, ms, "bursty", {"burst_on_s": ms * 1e-3, "snr_ref_db": snr})
    for label, snr in spacing_curves:
        for frac in spacing_x:
            add("spacing", label, frac, "continuous",
                {"fs": 2e6, "snr_ref_db": snr, "spacing_m": frac * lam, "dfcfg": {}})
    return jobs


def run_jobs(jobs: list[Job], workers: int | None = None) -> list[Point]:
    workers = workers or os.cpu_count() or 1
    t0 = time.perf_counter()
    if workers <= 1:
        out = [run_job(j) for j in jobs]
    else:
        out = [None] * len(jobs)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_job, j): i for i, j in enumerate(jobs)}
            for k, f in enumerate(as_completed(futs), 1):
                out[futs[f]] = f.result()
                print(f"\r{k}/{len(jobs)} jobs  {time.perf_counter() - t0:.0f}s", end="", file=sys.stderr)
        print(file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

def _curve(points, sweep, label):
    return sorted((p for p in points if p.sweep == sweep and p.label == label), key=lambda p: p.x)


def _labels(points, sweep):
    seen = []
    for p in points:
        if p.sweep == sweep and p.label not in seen:
            seen.append(p.label)
    return seen


def snr_floor(curve, thresh=ERR_THRESH_DEG):
    """Lowest SNR from which every higher point stays under ``thresh``."""
    floor = None
    for p in reversed(curve):
        if np.isnan(p.mean_abs_deg) or p.mean_abs_deg > thresh:
            break
        floor = p.x
    return floor


def shortest_usable_burst(curve, attr="mean_abs_deg", thresh=ERR_THRESH_DEG, min_detect=DETECT_THRESH):
    best = None
    for p in reversed(curve):
        v = getattr(p, attr)
        good = (p.detect_frac or 0.0) >= min_detect and v is not None and not np.isnan(v) and v <= thresh
        if not good:
            break
        best = p.x
    return best


def spacing_summary(curve, within_deg=1.0, breakdown_deg=5.0):
    errs = np.array([p.mean_abs_deg for p in curve])
    xs = np.array([p.x for p in curve])
    i_best = int(np.nanargmin(errs))
    knee = float(xs[np.flatnonzero(errs <= errs[i_best] + within_deg)[0]])
    after = np.flatnonzero((xs > xs[i_best]) & (errs > errs[i_best] + breakdown_deg))
    return {"best": float(xs[i_best]), "best_err": float(errs[i_best]), "knee": knee,
            "breaks_from": float(xs[after[0]]) if len(after) else None}


def analyze(points: list[Point]) -> dict:
    a = {"snr_floor_deg10": {}, "shortest_usable_burst_ms": {}, "shortest_usable_burst_fused_ms": {},
         "spacing": {}, "rate": {}}
    for lab in _labels(points, "snr"):
        a["snr_floor_deg10"][lab] = snr_floor(_curve(points, "snr", lab))
    for lab in _labels(points, "burst"):
        c = _curve(points, "burst", lab)
        a["shortest_usable_burst_ms"][lab] = shortest_usable_burst(c)
        a["shortest_usable_burst_fused_ms"][lab] = shortest_usable_burst(c, attr="fused_abs_deg")
    for lab in _labels(points, "spacing"):
        a["spacing"][lab] = spacing_summary(_curve(points, "spacing", lab))
    c2, c8 = _curve(points, "snr", "2 MSPS"), _curve(points, "snr", "8 MSPS")
    if c2 and c8:
        common = sorted(set(p.x for p in c2) & set(p.x for p in c8))
        d = [next(p.mean_abs_deg for p in c8 if p.x == x) - next(p.mean_abs_deg for p in c2 if p.x == x)
             for x in common]
        a["rate"] = {"floor_2msps": a["snr_floor_deg10"].get("2 MSPS"),
                     "floor_8msps": a["snr_floor_deg10"].get("8 MSPS"),
                     "mean_err_8_minus_2_deg": float(np.nanmean(d)) if d else None}
    return a


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

def _fmt(v, nd=1):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


def _table(points, sweep, x_name):
    labels = _labels(points, sweep)
    xs = sorted(set(p.x for p in points if p.sweep == sweep))
    by = {(p.label, p.x): p for p in points if p.sweep == sweep}
    head = f"| {x_name} | " + " | ".join(labels) + " |"
    sep = "|---|" + "---|" * len(labels)
    rows = []
    for x in xs:
        cells = []
        for lab in labels:
            p = by.get((lab, x))
            if p is None:
                cells.append("")
            elif p.detect_frac is None:
                cells.append(f"{_fmt(p.mean_abs_deg)}° (p90 {_fmt(p.p90_deg, 0)}°)")
            else:
                cells.append(f"{_fmt(p.mean_abs_deg)}° per burst, {_fmt(p.fused_abs_deg)}° fused, "
                             f"{100 * p.detect_frac:.0f}% det")
        rows.append(f"| {_fmt(x, 2)} | " + " | ".join(cells) + " |")
    return "\n".join([head, sep] + rows)


def write_results(points: list[Point], analysis: dict, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(
        {"generated": date.today().isoformat(), "points": [asdict(p) for p in points], "analysis": analysis},
        indent=1))
    n_b = max(1, len(set(p.x for p in points)))
    lines = [f"# Sweep results", "",
             f"Generated {date.today().isoformat()} by `tools/sweep.py`. Numbers only; the narrative is in "
             f"[README.md](README.md).", "",
             "Error = mean absolute circular error, degrees, over all bearings and trials (p90 = 90th "
             "percentile). Source is the noise-like LTE stand-in; switch timing known. "
             "SNR is in a 2 MHz reference bandwidth at both sample rates.", "",
             "## Computed findings", ""]
    for lab, v in analysis["snr_floor_deg10"].items():
        lines.append(f"- SNR floor for ≤ {ERR_THRESH_DEG:.0f}° error, **{lab}**: "
                     + (f"**{v:+.0f} dB** in 2 MHz" if v is not None else "never reached"))
    for lab, v in analysis["shortest_usable_burst_ms"].items():
        vf = analysis["shortest_usable_burst_fused_ms"].get(lab)
        lines.append(f"- Shortest usable burst at {lab} (≥ {100 * DETECT_THRESH:.0f}% detected and ≤ "
                     f"{ERR_THRESH_DEG:.0f}°): single burst "
                     + (f"**{v:.1f} ms**" if v is not None else "**never**")
                     + ", fused over 100 ms " + (f"**{vf:.1f} ms**" if vf is not None else "**never**"))
    for lab, s in analysis["spacing"].items():
        lines.append(f"- Spacing at {lab}: best {s['best']:.2f} λ ({s['best_err']:.1f}°), within 1° of best "
                     f"from {s['knee']:.2f} λ, " + (f"breaks down from {s['breaks_from']:.2f} λ"
                                                    if s["breaks_from"] is not None else "no breakdown seen"))
    r = analysis.get("rate") or {}
    if r:
        lines.append(f"- 8 MSPS minus 2 MSPS mean error, averaged over the SNR axis: "
                     f"{_fmt(r.get('mean_err_8_minus_2_deg'))}° (negative = 8 MSPS better)")
    lines += ["", "## SNR sweep", "", _table(points, "snr", "SNR in 2 MHz (dB)"), "",
              "## Burst length sweep (2 MSPS)", "", _table(points, "burst", "Burst (ms)"), "",
              "## Plate spacing sweep (2 MSPS)", "", _table(points, "spacing", "Spacing / λ"), ""]
    (out_dir / "results.md").write_text("\n".join(lines))


# --- plots (matplotlib is optional; only needed here) -----------------------

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # validated categorical slots 1-4, light mode
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def _style(ax, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_xlabel(xlabel, color=INK2, fontsize=10)
    ax.set_ylabel(ylabel, color=INK2, fontsize=10)


def _lines(ax, points, sweep, attr="mean_abs_deg", suffix="", dashed=False, legend=True):
    labels = _labels(points, sweep)
    for i, lab in enumerate(labels):
        c = _curve(points, sweep, lab)
        xs = [p.x for p in c]
        ys = [getattr(p, attr) for p in c]
        ax.plot(xs, ys, color=SERIES[i % len(SERIES)], linewidth=2, marker="o", markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1, label=lab + suffix,
                linestyle=(0, (4, 2)) if dashed else "-")
    if legend and len(ax.get_legend_handles_labels()[0]) >= 2:
        ax.legend(frameon=False, fontsize=9, labelcolor=INK2)


def _threshold(ax, y, text):
    ax.axhline(y, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(ax.get_xlim()[1], y, f" {text}", color=MUTED, fontsize=8, va="center", ha="left", clip_on=False)


def plot(points: list[Point], out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "sans-serif", "text.color": INK, "axes.titlecolor": INK,
                         "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE})
    out_dir = Path(out_dir)

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    _style(ax, "SNR in 2 MHz (dB)", "mean |bearing error| (deg)")
    _lines(ax, points, "snr")
    ax.set_ylim(0, None)
    _threshold(ax, ERR_THRESH_DEG, f"{ERR_THRESH_DEG:.0f}°")
    ax.set_title("Bearing error vs SNR, 20 ms capture, noise-like source", fontsize=11, loc="left")
    fig.tight_layout()
    fig.savefig(out_dir / "snr.png", dpi=150)
    plt.close(fig)

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.5, 6), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    _style(a1, "", "mean |bearing error| (deg)")
    _lines(a1, points, "burst", suffix=", single burst", legend=False)
    _lines(a1, points, "burst", attr="fused_abs_deg", suffix=", fused over 100 ms", dashed=True)
    a1.set_ylim(0, None)
    _threshold(a1, ERR_THRESH_DEG, f"{ERR_THRESH_DEG:.0f}°")
    a1.set_title("Per-burst bearing error vs burst length, 2 MSPS, 5 ms period", fontsize=11, loc="left")
    _style(a2, "burst length (ms)", "bursts detected (fraction)")
    _lines(a2, points, "burst", attr="detect_frac")
    a2.set_ylim(0, 1.05)
    _threshold(a2, DETECT_THRESH, f"{100 * DETECT_THRESH:.0f}%")
    fig.tight_layout()
    fig.savefig(out_dir / "burst.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    _style(ax, "element spacing / wavelength", "mean |bearing error| (deg)")
    _lines(ax, points, "spacing")
    ax.set_ylim(0, None)
    _threshold(ax, ERR_THRESH_DEG, f"{ERR_THRESH_DEG:.0f}°")
    plate = cellular_plate().spacing_m / wavelength(FREQ_HZ)
    ax.axvline(plate, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(plate, ax.get_ylim()[1], f" 3.5 in plate ({plate:.2f} λ)", color=MUTED, fontsize=8, va="top")
    ax.set_title("Bearing error vs plate spacing, 2 MSPS, 20 ms capture", fontsize=11, loc="left")
    fig.tight_layout()
    fig.savefig(out_dir / "spacing.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "sweeps")
    ap.add_argument("--trials", type=int, default=50)
    ap.add_argument("--bearings", type=int, default=8)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--quick", action="store_true", help="3 trials, 2 bearings, 2 points per sweep")
    ap.add_argument("--no-plot", action="store_true")
    a = ap.parse_args(argv)
    if a.quick:
        a.trials, a.bearings = 3, 2
    jobs = plan(a.trials, a.bearings, a.quick)
    print(f"{len(jobs)} jobs x {a.bearings} bearings x {a.trials} trials", file=sys.stderr)
    pts = run_jobs(jobs, a.workers)
    an = analyze(pts)
    write_results(pts, an, a.out)
    if not a.no_plot:
        plot(pts, a.out)
    print(json.dumps(an, indent=1))


if __name__ == "__main__":
    main()
