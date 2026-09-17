import numpy as np
import pytest

from bearing_df.array_geom import cellular_plate, wifi_plate, SquareArray
from bearing_df.sim import SimConfig, simulate
from bearing_df.dsp import (DFConfig, Calibration, estimate_bearing, estimate_switch_timing,
                            slice_baseband, estimate_carrier, wrap_deg)
from bearing_df.burst import bearings_from_bursts, detect_bursts
from bearing_df.tracker import Tracker, Ping
from bearing_df.geo import WedgeMap, Wedge, bearing_between, distance_m

ARR = cellular_plate()
BEARINGS = [0, 37, 90, 135, 200, 270, 333]


def err(est, true):
    return (est - true + 180) % 360 - 180


def test_spacing_rules():
    c = ARR.spacing_check(830e6)
    assert not c["ambiguous"] and 0.2 < c["spacing_over_lambda"] < 0.3
    assert wifi_plate().spacing_check(2.44e9)["spacing_over_lambda"] < 0.5
    assert SquareArray(0.3).spacing_check(830e6)["ambiguous"]


def test_physical_units_do_not_depend_on_fs():
    c2, c8 = DFConfig(fs=2e6), DFConfig(fs=8e6)
    # the 2 MSPS defaults are the historical sample counts
    assert (c2.edge_window, c2.numtaps) == (4, 401)
    # bandwidths and durations are identical at 8 MSPS; only the sample counts scale
    assert c2.slice_bw_hz == c8.slice_bw_hz
    assert c2.edge_window_s == c8.edge_window_s
    assert (c8.edge_window, c8.numtaps) == (16, 1605)
    assert c2.edge_window / 2e6 == c8.edge_window / 8e6
    tw2, tw8 = 2e6 / c2.numtaps, 8e6 / c8.numtaps       # FIR transition width scales as fs / numtaps
    assert abs(tw8 - tw2) / tw2 < 0.01


@pytest.mark.parametrize("b", BEARINGS)
def test_tone_bearing_clean(b):
    iq, _ = simulate(SimConfig(bearing_deg=b, snr_db=10, duration_s=0.02), ARR)
    e = estimate_bearing(iq, DFConfig())
    assert abs(err(e.bearing_deg, b)) < 3.0
    assert e.ok and e.sigma_deg < 5


@pytest.mark.parametrize("b", BEARINGS)
def test_tone_bearing_weak(b):
    iq, _ = simulate(SimConfig(bearing_deg=b, snr_db=-5, duration_s=0.02), ARR)
    e = estimate_bearing(iq, DFConfig())
    assert abs(err(e.bearing_deg, b)) < 8.0


@pytest.mark.parametrize("b", BEARINGS)
def test_wideband_source(b):
    """Noise-like source (LTE stand-in) at 0 dB SNR in 2 MHz."""
    iq, _ = simulate(SimConfig(bearing_deg=b, source="wideband", snr_db=0, duration_s=0.02), ARR)
    e = estimate_bearing(iq, DFConfig())
    assert abs(err(e.bearing_deg, b)) < 15.0


def test_carrier_offset_does_not_bias():
    """Frequency error -> DC in the discriminator -> rejected by lock-in."""
    outs = []
    for off in [-300e3, 12_345.0, 250e3]:
        iq, _ = simulate(SimConfig(bearing_deg=210, carrier_offset_hz=off, freq_drift_hz_per_s=2e3), ARR)
        outs.append(estimate_bearing(iq, DFConfig()).bearing_deg)
    assert max(abs(err(o, 210)) for o in outs) < 3.0


def test_switch_offset_known():
    for off in [10, 33.0, 61]:
        iq, _ = simulate(SimConfig(bearing_deg=120), ARR, switch_offset_samples=int(off))
        e = estimate_bearing(iq, DFConfig(switch_start_sample=off))
        assert abs(err(e.bearing_deg, 120)) < 3.0


def test_switch_timing_recovery():
    fs = 2e6
    for off in [0, 10, 33, 61]:
        iq, _ = simulate(SimConfig(bearing_deg=120, snr_db=5, duration_s=0.02), ARR, switch_offset_samples=off)
        fc, _ = estimate_carrier(iq, fs)
        x = slice_baseband(iq, fs, fc, 400e3)
        t0, _ = estimate_switch_timing(x, fs, 8e3)
        dwell = fs / (4 * 8e3)
        d = (t0 - off + dwell / 2) % dwell - dwell / 2
        assert abs(d) < 3.0   # samples
        # recovered timing gives the bearing modulo 90 deg
        e = estimate_bearing(iq, DFConfig(switch_start_sample=None))
        assert abs((err(e.bearing_deg, 120) + 45) % 90 - 45) < 5.0


def test_rotation_dir_and_calibration():
    iq, _ = simulate(SimConfig(bearing_deg=75, rotation_dir=-1), ARR)
    e = estimate_bearing(iq, DFConfig(cal=Calibration(rotation_dir=-1, offset_deg=0)))
    cal = Calibration.from_known_source(e.lockin, 75, rotation_dir=-1)
    for b in [10, 190, 300]:
        iq, _ = simulate(SimConfig(bearing_deg=b, rotation_dir=-1), ARR)
        e2 = estimate_bearing(iq, DFConfig(cal=cal))
        assert abs(err(e2.bearing_deg, b)) < 3.0


