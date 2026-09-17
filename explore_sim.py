"""Walk one simulated phone through every stage of the bearing pipeline.

    python explore_sim.py

Not part of the test suite. Change the knobs below and re-run.
"""
import numpy as np
from bearing_df.array_geom import SquareArray, wavelength
from bearing_df.sim import SimConfig, simulate
from bearing_df.dsp import (DFConfig, estimate_bearing, estimate_carrier, slice_baseband,
                            fm_discriminate, lockin, lockin_noise_floor, circ_mean_deg)
from bearing_df.burst import bearings_from_bursts, bearings_from_prach
from bearing_df.prach import PRACHDetector
from bearing_df.tracker import Tracker, Ping
from bearing_df.geo import WedgeMap, Wedge, bearing_between, distance_m

# ---- knobs -----------------------------------------------------------------
TRUE_BEARING_DEG = 137.0   # where the phone is, compass degrees from the plate's forward mark
SNR_DB = 3.0               # phone power vs noise in the 2 MHz capture; sweeps say < -7 dB falls apart
BURST_MS = 1.0             # how long each transmission lasts; 1 ms = one LTE subframe, try 0.4 or 2.0
SPACING_IN = 3.5           # plate side in inches; cellular_plate() is 3.5. Try 2.0 (weak) or 6.5 (ambiguous, ~lambda/2)
SOURCE = "wideband"        # "wideband" = noise-like LTE stand-in (realistic); "tone" = clean carrier (ideal); "prach" = one LTE random-access preamble per 5 ms, 1.08 MHz wide
SEED = 0                   # random seed for the noise; change it to see a different draw of the same setup, keep it to make runs repeatable
# ----------------------------------------------------------------------------

FREQ_HZ, FS, F_ROT = 830e6, 2e6, 8000.0
arr = SquareArray(spacing_m=SPACING_IN * 0.0254)
cfg = DFConfig()                      # fs 2 MSPS, f_rot 8 kHz, 400 kHz slice, 2 us edge window
err = lambda est, true: (est - true + 180) % 360 - 180
print(f"plate {SPACING_IN} in = {arr.spacing_m / wavelength(FREQ_HZ):.2f} wavelengths at {FREQ_HZ/1e6:.0f} MHz;"
      f" dwell {FS / (4 * F_ROT):.1f} samples per element, {4 * F_ROT:.0f} switch edges/s\n")

# ---- 1. raw I/Q: what the HackRF hands us -----------------------------------
# 20 ms of a continuous source. Every sample is a complex number I + jQ whose
# angle is the carrier phase seen by whichever antenna the Opera Cake has
# selected at that instant. The bearing is hiding in how that phase jumps at
# each switch.
sc = SimConfig(fs=FS, f_rot=F_ROT, freq_hz=FREQ_HZ, bearing_deg=TRUE_BEARING_DEG,
               snr_db=SNR_DB, source=SOURCE, duration_s=0.02, seed=SEED)
iq, _ = simulate(sc, arr)
print(f"1. raw I/Q: {len(iq)} samples, first three = {np.round(iq[:3], 3)}")
print(f"   mean power {np.mean(np.abs(iq)**2):.3f} (signal + noise; the phone alone would be"
      f" {10**(SNR_DB/10) / (1 + 10**(SNR_DB/10)):.2f} of that)\n")

# ---- 2. the switching tone in the spectrum ----------------------------------
# Switching antennas modulates the carrier's phase in a staircase. Phase
# modulation puts sidebands at carrier +- f_rot, +- 2 f_rot... For a clean
# tone you can see them in the raw spectrum. For the noise-like source you
# can't: the source is 180 kHz wide and the +-8 kHz sidebands are buried in
# it, and "the carrier" is just the strongest bin in that lump (so the
# estimate below can be off by tens of kHz — step 3 shows why that's fine).
# The PRACH source is the same story, only wider (1.08 MHz).
carrier_hz, _ = estimate_carrier(iq, FS)
spec = np.abs(np.fft.fftshift(np.fft.fft(iq))) ** 2
freqs = np.fft.fftshift(np.fft.fftfreq(len(iq), 1 / FS))
db_at = lambda f: 10 * np.log10(spec[np.argmin(np.abs(freqs - f))] + 1e-30)
print(f"2. carrier found at {carrier_hz/1e3:+.1f} kHz (sim put "
      + (f"the PRACH block's centre at {sc.prach_center_hz/1e3:+.1f} kHz; carrier_offset_hz does not apply" if SOURCE == 'prach'
         else f"it at {sc.carrier_offset_hz/1e3:+.1f} kHz") + ")")
