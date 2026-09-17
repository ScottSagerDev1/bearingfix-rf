# explore_sim.py — a walkthrough you can play with

`explore_sim.py` is not part of the product and not part of the test suite. It's a learning tool. It takes one imaginary phone at a bearing you choose, pushes one burst of its signal through every stage of the direction-finding pipeline, and prints what it sees at each step in plain English.

It uses the real code — the same `estimate_bearing()` the product uses — so what you see is what the system actually does, just slowed down and narrated.

Run it from the repo root:

```
git clone https://github.com/ScottSagerDev1/bearingfix-rf
cd bearingfix-rf
pip install -e .
python explore_sim.py
```

It takes about three seconds and needs nothing beyond what `pip install -e .` already installed. Would rather read than install? A full example run at the default settings: [explore_sim_sample_output.txt](explore_sim_sample_output.txt).

## The knobs

Five variables sit at the top of the file. Change one, run it again, read what moved. That's the whole idea.

| Variable | What it is | Try |
|---|---|---|
| `TRUE_BEARING_DEG` | Where the phone really is, in degrees from north | 45, 200, 350 — the error should stay small every time |
| `SNR_DB` | How loud the phone is compared to the noise | Walk it down to 0, then −5. Watch the error and the ± width grow |
| `BURST_MS` | How long the phone transmits | Make it longer at low SNR and the error shrinks back |
| `SPACING_IN` | Distance between antennas on the plate, in inches | 6.5 (about half a wavelength) — watch the loop check in step 3 fall apart. That's the ambiguity that puts a ceiling on antenna spacing |
| `SOURCE` | `"wideband"` for a realistic noise-like phone signal, `"tone"` for a clean test signal | `"tone"` makes steps 2 and 3 look clean, which separates the messiness of a real phone signal from the direction-finding math underneath |
| `SEED` | Random seed for the noise. Same seed, same numbers every run | 1, 2, 3 — a different draw of the same setup. How much the answers move between seeds *is* the noise; the sample output is seed 0 |

Change one at a time. If you change two, you won't know which one did it.

## The six stages

**1. Raw I/Q.** Three samples straight off the (simulated) radio, and how the total power splits between phone and noise. This is what the HackRF hands us: pairs of numbers, no bearing in sight.

**2. Spectrum.** The receiver hunts for the phone's carrier frequency. Because the Opera Cake is switching between four antennas thousands of times a second, that switching stamps a tone onto the signal — with a clean test tone you'll see it as sidebands on either side of the carrier; a real phone's signal is wide enough to bury them, which is exactly why the next step exists. The discriminator then locks onto that tone regardless. With a noisy phone it stands roughly 10 dB above the floor; with a clean test tone, more like 42 dB.

**3. Phase per antenna.** The four measured phase steps, one per antenna, printed beside what the plate's geometry says they should be. Then a loop-closure check: walk all the way around the square and the steps should sum back to zero. If they don't, something's ambiguous.

**4. Bearing.** The actual math, worked by hand: combine the four steps into one vector, take its angle, apply the 90° correction, compare to the true bearing. The script also calls `estimate_bearing()` on the same data — the two agree to the decimal, which is how you know the walkthrough is honest.

**5. Fusion.** One burst is never enough. The script runs 20 bursts, prints each one's error, then shows the tracker's fused bearing with its ± width. This is why the product accumulates pings instead of trusting any single one.

**6. Wedge map.** A 12-stop simulated drive past the phone. Each stop produces a wedge; overlapping wedges from different positions narrow down to a fix. The last line is how far that fix landed from the truth.

![Simulated wedge map: twelve translucent wedges from a drive-by overlapping near the phone](wedge_map_sim.png)

That stage, drawn by `tools/plot_wedges.py` from the same stops and seeds: the wedges are wide because the fused bearings are ±15–45°, and they still cross within a couple of kilometres of the phone.

## Two things worth noticing

These are explained in the comments too, but they're the reason the script exists.

**The carrier frequency estimate is 22 kHz off, and the bearing doesn't care.** That error adds the same ~12° to all four phase steps. Until the script subtracts the average step out, the per-antenna phases look like nonsense and the loop check fails — yet the bearing is still correct. A frequency error becomes a constant offset, and the bearing only depends on the *differences* between antennas, so the offset cancels. That's the "frequency error becomes DC and the lock-in ignores DC" claim in `dsp.py`, made visible.

**The measured phases are only ~0.65× what geometry predicts, and the bearing doesn't care about that either.** The 400 kHz filter smears each antenna-switch edge over about 2.5 µs, and the 2 µs measurement windows sit inside that smear, so every step comes out shrunk by the same factor. The bearing is the *rotation* of the four-step pattern, not its size, and a uniform shrink doesn't rotate anything.

## What this is for

Mostly it's for me, learning the math by watching it run instead of reading about it. It's also a quick sanity check: when something in `dsp.py` changes, this shows in three seconds which stage moved. And when real hardware arrives, the same six stages run against captured I/Q will show exactly where simulation and reality part ways.

If you're reading the repo and curious how pseudo-Doppler direction finding actually works, this is the file to start with. Change a number, break it, see what breaks. Nothing here is precious.
