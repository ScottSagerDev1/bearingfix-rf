# Test report template

Copy this file to `docs/reports/<phase>-report.md` and fill in every section.
A section with nothing to report says "None" or "Pending"; it is not deleted.

Rules for every report:

- Label each claim as **measured** (observed and recorded here, conditions
  stated), **author-stated** (my understanding or intent, not checked against a
  measurement) or **expected** (what theory or a simulation predicts).
- Put a unit on every number.
- State the reference for every dB value (for example "dB relative to the
  measured noise floor"). The instrument is uncalibrated, so no dBm values.
- A result that has not been measured is "Pending". A pass criterion is "Met"
  or "Not met" only with the measurement that shows it, and "Pending" otherwise.

---

# <Phase and title>

| Field | Value |
|---|---|
| Report status | Draft / Final |
| Test date(s) | |
| Report written | |
| Operator | |
| Repo commit used | |

## 1. Objective

What question this test answers, and the pass criteria, copied from the README
phase table.

## 2. Equipment

Every item in the signal chain and every item used to make the measurement,
with its row in [docs/hardware/manifest.md](../hardware/manifest.md). Include
firmware and software versions.

| Item | Identification | Version / setting | Notes |
|---|---|---|---|

## 3. Method

The steps, in the order they were done, in enough detail to repeat them.
Method notes that are assumptions are labeled author-stated.

## 4. Setup conditions

Location as a text label (see [data/README.md](../../data/README.md) for the
rule on coordinates), indoor or outdoor, distances and how they were measured,
antenna orientation, other known emitters nearby, and every receiver setting:
center frequency (Hz), sample rate (samples per second), LNA gain (dB), VGA
gain (dB), RF amplifier state, bias tee state.

## 5. Raw data location

Path of each capture and its metadata sidecar under `data/`. IQ files are not
committed; say where they are kept and give a checksum if one was taken.

## 6. Results

Tables of what was measured, each value with its unit and dB reference.
Expected values go in a separate column or table and are labeled expected.

## 7. Measurement uncertainty

What limits how far each number can be trusted, and an estimate where one can
be made. If no estimate can be made, say so.

## 8. Limitations

What this test does not show.

## 9. Conclusions

Each pass criterion, with "Met", "Not met" or "Pending" and the result that
supports it. No conclusion without a result in section 6.

## 10. Next steps
