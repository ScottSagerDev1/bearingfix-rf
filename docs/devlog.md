# Devlog

Notes on what I understand, what I don't yet, and what changed — in that order, as I go.

## 2026-09-16

## 2026-09-17

### A script I can actually poke at

Up to now the direction-finding code has been something I run tests against. The tests pass or they don't, and either way I'm looking at a green checkmark, not at what the math is doing. Today I asked Claude Code for something different: a single script that takes one simulated phone at a bearing I choose, pushes one burst through every stage of the pipeline, and prints what it sees at each step in plain English. No plots, under 150 lines, heavily commented, five knobs at the top I can turn without understanding anything else.

That script is `explore_sim.py` at the repo root. It came back at 152 lines and runs in about three seconds.

### What I asked for and what came back

I had Claude Code build it against the real pipeline (`SimConfig`, `cellular_plate()`, the actual `estimate_bearing()` function), not a simplified copy. The check that matters: the bearing worked out by hand in step 4 of the script matches what `estimate_bearing()` returns, to the decimal. So when I change a number and watch the output move, I'm watching the real algorithm move, not a cartoon of it.

The five knobs are `TRUE_BEARING_DEG`, `SNR_DB`, `BURST_MS`, `SPACING_IN`, and `SOURCE`. The script prints six stages:

1. **Raw I/Q** — three samples straight off the (simulated) radio, and how much of the power is phone versus noise.
2. **Spectrum** — where the phone's carrier was found, the sidebands the antenna switching creates on either side of it, and how strongly the switching tone stands out once the discriminator locks in. At 3 dB SNR the tone sits about 10 dB above the floor. With a clean test tone it's 42 dB.
3. **Phase per antenna** — the four measured phase steps, one per antenna, next to what the array geometry says they should be, plus a check that the four steps close back to zero when you walk around the square.
4. **Bearing** — the math itself: the combined vector, its angle, the 90° correction, the error against the true bearing, and the sigma.
5. **Fusion** — 20 bursts in a row, each one's error, then the tracker's fused bearing with its ± width.
6. **Wedge map** — a 12-stop simulated drive past the phone, one wedge per stop, and how far the final fix lands from the truth.

### Two things the script turned up

I didn't ask for discoveries. I asked for a walkthrough. But running the walkthrough on the real code surfaced two things that were true all along and now have numbers attached.

**The carrier estimate is off by 22 kHz, and it doesn't matter.** That frequency error adds the same ~12° to every one of the four phase steps. Before Claude Code subtracted the average step out, the per-antenna phases looked like garbage and the loop-closure check failed — and yet the bearing was still right. There's a comment in `dsp.py` that says frequency error turns into a DC offset and the lock-in ignores DC. I'd read that and taken it on faith. Now I've seen it: the wrong part cancels out because it's the same on every antenna, and the bearing only cares about the *differences* between antennas.

**The measured phases are only about 65% as big as geometry predicts, and that doesn't matter either.** Even with a perfectly clean tone the per-antenna phase steps come out at roughly 0.65× what the array spacing says they should be. The cause is the 400 kHz filter in front of the phase measurement: it smears every antenna-switch edge out over about 2.5 µs, and the 2 µs sampling windows sit inside that smear. So the measurement is consistently shrunk. It doesn't hurt the bearing because the bearing is the *phase* of the four-step pattern — which way it's rotated — not its size. A scale factor shrinks the whole pattern evenly and leaves the rotation alone.

Both of these are the kind of thing I'd have hit on hardware day with no idea what I was looking at. Now I'll recognize them.

### What I'm going to do with it

I don't understand enough yet to change the algorithm. I don't need to. The plan is to change one knob at a time and read the output:

- `TRUE_BEARING_DEG` first — 45, 200, 350. The error should stay small no matter where the phone is.
- Then `SNR_DB` — walk it down to 0, then −5, and watch the error and sigma grow. That's what a weak signal does, and weak signals are the whole job at 15 km from an aircraft.
- Then `BURST_MS` — make it longer at low SNR and watch the error shrink back. That's the trade the real system will make: listen longer, get a cleaner fix.

Two experiments Claude Code suggested that I'll try after: set `SPACING_IN = 6.5` (about half a wavelength) and watch the loop-closure in step 3 fall apart — that's the ambiguity you get when antenna spacing gets too wide. And set `SOURCE = "tone"` to see steps 2 and 3 go clean, which separates the messiness of a real cellular signal from the direction-finding math underneath it.

### Earlier today

Before the explore script, today also covered: an audit of `hackrf_io.py` against the current HackRF source (one bad flag fixed, and the finding that Opera Cake time-mode switching drives port A0 — the HackRF has to be cabled there, not to the B side); a sim sweep confirming the 3.5" cellular plate is within 1° of the best spacing; a refactor so the DSP config is in physical units (seconds, hertz) instead of sample counts, with 2 vs 8 MSPS showing no digital difference; and restructuring the repo to a standard flat layout while it's still young. Those each have their own write-ups.

