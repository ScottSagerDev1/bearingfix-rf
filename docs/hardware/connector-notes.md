# Connector notes

Nothing on this page has been verified at the bench.

## Copied from the hardware-day checklist

Source: [docs/hardware-day-checklist.md](../hardware-day-checklist.md),
section 1 "Cabling". The original stays in place; this is a copy. It applies
to the Opera Cake bring-up (Phase 2), not to Phase 0, and the Opera Cake is
not ordered.

> HackRF **ANT** SMA → Opera Cake **A0** with the short jumper. Time mode
> drives A0; B0 only mirrors it.

## Phase 0 antenna chain

Author-stated, not yet verified at the bench:

- The dipoles are RP-SMA male and the HackRF port is SMA female. They thread
  together but make no electrical contact without the SMA male to RP-SMA
  female adapter.
- The antenna goes on the ANTENNA port, not CLKIN, CLKOUT or the trigger
  connectors.
- Check both ends of an adapter for a center pin before fitting it.
- Finger-tight on the nut.
- Bias tee off. `hackrf_transfer -p` controls it.
- Never apply DC or a transmitter output to the antenna port.

Intended Phase 0 chain, in order: HackRF Pro ANTENNA port (SMA female), SMA
male to RP-SMA female adapter, dipole (RP-SMA male). For the noise-floor
baseline the SMA male 50 ohm termination goes directly on the ANTENNA port
instead.