def test_switch_glitch_tolerated():
    iq, _ = simulate(SimConfig(bearing_deg=250, switch_glitch=2.0, snr_db=10), ARR)
    e = estimate_bearing(iq, DFConfig(edge_window_s=3e-6))
    assert abs(err(e.bearing_deg, 250)) < 6.0


def test_bursts_detected_and_fused():
    iq, _ = simulate(SimConfig(bearing_deg=222, source="wideband", snr_db=3, duration_s=0.1, burst=True), ARR)
    res = bearings_from_bursts(iq, DFConfig())
    assert 15 <= len(res) <= 22            # 20 bursts in 100 ms
    tr = Tracker()
    for b, e in res:
        st = tr.add(Ping(t=b.start / 2e6, bearing_deg=e.bearing_deg, sigma_deg=e.sigma_deg,
                         strength_db=b.mean_db, ok=e.ok))
    assert st.n_used >= 5
    assert abs(err(st.bearing_deg, 222)) < 15.0


def test_no_false_bursts_on_noise():
    rng = np.random.default_rng(3)
    x = (rng.standard_normal(200_000) + 1j * rng.standard_normal(200_000)) / np.sqrt(2)
    bursts, _ = detect_bursts(x, 2e6)
    assert len(bursts) == 0


def test_tracker_trends():
    rng = np.random.default_rng(1)
    tr = Tracker(window_s=15)
    for i in range(20):
        st = tr.add(Ping(t=i, bearing_deg=100 - 1.5 * i + rng.normal(0, 6), sigma_deg=6,
                         strength_db=-95 + 0.6 * i + rng.normal(0, 1)))
    assert st.bearing_trend == "left" and st.strength_trend == "rising" and st.approaching
    tr = Tracker(window_s=15)
    for i in range(20):
        st = tr.add(Ping(t=i, bearing_deg=200 + rng.normal(0, 10), sigma_deg=10,
                         strength_db=-95 + rng.normal(0, 1)))
    assert st.bearing_trend == "steady" and st.strength_trend == "flat"
    assert st.strength_hwm_db >= st.strength_db


def test_wedge_fix_from_moving_platform():
    rng = np.random.default_rng(1)
    tlat, tlon = 39.72, -84.10
    wm = WedgeMap((39.66, -84.20), size_m=30_000, cell_m=150)
    for i in range(30):
        lat, lon, hdg = 39.65, -84.26 + 0.004 * i, 90.0
        rel = (bearing_between(lat, lon, tlat, tlon) - hdg) % 360
        p = Ping(t=3 * i, bearing_deg=rel + rng.normal(0, 8), sigma_deg=8, strength_db=-90,
                 lat=lat, lon=lon, heading_deg=hdg)
        wm.add(Wedge(lat, lon, p.abs_bearing_deg, 8, t=p.t))
    f = wm.fix()
    assert distance_m(f.lat, f.lon, tlat, tlon) < 1500


def test_wrap():
    assert wrap_deg(-10) == 350 and wrap_deg(370) == 10


# --- PRACH -----------------------------------------------------------------
from bearing_df.prach import PRACHDetector, generate_prach, despread, zc_sequence, N_ZC
from bearing_df.burst import bearings_from_prach


def test_zc_is_constant_amplitude_and_orthogonal_ish():
    x = zc_sequence(129)
    assert np.allclose(np.abs(x), 1.0)
    c = np.abs(np.fft.ifft(np.fft.fft(x) * np.conj(np.fft.fft(zc_sequence(130)))))
    assert c.max() < 0.2 * N_ZC   # different roots barely correlate


def test_prach_detect_clean_and_weak():
    fs = 2e6
    rng = np.random.default_rng(0)
    p = generate_prach(129, fs, center_hz=300e3, cyclic_shift=200)
    noise = (rng.standard_normal(len(p)) + 1j * rng.standard_normal(len(p))) / np.sqrt(2)
    det = PRACHDetector(fs, center_hz=300e3, auto_lock=False)
    n_cp = int(fs * 103.125e-6)
    for snr in [10, -10]:
        m, u, d, bo = det.score_window((p * 10 ** (snr / 20) + noise)[n_cp:n_cp + 1600])
        assert u == 129 and m > 25


def test_prach_no_false_alarms_on_noise():
    rng = np.random.default_rng(7)
    x = (rng.standard_normal(300_000) + 1j * rng.standard_normal(300_000)) / np.sqrt(2)
    assert PRACHDetector(2e6, center_hz=300e3).detect(x) == []


def test_prach_with_array_switching_minus_15db():
    iq, _ = simulate(SimConfig(source="prach", snr_db=-15, bearing_deg=222, duration_s=0.05,
                               burst_period_s=10e-3), ARR)
    hits = PRACHDetector(2e6, center_hz=300e3).detect(iq)
    assert len(hits) == 5 and all(h.root == 129 for h in hits)


def test_despread_bearing_minus_10db():
    for b in [30, 222, 300]:
        iq, _ = simulate(SimConfig(source="prach", snr_db=-10, bearing_deg=b, duration_s=0.05,
                                   burst_period_s=10e-3), ARR)
        res = bearings_from_prach(iq, DFConfig(), PRACHDetector(2e6, center_hz=300e3))
        assert len(res) >= 4
        tr = Tracker()
        for h, e in res:
            st = tr.add(Ping(t=h.start / 2e6, bearing_deg=e.bearing_deg, sigma_deg=max(e.sigma_deg, 5),
                             strength_db=h.metric, ok=True))
        assert abs(err(st.bearing_deg, b)) < 20.0
