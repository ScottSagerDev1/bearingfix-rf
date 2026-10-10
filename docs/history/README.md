# History: documents written under the earlier framing

Until 2026-09-19 this project was described as a passive cell-phone locator
for search and rescue, built around an 830 MHz cellular pseudo-Doppler
design. The scope then changed to a receive-only 2.4 GHz viewfinder
([decisions.md](../decisions.md)).

This page is an index only. No file was moved, renamed or deleted, because
moving them would break links. Each file listed below stays where it was.
Their content is simulation only, not validated on hardware, and deferred.
The README and five of the documents carry a scope note saying so
(`technical.md`, `devlog.md`, `hardware-day-checklist.md`, `explore_sim.md`,
`sweeps/README.md`); the result tables, raw results, sample output and
figures do not.

The commit column is the last commit that changed the file before the scope
change. `git show <commit>:<path>` prints the file exactly as it was then.

| File | Last commit before 2026-09-19 | Commit date | What it describes |
|---|---|---|---|
| [README.md](../../README.md) | 7c9e1f3 | 2026-09-17 | Project front page under the search-and-rescue framing |
| [docs/technical.md](../technical.md) | 1dc39be | 2026-09-17 | `bearing_df` package and its simulation results |
| [docs/devlog.md](../devlog.md) | eca4243 | 2026-09-17 | Learning notes for 2026-09-16 and 2026-09-17 |
| [docs/hardware-day-checklist.md](../hardware-day-checklist.md) | 943ba3c | 2026-09-17 | HackRF Pro + Opera Cake bring-up steps; none run |
| [docs/explore_sim.md](../explore_sim.md) | 62ab64d | 2026-09-17 | Guide to the `explore_sim.py` walkthrough |
| [docs/explore_sim_sample_output.txt](../explore_sim_sample_output.txt) | 952aac4 | 2026-09-17 | One example run of `explore_sim.py` |
| [docs/wedge_map_sim.png](../wedge_map_sim.png) | 7c9e1f3 | 2026-09-17 | Simulated wedge-map figure |
| [docs/sweeps/README.md](../sweeps/README.md) | 1dc39be | 2026-09-17 | Simulated parameter sweeps and their explanation |
| [docs/sweeps/results.md](../sweeps/results.md) | 1dc39be | 2026-09-17 | Sweep result tables |
| docs/sweeps/results.json | 1dc39be | 2026-09-17 | Sweep raw results |
| docs/sweeps/snr.png | 1dc39be | 2026-09-17 | SNR sweep plot |
| docs/sweeps/burst.png | 112645c | 2026-09-17 | Burst-length sweep plot |
| docs/sweeps/spacing.png | 112645c | 2026-09-17 | Plate-spacing sweep plot |

Changes made to these files after the scope change:

- Scope notes were added to the README and the five documents named above
  (2026-10-10). The README was also extended and three of its lines reworded
  for the current scope; the earlier text is at commit 7c9e1f3.
- The longitudes of the simulated example site were shifted 15.90 degrees
  west in the code and in one line of the sample output (2026-10-10). Earlier
  commits still contain the original values.
- The pytest case count in `docs/technical.md` was corrected from 32 to 39.

Not in this repo: the source documents for the 2026-09-19 decision.
