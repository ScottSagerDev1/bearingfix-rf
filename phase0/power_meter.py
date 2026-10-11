"""Phase 0: one live "loudness" number from a HackRF.

    hackrf_transfer -r - -f 2437000000 -s 4000000 -a 0 -l 24 -g 20 | python phase0/power_meter.py
    python phase0/power_meter.py --file fake.iq --mode average

What comes in
-------------
hackrf_transfer writes raw samples as signed 8-bit bytes: I, Q, I, Q, ...
Each pair is one sample. I ("in-phase") and Q ("quadrature") are the two
coordinates of the radio wave at that instant: think of a point on a 2-D
plane. Its distance from the centre is how strong the wave is, and its
angle is the wave's phase. We only care about strength here.

What goes out
-------------
One line per window (default 200 ms) with the level in dBFS, the noise
floor in dBFS, and the gap between them in dB. dBFS = decibels relative
to full scale, where 0 dBFS is the loudest sample the 8-bit converter can
represent (127 counts). So every reading is negative, and closer to 0 is
louder.

Why peak, not average
---------------------
An idle Wi-Fi hotspot is silent 98% of the time and sends a ~1.5 ms
beacon every ~100 ms. Averaging over 200 ms mixes 1.5 ms of signal with
198.5 ms of nothing, so the beacon barely moves the number. Peak-hold
("the loudest 1 ms block in the window") catches the beacon at full
strength. Run both modes on the fake file to see the difference.
"""
import argparse
import sys
import time
from collections import deque

import numpy as np

FULL_SCALE = 127.0            # the biggest value a signed 8-bit sample can hold
FULL_SCALE_POWER = FULL_SCALE ** 2


def block_powers(iq_bytes, samples_per_block):
    """Turn raw int8 IQ bytes into one power number per block.

    Returns a 1-D array with one value per *complete* block. Any bytes past
    the last complete block are ignored (the caller keeps them for next time).
    """
    raw = np.frombuffer(iq_bytes, dtype=np.int8)
    n_blocks = len(raw) // (2 * samples_per_block)
    if n_blocks == 0:
        return np.zeros(0)
    # Reshape to (block, sample, [I, Q]). float32 so squaring can't overflow int8.
    raw = raw[: n_blocks * 2 * samples_per_block].astype(np.float32)
    iq = raw.reshape(n_blocks, samples_per_block, 2)
    i, q = iq[:, :, 0], iq[:, :, 1]

    # Step 2a: remove DC. The HackRF adds a small constant offset to I and Q
    # (it shows up as a spike at the centre of a spectrum plot). A constant
    # is not radio signal, so subtract each block's mean I and mean Q.
    i = i - i.mean(axis=1, keepdims=True)
    q = q - q.mean(axis=1, keepdims=True)

    # Step 2b: power. By Pythagoras, I^2 + Q^2 is the squared distance of the
    # (I, Q) point from the centre, i.e. the squared strength of the wave at
    # that instant. Averaging it over the block gives the block's power.
    return (i ** 2 + q ** 2).mean(axis=1)


def to_dbfs(power):
    """Power (in counts^2) -> dB relative to full scale. log(0) is -infinity,
    so clamp tiny values first; -120 dBFS is far below anything real."""
    return 10.0 * np.log10(max(float(power), 1e-12) / FULL_SCALE_POWER)


def window_level(block_pows, mode):
    """Boil a window's worth of block powers down to one number.

    peak: the loudest block (catches short bursts).
    average: the mean block (what a plain power meter would show)."""
    if mode == "peak":
        return float(np.max(block_pows))
    return float(np.mean(block_pows))


def window_levels(iq_bytes, rate, block_ms=1.0, window_ms=200.0, mode="peak"):
    """Offline helper: whole recording in, one dBFS value per full window out.
    This is what the test calls; the live loop below does the same thing
    incrementally."""
    samples_per_block = int(round(rate * block_ms / 1000))
    blocks_per_window = max(1, int(round(window_ms / block_ms)))
    pows = block_powers(iq_bytes, samples_per_block)
    n_windows = len(pows) // blocks_per_window
    return [to_dbfs(window_level(pows[k * blocks_per_window:(k + 1) * blocks_per_window], mode))
            for k in range(n_windows)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", help="read this int8 IQ file instead of stdin")
    ap.add_argument("--rate", type=float, default=4_000_000, help="samples per second (default 4000000)")
    ap.add_argument("--block-ms", type=float, default=1.0, help="block length in ms (default 1)")
    ap.add_argument("--window-ms", type=float, default=200.0, help="print one line per this many ms (default 200)")
    ap.add_argument("--mode", choices=("peak", "average"), default="peak")
    ap.add_argument("--realtime", action="store_true", help="with --file, pace output at true speed")
    a = ap.parse_args()

    samples_per_block = int(round(a.rate * a.block_ms / 1000))
    bytes_per_block = 2 * samples_per_block                  # 2 bytes (I and Q) per sample
    blocks_per_window = max(1, int(round(a.window_ms / a.block_ms)))
    floor_blocks = int(round(5000 / a.block_ms))             # ~5 s of block powers for the noise floor

    src = open(a.file, "rb") if a.file else sys.stdin.buffer
    buf = bytearray()             # leftover bytes that don't yet make a whole block
    window = []                   # block powers collected for the current window
    history = deque(maxlen=floor_blocks)

    try:
        while True:
            # read1 returns whatever is available, up to the asked size. On a
            # pipe that can be any length, so it may end mid-block or even
            # mid-sample. We append to buf and only ever consume whole blocks
            # (an even number of bytes), so an I/Q pair is never split.
            chunk = src.read1(bytes_per_block * blocks_per_window)
            if not chunk:
                break                                        # EOF: pipe closed or file ended
            buf += chunk
            n_full = len(buf) // bytes_per_block
            if n_full == 0:
                continue
            pows = block_powers(bytes(buf[: n_full * bytes_per_block]), samples_per_block)
            del buf[: n_full * bytes_per_block]

            for p in pows:
                window.append(p)
                history.append(p)
                if len(window) < blocks_per_window:
                    continue
                level = to_dbfs(window_level(window, a.mode))
                # Noise floor: the 10th percentile of recent block powers.
                # 90% of blocks are louder than this, so it sits just above
                # the quietest blocks, which is what "nothing transmitting"
                # looks like. It ignores the occasional loud burst.
                floor = to_dbfs(np.percentile(history, 10))
                print(f"level: {level:6.1f} dBFS   floor: {floor:6.1f} dBFS   gap: {level - floor:5.1f} dB", flush=True)
                window = []
                if a.realtime and a.file:
                    time.sleep(a.window_ms / 1000)
    except KeyboardInterrupt:
        print()                                              # tidy line after ^C
    except BrokenPipeError:
        pass                                                 # e.g. piped into `head`
    finally:
        if a.file:
            src.close()


if __name__ == "__main__":
    main()
