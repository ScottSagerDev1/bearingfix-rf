"""Walk one real hackrf_transfer recording through every stage of the bearing pipeline.

    python explore_capture.py capture.iq --center-hz 830e6 [--fs 2e6] [--frot 8064.5]
                              [--switch-start N | --recover-timing] [--cal calibration.json]

Companion to explore_sim.py: same six stages, same prints, but stage 1 loads
a recording (interleaved signed 8-bit I/Q, as written by ``hackrf_transfer -r``)
instead of simulating one. The true bearing is unknown, so every "error" line
becomes the raw value. Each stage first prints the matching line from
docs/explore_sim_sample_output.txt so sim and reality can be read side by side.
Stage 6 becomes a single-position wedge: a static capture can't drive past anything.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from bearing_df.array_geom import SquareArray, wavelength
from bearing_df.hackrf_io import read_iq_int8
from bearing_df.dsp import (DFConfig, Calibration, estimate_bearing, estimate_carrier, slice_baseband,
                            fm_discriminate, lockin, lockin_noise_floor, circ_mean_deg)
from bearing_df.burst import bearings_from_bursts
from bearing_df.tracker import Tracker, Ping
from bearing_df.geo import WedgeMap, Wedge

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("path", help="interleaved signed 8-bit I/Q from hackrf_transfer -r")
ap.add_argument("--center-hz", type=float, required=True, help="RF centre frequency the capture was made at")
ap.add_argument("--fs", type=float, default=DFConfig().fs, help="sample rate (default %(default)s)")
ap.add_argument("--frot", type=float, default=DFConfig().f_rot, help="rotation rate = fs / (4 * dwell samples)")
ap.add_argument("--switch-start", type=float, default=0.0, help="sample index where element 0 starts")
ap.add_argument("--recover-timing", action="store_true",
                help="estimate switch timing from the capture (bearing then ambiguous by 90 deg until calibrated)")
ap.add_argument("--cal", default="", help="calibration.json from `python -m bearing_df.cli calibrate`")
ap.add_argument("--spacing-in", type=float, default=3.5, help="plate side in inches")
ap.add_argument("--max-seconds", type=float, default=0.1, help="how much of the file to read")
ap.add_argument("--lat", type=float, default=39.65)
ap.add_argument("--lon", type=float, default=-84.26)
ap.add_argument("--heading", type=float, default=90.0, help="compass direction the plate's forward mark points")
a = ap.parse_args()

FS, F_ROT = a.fs, a.frot
arr = SquareArray(spacing_m=a.spacing_in * 0.0254)
cfg = DFConfig(fs=FS, f_rot=F_ROT, switch_start_sample=None if a.recover_timing else a.switch_start)
if a.cal:
    cfg.cal = Calibration(**json.loads(Path(a.cal).read_text()))
wrap = lambda d: (d + 180) % 360 - 180
SAMPLE = Path(__file__).with_name("docs") / "explore_sim_sample_output.txt"


def sim_line(stage):
    """The matching line from explore_sim.py's sample run, for side-by-side reading."""
    try:
        lines = SAMPLE.read_text().splitlines()
    except OSError:
        return "(docs/explore_sim_sample_output.txt not found)"
    key = "   FIX" if stage == 6 else f"{stage}."
    return next((ln.strip() for ln in lines if ln.startswith(key)), "(no sample line)")


print(f"plate {a.spacing_in} in = {arr.spacing_m / wavelength(a.center_hz):.2f} wavelengths at {a.center_hz/1e6:.0f} MHz;"
      f" dwell {FS / (4 * F_ROT):.1f} samples per element, {4 * F_ROT:.0f} switch edges/s\n")

# ---- 1. raw I/Q: what the HackRF wrote to disk ------------------------------
# The file is I, Q, I, Q ... each a signed 8-bit number. read_iq_int8 (the same
# loader the CLI uses) pairs them into complex numbers scaled to +-1. The sim
# normalised the phone's power to 1.0; here the radio's gain sets the level,
# and the split between phone and noise is not known.
iq = read_iq_int8(a.path, max_samples=int(a.max_seconds * FS))
peak = float(np.max(np.abs(iq)))
print(f"   sim: {sim_line(1)}")
print(f"1. raw I/Q: {len(iq)} samples ({len(iq) / FS * 1e3:.1f} ms), first three = {np.round(iq[:3], 3)}")
print(f"   mean power {np.mean(np.abs(iq) ** 2):.4f}, peak |sample| {peak:.2f} of 1.0"
      f" ({'CLIPPING - lower the gain' if peak > 0.99 else 'no clipping'}); phone-vs-noise split unknown\n")

