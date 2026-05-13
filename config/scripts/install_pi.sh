```robot new version\pi5_brain\install\install_pi.sh#L1-240
#!/usr/bin/env bash
set -euo pipefail

# Pi 5 Offline Provisioning Script (Placeholder)
#
# Goal:
# - Prepare Raspberry Pi 5 to run fully offline:
#   - Ollama (local LLM runtime)
#   - Robot web host (local API/UI)
#   - Robot logic layer (sd_logic)
# - Prepare SSD mounting path for model storage
#
# This script is intentionally conservative and "safe by default".
# You should review and edit it before running.
#
# Usage:
#   sudo bash install_pi.sh
#
# Optional environment variables:
#   INSTALL_DOCKER=0|1          (default: 0)  # offline reliability: recommend 0
#   INSTALL_OLLAMA=0|1          (default: 1)
#   SETUP_SSD_DIRS=0|1          (default: 1)
#   SSD_MOUNT_POINT=/mnt/ssd    (default: /mnt/ssd)
#   OLLAMA_MODELS_DIR=/mnt/ssd/ollama_models (default derived from mount point)
#   SETUP_SERVICES=0|1          (default: 0)  # systemd service units are not created by this placeholder
#
# Notes:
# - This script installs packages using apt, which requires internet unless you have a local mirror/cache.
# - For truly offline installation, pre-download packages or image the SD card with dependencies.
# - Ollama installation method is left as a placeholder because it depends on your chosen approach
#   (native package/script vs container).

INSTALL_DOCKER="${INSTALL_DOCKER:-0}"
INSTALL_OLLAMA="${INSTALL_OLLAMA:-1}"
SETUP_SSD_DIRS="${SETUP_SSD_DIRS:-1}"
SSD_MOUNT_POINT="${SSD_MOUNT_POINT:-/mnt/ssd}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-${SSD_MOUNT_POINT}/ollama_models}"
SETUP_SERVICES="${SETUP_SERVICES:-0}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (use sudo)."
  exit 1
fi

echo "=================================================="
echo "Pi 5 Offline Provisioning (placeholder)"
echo "=================================================="
echo "INSTALL_DOCKER=${INSTALL_DOCKER}"
echo "INSTALL_OLLAMA=${INSTALL_OLLAMA}"
echo "SETUP_SSD_DIRS=${SETUP_SSD_DIRS}"
echo "SSD_MOUNT_POINT=${SSD_MOUNT_POINT}"
echo "OLLAMA_MODELS_DIR=${OLLAMA_MODELS_DIR}"
echo "SETUP_SERVICES=${SETUP_SERVICES}"
echo "=================================================="
echo

# -------------------------------
# Helper functions
# -------------------------------

need_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: required command not found: ${cmd}"
    exit 1
  fi
}

apt_install() {
  # Installs packages if available. Requires apt + network or local repo.
  local pkgs=("$@")
  echo "==> Installing packages: ${pkgs[*]}"
  apt-get update
  apt-get install -y "${pkgs[@]}"
}

# -------------------------------
# Basic OS prep
# -------------------------------

echo "==> Checking OS tools..."
need_cmd apt-get
need_cmd systemctl

echo "==> Setting timezone/locale is skipped by default (customize if needed)."
echo

echo "==> Updating base packages (requires apt repo access)..."
apt-get update
apt-get install -y ca-certificates curl git python3 python3-pip python3-venv
echo

# -------------------------------
# Python environment notes
# -------------------------------

echo "==> Python is installed."
echo "    You can create a venv for the backend, e.g.:"
echo "      python3 -m venv ~/robot-venv"
echo "      source ~/robot-venv/bin/activate"
echo "      pip install -r robot\\ new\\ version/pi5_brain/web_host/backend/requirements.txt"
echo

# -------------------------------
# SSD directories
# -------------------------------

if [[ "${SETUP_SSD_DIRS}" == "1" ]]; then
  echo "==> Preparing SSD directories (mount must be configured separately)..."
  echo "    Creating mount point: ${SSD_MOUNT_POINT}"
  mkdir -p "${SSD_MOUNT_POINT}"

  echo "    Creating Ollama models dir on SSD: ${OLLAMA_MODELS_DIR}"
  mkdir -p "${OLLAMA_MODELS_DIR}"

  echo "    NOTE: This does NOT mount the SSD automatically."
  echo "          See: robot new version/ssd_models/mount/ for fstab examples."
  echo
fi

# -------------------------------
# Ollama installation (placeholder)
# -------------------------------

if [[ "${INSTALL_OLLAMA}" == "1" ]]; then
  echo "==> Ollama install step (placeholder)"
  echo "    You want offline reliability, so I recommend running Ollama natively as a system service."
  echo
  echo "    Next actions when you have the Pi:"
  echo "    1) Install Ollama (method depends on your environment)"
  echo "    2) Configure Ollama to store models on SSD:"
  echo "       - Target dir: ${OLLAMA_MODELS_DIR}"
  echo "    3) Ensure SSD mounts before Ollama starts (systemd dependency)."
  echo
  echo "    This script does NOT install Ollama automatically yet."
  echo "    Reason: install approach differs (native vs container) and should match your Pi OS setup."
  echo
fi

# -------------------------------
# Docker (optional; not recommended first for offline robotics)
# -------------------------------

if [[ "${INSTALL_DOCKER}" == "1" ]]; then
  echo "==> Docker install step (optional; requires internet unless mirrored)"
  echo "    Skipping actual Docker install in this placeholder."
  echo "    If you choose Docker later, prefer docker-compose for reproducibility."
  echo
fi

# -------------------------------
# Services (placeholder)
# -------------------------------

if [[ "${SETUP_SERVICES}" == "1" ]]; then
  echo "==> systemd services setup (placeholder)"
  echo "    Recommended services to add later:"
  echo "      - ollama.service (with models dir on SSD)"
  echo "      - robot-backend.service (Flask/Gunicorn)"
  echo "      - robot-logic.service (sd_logic runner)"
  echo
  echo "    This placeholder does not create service unit files yet."
  echo
fi

# -------------------------------
# Final notes / next steps
# -------------------------------

echo "=================================================="
echo "Done (placeholder). Next steps for you:"
echo
echo "1) Configure SSD auto-mount on Pi:"
echo "   - Use UUID in /etc/fstab"
echo "   - Mount at: ${SSD_MOUNT_POINT}"
echo "   - Create:   ${OLLAMA_MODELS_DIR}"
echo
echo "2) Install and configure Ollama to use SSD models dir."
echo
echo "3) ESP32 bring-up:"
echo "   - Flash firmware from: robot new version/esp_muscles/firmware/"
echo "   - Test protocol: ping + stop_all"
echo
echo "4) Run sd_logic bring-up CLI on the Pi:"
echo "   - python3 -m sd_logic.run.run_robot --port /dev/ttyUSB0"
echo
echo "5) Run the offline backend API on the Pi:"
echo "   - cd robot\\ new\\ version/pi5_brain/web_host/backend"
echo "   - python3 app.py"
echo "=================================================="
