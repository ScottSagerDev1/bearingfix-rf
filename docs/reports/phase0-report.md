# Phase 0 report: first light, relative power meter at 2.4 GHz

**Skeleton only. No measurement has been made. Every result below is Pending.**

Format: [TEMPLATE.md](TEMPLATE.md). Claim types (measured, author-stated,
expected) are defined there.

| Field | Value |
|---|---|
| Report status | Draft: skeleton, no data |
| Test date(s) | Pending |
| Report written | Skeleton written 2026-10-10 |
| Operator | Repository author |
| Repo commit used | Pending |

## 1. Objective

Show that one 2.4 GHz dipole on a HackRF Pro, read by a laptop, gives a single
number that follows the strength of a hotspot I own.

Pass criteria (author-stated, from the README phase table):

1. Hotspot on/off is obvious in the printed number.
2. Walking away lowers it steadily, walking back raises it.
3. I can state the noise floor and the peak in dB and roughly how far apart
   they are.

## 2. Equipment

Parts are listed in [docs/hardware/manifest.md](../hardware/manifest.md).
Nothing in this table has been verified at the bench.

| Item | Identification | Version / setting | Notes |
|---|---|---|---|
| Receiver | HackRF Pro | Board ID: Pending. Firmware version: Pending (from `hackrf_info`) | |
| Host | Laptop | Host OS: Pending. hackrf host tools version: Pending | Phase 0 runs on a laptop, not the Raspberry Pi |
| Termination | SMA male 50 ohm termination | Power rating: not checked | Used for the noise-floor baseline |
| Antenna | Adafruit #945 2.4 GHz dipole, RP-SMA male | Pending | One of four |
| Adapter | SMA male to RP-SMA female | Pending | Between the HackRF ANTENNA port and the dipole |
| Cable | USB-A to USB-C data cable | Pending | HackRF to laptop |
| Emitter | Own phone hotspot, forced to 2.4 GHz | Model: Pending. Channel: Pending | |
| Traffic source | Second device streaming through the hotspot | Pending | Keeps the hotspot transmitting |
| Software | Phase 0 meter script | Not written | Intended behavior: [phase0/README.md](../../phase0/README.md) |

## 3. Method

To be carried out in this order. Not yet done.

**3.1 Record the configuration.** Before any capture, write down: board,
firmware version, host OS, antenna chain (every part between the ANTENNA port
and free space), LNA gain (dB), VGA gain (dB), RF amplifier state, bias tee
state, center frequency (Hz), sample rate (samples per second).

**3.2 Noise-floor baseline.** Fit the 50 ohm termination to the HackRF ANTENNA
port, with no antenna. Capture at the settings recorded in 3.1. The level
measured here is the noise floor that every later dB value is referred to.

**3.3 Hotspot on/off.** Replace the termination with the adapter and one
dipole. Same settings. Force the hotspot to 2.4 GHz and have a second device
stream through it. Record the reading with the hotspot on, then off, then on
again.

**3.4 Distance steps.** With the hotspot on and streaming, record the reading
at a series of measured distances, walking away and then walking back.

Method notes (author-stated, unverified):

- An idle hotspot sends a beacon about every 100 ms, lasting 1 to 2 ms.
  Averaging a buffer therefore mostly measures noise.
- Because of that, the reading needs a peak-hold over at least 100 ms.

## 4. Setup conditions

| Condition | Value |
|---|---|
| Location (text label) | Pending |
| Indoor / outdoor | Pending |
| Antenna chain | Pending |
| Antenna orientation | Pending |
| Center frequency (Hz) | Pending |
| Sample rate (samples per second) | Pending |
| LNA gain (dB) | Pending |
| VGA gain (dB) | Pending |
| RF amplifier | Pending |
| Bias tee | Pending (intended: off) |
| Hotspot channel | Pending |
| Distance measurement method | Pending |
| Other known 2.4 GHz emitters nearby | Pending |

## 5. Raw data location

No captures exist. When they do, each one goes under `data/phase0/` with a
metadata sidecar, following [data/README.md](../../data/README.md).

| Step | Capture file | Sidecar |
|---|---|---|
| 3.2 Noise floor, terminated | Pending | Pending |
| 3.3 Hotspot on/off | Pending | Pending |
| 3.4 Distance steps | Pending | Pending |

## 6. Results

All dB figures in this report are relative to the noise floor measured in step
3.2 with the 50 ohm termination on the ANTENNA port. The instrument is
uncalibrated. No dBm values are claimed.

**6.1 Device identification (`hackrf_info`)**

| Item | Result |
|---|---|
| Board identified | Pending |
| Firmware version | Pending |

**6.2 Noise floor, terminated**

| Quantity | Result |
|---|---|
| Noise floor (raw meter units, the 0 dB reference) | Pending |
| Variation over the capture (dB relative to the noise floor) | Pending |

**6.3 Hotspot on/off**

| Hotspot state | Reading (dB relative to the measured noise floor) |
|---|---|
| On, streaming | Pending |
| Off | Pending |
| On, streaming (repeat) | Pending |

**6.4 Distance steps**

Distances to be chosen at the time of the test.

| Distance (m) | Walking away (dB relative to the measured noise floor) | Walking back (dB relative to the measured noise floor) |
|---|---|---|
| Pending | Pending | Pending |

Expected value, not a result: in free space, received power follows the
inverse-square law, a drop of about 6 dB for each doubling of distance.
Whether the measured steps follow this is Pending.

## 7. Measurement uncertainty

Pending. No uncertainty has been estimated. Contributors I expect to matter,
none of them quantified:

- The receiver is uncalibrated; its absolute gain is unknown.
- Reflections (multipath) and the operator's body near the antenna.
- Changes in hotspot transmit power and traffic during a reading.
- How accurately distance is measured.
- Drift of the noise floor between the baseline and later steps.

## 8. Limitations

- Relative measurement only: dB above this receiver's own noise floor at the
  recorded settings. Not comparable with another instrument.
- One antenna, one emitter, one location.
- No direction information.
- No antenna or termination characterization. The NanoVNA-F V2 has not been
  used.

## 9. Conclusions

| Pass criterion | Status | Supporting result |
|---|---|---|
| 1. Hotspot on/off is obvious in the printed number | Pending | None yet |
| 2. Walking away lowers it steadily, walking back raises it | Pending | None yet |
| 3. Noise floor and peak stated in dB, with their separation | Pending | None yet |

## 10. Next steps

1. Run `hackrf_info` and record board and firmware in section 6.1.
2. Take the terminated noise-floor capture (step 3.2).
3. Write the Phase 0 meter and test it on canned IQ before using hardware
   ([phase0/README.md](../../phase0/README.md)).
4. Run steps 3.3 and 3.4 and fill in sections 4 to 9.
