"""Hardware-day preflight for HackRF Pro + Opera Cake. Runs in under a minute.

    python tools/hardware_smoke.py [--freq-hz 830e6] [--fs 2e6] [--dwell 62] [--ports B1,B2,B3,B4] [--keep]

Nine checks, PASS / FAIL / WARN / SKIP each with a one-line reason. A check whose
prerequisite failed is SKIPPED, not failed. Exit code 0 only if every non-skipped
check is PASS or WARN. --keep saves the 2 s capture as smoke_capture.iq. This cannot
prove the Opera Cake is physically switching: see docs/hardware-day-checklist.md 3 and 5.
"""
from __future__ import annotations
import argparse, os, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from bearing_df.hackrf_io import (tools_present, HackRFSettings, capture, operacake_manual,
                                  operacake_time_mode, read_iq_int8, exact_rotation_rate)

CAPTURE_S, CLIP_WARN, POWER_FLOOR_DB, DC_SPUR_HZ = 2.0, 0.01, -35.0, 2e3
statuses: list[str] = []


def report(status, name, why):
    statuses.append(status)
    print(f"{status:<5} {name}: {why}")
    return status == "PASS" or status == "WARN"


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def err_text(e):
    msg = (e.stderr or e.stdout or b"") if isinstance(e, subprocess.CalledProcessError) else str(e)
    lines = (msg.decode(errors="replace") if isinstance(msg, bytes) else msg).strip().splitlines()
    return lines[-1] if lines else f"{type(e).__name__}"


def check_tools():                                                            # 1
    missing = [t for t, ok in tools_present().items() if not ok]
    if missing:
        return report("FAIL", "host tools", f"missing {', '.join(missing)}: install hackrf host tools 2026.01.1 or newer")
    return report("PASS", "host tools", "hackrf_info, hackrf_transfer, hackrf_operacake all on PATH")


def check_device():                                                           # 2
    try:
        r = sh(["hackrf_info"])
    except FileNotFoundError:
        return report("FAIL", "hackrf_info", "hackrf_info not on PATH (tools missing, see above)")
    out = r.stdout + r.stderr
    serials = re.findall(r"Serial number:\s*(\S+)", out)
    if r.returncode != 0 or not serials:
        return report("FAIL", "hackrf_info", "no HackRF found: check the USB-C cable and that the port supplies power; try another port")
    if len(serials) > 1:
        return report("FAIL", "hackrf_info", f"{len(serials)} devices found; unplug all but the one on the plate")
    board = re.search(r"Board ID Number:\s*\d+\s*\(([^)]+)\)", out)
    fw = re.search(r"Firmware Version:\s*(\S+)", out)
    return report("PASS", "hackrf_info", f"{board.group(1) if board else 'unknown board'}, serial {serials[0]}, "
                                         f"firmware {fw.group(1) if fw else 'unknown'}")


def check_operacake_listed():                                                 # 3
    r = sh(["hackrf_operacake", "-o", "0", "-l"])
    addrs = re.findall(r"Address:\s*(\d+)", r.stdout + r.stderr)
    if r.returncode != 0 or not addrs:
        return report("FAIL", "operacake list", "no Opera Cake found: reseat it on the expansion headers; no PortaPack attached")
    return report("PASS", "operacake list", f"Opera Cake at address {', '.join(addrs)}")


def check_manual(ports):                                                      # 4
    for port in (ports[0], ports[-1]):
        try:
            operacake_manual(port)
        except Exception as e:
            return report("FAIL", "manual mode", f"parking A0 on {port} failed: {err_text(e)}")
    return report("PASS", "manual mode", f"A0 parked on {ports[0]} then {ports[-1]} cleanly (green LED should have moved)")


def check_time_mode(dwell, ports, fs):                                        # 5
    try:
        cmd = operacake_time_mode(dwell, tuple(ports))
    except Exception as e:
        return report("FAIL", "time mode", f"dwell plan rejected: {err_text(e)}")
    ok = report("PASS", "time mode", f"accepted `{' '.join(cmd)}` -> f_rot {exact_rotation_rate(fs, dwell):.1f} Hz; use that --frot downstream")
    print("      only proves the command was accepted; that the switch physically moves is checklist step 3 (-g) and step 5 (LED walk)")
    return ok


