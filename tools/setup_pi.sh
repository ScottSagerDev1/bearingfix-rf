#!/usr/bin/env bash
# tools/setup_pi.sh -- provision a fresh Raspberry Pi OS (64-bit, Bookworm or
# later) on a Pi 5 for hardware day. Run as the normal user; sudo is used
# where needed. Idempotent: run it twice and the second run is a no-op apart
# from the smoke test. Exits nonzero on the first failure.
#
#   bash tools/setup_pi.sh
#
# The hackrf host tools are built from source, not apt-installed: Bookworm's
# hackrf package is 2023.01.1 and the HackRF Pro needs 2026.01.1 or newer
# (docs/hardware-day-checklist.md step 0). bearing_df/hackrf_io.py is audited
# against 2026.01.3, so that is the pinned tag. Override with HACKRF_TAG=...
set -euo pipefail

HACKRF_TAG="${HACKRF_TAG:-v2026.01.3}"
HACKRF_SRC="https://github.com/greatscottgadgets/hackrf.git"
HACKRF_DIR="$HOME/src/hackrf"
REPO_URL="https://github.com/ScottSagerDev1/bearingfix-rf.git"
REPO_DIR="$HOME/projects/bearingfix-rf"
ME="${USER:-$(id -un)}"

step() { printf '\n==> %s\n' "$*"; }

if [[ $EUID -eq 0 ]]; then
    echo "Run this as your normal user, not root; it calls sudo where needed." >&2
    exit 1
fi
if [[ $(uname -m) != aarch64 ]]; then
    echo "warning: expected a 64-bit (aarch64) Pi OS, found $(uname -m); carrying on" >&2
fi

step "apt update"
sudo apt-get update

step "apt install: compiler + cmake, libusb/fftw (for hackrf), python venv/pip, git, BLAS/gfortran (numpy/scipy build fallback on arm64)"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential cmake pkg-config git \
    libusb-1.0-0-dev libfftw3-dev \
    python3 python3-venv python3-pip python3-dev \
    gfortran libopenblas-dev

step "hackrf host tools + libhackrf ${HACKRF_TAG#v}"
want="${HACKRF_TAG#v}"
have=""
if command -v hackrf_info >/dev/null 2>&1; then
    # hackrf_info prints its version even with no board attached (and then exits 1).
    have=$(hackrf_info 2>/dev/null | sed -n 's/^hackrf_info version: //p' || true)
fi
if [[ "$have" == "$want" ]]; then
    echo "already installed: hackrf_info $have"
else
    echo "found '${have:-none}', want $want: building from source in $HACKRF_DIR"
    if dpkg -s hackrf >/dev/null 2>&1; then
        echo "warning: apt's hackrf package is also installed; /usr/local/bin comes first in PATH, but 'sudo apt remove hackrf' avoids confusion" >&2
    fi
    mkdir -p "$(dirname "$HACKRF_DIR")"
    if [[ -d "$HACKRF_DIR/.git" ]]; then
        git -C "$HACKRF_DIR" fetch --quiet --tags origin
    else
        git clone --quiet "$HACKRF_SRC" "$HACKRF_DIR"
    fi
    git -C "$HACKRF_DIR" checkout --quiet "$HACKRF_TAG"
    cmake -S "$HACKRF_DIR/host" -B "$HACKRF_DIR/host/build" -DCMAKE_BUILD_TYPE=Release -DINSTALL_UDEV_RULES=ON
    cmake --build "$HACKRF_DIR/host/build" -j"$(nproc)"
    sudo cmake --install "$HACKRF_DIR/host/build"
    sudo ldconfig
    hash -r
fi

step "udev rule so hackrf_info works without sudo"
# Use the rules file shipped with the release rather than hand-typed USB IDs,
# so the Pro's IDs come from the same source the tools were built from.
rules=$(ls "$HACKRF_DIR"/host/libhackrf/*hackrf*.rules 2>/dev/null | head -n 1 || true)
if [[ -z "$rules" ]]; then
    # tools came from somewhere else (e.g. a previous run's install): fetch the file
    mkdir -p "$(dirname "$HACKRF_DIR")"
    [[ -d "$HACKRF_DIR/.git" ]] || git clone --quiet "$HACKRF_SRC" "$HACKRF_DIR"
    git -C "$HACKRF_DIR" checkout --quiet "$HACKRF_TAG"
    rules=$(ls "$HACKRF_DIR"/host/libhackrf/*hackrf*.rules | head -n 1)
fi
dest="/etc/udev/rules.d/$(basename "$rules")"
if sudo cmp -s "$rules" "$dest"; then
    echo "already in place: $dest"
else
    sudo install -m 644 "$rules" "$dest"
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "installed $dest"
fi

step "plugdev group membership for $ME"
was_in_plugdev=0
if id -nG "$ME" | grep -qw plugdev; then
    was_in_plugdev=1
    echo "already a member"
else
    sudo usermod -aG plugdev "$ME"
    echo "added; takes effect in new logins"
fi

step "repo: $REPO_URL -> $REPO_DIR"
mkdir -p "$(dirname "$REPO_DIR")"
if [[ -d "$REPO_DIR/.git" ]]; then
    git -C "$REPO_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$REPO_DIR"
fi

step "python venv at $REPO_DIR/.venv"
if [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
    echo "already exists"
else
    python3 -m venv "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/pip" install --quiet --upgrade pip

step "pip install -e . plus requirements.txt (pytest, matplotlib)"
"$REPO_DIR/.venv/bin/pip" install --quiet -e "$REPO_DIR" -r "$REPO_DIR/requirements.txt"

step "tools/hardware_smoke.py (plug in the HackRF Pro first; this is the script's exit status)"
cd "$REPO_DIR"
if [[ $was_in_plugdev -eq 1 ]]; then
    exec .venv/bin/python tools/hardware_smoke.py
else
    echo "(plugdev membership is new, so this one run goes through 'sg plugdev'; log out and in for it to apply everywhere)"
    exec sg plugdev -c "$REPO_DIR/.venv/bin/python tools/hardware_smoke.py"
fi
