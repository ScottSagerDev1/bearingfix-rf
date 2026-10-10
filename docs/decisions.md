# Decision log

Dated record of decisions that changed what this project is or how it is run.
Newest last. Reasons are author-stated unless marked otherwise.

## 2026-09-19: scope change from 830 MHz phone locating to a 2.4 GHz viewfinder

**Decision.** The project stops working toward a passive cell-phone locator
for search and rescue and works instead toward a receive-only 2.4 GHz
direction-finding viewfinder, built in four phases (Phase 0 power meter,
Phase 1 handheld viewfinder, Phase 2 four antennas, Phase 3 vehicle and map).

This is a change of scope. Everything committed before this date describes
the earlier goal.

**Context and reasons (author-stated).**

- In coverage, search and rescue teams already get carrier locates and 911
  coordinates.
- A passive system cannot legally make a phone transmit.
- The antennas in hand are 2.4 GHz.
- The display I want is a live viewfinder.

The pseudo-Doppler technique is not invalidated by this decision.

**Consequences.**

- Each phase adds one new unknown.
- No purchase before the previous phase passes.
- The Opera Cake antenna switch is deferred to Phase 2 and is not ordered.
- The 830 MHz cellular, PRACH and burst code in `bearing_df/`, and the
  documents written for it, are simulation only, not validated on hardware,
  and deferred. They stay in the repo as written, with scope notes.

**Source.** Dated from the author's notes. The source document for this
decision is not in this repo.

## 2026-10 (day not recorded): NanoVNA-F V2 bought ahead of Phase 2

**Decision.** Buy a NanoVNA-F V2 (with included calibration kit, 50 kHz to
3 GHz) now, to characterize the dipole and the 50 ohm termination.

**Context.** This is a deliberate exception to the rule above, "no purchase
before the previous phase passes". Phase 0 has not been passed.

**Consequences.** The instrument is in hand but has not been used. No dipole
or termination measurement exists.

**Cost.** TBD (from receipts).

**Source.** Dated from the author's notes. The source document for this
decision is not in this repo.
