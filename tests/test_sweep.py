"""Tiny end-to-end run of tools/sweep.py so it can't rot when the pipeline changes."""
from tools.sweep import plan, run_jobs, analyze, write_results


def test_sweep_smoke(tmp_path):
    jobs = plan(trials=2, n_bearings=2, quick=True)
    pts = run_jobs(jobs, workers=1)
    assert {p.sweep for p in pts} == {"snr", "burst", "spacing"}
    assert all(p.n > 0 for p in pts)

    hi = max((p for p in pts if p.sweep == "snr" and p.label == "2 MSPS"), key=lambda p: p.x)
    assert hi.mean_abs_deg < 15.0, "pipeline no longer resolves a strong source"

    long_burst = max((p for p in pts if p.sweep == "burst"), key=lambda p: p.x)
    assert long_burst.detect_frac > 0.5

    a = analyze(pts)
    assert "snr_floor_deg10" in a and "2 MSPS" in a["snr_floor_deg10"]
    write_results(pts, a, tmp_path)
    assert (tmp_path / "results.md").exists() and (tmp_path / "results.json").exists()