print(f"   raw spectrum, dB relative to the carrier bin ({'clean sidebands' if SOURCE == 'tone' else 'buried: PRACH block is 1.08 MHz wide' if SOURCE == 'prach' else 'buried: source is 180 kHz wide'}):  "
      + "  ".join(f"{k:+d}f_rot {db_at(carrier_hz + k*F_ROT) - db_at(carrier_hz):+5.1f}" for k in (-2, -1, 1, 2)))
# That is why the pipeline doesn't read sidebands. It mixes the carrier to
# 0 Hz, low-passes to 400 kHz, then takes the phase step sample-to-sample (an
# FM discriminator). In that signal the switching is a clean tone at f_rot
# whatever the source looks like. "Lock-in" = correlate against
# exp(-j 2 pi f_rot t) = pick out that one tone and ignore everything else.
x = slice_baseband(iq, FS, carrier_hz, cfg.slice_bw_hz, cfg.numtaps)
d = fm_discriminate(x)
tone, floor = abs(lockin(d, FS, F_ROT)), lockin_noise_floor(d, FS, F_ROT)
print(f"   discriminator lock-in at f_rot: {tone:.4f}, off-frequency floor {floor:.4f}"
      f" -> {20*np.log10(tone/floor):.1f} dB above the floor\n")

# ---- 3. phase per antenna ---------------------------------------------------
# At each switch edge, average a 2 us window before and after and take the
# angle of after * conj(before): that is the phase step from one antenna to
# the next. Group the steps by which antenna we stepped INTO and average.
w, dwell = cfg.edge_window, FS / (4 * F_ROT)
edges = np.arange(0, len(x) - w, dwell)
k = np.round(edges / dwell).astype(int)                # edge number; edge k lands on element k % 4
idx, k = np.ceil(edges - 1e-9).astype(int)[edges >= w], k[edges >= w]
before = sum(x[idx - 1 - m] for m in range(w)) / w
after = sum(x[idx + m] for m in range(w)) / w
step_deg = np.rad2deg(np.angle(after * np.conj(before)))
# The carrier estimate was off by some kHz. A frequency error is a phase ramp,
# so it adds the SAME amount to every step (a DC term). The true steps around
# the square sum to zero, so the average step IS that error: subtract it.
# (This is the whole reason the pipeline is immune to tuning error.)
dc = circ_mean_deg(step_deg)[0]
into = [err(circ_mean_deg(step_deg[k % 4 == g])[0] - dc, 0) for g in range(4)]   # mean step into element g
meas = np.cumsum([0.0] + [into[g] for g in (1, 2, 3)])                            # phase of element g vs element 0
model = np.rad2deg(arr.element_phases(TRUE_BEARING_DEG, FREQ_HZ)); model -= model[0]
# Expect the measured phases to be the geometry's shape but SMALLER by a
# constant factor: the 400 kHz filter smears each edge over ~2.5 us and the
# 2 us windows sit inside that smear. A common scale doesn't move the
# bearing (step 4 needs the pattern's phase, not its size) — it also shrinks
# the frequency-error reading above by the same factor.
scale = np.dot(err(meas, 0), err(model, 0)) / np.dot(err(model, 0), err(model, 0))
print(f"3. {len(idx)} switch edges. Average step {err(dc, 0):+.1f} deg = leftover frequency error, removed."
      f" Reads as {err(dc, 0) / 360 * FS / w / 1e3:+.1f} kHz; truly {(sc.carrier_offset_hz - carrier_hz) / 1e3:+.1f} kHz.")
print(f"   Phase of each antenna relative to antenna 0 (degrees); filter smear scales them by ~{scale:.2f}:")
for g in range(4):
    print(f"   antenna {g} at compass {45 + 90*g:3d}:  measured {err(meas[g], 0):+7.1f}   geometry says {err(model[g], 0):+7.1f}")
print(f"   (loop closes: step back into antenna 0 = {into[0]:+.1f}, should be {err(-meas[3], 0):+.1f})\n")

# ---- 4. the bearing math ----------------------------------------------------
# The four steps around the square trace one cycle of a sine whose PHASE is the
# bearing: the antenna nearest the phone leads. Multiplying each step by
# exp(-j 2 pi f_rot t) and averaging (the lock-in again, edges only) gives one
# complex number L. angle(L) is where in the rotation the peak fell. With
# element 0 starting at sample 0 and clockwise switching, bearing = 90 - angle(L);
# real hardware adds a constant that one calibration measures.
ref = np.exp(-2j * np.pi * F_ROT * (idx - 0.5) / FS)
L = np.mean(np.deg2rad(step_deg) * ref)
by_hand = (90 - np.rad2deg(np.angle(L))) % 360
e = estimate_bearing(iq, cfg)
print(f"4. L = {L:.4f}  angle {np.rad2deg(np.angle(L)):+.1f}  ->  bearing {by_hand:.1f} by hand,"
      f" {e.bearing_deg:.1f} from estimate_bearing()")
