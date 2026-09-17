# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Restructured to a standard flat layout: `bearing_df/` package, `tests/`,
  `pyproject.toml`, and `requirements.txt` now live at the repo root. The
  technical writeup moved from `bearing_df/README.md` to `docs/technical.md`.
- `pyproject.toml` now declares a `[build-system]`, `requires-python`, and
  runtime `dependencies`, so `pip install -e .` pulls in numpy and scipy.
- Audited `hackrf_io.py` against the hackrf 2026.01.3 host tools, libhackrf
  and firmware source for HackRF Pro. Flags are now verified; what still
  needs the radio is marked `UNVERIFIED` with a test in
  `docs/hardware-day-checklist.md`.

- `DFConfig` now stores bandwidths and durations in physical units:
  `slice_bw_hz` (was `slice_bw`, default `0.2 * fs`), `edge_window_s`
  (was `edge_window` in samples) and `filter_len_s` (was `numtaps`), with
  `edge_window` and `numtaps` derived from `fs`. `SimConfig` gains
  `source_filter_s` for the same reason. Defaults are unchanged at 2 MSPS
  (400 kHz, 2 µs, 401 taps) and bit-identical in output; at 8 MSPS the
  estimator now behaves the same instead of admitting 4× the noise.
  CLI: `--slice-bw` is in Hz, new `--edge-window-us`.
- `tools/sweep.py`: `--sweeps` reruns a subset and merges the rest from
  `results.json` (`--sweeps none` re-analyses only); the SNR floor is now the
  interpolated 10° crossing instead of the nearest 2 dB grid point. SNR
  sweep rerun after the units change: 8 MSPS now matches 2 MSPS.

### Fixed

- `operacake_time_mode` passed a non-existent `-T` flag to
  `hackrf_operacake`; the real flag is `-t <port[:dwell]>`.

### Added

- `explore_sim.py`: a narrated, single-burst walkthrough of the whole
  pipeline with five knobs at the top, for learning and for poking at the
  DSP; documented in `docs/explore_sim.md` and linked from the README.
- `tools/sweep.py`: bearing-error sweeps over SNR, burst length, plate
  spacing and sample rate (2 vs 8 MSPS at matched transmitter power), with
  plots and a plain-language write-up in `docs/sweeps/`. `matplotlib` is an
  optional dependency (`pip install -e .[sweep]`); `tests/test_sweep.py`
  runs a tiny version so the tool can't rot.
- `docs/hardware-day-checklist.md`: ordered commands to prove the Opera Cake
  is switching on a HackRF Pro before trusting a bearing.

- Pseudo-Doppler direction-finding core (`bearing_df` package): array
  geometry, IQ simulator, FM-discriminator DSP with edge-only lock-in,
  burst detection, ping tracker, and wedge-map fix accumulation.
- CLI with `sim`, `file`, `calibrate`, and `drive` commands.
- Test suite covering the DSP pipeline against the simulator (no hardware
  required).
- Root-level project docs (README, LICENSE, TRADEMARKS, devlog).
