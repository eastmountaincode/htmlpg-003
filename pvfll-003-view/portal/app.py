#!/usr/bin/env python3
"""
Captive portal for WiFi configuration.
Runs on port 80, bound to the AP interface (192.168.4.1).
"""

import subprocess
import re
from flask import Flask, render_template, request, jsonify, redirect

app = Flask(__name__)


def get_wifi_networks():
    """Scan and return available WiFi networks."""
    # Trigger a fresh scan (may fail if busy, that's ok)
    subprocess.run(
        ["nmcli", "dev", "wifi", "rescan", "ifname", "wlan0"],
        capture_output=True, timeout=10
    )
    result = subprocess.run(
        ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", "wlan0"],
        capture_output=True, text=True, timeout=10
    )
    networks = []
    seen = set()
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(":")
        if len(parts) >= 3:
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            networks.append({
                "ssid": ssid,
                "signal": int(parts[1]) if parts[1].isdigit() else 0,
                "security": parts[2].strip(),
            })
    networks.sort(key=lambda n: n["signal"], reverse=True)
    return networks


def get_current_connection():
    """Get current WiFi connection info on wlan0."""
    result = subprocess.run(
        ["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "con", "show", "--active"],
        capture_output=True, text=True, timeout=10
    )
    for line in result.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] == "wlan0" and parts[2] == "802-11-wireless":
            return parts[0]
    return None


def get_ip_address():
    """Get wlan0 IP address."""
    result = subprocess.run(
        ["nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", "wlan0"],
        capture_output=True, text=True, timeout=10
    )
    for line in result.stdout.strip().split("\n"):
        if line.startswith("IP4.ADDRESS"):
            addr = line.split(":", 1)[1].strip()
            return addr.split("/")[0] if "/" in addr else addr
    return None


# --- Captive portal detection endpoints ---

@app.route("/hotspot-detect.html")
def apple_captive():
    return redirect("/")


@app.route("/generate_204")
def android_captive():
    return redirect("/")


@app.route("/ncsi.txt")
def windows_captive():
    return redirect("/")


@app.route("/connecttest.txt")
def windows_captive_2():
    return redirect("/")


# --- Main routes ---

@app.route("/")
def index():
    networks = get_wifi_networks()
    current = get_current_connection()
    ip = get_ip_address()
    return render_template("index.html", networks=networks, current=current, ip=ip)


@app.route("/disconnect", methods=["POST"])
def disconnect():
    current = get_current_connection()
    if not current:
        return jsonify({"success": False, "message": "Not connected to any network"})
    result = subprocess.run(
        ["nmcli", "con", "down", current],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        return jsonify({"success": True, "message": f"Disconnected from {current}"})
    else:
        err = result.stderr.strip() or result.stdout.strip()
        msg = re.sub(r"Error:?\s*", "", err) if err else "Disconnect failed"
        return jsonify({"success": False, "message": msg})


@app.route("/connect", methods=["POST"])
def connect():
    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("password", "").strip()

    if not ssid:
        return jsonify({"success": False, "message": "No network selected"}), 400

    con_name = f"portal-{ssid}"

    # Remove any existing connection for this SSID
    subprocess.run(
        ["nmcli", "con", "delete", con_name],
        capture_output=True, timeout=10
    )

    # Create connection profile with explicit security properties
    cmd = [
        "nmcli", "con", "add",
        "type", "wifi",
        "ifname", "wlan0",
        "con-name", con_name,
        "ssid", ssid,
    ]
    if password:
        cmd += [
            "802-11-wireless-security.key-mgmt", "wpa-psk",
            "802-11-wireless-security.psk", password,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        msg = re.sub(r"Error:?\s*", "", err) if err else "Failed to create profile"
        return jsonify({"success": False, "message": msg})

    # Activate the connection
    result = subprocess.run(
        ["nmcli", "con", "up", con_name],
        capture_output=True, text=True, timeout=30
    )

    if result.returncode == 0:
        return jsonify({"success": True, "message": f"Connected to {ssid}"})
    else:
        err = result.stderr.strip() or result.stdout.strip()
        msg = re.sub(r"Error:?\s*", "", err) if err else "Connection failed"
        # Clean up the failed profile
        subprocess.run(["nmcli", "con", "delete", con_name], capture_output=True, timeout=10)
        return jsonify({"success": False, "message": msg})


@app.route("/status")
def status():
    return jsonify({
        "connected": get_current_connection(),
        "ip": get_ip_address(),
    })


if __name__ == "__main__":
    app.run(host="192.168.4.1", port=80)