print(f"   error {err(e.bearing_deg, TRUE_BEARING_DEG):+.1f} deg, sigma {e.sigma_deg:.1f}"
      f" (spread across {e.n_blocks} sub-blocks), ok={e.ok}\n")

# ---- 5. fusion over several bursts -----------------------------------------
# A real phone transmits in bursts. 100 ms with a 5 ms period = 20 bursts of
# BURST_MS each. Each burst gives one noisy bearing; the tracker averages them
# on the circle, weighting by each burst's confidence.
sc_b = SimConfig(**{**sc.__dict__, "burst": True, "burst_on_s": BURST_MS * 1e-3, "duration_s": 0.1})
iq_b, _ = simulate(sc_b, arr)
# A PRACH preamble is a known Zadoff-Chu sequence 1.08 MHz wide, which the
# 400 kHz slice above cannot hold. So for PRACH: find each preamble by
# correlating against its root, multiply that sequence back out ("despread")
# so the wide block collapses to a tone, then run the same chain with a
# narrow slice. (The sim sends one 1 ms preamble per 5 ms; BURST_MS is ignored.)
if SOURCE == "prach":
    det = PRACHDetector(FS, center_hz=sc.prach_center_hz, roots=[sc.prach_root])
    burst_bearings = lambda iq_: bearings_from_prach(iq_, cfg, det)
    strength_db = lambda h: 10 * np.log10(h.metric)          # correlator peak/mean, in dB
    what = f"PRACH preambles, each despread against prach_root={sc.prach_root} first"
else:
    burst_bearings = lambda iq_: bearings_from_bursts(iq_, cfg)
    strength_db = lambda b: b.mean_db
    what = f"bursts of {BURST_MS} ms"
tr, st = Tracker(), None
res = burst_bearings(iq_b)
for b, eb in res:
    st = tr.add(Ping(t=b.start / FS, bearing_deg=eb.bearing_deg, sigma_deg=eb.sigma_deg, strength_db=strength_db(b), ok=eb.ok))
per_burst = [err(eb.bearing_deg, TRUE_BEARING_DEG) for _, eb in res]
print(f"5. {len(res)} {what}, per-burst errors: " + " ".join(f"{v:+.0f}" for v in per_burst))
print(f"   mean |error| per burst {np.mean(np.abs(per_burst)):.1f}  ->  fused {st.bearing_deg:.1f} +- {st.half_width_deg:.1f},"
      f" error {err(st.bearing_deg, TRUE_BEARING_DEG):+.1f} deg from {st.n_used} pings\n")

# ---- 6. the wedge map -------------------------------------------------------
# Drive east along a road 8 km south of the phone, from well before it to
# well past it. At each stop, repeat step 5 for the bearing the phone really
# is at from there, and lay a wedge on the map: a fan of cells along that
# bearing, as wide as the fused uncertainty. Wedges from different positions
# cross where the phone is; the pile-up is the fix. A short drive gives
# nearly parallel wedges and a long smear; passing the phone is what works.
tlat, tlon = 39.72, -84.10
wm = WedgeMap((39.66, -84.20), size_m=30_000, cell_m=150)
print("6. stop  true rel. bearing  measured")
for i in range(12):
    lat, lon, hdg = 39.65, -84.26 + 0.015 * i, 90.0
    rel = (bearing_between(lat, lon, tlat, tlon) - hdg) % 360
    iq_i, _ = simulate(SimConfig(**{**sc_b.__dict__, "bearing_deg": rel, "seed": SEED + 100 + i}), arr)
    tr, st = Tracker(), None
    for b, eb in burst_bearings(iq_i):
        st = tr.add(Ping(t=b.start / FS, bearing_deg=eb.bearing_deg, sigma_deg=eb.sigma_deg, strength_db=strength_db(b), ok=eb.ok))
    if st is None or st.bearing_deg is None:
        print(f"   {i:4d}  {rel:9.1f}          no fix: no accepted pings")
        continue
    wm.add(Wedge(lat, lon, (hdg + st.bearing_deg) % 360, max(st.half_width_deg, 3.0), t=3.0 * i))
    print(f"   {i:4d}  {rel:9.1f}          {st.bearing_deg:6.1f} +- {st.half_width_deg:4.1f}")
f = wm.fix()
print(f"\n   FIX {f.lat:.4f}, {f.lon:.4f}: {distance_m(f.lat, f.lon, tlat, tlon):.0f} m from the phone,"
      f" 50% spread {f.spread_m:.0f} m, from {f.n_wedges} wedges")
