# Capture data

No captures exist yet. This page sets the convention before the first one.

IQ recordings are large and stay out of git. Each recording has a small
metadata sidecar that is committed, so the repo always says what was captured
and under what settings even though the samples are kept elsewhere.

## Layout

One folder per phase: `data/phase0/`, `data/phase1/`, and so on.

## File naming

```
<UTC date>T<UTC time>Z_<instrument>_<center freq>_<sample rate>_<gains>_<label>.iq
```

| Part | Format | Example of the format |
|---|---|---|
| UTC date and time | `YYYYMMDDTHHMMSSZ` | `20270101T120000Z` |
| Instrument | lower case, no spaces | `hackrfpro` |
| Center frequency | MHz with `M` | `2437M` |
| Sample rate | millions of samples per second with `Msps` | `2Msps` |
| Gains | `l<LNA dB>-g<VGA dB>-a<RF amplifier 0 or 1>` | `l16-g16-a0` |
| Label | short, lower case, hyphens | `term50`, `hotspot-on` |

Assembled, the examples give
`20270101T120000Z_hackrfpro_2437M_2Msps_l16-g16-a0_term50.iq`. That name
illustrates the format only. It is not a real capture and its settings are not
a recommendation.

The `.iq` file is what `hackrf_transfer -r` writes: interleaved signed 8-bit
I and Q samples.

## Metadata sidecar

One per capture, same base name, extension `.sigmf-meta`, JSON. Field names
follow SigMF where a SigMF field exists; settings SigMF has no field for use a
`bearingfix:` prefix. The files are written by hand. No SigMF tooling is used
and they have not been validated against the SigMF schema.

Required fields:

| Field | Meaning | Unit |
|---|---|---|
| `core:datatype` | Sample format; `ci8` for `hackrf_transfer` output | none |
| `core:sample_rate` | Sample rate | samples per second |
| `core:hw` | Receiver and firmware version | none |
| `core:description` | One line: what this capture is | none |
| `core:frequency` (in `captures`) | Center frequency | Hz |
| `core:datetime` (in `captures`) | Start time, UTC, ISO 8601 | none |
| `bearingfix:lna_gain_db` | LNA gain setting | dB |
| `bearingfix:vga_gain_db` | VGA gain setting | dB |
| `bearingfix:rf_amp` | RF amplifier on or off | none |
| `bearingfix:bias_tee` | Bias tee on or off | none |
| `bearingfix:antenna_chain` | Every part from the ANTENNA port outward, in order | none |
| `bearingfix:location_label` | Where the capture was made, as text | none |
| `bearingfix:notes` | Anything else that affects the reading | none |

Shape of a sidecar (values here are placeholders, not a real capture):

```json
{
  "global": {
    "core:datatype": "ci8",
    "core:sample_rate": 2000000,
    "core:hw": "HackRF Pro, firmware <version from hackrf_info>",
    "core:description": "<what this capture is>",
    "bearingfix:lna_gain_db": 16,
    "bearingfix:vga_gain_db": 16,
    "bearingfix:rf_amp": false,
    "bearingfix:bias_tee": false,
    "bearingfix:antenna_chain": "<parts, in order from the ANTENNA port>",
    "bearingfix:location_label": "indoor bench",
    "bearingfix:notes": "<free text>"
  },
  "captures": [
    {
      "core:sample_start": 0,
      "core:frequency": 2437000000,
      "core:datetime": "2027-01-01T12:00:00Z"
    }
  ],
  "annotations": []
}
```

## Location rule

- Captures made at home record location as a text label such as
  "indoor bench", never as latitude and longitude.
- Coordinates appear in a committed sidecar only for a field site the author
  names, and only after the author approves that commit.
- `core:geolocation` is therefore left out unless both conditions are met.

## What git tracks

Set in the repo's [.gitignore](../.gitignore):

- Ignored: `*.iq`, `*.cfile`, `*.sigmf-data`, and `*.cs8` under `data/`.
- Tracked: `*.sigmf-meta` sidecars under `data/`, and this README.

Before committing, run `git status` and confirm that only sidecars are staged.
