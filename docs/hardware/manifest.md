# Hardware manifest

Status as of 2026-10-10. Every entry is author-stated.

"Verified?" means the part has been inspected and exercised at the bench and
the result is written in a report under [docs/reports/](../reports/). Nothing
has been verified yet, so every row says No. Order dates and costs will be
filled in from receipts; they are not guessed here.

| Part | Source | Status | Verified? | Order date | Cost |
|---|---|---|---|---|---|
| HackRF Pro | TBD (from receipts) | Received | No | TBD (from receipts) | TBD (from receipts) |
| 4x 2.4 GHz dipole antenna, RP-SMA male | Adafruit product #945; vendor TBD (from receipts) | Received | No | TBD (from receipts) | TBD (from receipts) |
| SMA male to RP-SMA female adapters, 5-pack | TBD (from receipts) | Received | No | TBD (from receipts) | TBD (from receipts) |
| SMA male 50 ohm termination | TBD (from receipts) | Received; power rating not checked | No | TBD (from receipts) | TBD (from receipts) |
| NanoVNA-F V2 with included calibration kit, 50 kHz to 3 GHz | TBD (from receipts) | Received | No | TBD (from receipts) | TBD (from receipts) |
| USB-A to USB-C data cable | TBD (from receipts) | Received | No | TBD (from receipts) | TBD (from receipts) |
| Raspberry Pi 27 W power supply | TBD (from receipts) | Received | No | TBD (from receipts) | TBD (from receipts) |
| Raspberry Pi 5 | Already owned | Owned | No | TBD (from receipts) | TBD (from receipts) |
| Opera Cake antenna switch | Not applicable | Not ordered; gated on Phase 2 entry | No | Not ordered | Not ordered |

Notes:

- The Opera Cake is bought only when Phase 2 starts. The gate is a Phase 1
  pass plus an `explore_sim.py` run with a Wi-Fi-like wideband source, because
  pseudo-Doppler was designed for narrowband carriers.
- The NanoVNA-F V2 was bought ahead of that rule on purpose. See
  [docs/decisions.md](../decisions.md).
- Phase 0 also uses a laptop, a phone hotspot and a second device to stream
  through it. They are recorded in the
  [Phase 0 report](../reports/phase0-report.md), not here.
- Connector details: [connector-notes.md](connector-notes.md).
