# bearing_df — pseudo-Doppler direction finding core

Python package for the HackRF Pro + Opera Cake 4-element switched array.
Everything here runs and is tested **without hardware** against a simulator
that produces what the HackRF will see. When the radio arrives, the same
code runs on recorded `.iq` files and then live.

## What is here

| module | job | status |
|---|---|---|
| `array_geom.py` | square array geometry, λ/4 spacing check, element phase model | done, tested |
| `sim.py` | synthetic switched-array IQ: tone or noise-like (LTE stand-in), bursty, switch glitches, drift | done |
| `dsp.py` | **the hard part** — carrier find, slice, FM discriminator, edge-only lock-in at f_rot, bearing, confidence, switch-timing recovery, calibration | done, tested |
| `burst.py` | energy burst detector + per-burst bearing | done, tested |
| `tracker.py` | fuse sparse pings; strength bar + high-water mark; approaching/receding + left/right trend with a significance test | done, tested |
| `geo.py` | wedge map: pings from a moving platform accumulate on a grid, peak = fix | done, tested |
| `hackrf_io.py` | read/write hackrf_transfer files, capture, Opera Cake time-mode setup | flags verified against 2026.01.3 host-tools source; **switch timing and Pro behaviour unverified until hardware** |
| `cli.py` | `sim`, `file`, `calibrate`, `drive` commands | done |
| `tests/` | 32 pytest cases | passing |

## Simulation results (2 MSPS, f_rot = 8 kHz, 3.5 in plate @ 830 MHz)

* Clean tone, 10 dB SNR, 20 ms: bearing error < 1–2°, sigma ≈ 1°.
* Tone at −5 dB SNR (in 2 MHz): error < 5°.
* Noise-like 180 kHz source at 0 dB SNR, 20 ms: error < 10°, sigma 10–15°.
* Bursty noise-like source (1 ms every 5 ms) at 0–3 dB, 100 ms: per-burst
  bearings scatter ±30°, fused bearing within ~10° from 6–12 pings.
* 30 pings with 8° noise from a truck driving 10 km past a target 7 km off:
  wedge-map fix within ~800 m.
* Carrier offset up to ±300 kHz and 2 kHz/s drift: no bearing bias (the
  discriminator turns frequency error into DC, which the lock-in rejects).
* Full sweeps over SNR, burst length, plate spacing and sample rate, with
  the physics behind each failure mode: [sweeps/README.md](sweeps/README.md).

## Two things learned that change the build

1. **Do not narrowband-filter below a few × f_rot.** The bearing lives in
   the switching sidebands at ±f_rot, ±2f_rot… A 2 kHz slice destroys it;
   400 kHz works. `slice_bw` defaults to 0.2 × fs.
2. **Use only the samples at the switch edges.** Between edges there is no
   bearing information, only noise and (for LTE-type sources) the source's
   own random phase. Edge-only lock-in cut wideband-source error from ~10°
   to ~4° at 0 dB. This needs the switch timing; `estimate_switch_timing`
   recovers it from the capture modulo one dwell, which leaves a 90°
   ambiguity that a one-time calibration with a known source resolves.

## Run it

```bash
pip install numpy scipy pytest          # Python 3.10+
python -m pytest tests

python -m bearing_df.cli sim --bearing 135 --source tone --snr 10
python -m bearing_df.cli sim --bearing 222 --source wideband --snr 0 --burst --duration 0.1
python -m bearing_df.cli sim --bearing 47 --snr -5 --recover-timing --switch-start 21
python -m bearing_df.cli drive
```

## Hardware day checklist (when HackRF Pro + Opera Cake are in hand)

See [hardware-day-checklist.md](hardware-day-checklist.md): the exact
commands, in order, to confirm the Opera Cake is switching on the Pro
before trusting any bearing. The firmware clears the switch counter every
time a transfer stops, so `switch_start_sample` should be a fixed constant;
step 8 there is the test that settles it.

## Known gaps (deliberately not built yet)

* No live streaming loop / GPS / WebSocket — `cli.py` is file-based.
  Live path is: capture N ms → `bearings_from_bursts` → `Tracker.add` →
  `WedgeMap.add` → push `TrackState` + `Fix` to the display.
* No map UI. `geo.Fix.grid` is a ready-to-render heat map.
* Burst detector is a plain energy detector; below ~0 dB in 2 MHz it starts
  fragmenting bursts. Matched detection of LTE PRACH/DMRS is the next step
  if the no-bars phone proves too quiet.
* Multipath is not simulated. Expect real sigma to be worse than sim.

## Conventions

Bearings are compass degrees relative to the plate's forward mark. Element k
sits at 45° + 90°k; Opera Cake B1→element 0 … B4→element 3, clockwise
looking down. Absolute bearing = vehicle heading + relative bearing.
