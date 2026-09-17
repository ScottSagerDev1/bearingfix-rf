# Sweep results

Generated 2026-09-17 by `tools/sweep.py`. Numbers only; the narrative is in [README.md](README.md).

Error = mean absolute circular error, degrees, over all bearings and trials (p90 = 90th percentile). Source is the noise-like LTE stand-in; switch timing known. SNR is in a 2 MHz reference bandwidth at both sample rates.

## Computed findings

- SNR floor for ≤ 10° error, **2 MSPS**: **-6 dB** in 2 MHz
- SNR floor for ≤ 10° error, **8 MSPS**: **-4 dB** in 2 MHz
- SNR floor for ≤ 10° error, **8 MSPS, slice 400 kHz**: **-6 dB** in 2 MHz
- SNR floor for ≤ 10° error, **8 MSPS, slice 400 kHz, edge_window 16**: **-8 dB** in 2 MHz
- Shortest usable burst at 10 dB (≥ 80% detected and ≤ 10°): single burst **never**, fused over 100 ms **0.6 ms**
- Shortest usable burst at 3 dB (≥ 80% detected and ≤ 10°): single burst **never**, fused over 100 ms **0.6 ms**
- Spacing at 0 dB: best 0.33 λ (3.9°), within 1° of best from 0.25 λ, breaks down from 0.46 λ
- Spacing at -6 dB: best 0.29 λ (8.0°), within 1° of best from 0.29 λ, breaks down from 0.42 λ
- 8 MSPS minus 2 MSPS mean error, averaged over the SNR axis: 1.0° (negative = 8 MSPS better)

## SNR sweep

| SNR in 2 MHz (dB) | 2 MSPS | 8 MSPS | 8 MSPS, slice 400 kHz | 8 MSPS, slice 400 kHz, edge_window 16 |
|---|---|---|---|---|
| -10.00 | 17.2° (p90 39°) | 34.2° (p90 78°) | 19.9° (p90 39°) | 13.6° (p90 29°) |
| -8.00 | 11.4° (p90 24°) | 21.2° (p90 44°) | 13.0° (p90 28°) | 9.9° (p90 21°) |
| -6.00 | 9.1° (p90 19°) | 11.8° (p90 26°) | 9.0° (p90 19°) | 7.0° (p90 15°) |
| -4.00 | 6.6° (p90 14°) | 8.9° (p90 18°) | 6.5° (p90 14°) | 5.5° (p90 12°) |
| -2.00 | 5.7° (p90 12°) | 6.2° (p90 13°) | 5.4° (p90 12°) | 4.2° (p90 9°) |
| 0.00 | 4.8° (p90 10°) | 4.8° (p90 9°) | 4.1° (p90 9°) | 4.0° (p90 8°) |
| 2.00 | 4.2° (p90 8°) | 3.2° (p90 6°) | 3.7° (p90 7°) | 3.4° (p90 7°) |
| 4.00 | 3.4° (p90 7°) | 2.6° (p90 5°) | 3.1° (p90 6°) | 3.3° (p90 7°) |
| 6.00 | 3.4° (p90 7°) | 2.0° (p90 4°) | 3.0° (p90 6°) | 3.1° (p90 7°) |
| 8.00 | 3.0° (p90 7°) | 1.6° (p90 3°) | 3.0° (p90 6°) | 2.9° (p90 6°) |
| 10.00 | 3.0° (p90 6°) | 1.5° (p90 3°) | 2.7° (p90 6°) | 2.8° (p90 6°) |
| 12.00 | 3.1° (p90 7°) | 1.2° (p90 3°) | 2.6° (p90 5°) | 2.8° (p90 5°) |
| 14.00 | 3.2° (p90 7°) | 1.0° (p90 2°) | 2.6° (p90 5°) | 2.8° (p90 6°) |
| 16.00 | 2.9° (p90 6°) | 1.0° (p90 2°) | 2.4° (p90 5°) | 2.6° (p90 5°) |
| 18.00 | 3.2° (p90 7°) | 0.9° (p90 2°) | 2.3° (p90 5°) | 2.7° (p90 6°) |
| 20.00 | 3.1° (p90 7°) | 0.8° (p90 2°) | 2.5° (p90 5°) | 2.6° (p90 5°) |

## Burst length sweep (2 MSPS)

| Burst (ms) | 10 dB | 3 dB |
|---|---|---|
| 0.20 | 62.8° per burst, 20.4° fused, 100% det | 63.6° per burst, 22.4° fused, 100% det |
| 0.40 | 45.7° per burst, 11.1° fused, 100% det | 47.7° per burst, 11.5° fused, 100% det |
| 0.60 | 31.8° per burst, 6.9° fused, 100% det | 35.3° per burst, 8.4° fused, 100% det |
| 0.80 | 25.7° per burst, 5.6° fused, 100% det | 29.4° per burst, 6.8° fused, 100% det |
| 1.00 | 21.1° per burst, 4.5° fused, 100% det | 24.2° per burst, 5.0° fused, 100% det |
| 1.20 | 18.0° per burst, 4.5° fused, 100% det | 20.3° per burst, 4.6° fused, 100% det |
| 1.40 | 16.4° per burst, 3.9° fused, 100% det | 18.8° per burst, 4.2° fused, 100% det |
| 1.60 | 14.3° per burst, 3.2° fused, 100% det | 16.4° per burst, 3.7° fused, 100% det |
| 1.80 | 13.5° per burst, 3.4° fused, 100% det | 15.1° per burst, 3.4° fused, 100% det |
| 2.00 | 12.4° per burst, 2.9° fused, 100% det | 14.0° per burst, 3.3° fused, 100% det |

## Plate spacing sweep (2 MSPS)

| Spacing / λ | 0 dB | -6 dB |
|---|---|---|
| 0.17 | 6.3° (p90 13°) | 11.7° (p90 24°) |
| 0.21 | 5.3° (p90 11°) | 9.5° (p90 21°) |
| 0.25 | 4.6° (p90 10°) | 9.3° (p90 19°) |
| 0.29 | 4.1° (p90 9°) | 8.0° (p90 16°) |
| 0.33 | 3.9° (p90 8°) | 8.2° (p90 18°) |
| 0.38 | 4.6° (p90 9°) | 10.2° (p90 21°) |
| 0.42 | 5.4° (p90 11°) | 14.1° (p90 29°) |
| 0.46 | 13.1° (p90 24°) | 23.6° (p90 59°) |
| 0.50 | 49.3° (p90 162°) | 46.9° (p90 150°) |
