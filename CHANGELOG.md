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

### Fixed

- `operacake_time_mode` passed a non-existent `-T` flag to
  `hackrf_operacake`; the real flag is `-t <port[:dwell]>`.

### Added

- `docs/hardware-day-checklist.md`: ordered commands to prove the Opera Cake
  is switching on a HackRF Pro before trusting a bearing.

- Pseudo-Doppler direction-finding core (`bearing_df` package): array
  geometry, IQ simulator, FM-discriminator DSP with edge-only lock-in,
  burst detection, ping tracker, and wedge-map fix accumulation.
- CLI with `sim`, `file`, `calibrate`, and `drive` commands.
- Test suite covering the DSP pipeline against the simulator (no hardware
  required).
- Root-level project docs (README, LICENSE, TRADEMARKS, devlog).
