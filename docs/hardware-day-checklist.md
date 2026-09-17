# Hardware day checklist — HackRF Pro + Opera Cake

Run `python tools/hardware_smoke.py` first: it covers steps 0–2 and a
levels/spectrum sanity check in under a minute.

Run these in order. Do not trust a bearing until steps 1–8 pass. Expected
output is from the hackrf 2026.01.3 host tools, libhackrf and firmware
source; anything marked UNVERIFIED is what this checklist exists to settle.

## 0. Software

Host tools and firmware must be from the same release, and it must be
2026.01.1 or newer (first release with HackRF Pro support; 2026.01.3 at
time of writing). If `hackrf_info` shows an older firmware, update it per
<https://hackrf.readthedocs.io/en/latest/updating_firmware.html>.

```bash
hackrf_info
```

Expect: `Board ID Number: 5 (HackRF Pro)`, `Firmware Version: 2026.01.x`,
an API version of 1.05 or higher (the dwell-time command needs it).

## 1. Cabling

- Opera Cake sits on the Pro's internal expansion headers. No PortaPack —
  the firmware disables Opera Cake time mode when one is attached.
- HackRF **ANT** SMA → Opera Cake **A0** with the short jumper. Time mode
  drives A0; B0 only mirrors it.
- Elements 0–3 → **B1, B2, B3, B4**, clockwise looking down at the plate
  (element k sits at 45° + 90°k, see `docs/technical.md` Conventions).
- Leave A1–A4 open.

## 2. Board is seen

```bash
hackrf_operacake -l
```

Expect: `Opera Cakes found:` / `Address: 0  Switching mode: manual`.

## 3. GPIO control works (needed for time mode)

```bash
hackrf_operacake -g
```

Expect: `GPIO test passed`. `GPIO mode disabled` means another add-on board
is in the way. A pin-by-pin failure table means a bad header connection.
**UNVERIFIED on Pro** — GSG say Opera Cake is compatible and the firmware
carries a Pro branch for the switch timer, but nobody has told us it works.

## 4. Manual mode walks the LEDs in the right order

```bash
hackrf_operacake -m manual -a B1   # green LED on A0 and B1
hackrf_operacake -m manual -a B2
hackrf_operacake -m manual -a B3
hackrf_operacake -m manual -a B4
```

The green LED should walk B1 → B4 clockwise around the plate. If it walks
counter-clockwise, remember that for the calibration step (`--rotation-dir
-1`) or re-cable.

## 5. Time mode switches, slowly enough to see

One second per port at 2 MSPS, then stream 10 s to /dev/null and watch:

```bash
hackrf_operacake -m time -w 2000000 -t B1 -t B2 -t B3 -t B4
hackrf_transfer -r /dev/null -f 830000000 -s 2000000 -l 16 -g 16 -n 20000000
```

Expect the green LED to step B1 → B2 → B3 → B4 → B1 once per second while
streaming, starting on B1. Note whether it *also* steps when nothing is
streaming — that tells you if the sample clock runs idle. Either way the
counter is cleared when a transfer stops, so each capture starts on B1.

## 6. Real dwell

```bash
# 2 MSPS: dwell 62 -> f_rot = 2e6 / (4 * 62) = 8064.5 Hz
hackrf_operacake -m time -w 62 -t B1 -t B2 -t B3 -t B4
```

Pass that exact `--frot 8064.5` to every `bearing_df` command below. (At
8 MSPS use `-w 250` and `--frot 8000`.)

## 7. Find the source

Park the switch and find the actual uplink carrier in GQRX / SDR++. Phone
on a continuous call ~100 ft away at a known compass bearing from the
plate's forward mark.

```bash
hackrf_operacake -m manual -a B1
# ... find the carrier, note freq_hz ...
hackrf_operacake -m time -w 62 -t B1 -t B2 -t B3 -t B4
```

## 8. Three captures, is switch_start fixed? (the key UNVERIFIED item)

```bash
for i in 1 2 3; do
  hackrf_transfer -r cal$i.iq -f <freq_hz> -s 2000000 -l 32 -g 20 -n 2000000
done
for i in 1 2 3; do
  python -m bearing_df.cli file cal$i.iq --fs 2e6 --frot 8064.5 --recover-timing
done
```

Compare `switch_start` and the raw bearing across the three runs.

- **Same each time** → the firmware's counter reset is doing its job. Use
  that `switch_start` as a fixed `--switch-start` from now on; calibrate once.
- **Different** → always `--recover-timing`; bearings are ambiguous by
  multiples of 90° until calibrated, every capture.

Also check `snr` and `sigma` in the output. Huge sigma with good snr means
the switch isn't actually switching (go back to step 5).

## 9. Calibrate

```bash
python -m bearing_df.cli calibrate cal1.iq --true-bearing <deg> --fs 2e6 --frot 8064.5
```

Writes `calibration.json`. Walk the phone around the plate and re-run
`file ... --cal calibration.json`; if bearings come out mirrored, the ports
are wired counter-clockwise: rerun calibrate with `--rotation-dir -1`.

## 10. Sample rate A/B (UNVERIFIED: is 2 MSPS good enough?)

GSG say < 8 MSPS is not recommended: the ADC isn't specified below 8 MHz
and the 1.75 MHz minimum baseband filter can't stop energy 1–2 MHz
off-carrier aliasing into a 2 MSPS capture. Same source, same spot:

```bash
hackrf_operacake -m time -w 250 -t B1 -t B2 -t B3 -t B4
hackrf_transfer -r cal_8m.iq -f <freq_hz> -s 8000000 -l 32 -g 20 -n 8000000
python -m bearing_df.cli file cal_8m.iq --fs 8e6 --frot 8000 --recover-timing
```

If sigma is clearly better at 8 MSPS, change the defaults (`DFConfig.fs`,
`HackRFSettings.fs`, the CLI `--fs` default) and the sim tests together.

## 11. Gain

Start where GSG suggest — amp off, `-l 16 -g 16` — and raise `-l`/`-g`
together until `snr` stops improving. Distortion (new spurs appearing as
you raise gain) means back off. Turn on `-a 1` only if the phone is still
buried in noise.

## 12. Park it

```bash
hackrf_operacake -m manual
```

Time mode otherwise persists until the Pro is unplugged.
