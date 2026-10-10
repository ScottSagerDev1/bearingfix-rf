# Phase 0: first light, relative power meter

**No script exists yet.** This page records the intended behavior and the pass
criteria so that the script can be checked against them. Nothing here has been
run.

## Purpose

One dipole on a HackRF Pro, read by a laptop, prints one number that follows
the strength of a 2.4 GHz hotspot I own. Phase 0 runs on a laptop, not the
Raspberry Pi. Receive-only; no message content is decoded.

## Intended behavior

| Behavior | Intent |
|---|---|
| Tuning | Narrow tune on the hotspot's channel |
| Detector | Peak-hold over at least 100 ms |
| Output | One dB number, printed 5 to 10 times per second |
| Gains | Start mid-range |
| Reference | dB relative to the measured noise floor |

The noise floor is the level measured with the 50 ohm termination on the
HackRF ANTENNA port, at the same settings. The instrument is uncalibrated, so
the meter never reports dBm.

Reason for peak-hold (author-stated, unverified): an idle hotspot sends a
beacon about every 100 ms, lasting 1 to 2 ms, so averaging a buffer mostly
measures noise.

## Test before hardware

The meter will be tested on canned IQ before it is used with the radio. No
canned IQ file and no such test exist yet.

## Pass criteria

Author-stated, from the README phase table:

1. Hotspot on/off is obvious in the printed number.
2. Walking away lowers it steadily, walking back raises it.
3. I can state the noise floor and the peak in dB and roughly how far apart
   they are.

Status of all three: Pending. Results will be recorded in
[docs/reports/phase0-report.md](../docs/reports/phase0-report.md).

## Related

- Method and report: [docs/reports/phase0-report.md](../docs/reports/phase0-report.md)
- Antenna chain: [docs/hardware/connector-notes.md](../docs/hardware/connector-notes.md)
- Capture naming and metadata: [data/README.md](../data/README.md)
