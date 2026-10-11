"""Write a fake HackRF recording so power_meter.py can be tested with no radio.

    python phase0/make_fake_iq.py --out phase0/fake.iq

Same format hackrf_transfer -r writes: signed 8-bit bytes, I, Q, I, Q, ...

Contents: background noise the whole time (Gaussian, std ~3 counts, which is
about what a HackRF shows with nothing on the air). The first half is noise
only: "hotspot off". In the second half a 1.5 ms burst of a steady tone at
amplitude ~30 counts fires every 102.4 ms: "hotspot on, idle", i.e. just
Wi-Fi beacons. That is a 20 dB jump in power, but only 1.5% of the time.
"""
import argparse

import numpy as np

NOISE_STD = 3.0          # counts, per I and per Q
TONE_AMP = 30.0          # counts
TONE_HZ = 250e3          # any frequency well inside the capture bandwidth
BURST_S = 1.5e-3
PERIOD_S = 102.4e-3      # the Wi-Fi beacon interval


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--rate", type=float, default=4_000_000)
    ap.add_argument("--seconds", type=float, default=10.0)
    a = ap.parse_args()

    rng = np.random.default_rng(0)                          # fixed seed: same file every run
    n_total = int(a.rate * a.seconds)
    half = n_total // 2
    chunk = int(a.rate)                                     # write one second at a time to keep memory small

    with open(a.out, "wb") as f:
        for start in range(0, n_total, chunk):
            n = min(chunk, n_total - start)
            idx = np.arange(start, start + n)
            t = idx / a.rate

            # Noise: independent Gaussian on I and on Q.
            i = rng.normal(0, NOISE_STD, n)
            q = rng.normal(0, NOISE_STD, n)

            # Bursts, second half only. A "complex tone" is a point going round
            # a circle of radius TONE_AMP: I = A cos, Q = A sin. Its power
            # (I^2 + Q^2) is A^2 all the time, the simplest possible signal.
            on = (idx >= half) & (np.mod(t, PERIOD_S) < BURST_S)
            phase = 2 * np.pi * TONE_HZ * t
            i += on * TONE_AMP * np.cos(phase)
            q += on * TONE_AMP * np.sin(phase)

            # Interleave I, Q, I, Q ... and clip to what int8 can hold.
            out = np.empty(2 * n, dtype=np.int8)
            out[0::2] = np.clip(np.round(i), -127, 127)
            out[1::2] = np.clip(np.round(q), -127, 127)
            out.tofile(f)

    print(f"wrote {a.out}: {n_total} samples, {a.seconds} s at {a.rate:.0f} Sa/s, bursts start at {a.seconds/2:.1f} s")


if __name__ == "__main__":
    main()