# ---- 2. the switching tone in the spectrum ----------------------------------
# Find the strongest thing in the capture and call it the carrier. For a real
# phone it is a lump tens to hundreds of kHz wide, so "the carrier" can be off
# by tens of kHz; step 3 shows why that's harmless. Then mix it to 0 Hz,
# low-pass to 400 kHz, take the sample-to-sample phase step (FM discriminator)
# and lock in at f_rot: if the Opera Cake is switching, a tone is there.
carrier_hz, _ = estimate_carrier(iq, FS)
spec = np.abs(np.fft.fftshift(np.fft.fft(iq))) ** 2
freqs = np.fft.fftshift(np.fft.fftfreq(len(iq), 1 / FS))
db_at = lambda f: 10 * np.log10(spec[np.argmin(np.abs(freqs - f))] + 1e-30)
x = slice_baseband(iq, FS, carrier_hz, cfg.slice_bw_hz, cfg.numtaps)
d = fm_discriminate(x)
tone, floor = abs(lockin(d, FS, F_ROT)), lockin_noise_floor(d, FS, F_ROT)
print(f"   sim: {sim_line(2)}")
print(f"2. carrier found at {carrier_hz / 1e3:+.1f} kHz from centre = {(a.center_hz + carrier_hz) / 1e6:.4f} MHz absolute")
print("   raw spectrum, dB relative to the carrier bin (clean only for a tone; a phone buries them):  "
      + "  ".join(f"{k:+d}f_rot {db_at(carrier_hz + k * F_ROT) - db_at(carrier_hz):+5.1f}" for k in (-2, -1, 1, 2)))
print(f"   discriminator lock-in at f_rot: {tone:.4f}, off-frequency floor {floor:.4f}"
      f" -> {20 * np.log10(tone / floor):.1f} dB above the floor"
      f" ({'switching is visible' if tone / floor > 2 else 'weak: is the Opera Cake in time mode, and is f_rot right?'})\n")

# ---- 3. phase per antenna ---------------------------------------------------
# Same as the sim: average 2 us before and after each switch edge, take the
# angle of after * conj(before) = the phase step into the next antenna, group
# by antenna, subtract the average step (the leftover frequency error, a DC
# term the lock-in would ignore anyway). Truth is unknown, so "geometry" is
# what the plate predicts AT THE BEARING STEP 4 FINDS: it checks the shape of
# the pattern, not the answer. The ~0.65 filter-smear scale still applies.
e = estimate_bearing(iq, cfg)                      # the real pipeline, run once; also gives us the switch timing
start = e.detail["switch_start_sample"]            # --switch-start, or the timing recovered from the capture
w, dwell = cfg.edge_window, FS / (4 * F_ROT)
edges = np.arange(np.mod(start, dwell), len(x) - w, dwell)
k = np.round((edges - start) / dwell).astype(int)  # edge k steps INTO element k % 4 (negative k wraps correctly)
keep = edges >= w
idx, k = np.ceil(edges[keep] - 1e-9).astype(int), k[keep]
before = sum(x[idx - 1 - m] for m in range(w)) / w
after = sum(x[idx + m] for m in range(w)) / w
step_deg = np.rad2deg(np.angle(after * np.conj(before)))
dc = circ_mean_deg(step_deg)[0]
into = [wrap(circ_mean_deg(step_deg[k % 4 == g])[0] - dc) for g in range(4)]
meas = np.cumsum([0.0] + [into[g] for g in (1, 2, 3)])
model = np.rad2deg(arr.element_phases(e.bearing_deg, a.center_hz)); model -= model[0]
scale = np.dot(wrap(meas), wrap(model)) / max(np.dot(wrap(model), wrap(model)), 1e-9)
print(f"   sim: {sim_line(3)}")
print(f"3. {len(idx)} switch edges. Average step {wrap(dc):+.1f} deg = leftover frequency error, removed."
      f" Reads as {wrap(dc) / 360 * FS / w / 1e3:+.1f} kHz (true offset unknown).")