def check_capture(path, s):                                                   # 6
    n = int(CAPTURE_S * s.fs)
    try:
        capture(path, s, n, timeout_s=CAPTURE_S + 20)
    except Exception as e:
        return report("FAIL", "capture", f"hackrf_transfer failed: {err_text(e)}")
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if size < 0.9 * 2 * n:
        return report("FAIL", "capture", f"file is {size} bytes, expected ~{2 * n}: transfer stopped early (USB drops? disk?)")
    return report("PASS", "capture", f"{CAPTURE_S:.0f} s at {s.freq_hz / 1e6:.1f} MHz / {s.fs / 1e6:.0f} MSPS, "
                                     f"lna {s.lna_db} vga {s.vga_db} amp {'on' if s.amp else 'off'}, {size} bytes")


def check_levels(path):                                                       # 7
    iq = read_iq_int8(path)
    if len(iq) == 0 or (np.ptp(iq.real) == 0 and np.ptp(iq.imag) == 0):
        report("FAIL", "levels", "samples are all the same value: no data reached the file")
        return None
    clip = float(np.mean((np.abs(iq.real) >= 127 / 128) | (np.abs(iq.imag) >= 127 / 128)))
    p_db = float(10 * np.log10(np.mean(np.abs(iq) ** 2) + 1e-30))
    why = f"mean power {p_db:.1f} dB re full scale, {100 * clip:.2f}% of samples clipped"
    if clip > CLIP_WARN:
        report("WARN", "levels", why + " -> gain too high, lower -l/-g")
    elif p_db < POWER_FLOOR_DB:
        report("WARN", "levels", why + " -> very quiet: antenna on? gain at 0? HackRF actually cabled to A0?")
    else:
        report("PASS", "levels", why)
    return iq


def check_spectrum(iq, fs, freq_hz):                                          # 8
    n = min(len(iq), 1 << 18)
    spec = np.abs(np.fft.fftshift(np.fft.fft(iq[:n] * np.hanning(n)))) ** 2
    f = np.fft.fftshift(np.fft.fftfreq(n, 1 / fs))
    i = int(np.argmax(spec))
    why = (f"strongest bin {f[i] / 1e3:+.1f} kHz from centre ({(freq_hz + f[i]) / 1e6:.4f} MHz), "
           f"{10 * np.log10(spec[i] / (np.median(spec) + 1e-30)):.0f} dB above the median")
    if abs(f[i]) < DC_SPUR_HZ:
        return report("WARN", "spectrum", why + " -> the DC spur: expected, and why the carrier search skips |f| < 2 kHz")
    return report("PASS", "spectrum", why)


def check_import():                                                           # 9
    r = subprocess.run([sys.executable, "-c", "import bearing_df, importlib.metadata as m; print(m.version('bearing_df'))"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return report("FAIL", "import", f"`import bearing_df` failed: {r.stderr.strip().splitlines()[-1]}; run pip install -e .")
    try:
        commit = sh(["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "--short", "HEAD"]).stdout.strip()
    except Exception:
        commit = ""
    return report("PASS", "import", f"bearing_df {r.stdout.strip()} at commit {commit or 'unknown'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freq-hz", type=float, default=HackRFSettings().freq_hz)
    ap.add_argument("--fs", type=float, default=HackRFSettings().fs)
    ap.add_argument("--dwell", type=int, default=62, help="samples per element (62 at 2 MSPS -> f_rot 8064.5)")
    ap.add_argument("--ports", default="B1,B2,B3,B4", help="A0 cycles these; elements 0-3 in order")
    ap.add_argument("--keep", action="store_true", help="save the capture as smoke_capture.iq")
    a = ap.parse_args(argv)
    ports, s = a.ports.split(","), HackRFSettings(freq_hz=a.freq_hz, fs=a.fs)
    skip = lambda name, why: report("SKIP", name, why) and False

    tools = check_tools()
    dev = check_device()
    oc = check_operacake_listed() if dev else skip("operacake list", "needs a radio first")
    man = check_manual(ports) if oc else skip("manual mode", "needs an Opera Cake first")
    check_time_mode(a.dwell, ports, a.fs) if man else skip("time mode", "needs manual mode to work first")
    path = "smoke_capture.iq" if a.keep else tempfile.mkstemp(prefix="smoke_", suffix=".iq")[1]
    cap = check_capture(path, s) if (dev and tools) else skip("capture", "needs a radio first")
    iq = check_levels(path) if cap else (skip("levels", "needs a capture") or None)
    check_spectrum(iq, a.fs, a.freq_hz) if iq is not None else skip("spectrum", "needs samples")
    if a.keep and cap:
        print(f"      capture kept at {path}")
    elif os.path.exists(path):
        os.remove(path)
    check_import()
    fails = statuses.count("FAIL")
    print(f"\n{statuses.count('PASS')} pass, {statuses.count('WARN')} warn, {fails} fail, {statuses.count('SKIP')} skip")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
