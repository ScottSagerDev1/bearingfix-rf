# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Project scope changed on 2026-09-19 from an 830 MHz passive phone locator
  for search and rescue to a receive-only 2.4 GHz viewfinder built in four
  phases. `README.md` now describes the current scope, and
  `docs/decisions.md` records the decision. The 830 MHz code and documents
  stay in the repo, labeled simulation only, not validated on hardware,
  deferred. No measurements exist.
- `README.md` extended: objective, scope and safety limits (receive-only, own
  emitters only, no decoding of content), phase status table with pass
  criteria, a "what works / what is unverified" table, repo map and test
  instructions. The "What it's not" section and license text are unchanged.
- Scope notes added at the top of `docs/technical.md`, `docs/devlog.md`,
  `docs/hardware-day-checklist.md`, `docs/sweeps/README.md` and
  `docs/explore_sim.md`. The original text is kept.
- `docs/technical.md`: pytest case count corrected from 32 to 39.
- Simulated example site moved 15.90 degrees west: the target, map origin and
  track-start longitudes in `bearing_df/cli.py`, `explore_sim.py`,
  `explore_capture.py`, `tests/test_pipeline.py` and `tools/plot_wedges.py`,
  and one line of `docs/explore_sim_sample_output.txt`. Latitudes, geometry
  and all reported distances are unchanged. Earlier commits still contain the
  original values.
- `pyproject.toml` is now the single source of dependencies, with a `dev`
  extra (pytest, ruff). `requirements.txt` installs the package with the
  `dev` and `sweep` extras instead of listing packages itself.
- `.gitignore` now also covers `venv/`, `.ruff_cache/`, `build/`, `dist/`,
  `calibration.json` and further IQ capture formats, and keeps
  `.sigmf-meta` sidecars under `data/` trackable.

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

- `docs/reports/TEMPLATE.md`: test report format with rules for claim types
  (measured, author-stated, expected), units and dB references.
- `docs/reports/phase0-report.md`: Phase 0 report skeleton. Method only;
  every result and pass criterion is Pending.
- `docs/hardware/manifest.md` and `docs/hardware/connector-notes.md`: parts
  list as of 2026-10-10 (nothing verified, dates and costs TBD from receipts)
  and connector notes (author-stated, not verified at the bench).
- `docs/decisions.md`: dated decision log.
- `docs/history/README.md`: index of documents written under the earlier
  framing, with the commit each was last changed in. No files were moved.
- `data/README.md`: capture naming, metadata sidecar fields and the rule that
  home captures record location as a text label, not coordinates.
- `phase0/README.md`: intended behavior and pass criteria for the Phase 0
  power meter. The script is not written.
- `.github/workflows/ci.yml`: runs pytest and a narrow ruff rule set (syntax
  errors and undefined names) on Python 3.14. The workflow has not run; it
  cannot until this work is pushed.

- `explore_sim.py`: a narrated, single-burst walkthrough of the whole
  pipeline with five knobs at the top, for learning and for poking at the
  DSP; documented in `docs/explore_sim.md` and linked from the README.
- `explore_capture.py`: the same six stages on a `hackrf_transfer -r`
  recording, printing the sim's sample line beside each stage for
  side-by-side reading; stage 6 becomes a single-position wedge.
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