print(f"   Phase of each antenna relative to antenna 0 (degrees); geometry at step 4's bearing, scale ~{scale:.2f}:")
for g in range(4):
    print(f"   antenna {g} at compass {45 + 90 * g:3d}:  measured {wrap(meas[g]):+7.1f}   geometry says {wrap(model[g]):+7.1f}")
print(f"   (loop closes: step back into antenna 0 = {into[0]:+.1f}, should be {wrap(-meas[3]):+.1f})"
      + ("\n   timing was recovered from the capture, so which antenna is 'antenna 0' is unknown:"
         " labels may be rotated by 90, 180 or 270 deg" if a.recover_timing else "") + "\n")

# ---- 4. the bearing math ----------------------------------------------------
# The four steps around the square trace one cycle of a sine whose PHASE is the
# bearing. Multiply each step by exp(-j 2 pi f_rot t), average: one complex
# number L. bearing = calibration offset - angle(L). Without a calibration
# file the offset is the sim's 90 deg, and a real plate adds a constant
# (cable, switch, filter delay) that `cli calibrate` measures once.
ref = np.exp(-2j * np.pi * F_ROT * (idx - 0.5 - start) / FS)
L = np.mean(np.deg2rad(step_deg) * ref)
by_hand = cfg.cal.bearing_from_lockin(L)
print(f"   sim: {sim_line(4)}")
print(f"4. L = {L:.4f}  angle {np.rad2deg(np.angle(L)):+.1f}  ->  bearing {by_hand:.1f} by hand,"
      f" {e.bearing_deg:.1f} from estimate_bearing()")
print(f"   true bearing unknown. sigma {e.sigma_deg:.1f} (spread across {e.n_blocks} sub-blocks),"
      f" lock-in snr {e.snr_lockin_db:.1f} dB, ok={e.ok}"
      + ("" if a.cal else "; no --cal, so this is relative to the plate plus an unmeasured hardware constant") + "\n")

# ---- 5. fusion over several bursts -----------------------------------------
# A phone with no bars transmits in bursts. Find them, get one bearing each,
# fuse on the circle weighted by confidence. A phone on a call is on more
# than half the time, so the burst detector sees no "floor" and finds
# nothing; then step 4 already used the whole capture and is the answer.
res = bearings_from_bursts(iq, cfg)
tr, st = Tracker(), None
for b, eb in res:
    st = tr.add(Ping(t=b.start / FS, bearing_deg=eb.bearing_deg, sigma_deg=eb.sigma_deg, strength_db=b.mean_db, ok=eb.ok))
print(f"   sim: {sim_line(5)}")
if st is None or st.n_used == 0:
    print(f"5. {len(res)} bursts usable in {len(iq) / FS * 1e3:.0f} ms: continuous source, or too weak to detect; step 4 stands\n")
else:
    print(f"5. {len(res)} bursts in {len(iq) / FS * 1e3:.0f} ms, per-burst bearings: "
          + " ".join(f"{eb.bearing_deg:.0f}" for _, eb in res))
    print(f"   fused {st.bearing_deg:.1f} +- {st.half_width_deg:.1f} from {st.n_used} pings (true bearing unknown)\n")

# ---- 6. one wedge, not a drive ----------------------------------------------
# The sim drove past the phone and let twelve wedges cross. A static capture
# is one position, so it lays one wedge: a fan along the bearing, as wide as
# the uncertainty. One wedge tells you which way to drive; the crossing is
# what a second and third position will add.
bearing, half = (st.bearing_deg, st.half_width_deg) if st and st.n_used else (e.bearing_deg, e.sigma_deg)
abs_bearing = (a.heading + bearing) % 360
wm = WedgeMap((a.lat, a.lon), size_m=30_000, cell_m=150)
wm.add(Wedge(a.lat, a.lon, abs_bearing, max(half, 3.0), t=0.0))
f = wm.fix()
print(f"   sim: {sim_line(6)}")
print(f"6. one wedge from {a.lat}, {a.lon}: absolute bearing {abs_bearing:.1f} +- {max(half, 3.0):.1f}"
      f" (heading {a.heading} + relative {bearing:.1f})")
print(f"   no fix from one position: the map's best cell ({f.lat:.4f}, {f.lon:.4f}) is just somewhere along the wedge,"
      f" 50% spread {f.spread_m:.0f} m. Move, capture again, let the wedges cross.")
