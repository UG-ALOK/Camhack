#!/data/data/com.termux/files/usr/bin/bash
# CamAccess-Termux installer
# Installs Python, Flask, and requests storage permission.

set -e

echo "============================================================"
echo "  CamAccess-Termux Installer"
echo "============================================================"

echo "[1/4] Updating package lists..."
pkg update -y

echo "[2/4] Installing Python..."
pkg install -y python

echo "[3/5] Installing Python dependencies (flask, werkzeug)..."
pip install --upgrade pip
pip install flask werkzeug

echo "[4/5] Installing termux-api (needed so captured photos appear in Gallery)..."
pkg install -y termux-api

echo "[5/5] Requesting Termux storage permission..."
termux-setup-storage || echo "  (termux-setup-storage not available or already granted — continuing)"

echo
echo "  NOTE: termux-api also requires the separate 'Termux:API' companion"
echo "  app installed on your phone (same source as Termux itself — F-Droid"
echo "  or GitHub releases). Without it, photos still save correctly but"
echo "  won't auto-appear in Gallery until you rescan storage manually."

echo "============================================================"
echo "  Installation complete."
echo "  Run the tool with:"
echo "      python main.py"
echo "============================================================"
