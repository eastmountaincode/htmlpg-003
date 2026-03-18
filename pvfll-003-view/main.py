#!/usr/bin/env python3
"""
HTMLPG_003 Display Controller
Main loop: boots system, listens for Pusher events, rotates QR code.
"""

import time
import signal
import sys
import threading
import requests
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from api import fetch_box_status, fetch_all_boxes
from display import display_boxes, clear_display, sleep_display
from boot import boot_sequence
from qr_token import get_qr_url, seconds_until_next_slot, QR_INTERVAL_SECONDS

load_dotenv(".env.local")

API_BASE = os.getenv("API_BASE")
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "8"))
DEVICE_ID = os.getenv("DEVICE_ID", "htmlpg-003")

CONNECTION_CHECK_INTERVAL = 60
SYNC_POLL_INTERVAL = 300  # 5 minutes

running = True
current_box_data = {}
current_qr_url = ""
data_lock = threading.Lock()
pusher_listener = None


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def signal_handler(sig, frame):
    global running, pusher_listener
    log("Shutting down...")
    running = False
    if pusher_listener:
        pusher_listener.disconnect()
    try:
        clear_display()
    except Exception:
        pass
    finally:
        sleep_display()
    sys.exit(0)


def refresh_display():
    """Push current state to the e-ink display."""
    with data_lock:
        display_boxes(dict(current_box_data), qr_url=current_qr_url)


def sync_poll():
    """Fetch all box statuses and update display if changed."""
    global current_box_data
    try:
        log("Sync poll: fetching all boxes...")
        fresh_data = fetch_all_boxes()
        with data_lock:
            if fresh_data != current_box_data:
                log("Sync poll: data changed, refreshing display")
                current_box_data = fresh_data
        refresh_display()
    except Exception as e:
        log(f"Sync poll error: {e}")


def report_health(connected: bool):
    """POST device heartbeat to the API."""
    try:
        url = f"{API_BASE}/devices/health"
        payload = {
            "deviceId": DEVICE_ID,
            "connected": connected,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
        log("Health reported OK")
    except Exception as e:
        log(f"Health report failed: {e}")


def main():
    global running, current_box_data, current_qr_url, pusher_listener

    log(f"=== HTMLPG_003 Display System ===")
    log(f"Device ID: {DEVICE_ID}")
    log(f"QR interval: {QR_INTERVAL_SECONDS}s")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Boot sequence
    initial_data, pusher_listener = boot_sequence()
    if initial_data is None:
        log("Boot failed. Halted.")
        try:
            while running:
                time.sleep(1)
        except KeyboardInterrupt:
            signal_handler(None, None)
        return

    with data_lock:
        current_box_data = initial_data

    # Initial QR + display
    current_qr_url = get_qr_url()
    log(f"Initial QR URL: {current_qr_url}")
    display_boxes(initial_data, force_full=True, qr_url=current_qr_url)

    # Attach Pusher callback
    if pusher_listener:
        def on_box_update(box_number: int):
            try:
                new_data = fetch_box_status(box_number)
                with data_lock:
                    current_box_data[box_number] = new_data
                log(f"Refreshing display for box {box_number}")
                refresh_display()
            except Exception as e:
                log(f"Error updating box {box_number}: {e}")
        pusher_listener.on_box_update = on_box_update
        log("Real-time updates enabled")

    # Main loop
    log("System ready.")
    last_connection_check = time.monotonic()
    last_sync_poll = time.monotonic()
    last_health_report = time.monotonic()
    last_qr_slot = int(time.time()) // QR_INTERVAL_SECONDS

    try:
        while running:
            time.sleep(1)
            now_mono = time.monotonic()
            now_unix = int(time.time())
            current_slot = now_unix // QR_INTERVAL_SECONDS

            # QR rotation — check if we've entered a new time slot
            if current_slot != last_qr_slot:
                last_qr_slot = current_slot
                current_qr_url = get_qr_url()
                log(f"QR rotated: {current_qr_url}")
                refresh_display()

            # Connection health check every 60s
            if pusher_listener and now_mono - last_connection_check >= CONNECTION_CHECK_INTERVAL:
                last_connection_check = now_mono
                if not pusher_listener.check_health():
                    log("Pusher unhealthy — forcing full reconnect...")
                    try:
                        if pusher_listener.force_reconnect():
                            log("Reconnected OK — syncing data")
                            sync_poll()
                            last_sync_poll = now_mono
                        else:
                            log("Reconnect failed — will retry next cycle")
                    except Exception as e:
                        log(f"Reconnect error: {e}")

            # Sync poll every 5 minutes
            if now_mono - last_sync_poll >= SYNC_POLL_INTERVAL:
                last_sync_poll = now_mono
                sync_poll()

            # Health report every 60s
            if now_mono - last_health_report >= CONNECTION_CHECK_INTERVAL:
                last_health_report = now_mono
                connected = pusher_listener.connected if pusher_listener else False
                report_health(connected)

    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
