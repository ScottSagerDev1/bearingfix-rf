# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Pseudo-Doppler direction-finding core (`bearing_df` package): array
  geometry, IQ simulator, FM-discriminator DSP with edge-only lock-in,
  burst detection, ping tracker, and wedge-map fix accumulation.
- CLI with `sim`, `file`, `calibrate`, and `drive` commands.
- Test suite covering the DSP pipeline against the simulator (no hardware
  required).
- Root-level project docs (README, LICENSE, TRADEMARKS, devlog).
